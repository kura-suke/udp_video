import struct
import zlib
import numpy as np
import cv2
from typing import Optional, Tuple

# 送出側(diffproc)と合わせたヘッダ仕様
HDR_FMT = "!4sBBHHHBBH"   # magic, ver, frame_type, reserved, w, h, block, T, nblocks
BLK_FMT = "!HHbbH"        # bx, by, dx, dy, datalen
MAGIC   = b"DXF0"
FRAME_I = 0
FRAME_P = 1


class DiffDecoder:
    """
    I/P差分フレームを復号するデコーダ。
    - I: JPEGを復号 → 参照更新 → BGRを返す
    - P: 残差ブロックを参照Yに適用 → YUV420 → BGRへ変換 → 参照更新 → BGRを返す

    ★ パケットロスやブロック破損に強くするため、
      ・zlib 展開に失敗したブロック
      ・サイズ不一致のブロック
      は「そのブロックだけ無視」して処理を続行する。
      → その領域は前フレームのままだが、全体としてはクラッシュせず再生できる。
    """

    def __init__(self):
        self.ref_bgr: Optional[np.ndarray] = None
        self.ref_y:   Optional[np.ndarray] = None
        self.ref_u:   Optional[np.ndarray] = None
        self.ref_v:   Optional[np.ndarray] = None
        self.last_shape: Optional[Tuple[int, int]] = None  # (h, w)

    @staticmethod
    def _bgr_to_yuv420(bgr: np.ndarray):
        """
        OpenCVのI420は (H*3/2, W) 形状の2D配列で返る。
        先頭H行がY面、その後にU面(H/2×W/2)とV面(H/2×W/2)が縦に続く。
        """
        h, w = bgr.shape[:2]#画像サイズを取得
        yuv2d = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV_I420)  # (H*3//2, W)
        # Y面
        y = yuv2d[:h, :].copy()
        # 残り(H/2)行はUとV（各H/2×W/2）。1次元にしてから分割する。
        uv_flat = yuv2d[h:, :].reshape(-1)#1次元配列に変換
        uv_size = (h // 2) * (w // 2)#UまたはVの要素数
        u = uv_flat[:uv_size].reshape(h // 2, w // 2)#U面
        v = uv_flat[uv_size:uv_size * 2].reshape(h // 2, w // 2)#V面
        return y, u, v

    @staticmethod
    def _yuv420_to_bgr(y: np.ndarray, u: np.ndarray, v: np.ndarray):
        """Y(UV1/4, V1/4) → I420 (H*3/2, W) → BGR"""
        h, w = y.shape#画像サイズを取得
        uv_flat = np.concatenate([u.reshape(-1), v.reshape(-1)], axis=0)#UとVを1次元配列に結合
        yuv = np.concatenate([y.reshape(-1), uv_flat], axis=0).astype(np.uint8)#YUV420データを1次元配列に結合
        yuv_2d = yuv.reshape((h * 3) // 2, w)#2D配列に変換
        bgr = cv2.cvtColor(yuv_2d, cv2.COLOR_YUV2BGR_I420)#BGRに変換
        return bgr

    def reset(self):
        self.ref_bgr = None
        self.ref_y = self.ref_u = self.ref_v = None
        self.last_shape = None

    def decode(self, frame_bytes: bytes) -> Optional[np.ndarray]:
        """DXF0フレームを復号してBGR画像を返す"""
        need = struct.calcsize(HDR_FMT)#ヘッダサイズを計算
        if len(frame_bytes) < need:
            return None

        try:
            (magic, ver, ftype, _reserved,w, h, block, T, nblocks) = struct.unpack(HDR_FMT, frame_bytes[:need])#ヘッダの確認
        except struct.error:
            # ヘッダ自体がおかしい → このフレームは破棄
            return None

        # マジック/バージョンチェック
        if magic != MAGIC or ver != 1:
            return None

        payload = frame_bytes[need:]

        # ==========================
        # Iフレーム：JPEG復号
        # ==========================
        if ftype == FRAME_I:
            np_arr = np.frombuffer(payload, dtype=np.uint8)#バイトデータをNumPy配列に変換
            bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)#JPEG復号
            if bgr is None:
                return None
            self.ref_bgr = bgr.copy()#参照フレームを更新
            self.ref_y, self.ref_u, self.ref_v = self._bgr_to_yuv420(self.ref_bgr)#YUV420に変換して保存
            self.last_shape = (h, w)#画像サイズを保存
            return bgr

        # ==========================
        # Pフレーム
        # ==========================
        # 参照がない／サイズが変わった場合は復号できないので捨てる
        if self.ref_y is None or self.ref_u is None or self.ref_v is None:
            return None
        if self.last_shape != (h, w):
            # 送信側で急に解像度が変わったなど
            self.reset()
            return None

        new_y = self.ref_y.copy()#Y面の新規配列を作成
        off = 0
        blk_hdr_size = struct.calcsize(BLK_FMT)#ブロックヘッダサイズを計算

        # nblocks は「送信側が書いた個数」だが、
        # パケットロスで途中までしか来ていない場合もあるので、
        # 安全に while で回す（off の範囲もチェック）。
        for _ in range(nblocks):
            # ヘッダが読めないほど短い → 以降は信頼できないのでループ終了
            if off + blk_hdr_size > len(payload):#ブロックのヘッダが残っているか
                break

            try:
                bx, by, dx, dy, datalen = struct.unpack(
                    BLK_FMT, payload[off:off + blk_hdr_size]#ブロックヘッダを分解
                )
            except struct.error:
                # このブロック以降は怪しいので終了
                break

            off += blk_hdr_size#どこまで読んだかを更新

            if off + datalen > len(payload):#圧縮データが残っているか
                # datalen が壊れている（実際の残りより長い）→ 以降は処理せず終了
                break

            comp = payload[off:off + datalen]#圧縮データを抽出
            off += datalen#どこまで読んだかを更新

            # --- 安全にデコードする ---
            try:
                raw = zlib.decompress(comp)#圧縮データを展開
            except zlib.error:
                # 壊れたブロック → このブロックは無視して次へ
                continue

            # int16 の数が block*block と合わない場合もスキップ
            if len(raw) % 2 != 0:#2バイト単位でない → おかしいので破棄
                continue

            expected_bytes = block * block * 2  # int16 = 2バイト
            if len(raw) != expected_bytes:#想定外のサイズ → このブロックは捨てる
                continue

            try:
                rblk = np.frombuffer(raw, dtype=np.int16).reshape((block, block))#残差ブロックを生成
            except ValueError:
                # reshape に失敗 → 破棄
                continue

            y0, x0 = by, bx
            y1, x1 = by + block, bx + block
            if y1 > new_y.shape[0] or x1 > new_y.shape[1]:
                # 範囲外 → 無視
                continue

            # いまはゼロモーション（dx,dyは将来拡張用）
            pred = self.ref_y[y0:y1, x0:x1].astype(np.int16)#参照Y面から予測ブロックを取得
            cur = pred + rblk#残差を加算して現在ブロックを復元
            new_y[y0:y1, x0:x1] = np.clip(cur, 0, 255).astype(np.uint8)#画素値をクリップして保存

        # ここまで来たら、たとえ一部ブロックが欠けていても new_y は「とりあえず成立」している
        bgr = self._yuv420_to_bgr(new_y, self.ref_u, self.ref_v)

        # 参照更新
        self.ref_bgr = bgr.copy()
        self.ref_y = new_y
        self.last_shape = (h, w)
        return bgr

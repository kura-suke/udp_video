# diffproc_fixed.py  --- press.py に依存しない自前版
import zlib
import struct
import numpy as np
import cv2
from typing import List, Optional

# ==========================
# このファイル内で JPEG エンコード関数を定義
# ==========================
def encode_jpeg(bgr: np.ndarray, quality: int = 80) -> bytes:
    """
    BGR画像を JPEG にエンコードして bytes を返す。
    OpenCV の imencode を使用（quality: 0〜100）。
    """
    # OpenCV の JPEG 品質指定
    params = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]#JPEG品質指定
    ok, buf = cv2.imencode(".jpg", bgr, params)#JPEGエンコード
    if not ok:
        raise RuntimeError("encode_jpeg: cv2.imencode に失敗しました")
    return buf.tobytes()


# ==========================
HDR_FMT = "!4sBBHHHBBH"#magic(4='DXF0'), ver(1), frame_type(1;0=I,1=P), reserved(2) width(2), height(2), block_size(1), T(1), nblocks(2)
MAGIC = b"DXF0"
VER = 1
# ==========================
# ブロックヘッダ構造体
BLK_HDR_FMT = "!HHbbH"#bx(2), by(2), dx(1), dy(1), datalen(2) + data(?)


def _bgr_to_y(bgr: np.ndarray) -> np.ndarray:
    h, w = bgr.shape[:2]#高さ、幅
    yuv2d = cv2.cvtColor(bgr, cv2.COLOR_BGR2YUV_I420)#YUV変換 輝度成分抽出
    y = yuv2d[:h, :].copy()#輝度成分取得
    return y


class DiffCodec:
    """
    I: JPEG（丸ごと）
    P: ブロック毎にY残差を抽出し、閾値/スキップ後に zlib 圧縮して送る。
    """
    def __init__(
        self,
        block: int,
        T: int,
        sad_skip_per_px: float,
        scene_change_ratio: float,
        jpeg_gate_ratio: float = 0.85,
        zlib_level: int = 4,
    ):
        self.block = int(block)
        self.T = int(T)
        self.sad_skip_per_px = float(sad_skip_per_px)
        self.scene_change_ratio = float(scene_change_ratio)
        self.jpeg_gate_ratio = float(jpeg_gate_ratio)
        self.zlib_level = int(zlib_level)
        self._refY: Optional[np.ndarray] = None

    def reset(self) -> None:
        self._refY = None

    def _encode_I(self, frame_bgr: np.ndarray, jpeg_quality: int) -> bytes:
        h, w = frame_bgr.shape[:2]#高さ、幅
        jpg = encode_jpeg(frame_bgr, quality=jpeg_quality)#JPEGエンコード
        header = struct.pack(HDR_FMT, MAGIC, VER, 0, 0, w, h, self.block, self.T, 0)
        self._refY = _bgr_to_y(frame_bgr)  # 参照更新
        return header + jpg #ヘッダ＋JPEGデータ

    def encode_frame(self, frame_bgr: np.ndarray, force_I: bool, jpeg_quality: int) -> bytes:
        """
        戻り値: フレーム1枚分のバイナリ
          - I: [HDR][JPEG]
          - P: [HDR][(BLK_HDR+comp_residual)*n]
        """
        h, w = frame_bgr.shape[:2]#高さ、幅
        y = _bgr_to_y(frame_bgr)#輝度成分取得

        # サイズ・ゲート用に毎回JPEGを先に作成
        jpg_bytes = encode_jpeg(frame_bgr, quality=jpeg_quality)
        jpg_size = len(jpg_bytes)#JPEGデータサイズ

        # --- Iフレーム ---
        if force_I or self._refY is None:
            # 既に作ったJPEGを使う（再圧縮しない）
            header = struct.pack(HDR_FMT, MAGIC, VER, 0, 0, w, h, self.block, self.T, 0)
            self._refY = y.copy()
            return header + jpg_bytes

        # --- Pフレーム（ゼロモーション差分） ---
        blk = self.block
        ref = self._refY
        assert ref.shape == y.shape

        diff = y.astype(np.int16) - ref.astype(np.int16)#差分計算

        # 微小差分のゼロ化
        if self.T > 0:
            mask = np.abs(diff) < self.T#閾値未満のマスク
            diff[mask] = 0#true部分を0に

        H, W = y.shape
        blocks: List[bytes] = []
        nblocks = 0
        total_blocks = (H // blk) * (W // blk)#全ブロック数

        # Pの総バイトを見積もる（ヘッダ＋ブロック列）
        p_bytes_sum = 0

        for by in range(0, H, blk):
            for bx in range(0, W, blk):
                rblk = diff[by:by+blk, bx:bx+blk]#ブロック差分取得
                sad_per_px = np.abs(rblk).sum() / (rblk.size)#SAD計算 ブロック内の1画素あたり平均絶対差分
                if sad_per_px < self.sad_skip_per_px:#スキップ判定
                    continue

                raw = rblk.astype(np.int16).tobytes()#バイト列化
                comp = zlib.compress(raw, level=self.zlib_level)#zlib圧縮
                blk_hdr = struct.pack(BLK_HDR_FMT, bx, by, 0, 0, len(comp))#ブロックヘッダ作成
                blocks.append(blk_hdr + comp)#ブロックデータ追加
                nblocks += 1
                p_bytes_sum += len(blk_hdr) + len(comp)

        # --- シーンチェンジ検出 → I昇格 ---
        changed_ratio = (nblocks / max(1, total_blocks))#変化ブロック率計算
        if changed_ratio > self.scene_change_ratio:#シーンチェンジ判定
            header = struct.pack(HDR_FMT, MAGIC, VER, 0, 0, w, h, blk, self.T, 0)
            self._refY = y.copy()
            return header + jpg_bytes

        # --- サイズ・ゲート → I昇格 ---
        p_total_est = struct.calcsize(HDR_FMT) + p_bytes_sum#Pフレーム総サイズ見積もり
        if p_total_est > self.jpeg_gate_ratio * jpg_size:#iフレームのが小さい場合
            header = struct.pack(HDR_FMT, MAGIC, VER, 0, 0, w, h, blk, self.T, 0)
            self._refY = y.copy()
            return header + jpg_bytes

        # --- Pで送る ---
        self._refY = y.copy()
        header = struct.pack(HDR_FMT, MAGIC, VER, 1, 0, w, h, blk, self.T, nblocks)
        return header + b"".join(blocks)

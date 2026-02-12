# fec_reassembler_low.py  --- packet.py を使わない単独版
import struct
from typing import Dict, List, Optional, Tuple

# ===== packet.py の依存を完全に排除 =====
HEADER_FMT = "!IHH"# !;ネットワーク送信　I;４バイトframe_id H;2バイトchunk_id H;2バイトtotal_chunks
HEADER_SIZE = struct.calcsize(HEADER_FMT)#ヘッダサイズ計算
# ==========================================

K = 8
R = 1

def _xor_bytes(a: bytes, b: bytes) -> bytes:
    if len(a) < len(b):
        a += b"\x00" * (len(b) - len(a))#長さ合わせ
    elif len(b) < len(a):
        b += b"\x00" * (len(a) - len(b))#長さ合わせ
    return bytes(x ^ y for x, y in zip(a, b))#aとbのXOR演算

class _FrameStateLow:
    def __init__(self, frame_id: int, data_total: int):
        self.frame_id = frame_id
        self.data_total = data_total

        self.G = (data_total + K - 1) // K if data_total > 0 else 0#グループ数

        self.di: List[int] = []
        r = data_total
        for _ in range(self.G):#各グループのデータチャンク数を計算
            t = K if r >= K else r
            self.di.append(t)
            r -= t

        # data[g][i]
        self.data = [[None]*d for d in self.di]#データチャンクの2次元リスト
        # parity[g]
        self.p = [None]*self.G#冗長チャンクリスト

        self.data_received = 0
        self.recovered = 0

    def _try_recover_group(self, g: int):
        if g < 0 or g >= self.G:
            return
        d = self.di[g]#データチャンク数
        missing = [i for i in range(d) if self.data[g][i] is None]#まだ受信していないチャンクリスト
        if len(missing) != 1:#欠損チャンクが1つでなければ復元不可
            return
        if self.p[g] is None:#冗長チャンクがなければ復元不可
            return

        need = missing[0]#欠損チャンクID
        acc = self.p[g]#冗長チャンクデータ
        for i in range(d):
            if i != need and self.data[g][i] is not None:#他のチャンクが存在すればXOR演算
                acc = _xor_bytes(acc, self.data[g][i])

        self.data[g][need] = acc#復元チャンクを保存
        self.data_received += 1#受信済みチャンク数をインクリメント
        self.recovered += 1#復元チャンク数をインクリメント

    def add_packet(self, packet: bytes):
        if len(packet) < HEADER_SIZE:#パケットサイズ確認
            return None

        frame_id, chunk_id, data_total_hdr = struct.unpack(HEADER_FMT, packet[:HEADER_SIZE])#ヘッダ解析
        payload = packet[HEADER_SIZE:]#ヘッダの後ろの映像データを取得

        if chunk_id & 0x8000:#最上位ビットが1なら冗長チャンク　先に冗長パケットが来た場合
            g = chunk_id & 0x7FFF#グループID取得
            if 0 <= g < self.G:#グループ範囲確認
                self.p[g] = payload#冗長チャンク保存
                self._try_recover_group(g)
        else:#先に映像データチャンクが来た場合
            cid = int(chunk_id)#データチャンクID取得
            if 0 <= cid < self.data_total:#データチャンク範囲確認
                g = cid // K#どのグループか
                li = cid % K#何チャンク目か
                if li < self.di[g] and self.data[g][li] is None:#チャンク範囲確認と未受信確認
                    self.data[g][li] = payload#データチャンク保存
                    self.data_received += 1#受信済みチャンク数インクリメント
                    self._try_recover_group(g)#グループ復元試行

        if self.data_received == self.data_total:#すべてのフレームチャンクを受信済みか確認
            out = []
            for g in range(self.G):
                for i in range(self.di[g]):
                    if self.data[g][i] is None:
                        return None
                    out.append(self.data[g][i])#チャンク結合
            return (self.frame_id, b"".join(out), self.recovered)#フレーム復元完了

        return None

class FECLowReassembler:
    def __init__(self):
        self.frames: Dict[int, _FrameStateLow] = {}

    def add_packet(self, packet: bytes):
        if len(packet) < HEADER_SIZE:
            return None

        frame_id, chunk_id, data_total = struct.unpack(HEADER_FMT, packet[:HEADER_SIZE])#ヘッダ解析

        st = self.frames.get(frame_id)#フレーム状態取得
        if st is None:
            st = _FrameStateLow(frame_id, data_total)#新しいフレーム状態を作成
            self.frames[frame_id] = st#このフレームを復元するための状態を辞書に登録し、後から来るチャンクもすべてここに蓄積できるようにする

        res = st.add_packet(packet)#チャンク追加と復元試行
        if res is not None:#フレーム完成
            del self.frames[frame_id]#メモリ解放
            return res
        return None

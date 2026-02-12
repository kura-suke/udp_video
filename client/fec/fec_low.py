# fec_low.py --- packet.py 依存なし
import struct
from typing import List

# ===== packet.py 不使用のため自前定義 =====
MAX_PAYLOAD = 1048
HEADER_FMT = "!IHH" # !;ネットワーク送信　I;４バイトframe_id H;2バイトchunk_id H;2バイトtotal_chunks
HEADER_SIZE = struct.calcsize(HEADER_FMT) #バイト計算
# ============================================

_frame_counter = 0

def _next_frame_id() -> int:
    global _frame_counter #呼び出しで戻らないようにする
    fid = _frame_counter
    _frame_counter += 1
    return fid

def _xor_bytes(buffers: List[bytes]) -> bytes:
    if not buffers:
        return b"" #空の場合
    max_len = max(len(b) for b in buffers) #最大長を取得
    out = bytearray(max_len) #最大長のバイト配列を作成
    for b in buffers:
        for i, v in enumerate(b):
            out[i] ^= v #XOR演算
    return bytes(out)

def make_packets_lrc(frame_bytes: bytes, k: int = 8, *, frame_id: int = None) -> List[bytes]:
    if frame_id is None:
        frame_id = _next_frame_id()

    chunk_size = MAX_PAYLOAD - HEADER_SIZE
    data_chunks = [frame_bytes[i:i+chunk_size] for i in range(0, len(frame_bytes), chunk_size)] #チャンク分割
    data_total = len(data_chunks)#データチャンク数

    packets = []
    next_data_cid = 0

    if k <= 0:
        k = 8

    groups = (data_total + k - 1) // k #グループ数計算
    for g in range(groups):
        start = g * k
        end = min(start + k, data_total) #グループのお尻を判定
        group = data_chunks[start:end]#グループの最初と最後を取得

        for payload in group:
            header = struct.pack(HEADER_FMT, frame_id, next_data_cid, data_total)
            packets.append(header + payload)
            next_data_cid += 1

        parity_payload = _xor_bytes(group) #冗長データ生成
        parity_cid = (0x8000 | g) & 0xFFFF #最上位ビットを1にしてチャンクIDを設定
        header_p = struct.pack(HEADER_FMT, frame_id, parity_cid, data_total)
        packets.append(header_p + parity_payload)

    return packets

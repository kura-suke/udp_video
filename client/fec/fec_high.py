# fec_high.py --- packet.py 依存なし
import struct
from typing import List, Tuple

# ===== packet.py 不使用のため自前定義 =====
MAX_PAYLOAD = 1048
HEADER_FMT = "!IHH" # !;ネットワーク送信　I;４バイトframe_id H;2バイトchunk_id H;2バイトtotal_chunks
HEADER_SIZE = struct.calcsize(HEADER_FMT)
# ============================================

MASKS = [1, 2, 3, 4, 5, 6, 7, 8]

def _xor_bytes(a: bytes, b: bytes) -> bytes:
    if len(a) < len(b):
        a += b"\x00" * (len(b) - len(a))#長さ合わせ
    elif len(b) < len(a):
        b += b"\x00" * (len(a) - len(b))#長さ合わせ
    return bytes(x ^ y for x, y in zip(a, b))#aとbのXOR演算

def _make_data_chunks(frame_bytes: bytes) -> List[bytes]:
    chunk_size = MAX_PAYLOAD - HEADER_SIZE
    return [frame_bytes[i:i+chunk_size] for i in range(0, len(frame_bytes), chunk_size)]#バイト分割、チャンク範囲

def _make_four_parity(chunks: List[bytes]) -> Tuple[bytes, bytes, bytes, bytes]:
    if not chunks:
        z = b""
        return z, z, z, z

    p = [b"\x00", b"\x00", b"\x00", b"\x00"]
    for idx, c in enumerate(chunks):
        m = MASKS[idx % len(MASKS)] #割り当て
        for bit in range(4):
            if (m >> bit) & 1: #冗長パケット割り当て
                p[bit] = _xor_bytes(p[bit], c)#XOR演算
    return p[0], p[1], p[2], p[3]

def make_packets_fec_high(frame_id: int, frame_bytes: bytes, k: int = 8) -> List[bytes]:
    data_chunks = _make_data_chunks(frame_bytes)#チャンク分割
    total_data = len(data_chunks)#データチャンク数

    groups = [data_chunks[i:i+k] for i in range(0, total_data, k)]#グループ分割

    packets = []
    next_chunk_id = 0

    for g in groups:
        for c in g:
            header = struct.pack(HEADER_FMT, frame_id, next_chunk_id, 0)#データパケットヘッダ作成
            packets.append(header + c)
            next_chunk_id += 1

        p0, p1, p2, p3 = _make_four_parity(g)
        for p in (p0, p1, p2, p3):
            header = struct.pack(HEADER_FMT, frame_id, next_chunk_id, 0)#冗長パケットヘッダ作成
            packets.append(header + p)
            next_chunk_id += 1

    total_chunks = next_chunk_id
    out = []
    for pkt in packets:
        fid, cid, _tc = struct.unpack(HEADER_FMT, pkt[:HEADER_SIZE])#データパケットと冗長パケットのヘッダ取得
        new_header = struct.pack(HEADER_FMT, fid, cid, total_chunks)# 全パケット数を設定した新ヘッダ作成
        out.append(new_header + pkt[HEADER_SIZE:])
    return out

# fec_medium.py  --- packet.py 依存なしの完全単独版
import struct
from typing import List, Tuple

# ===== packet.py を使わないため自前定義 =====
MAX_PAYLOAD = 1048
HEADER_FMT = "!IHH" # !;ネットワーク送信　I;４バイトframe_id H;2バイトchunk_id H;2バイトtotal_chunks
HEADER_SIZE = struct.calcsize(HEADER_FMT)
# ============================================

def _xor_bytes(a: bytes, b: bytes) -> bytes:
    if len(a) < len(b):
        a += b"\x00" * (len(b) - len(a))#長さ合わせ
    elif len(b) < len(a):
        b += b"\x00" * (len(a) - len(b))#長さ合わせ
    return bytes(x ^ y for x, y in zip(a, b))#aとbのXOR演算

def _make_data_chunks(frame_bytes: bytes) -> List[bytes]:
    chunk_size = MAX_PAYLOAD - HEADER_SIZE
    return [frame_bytes[i:i+chunk_size] for i in range(0, len(frame_bytes), chunk_size)] #バイト分割、チャンク範囲

def _make_two_parity(chunks: List[bytes]) -> Tuple[bytes, bytes]:
    if not chunks:
        return b"", b""

    p0 = b"\x00"
    for c in chunks:
        p0 = _xor_bytes(p0, c) #全チャンクのXOR演算

    p1 = b"\x00"
    for i, c in enumerate(chunks):
        if i % 2 == 0:
            p1 = _xor_bytes(p1, c) #偶数インデックスのチャンクのXOR演算

    return p0, p1


def make_packets_fec_medium(frame_id: int, frame_bytes: bytes, k: int = 8) -> List[bytes]:
    data_chunks = _make_data_chunks(frame_bytes) #チャンク分割
    total_data = len(data_chunks)#データチャンク数

    groups = [data_chunks[i:i+k] for i in range(0, total_data, k)]#グループ分割

    packets: List[bytes] = []
    next_chunk_id = 0

    for g in groups:
        for c in g:
            header = struct.pack(HEADER_FMT, frame_id, next_chunk_id, 0)
            packets.append(header + c)
            next_chunk_id += 1

        p0, p1 = _make_two_parity(g)
        for p in (p0, p1):
            header = struct.pack(HEADER_FMT, frame_id, next_chunk_id, 0)
            packets.append(header + p)
            next_chunk_id += 1

    total_chunks = next_chunk_id
    out = []
    for pkt in packets:
        fid, cid, _tc = struct.unpack(HEADER_FMT, pkt[:HEADER_SIZE])#データパケットと冗長パケットのヘッダ取得
        new_header = struct.pack(HEADER_FMT, fid, cid, total_chunks)# 全パケット数を設定した新ヘッダ作成
        out.append(new_header + pkt[HEADER_SIZE:])
    return out

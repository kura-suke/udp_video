# packet_no_fec.py
import struct

HEADER_FMT = "!IHH"  # !;ネットワーク送信　I;４バイトframe_id H;2バイトchunk_id H;2バイトtotal_chunks
HEADER_SIZE = struct.calcsize(HEADER_FMT)
MAX_PAYLOAD = 1048
DATA_SIZE = MAX_PAYLOAD - HEADER_SIZE

def make_packets_no_fec(frame_id: int, frame_bytes: bytes):
    packets = []

    total_chunks = (len(frame_bytes) + DATA_SIZE - 1) // DATA_SIZE # 切り上げ　分割
    if total_chunks == 0:
        total_chunks = 1

    for chunk_id in range(total_chunks):
        start = chunk_id * DATA_SIZE #チャンクの開始位置
        end = start + DATA_SIZE #チャンクの終了位置
        payload = frame_bytes[start:end]

        header = struct.pack(HEADER_FMT, frame_id, chunk_id, total_chunks)
        packets.append(header + payload) #ヘッダとペイロードを結合してパケットにする

    return packets

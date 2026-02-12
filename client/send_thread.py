# send_thread.py
import threading
import queue
import socket
import struct
from typing import Tuple

from .fec.fec_low import make_packets_lrc
from .fec.fec_medium import make_packets_fec_medium
from .fec.fec_high import make_packets_fec_high
from .fec.packet_no_fec import make_packets_no_fec

# FECなし用のヘッダ定義（元 client.py と同じ仕様）
HEADER_FMT = "!IHH"  # frame_id, chunk_id, total_chunks
HEADER_SIZE = struct.calcsize(HEADER_FMT)
MAX_PAYLOAD = 1048
DATA_SIZE = MAX_PAYLOAD - HEADER_SIZE


def start_send_thread(
    encoded_buffer: "queue.Queue[Tuple[int, bytes]]",
    stop_flag: threading.Event,
    args,
    server_addr,
    sock: socket.socket,
) -> threading.Thread:
    """
    encoded_buffer から (frame_id, frame_bytes) を取り出し、
    FEC none/low/mid/high に応じたパケット列を生成し、UDP送信するスレッド。
    """

    def send_loop():
        while not stop_flag.is_set():
            # ★ ここで必ず 1 フレーム取り出す
            try:
                frame_id, frame_bytes = encoded_buffer.get(timeout=0.1)
            except queue.Empty:
                # しばらくフレームが来ないだけなのでループ継続
                continue

            # FEC 分岐
            if args.fec == "none":
                packets = make_packets_no_fec(frame_id, frame_bytes)

            elif args.fec == "low":
                packets = make_packets_lrc(frame_bytes, k=args.fec_k, frame_id=frame_id)

            elif args.fec == "mid":
                packets = make_packets_fec_medium(frame_id, frame_bytes, k=args.fec_k)

            elif args.fec == "high":
                packets = make_packets_fec_high(frame_id, frame_bytes, k=args.fec_k)

            else:
                # 不明な指定の場合はいったん FECなしで送る
                packets = make_packets_no_fec(frame_id, frame_bytes)

            # UDP 送信
            for pkt in packets:
                try:
                    sock.sendto(pkt, server_addr)
                except OSError as e:
                    print("[SEND] send error:", e)
                    break

    t = threading.Thread(target=send_loop, daemon=True)
    t.start()
    return t

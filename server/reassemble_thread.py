# reassemble_thread.py
import threading
import queue
from typing import Any


def start_reassemble_thread(
    packet_queue: "queue.Queue[bytes]",
    frame_queue: "queue.Queue[tuple[int, bytes, int]]",
    stop_flag: threading.Event,
    reassembler: Any,
) -> threading.Thread:
    """
    packet_queue からパケットを取り出し、reassembler.add_packet() を呼んで
    フレーム完成時に frame_queue へ (frame_id, frame_bytes, recovered) を流すスレッド。
    """
    def reassemble_loop():
        while not stop_flag.is_set():#停止フラグが立つまでループ
            try:
                packet = packet_queue.get(timeout=0.1)#パケットをキューから取り出す
            except queue.Empty:
                continue

            res = reassembler.add_packet(packet)#パケットを再構成器に渡す
            if res is None:
                continue

            frame_id, frame_bytes, recovered = res#ヘッダ情報を展開

            try:
                frame_queue.put((frame_id, frame_bytes, recovered), timeout=0.1)#フレームキューに流す
            except queue.Full:
                # 満杯なら捨てる
                pass

    t = threading.Thread(target=reassemble_loop, daemon=True)
    t.start()
    return t

# recv_thread.py
import threading
import queue
import socket


def start_recv_thread(
    sock: socket.socket,
    packet_queue: "queue.Queue[bytes]",
    stop_flag: threading.Event,
) -> threading.Thread:
    """
    UDPソケットからパケットを受信し、packet_queue に流すスレッド。
    """
    def recv_loop():
        while not stop_flag.is_set():#停止フラグが立つまでループ
            try:
                packet, addr = sock.recvfrom(2000)#パケットを受信 少し多めにとっている
            except socket.timeout:
                continue
            except OSError:
                # ソケットクローズ時など
                break

            try:
                packet_queue.put(packet, timeout=0.1)#パケットをキューに入れる
            except queue.Full:
                # キュー満杯なら捨てる
                pass

    t = threading.Thread(target=recv_loop, daemon=True)
    t.start()
    return t

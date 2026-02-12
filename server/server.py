#!/usr/bin/env python
import argparse
import socket
import struct
import threading
import queue
import time

import cv2
import numpy as np

from .fec.fec_reassembler_low import FECLowReassembler
from .fec.fec_reassembler_mid import FECMediumReassembler
from .fec.fec_reassembler_high import FECHighReassembler
from .fec.simple_reassembler import SimpleFrameReassembler


from .diff.diffdecode import DiffDecoder

# ★ 追加：スレッド外部モジュール
from .recv_thread import start_recv_thread
from .reassemble_thread import start_reassemble_thread
from .decode_thread import start_decode_thread
from .display_thread import start_display_thread

# ============================================================
# 引数
# ============================================================
def parse_args():
    p = argparse.ArgumentParser(
        description="Step8: 4-thread UDP video server (FEC none/low/mid/high, diff on/off)"
    )

    p.add_argument("--bind-ip", type=str, default="0.0.0.0",
                   help="Bind IP address")
    p.add_argument("--port", type=int, default=5000,
                   help="UDP port")

    p.add_argument("--fec", choices=["none", "low", "mid", "high"], default="none",
                   help="FEC mode")
    p.add_argument("--diff", choices=["on", "off"], default="off",
                   help="Diff decode mode")
    p.add_argument("--buffer", choices=["on", "off"], default="off",
                   help="Future: frame buffer")
    p.add_argument("--record", choices=["on", "off"], default="off",
                   help="Future: record received frames")

    return p.parse_args()


# ============================================================
# メイン
# ============================================================
def main():
    args = parse_args()

    # 起動時の設定だけ表示（ループ内のログは削除）
    print("[SERVER] Step8 start (4-thread, FEC none/low/mid/high, diff on/off)")
    print(f"  bind   = {args.bind_ip}:{args.port}")
    print(f"  fec    = {args.fec}")
    print(f"  diff   = {args.diff}")
    print(f"  buffer = {args.buffer}, record={args.record}")

    # ソケット
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind_ip, args.port))
    sock.settimeout(0.5)

    # スレッド間キュー
    packet_queue = queue.Queue(maxsize=1000)
    frame_queue = queue.Queue(maxsize=120)
    decoded_queue = queue.Queue(maxsize=120)

    # FECモードに応じて Reassembler を選択
    if args.fec == "none":
        reassembler = SimpleFrameReassembler()
    elif args.fec == "low":
        reassembler = FECLowReassembler()
    elif args.fec == "mid":
        reassembler = FECMediumReassembler()
    elif args.fec == "high":
        reassembler = FECHighReassembler()
    else:
        reassembler = SimpleFrameReassembler()

    # DiffDecoder 準備（diff=on のときのみ使用）
    diff_decoder = None
    if args.diff == "on":
        diff_decoder = DiffDecoder()

    stop_flag = threading.Event()

    # =================================================
    # スレッド開始（外部モジュール呼び出し）
    # =================================================
    t_recv = start_recv_thread(
        sock=sock,
        packet_queue=packet_queue,
        stop_flag=stop_flag,
    )

    t_reasm = start_reassemble_thread(
        packet_queue=packet_queue,
        frame_queue=frame_queue,
        stop_flag=stop_flag,
        reassembler=reassembler,
    )

    t_dec = start_decode_thread(
        frame_queue=frame_queue,
        decoded_queue=decoded_queue,
        stop_flag=stop_flag,
        args=args,
        diff_decoder=diff_decoder,
    )

    t_disp = start_display_thread(
        decoded_queue=decoded_queue,
        stop_flag=stop_flag,
        window_name="RECV_STEP8",
    )

    print("[SERVER] running... (Ctrl+C or 'q' to stop)")

    try:
        while not stop_flag.is_set():
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[SERVER] KeyboardInterrupt -> stopping...")
        stop_flag.set()

    sock.close()
    time.sleep(0.5)
    # display_thread 側で destroyAllWindows 済み
    print("[SERVER] clean exit.")


if __name__ == "__main__":
    main()

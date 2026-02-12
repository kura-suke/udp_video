#!/usr/bin/env python
import argparse
import socket
import time
import threading
import queue
from collections import deque

import cv2

# Diff codec
from .diff.diffproc_fixed import DiffCodec

# ★ スレッドは外部モジュールから呼び出し
from .capture_thread import start_capture_thread
from .encode_thread import start_encode_thread
from .send_thread import start_send_thread


# ============================================================
# 引数
# ============================================================
def parse_args():
    p = argparse.ArgumentParser(
        description="Step8: 3-thread UDP video client (FEC none/low/mid/high, diff on/off)"
    )

    # --- 通信先 ---
    p.add_argument("--server-ip", type=str, default="127.0.0.1",
                   help="Server IP address")
    p.add_argument("--server-port", type=int, default=5000,
                   help="Server UDP port")

    # --- カメラ / フレーム関連 ---
    p.add_argument("--width", type=int, default=640,
                   help="Capture width")
    p.add_argument("--height", type=int, default=480,
                   help="Capture height")
    p.add_argument("--fps", type=float, default=25.0,
                   help="Capture FPS")
    p.add_argument("--jpeg-quality", type=int, default=70,
                   help="Base JPEG quality (for diff=on/off)")

    # --- 差分処理関連 ---
    p.add_argument("--diff", choices=["on", "off"], default="off",
                   help="Enable diff coding (on/off)")
    p.add_argument("--block", type=int, default=16,
                   help="Block size for diff")
    p.add_argument("--T", type=float, default=5.0,
                   help="Threshold T for diff coding")
    p.add_argument("--sad-skip-per-px", type=float, default=1.5,
                   help="SAD skip per pixel for diff")
    p.add_argument("--scene-change-ratio", type=float, default=0.25,
                   help="Scene change detection ratio")
    p.add_argument("--jpeg-gate-ratio", type=float, default=0.70,
                   help="JPEG gate ratio for diff")
    p.add_argument("--zlib-level", type=int, default=6,
                   help="Zlib compression level for diff")
    p.add_argument("--reset-interval", type=float, default=1.0,
                   help="Force I-frame interval for diff coding (sec)")
    

    # --- FEC 関連 ---
    p.add_argument("--fec", choices=["none", "low", "mid", "high"], default="none",
                   help="FEC mode")
    p.add_argument("--fec-k", type=int, default=8,
                   help="FEC data packet count k")

    return p.parse_args()


# ============================================================
# メイン
# ============================================================
def main():
    args = parse_args()

    server_addr = (args.server_ip, args.server_port)

    # 起動時の概要だけ表示（ループ中のログは削除）
    print("[CLIENT] Step8 start (3-thread, FEC none/low/mid/high, diff on/off)")
    print(f"  server = {server_addr}")
    print(f"  size   = {args.width}x{args.height}, fps={args.fps}")
    print(f"  jpeg   = quality {args.jpeg_quality}")
    print(f"  diff   = {args.diff} (block={args.block}, T={args.T}, "
          f"sad_skip={args.sad_skip_per_px}, "
          f"scene_ratio={args.scene_change_ratio}, "
          f"jpeg_gate={args.jpeg_gate_ratio}, zlib={args.zlib_level})")
    print(f"  fec    = {args.fec} (k={args.fec_k})")
    print(f"  reset-interval = {args.reset_interval}s")

    # DiffCodec 準備（diff=on の場合のみ）
    diff_codec = None
    if args.diff == "on":
        diff_codec = DiffCodec(
            block=args.block,
            T=args.T,
            sad_skip_per_px=args.sad_skip_per_px,
            scene_change_ratio=args.scene_change_ratio,
            jpeg_gate_ratio=args.jpeg_gate_ratio,
            zlib_level=args.zlib_level,
        )

    # --------------------------------------------------------
    # カメラ
    # --------------------------------------------------------
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[CLIENT] Camera open failed (device 0).")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    interval = 1.0 / args.fps

    # --------------------------------------------------------
    # スレッド間バッファ
    # --------------------------------------------------------
    frame_buffer = deque(maxlen=3)              # Capture → Encode
    encoded_buffer = queue.Queue(maxsize=1)    # Encode → Send

    stop_flag = threading.Event()

    # --------------------------------------------------------
    # ソケット
    # --------------------------------------------------------
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # ========================================================
    # スレッド起動（外部モジュール）
    # ========================================================
    t_cap = start_capture_thread(
        cap=cap,
        frame_buffer=frame_buffer,
        interval=interval,
        stop_flag=stop_flag,
    )

    t_enc = start_encode_thread(
        frame_buffer=frame_buffer,
        encoded_buffer=encoded_buffer,
        stop_flag=stop_flag,
        args=args,
        diff_codec=diff_codec,
    )

    t_send = start_send_thread(
        encoded_buffer=encoded_buffer,
        stop_flag=stop_flag,
        args=args,
        server_addr=server_addr,
        sock=sock,
    )

    print("[CLIENT] running... (Ctrl+C to stop)")

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[CLIENT] KeyboardInterrupt -> stopping...")
        stop_flag.set()

    cap.release()
    sock.close()
    print("[CLIENT] clean exit.")


if __name__ == "__main__":
    main()

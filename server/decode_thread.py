# decode_thread.py
import threading
import queue
from typing import Optional, Tuple

import cv2
import numpy as np
from .diff.diffdecode import DiffDecoder


def start_decode_thread(
    frame_queue: "queue.Queue[tuple[int, bytes, int]]",
    decoded_queue: "queue.Queue[tuple[int, any, int]]",
    stop_flag: threading.Event,
    args,
    diff_decoder: Optional[DiffDecoder],
) -> threading.Thread:
    """
    frame_queue から (frame_id, frame_bytes, recovered) を取り出し、
      - diff=on: DiffDecoder でDXF0復号
      - diff=off: JPEG復号
    して decoded_queue に (frame_id, frame, recovered) を流すスレッド。
    """

    def decode_loop():
        while not stop_flag.is_set():
            try:
                frame_id, frame_bytes, recovered = frame_queue.get(timeout=0.1)#フレームキューから取り出す
            except queue.Empty:
                continue

            # diff=on → DXF0デコード、diff=off → JPEGデコード
            if args.diff == "on" and diff_decoder is not None:#差分が有効な場合
                frame = diff_decoder.decode(frame_bytes)#差分処理を行う
                if frame is None:
                    # 参照不足やヘッダ破損など → このフレームはスキップ
                    continue
            else:
                # 通常JPEG
                np_data = np.frombuffer(frame_bytes, dtype=np.uint8)#バイトデータをnumpy配列に変換
                frame = cv2.imdecode(np_data, cv2.IMREAD_COLOR)#JPEG復号
                if frame is None:
                    print(f"[DECODE] JPEG decode failed for frame_id={frame_id}")
                    continue

            try:
                decoded_queue.put((frame_id, frame, recovered), timeout=0.1)
            except queue.Full:
                # 満杯なら捨てる
                pass

    t = threading.Thread(target=decode_loop, daemon=True)
    t.start()
    return t

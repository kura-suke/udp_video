# capture_thread.py
import threading
import time
from collections import deque
import queue

import cv2


def start_capture_thread(
    cap: cv2.VideoCapture,
    frame_buffer: deque,
    interval: float,
    stop_flag: threading.Event,
) -> threading.Thread:
    """
    カメラから一定FPSでフレームを取得し、frame_buffer に最新フレームを貯めるスレッド。
    """

    def capture_loop():
        last = time.time()
        while not stop_flag.is_set():#メインループ
            now = time.time()
            dt = now - last
            if dt < interval:
                time.sleep(interval - dt)#待機
            last = time.time()

            ret, frame = cap.read()#フレーム取得
            if not ret:
                continue

            # 最新フレーム優先（最大 len(frame_buffer) 枚まで保持）
            frame_buffer.append(frame)#最新フレームを追加 古いフレームは自動削除

    t = threading.Thread(target=capture_loop, daemon=True)#スレッド作成
    t.start()
    return t

# display_thread.py
import threading
import queue
import time

import cv2


def start_display_thread(
    decoded_queue: "queue.Queue[tuple[int, any, int]]",
    stop_flag: threading.Event,
    window_name: str = "RECV_STEP8",
) -> threading.Thread:
    """
    decoded_queue から最新フレームを取り出して表示するスレッド。
    'q' キーで stop_flag を立てて終了。
    """

    def display_loop():
        last = None
        while not stop_flag.is_set():
            # 最新フレーム優先でまとめて吸う
            try:
                while True:
                    frame_id, frame, recovered = decoded_queue.get_nowait()#最新フレームをキューから取り出す
                    last = (frame_id, frame, recovered)
            except queue.Empty:
                pass

            if last is not None:
                frame_id, frame, recovered = last
                cv2.imshow(window_name, frame)#フレームを表示

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                stop_flag.set()
                break

            time.sleep(0.01)

        cv2.destroyAllWindows()

    t = threading.Thread(target=display_loop, daemon=True)
    t.start()
    return t

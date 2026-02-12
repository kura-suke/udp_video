import threading
import time
import queue
from collections import deque
from typing import Tuple, Optional

import numpy as np  # 型ヒント用
from .diff.diffproc_fixed import DiffCodec
from .common.press import encode_jpeg  # JPEGエンコードは共通モジュールを使用


def start_encode_thread(
    frame_buffer: deque,
    encoded_buffer: "queue.Queue[Tuple[int, bytes]]",
    stop_flag: threading.Event,
    args,
    diff_codec: Optional[DiffCodec],
) -> threading.Thread:
    """
    frame_buffer の最新フレームを取り出し、
      - diff=on: DiffCodec で I/P エンコード
      - diff=off: JPEG エンコード
    を行って encoded_buffer に (frame_id, frame_bytes) を流すスレッド。
    """

    def encode_loop():
        frame_id = 0
        last_I_time = time.time()
        codec = diff_codec

        # ★ ここでエンコードFPSを決める
        interval = 1.0 / args.fps if getattr(args, "fps", 0) > 0 else 0.0
        last_encode_time = time.time()

        while not stop_flag.is_set():
            # フレームが無い場合の待機
            if not frame_buffer:
                time.sleep(0.001)
                continue

            # ★ エンコード周期を args.fps に合わせる
            if interval > 0.0:
                now = time.time()
                dt = now - last_encode_time
                if dt < interval:
                    time.sleep(interval - dt)
                # sleep 後にもう一度現在時刻を取り直す
                last_encode_time = time.time()

            # 常に「一番新しいフレーム」を取る
            frame = frame_buffer[-1]

            try:
                if args.diff == "on" and codec is not None:
                    now = time.time()
                    force_I = (frame_id == 0) or (
                        args.reset_interval > 0
                        and (now - last_I_time) >= args.reset_interval
                    )

                    # 差分コーデック経由で I/P を決定
                    frame_bytes = codec.encode_frame(
                        frame_bgr=frame,
                        force_I=force_I,
                        jpeg_quality=args.jpeg_quality,
                    )
                    if force_I:
                        last_I_time = now
                else:
                    # diff=off → そのままJPEG
                    frame_bytes = encode_jpeg(frame, quality=args.jpeg_quality)

            except Exception as e:
                # エラー時のみログ（頻度は低い想定）
                print("[ENCODE] encode error:", e)
                continue

            
            encoded_buffer.put((frame_id, frame_bytes))

            frame_id += 1

    t = threading.Thread(target=encode_loop, daemon=True)
    t.start()
    return t

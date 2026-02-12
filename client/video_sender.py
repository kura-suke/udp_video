# client/video_sender.py
"""
UDP動画送信SDK（送信側）

目的：
- 他の通信プログラムから import して
  start() → send_frame(frame) だけで映像送信できるようにする

前提：
- frame は OpenCV の BGR (numpy.ndarray) を想定
- 既存の dir_encode_thread.py / send_thread.py をそのまま流用する
"""

from __future__ import annotations

import socket
import threading
import queue
from collections import deque
from types import SimpleNamespace
from typing import Optional, Tuple, Deque

# 既存資産を流用（相対importで統一）
from .diff.diffproc_fixed import DiffCodec
from .encode_thread import start_encode_thread
from .send_thread import start_send_thread


class VideoSender:
    """
    送信エンジン（SDKの入口）

    典型的な使い方:
        from client.video_sender import VideoSender
        sender = VideoSender(server_ip="192.168.0.10", server_port=5000, fec="high", diff="on")
        sender.start()
        sender.send_frame(frame_bgr)
        sender.stop()

    重要：
    - start() しないと送信スレッドが動かない
    - send_frame() は最新フレーム優先（deque maxlen=3）
    """

    def __init__(
        self,
        server_ip: str = "127.0.0.1",
        server_port: int = 5000,
        *,
        fps: float = 25.0,
        jpeg_quality: int = 70,
        diff: str = "off",          # "on" or "off"
        block: int = 16,
        T: float = 5.0,
        sad_skip_per_px: float = 1.5,
        scene_change_ratio: float = 0.25,
        jpeg_gate_ratio: float = 0.70,
        zlib_level: int = 6,
        reset_interval: float = 1.0,
        fec: str = "none",          # "none" / "low" / "mid" / "high"
        fec_k: int = 8,
    ):
        # 既存スレッド関数が args.xxx を参照するので、それに合わせる
        self.args = SimpleNamespace(
            server_ip=server_ip,
            server_port=server_port,
            fps=float(fps),
            jpeg_quality=int(jpeg_quality),
            diff=str(diff),
            block=int(block),
            T=float(T),
            sad_skip_per_px=float(sad_skip_per_px),
            scene_change_ratio=float(scene_change_ratio),
            jpeg_gate_ratio=float(jpeg_gate_ratio),
            zlib_level=int(zlib_level),
            reset_interval=float(reset_interval),
            fec=str(fec),
            fec_k=int(fec_k),
        )

        self.server_addr: Tuple[str, int] = (server_ip, int(server_port))

        # スレッド間バッファ（既存設計を踏襲）
        self.frame_buffer: Deque = deque(maxlen=3)             # 外部 → Encode
        self.encoded_buffer: "queue.Queue[Tuple[int, bytes]]" = queue.Queue(maxsize=1)  # Encode → Send
        self.stop_flag = threading.Event()

        # UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # DiffCodec（diff=on の場合のみ）
        self.diff_codec: Optional[DiffCodec] = None
        if self.args.diff == "on":
            self.diff_codec = DiffCodec(
                block=self.args.block,
                T=self.args.T,
                sad_skip_per_px=self.args.sad_skip_per_px,
                scene_change_ratio=self.args.scene_change_ratio,
                jpeg_gate_ratio=self.args.jpeg_gate_ratio,
                zlib_level=self.args.zlib_level,
            )

        self._started = False
        self._lock = threading.Lock()
        self._t_encode: Optional[threading.Thread] = None
        self._t_send: Optional[threading.Thread] = None

    def start(self) -> None:
        """Encodeスレッド + Sendスレッドを起動する"""
        with self._lock:
            if self._started:
                return

            # stop_flag は再利用しない（stop後に再startするなら作り直し推奨）
            if self.stop_flag.is_set():
                raise RuntimeError("この VideoSender は stop() 済みです。新しく作り直してください。")

            self._t_encode = start_encode_thread(
                frame_buffer=self.frame_buffer,
                encoded_buffer=self.encoded_buffer,
                stop_flag=self.stop_flag,
                args=self.args,
                diff_codec=self.diff_codec,
            )

            self._t_send = start_send_thread(
                encoded_buffer=self.encoded_buffer,
                stop_flag=self.stop_flag,
                args=self.args,
                server_addr=self.server_addr,
                sock=self.sock,
            )

            self._started = True

    def send_frame(self, frame_bgr) -> None:
        """
        外部で生成したBGRフレームを投入する（最重要API）

        NOTE:
        - 最新優先で送るので、処理が詰まっても古いフレームは捨てられる
        """
        if not self._started:
            raise RuntimeError("VideoSender.start() を先に呼んでください。")
        # deque(maxlen=3) なので溢れたら古い方が自動で落ちる
        self.frame_buffer.append(frame_bgr)

    def stop(self) -> None:
        """送信停止（スレッド停止フラグを立て、ソケットを閉じる）"""
        with self._lock:
            if not self._started:
                return
            self.stop_flag.set()

            # スレッドは daemon=True なので join 必須ではないが、軽く待つのはアリ
            # ただし固まるのを避けて短いtimeoutにしておく
            try:
                if self._t_encode is not None:
                    self._t_encode.join(timeout=0.2)
                if self._t_send is not None:
                    self._t_send.join(timeout=0.2)
            except Exception:
                pass

            try:
                self.sock.close()
            except Exception:
                pass

            self._started = False

    # 使いやすくするため（with で安全に止められる）
    def __enter__(self) -> "VideoSender":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

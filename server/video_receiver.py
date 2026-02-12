# server/video_receiver.py
from __future__ import annotations

import socket
import threading
import queue
import time
from types import SimpleNamespace
from typing import Optional, Any, Tuple

from .fec.fec_reassembler_low import FECLowReassembler
from .fec.fec_reassembler_mid import FECMediumReassembler
from .fec.fec_reassembler_high import FECHighReassembler
from .fec.simple_reassembler import SimpleFrameReassembler

from .diff.diffdecode import DiffDecoder

from .recv_thread import start_recv_thread
from .reassemble_thread import start_reassemble_thread
from .decode_thread import start_decode_thread


class VideoReceiver:
    """
    server.py と同じ “4-thread設計のうち表示以外” をSDK化した受信クラス。

    - start(): 受信パイプライン起動
    - get_latest_frame(): 最新フレーム取得（表示は利用側でcv2.imshow等）
    - stop(): 停止

    ※ decode_thread が args を読む設計なので、args互換(SimpleNamespace)を内部生成する。
    """

    def __init__(
        self,
        *,
        bind_ip: str = "0.0.0.0",
        port: int = 5000,
        fec: str = "none",   # "none" / "low" / "mid" / "high"
        diff: str = "off",   # "on" / "off"
        buffer: str = "off",
        record: str = "off",
        packet_qsize: int = 1000,
        frame_qsize: int = 120,
        decoded_qsize: int = 120,
    ):
        # server.py の args と同じフィールド名にしておく（decode_thread が args.xxx を参照するため）
        self.args = SimpleNamespace(
            bind_ip=bind_ip,
            port=port,
            fec=fec,
            diff=diff,
            buffer=buffer,
            record=record,
        )

        self.stop_flag = threading.Event()
        self._lock = threading.Lock()
        self._started = False

        self.sock: Optional[socket.socket] = None

        # server.py と同じキュー構成
        self.packet_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=packet_qsize)
        self.frame_queue: "queue.Queue[Any]" = queue.Queue(maxsize=frame_qsize)
        self.decoded_queue: "queue.Queue[Any]" = queue.Queue(maxsize=decoded_qsize)

        # FEC選択（server.py と同じ）
        if self.args.fec == "none":
            self.reassembler = SimpleFrameReassembler()
        elif self.args.fec == "low":
            self.reassembler = FECLowReassembler()
        elif self.args.fec == "mid":
            self.reassembler = FECMediumReassembler()
        elif self.args.fec == "high":
            self.reassembler = FECHighReassembler()
        else:
            self.reassembler = SimpleFrameReassembler()

        # DiffDecoder（server.py と同じ）
        self.diff_decoder = DiffDecoder() if self.args.diff == "on" else None

        # 最新フレーム保持
        self._latest: Optional[Tuple[int, Any, int]] = None  # (frame_id, frame, recovered)
        self._tap_thread: Optional[threading.Thread] = None

        # 簡易統計
        self._started_ts: Optional[float] = None
        self._decoded_count = 0

        # 起動したスレッド
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            if self.stop_flag.is_set():
                raise RuntimeError("この VideoReceiver は stop() 済みです。新しく作り直してください。")

            # server.py と同じソケット設定
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.args.bind_ip, self.args.port))
            self.sock.settimeout(0.5)

            # server.py と同じスレッド開始（display_threadはSDKでは起動しない）
            t_recv = start_recv_thread(sock=self.sock, packet_queue=self.packet_queue, stop_flag=self.stop_flag)
            t_reasm = start_reassemble_thread(
                packet_queue=self.packet_queue,
                frame_queue=self.frame_queue,
                stop_flag=self.stop_flag,
                reassembler=self.reassembler,
            )
            t_dec = start_decode_thread(
                frame_queue=self.frame_queue,
                decoded_queue=self.decoded_queue,
                stop_flag=self.stop_flag,
                args=self.args,
                diff_decoder=self.diff_decoder,
            )

            self._threads = [t_recv, t_reasm, t_dec]

            # decoded_queue から最新フレームを拾う
            def tap():
                while not self.stop_flag.is_set():
                    try:
                        item = self.decoded_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue

                    # 期待: (frame_id, frame, recovered)  ※display_thread側がこれを想定しているのと同じ流れ
                    if isinstance(item, tuple) and len(item) >= 3:
                        frame_id, frame, recovered = item[0], item[1], item[2]
                        self._latest = (int(frame_id), frame, int(recovered))
                        self._decoded_count += 1

            self._tap_thread = threading.Thread(target=tap, daemon=True)
            self._tap_thread.start()

            self._started = True
            self._started_ts = time.time()

    def get_latest_frame(self) -> Optional[Tuple[int, Any, int]]:
        return self._latest

    def stop(self) -> None:
        with self._lock:
            if not self._started:
                return
            self.stop_flag.set()
            try:
                if self.sock is not None:
                    self.sock.close()
            except Exception:
                pass
            self.sock = None
            self._started = False

    def status(self) -> dict:
        now = time.time()
        age = None if self._started_ts is None else round(now - self._started_ts, 3)
        return {
            "running": self._started,
            "bind_ip": self.args.bind_ip,
            "port": self.args.port,
            "fec": self.args.fec,
            "diff": self.args.diff,
            "has_latest": self._latest is not None,
            "latest_frame_id": None if self._latest is None else self._latest[0],
            "decoded_count": self._decoded_count,
            "age_since_start": age,
        }

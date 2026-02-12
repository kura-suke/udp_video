from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import cv2
import time

from .video_receiver import VideoReceiver

app = FastAPI()
_rx: VideoReceiver | None = None


class StartBody(BaseModel):
    bind_ip: str = "0.0.0.0"
    port: int = 5000
    fec: str = "none"  # none/low/mid/high
    diff: str = "off"  # on/off


@app.get("/status")
def status():
    if _rx is None:
        return {"running": False}
    return _rx.status()


@app.post("/start")
def start(body: StartBody):
    global _rx
    if _rx is not None:
        return {"ok": True, "status": _rx.status(), "note": "already running"}

    _rx = VideoReceiver(
        bind_ip=body.bind_ip,
        port=body.port,
        fec=body.fec,
        diff=body.diff,
    )
    _rx.start()
    return {"ok": True, "status": _rx.status()}


@app.post("/stop")
def stop():
    global _rx
    rx = _rx
    if rx is None:
        return {"ok": True, "status": {"running": False}}

    rx.stop()
    _rx = None
    return {"ok": True, "status": {"running": False}}



@app.get("/mjpeg")
def mjpeg():
    """
    ブラウザで映像確認用: http://localhost:8000/mjpeg
    ※ /start で受信を開始してからアクセス
    """
    def gen():
        while True:
            # 毎ループで現在の _rx を見る（stopされたら終わる）
            rx = _rx
            if rx is None:
                # stopされたのでストリーム終了
                return

            item = rx.get_latest_frame()
            if item is None:
                time.sleep(0.01)
                continue

            _, frame, _ = item
            ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ok:
                continue

            data = jpg.tobytes()
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + data + b"\r\n")

    if _rx is None:
        return {"error": "receiver not started. call POST /start first"}

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


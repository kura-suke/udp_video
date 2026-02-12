# jpeg_util.py
import cv2
import numpy as np
#frame_bgr;画像データ　quality;JPEG品質
def encode_jpeg(frame_bgr: np.ndarray, quality: int):
    ok, enc = cv2.imencode(
        ".jpg",
        frame_bgr,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
    )
    if not ok:
        raise RuntimeError("JPEG encode failed")
    #enc;エンコードされた画像データ
    return enc.tobytes()

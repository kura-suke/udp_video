
import cv2

def encode_jpeg(frame, quality: int = 80) -> bytes:
    """
    フレームをJPEGに圧縮してバイト列を返す
    Args:
        frame: numpy.ndarray (BGR画像)
        quality: JPEG品質 (1〜100)
    Returns:
        bytes: JPEG圧縮済みバイト列
    Raises:
        RuntimeError: エンコード失敗時
    """
    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return encoded.tobytes()

# udp-video

UDP-based real-time video transmission library  
with optional Diff encoding and Forward Error Correction (FEC).

Designed for research on reliable low-latency video transmission over unreliable networks.

---

## Overview

udp-video is a Python library for transmitting video frames over UDP with:

- Differential (Diff) encoding
- Forward Error Correction (FEC)
- Thread-based modular architecture
- Real-time decoding and display

This project is intended for:

- Real-time video transmission experiments
- UDP reliability research
- Bandwidth optimization studies
- Embedded or edge-device streaming

---

## Installation

### Basic installation

```bash
pip install "udp-video @ git+https://github.com/kura-suke/udp_video.git"
```

### With OpenCV (camera + display support)

```bash
pip install "udp-video[opencv] @ git+https://github.com/kura-suke/udp_video.git"
```

### Raspberry Pi (lightweight)

```bash
pip install "udp-video[opencv-headless] @ git+https://github.com/kura-suke/udp_video.git"
```

---

## Requirements

- Python 3.10+
- numpy
- opencv-python (optional)

---

## Quick Start

### Receiver (Server Side)

Create `run_receiver.py`

```python
import time
import cv2
from server import VideoReceiver

def main():
    rx = VideoReceiver(bind_ip="0.0.0.0", port=5000, fec="none", diff="off")
    rx.start()
    print("Receiver started on port 5000")

    try:
        while True:
            item = rx.get_latest_frame()
            if item is None:
                time.sleep(0.01)
                continue

            frame = item["frame"]
            cv2.imshow("recv", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        rx.stop()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
```

Run:

```bash
python run_receiver.py
```

---

### Sender (Client Side)

Create `run_sender.py`

```python
import cv2
from client import VideoSender

def main():
    sender = VideoSender(
        server_ip="127.0.0.1",
        server_port=5000,
        fec="none",
        diff="off"
    )

    sender.start()
    cap = cv2.VideoCapture(0)

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        sender.send_frame(frame)

        cv2.imshow("local", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    sender.stop()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
```

Run:

```bash
python run_sender.py
```

---

## Multi-PC Usage

Receiver machine:

```python
VideoReceiver(bind_ip="0.0.0.0", port=5000)
```

Sender machine:

```python
VideoSender(server_ip="RECEIVER_IP", server_port=5000)
```

Make sure UDP port 5000 is open and firewall allows traffic.

---

## Configuration Options

### FEC Modes

- none
- low
- medium
- high

Example:

```python
VideoSender(server_ip="127.0.0.1", fec="high")
```

### Diff Encoding

```python
VideoSender(server_ip="127.0.0.1", diff="on")
```

---

## Architecture

The system consists of:

- Capture Thread
- Encode Thread (JPEG + Diff)
- Send Thread (UDP transmission)
- Receive Thread
- Reassembly Thread (FEC)
- Decode Thread
- Display Thread

---

## Research Context

Developed for:

- UDP-based real-time video transmission research
- Bandwidth optimization under unstable networks
- FEC-based reliability improvement
- Differential encoding evaluation

---

## License

For research and experimental use.

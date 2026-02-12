# udp-video

UDP-based real-time video transmission library  
with optional Differential encoding and Forward Error Correction (FEC).

Designed for research on reliable low-latency video transmission over unreliable networks.

---

## Overview

`udp-video` is a Python library for transmitting video frames over UDP with:

- Differential (Diff) encoding
- Forward Error Correction (FEC) (none / low / mid / high)
- Thread-based modular architecture
- Real-time decoding and display

This project is intended for:

- Real-time video transmission experiments
- UDP reliability research
- Bandwidth optimization studies
- Embedded or edge-device streaming
- Academic research on unreliable networks

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

### Raspberry Pi (headless)

```bash
pip install "udp-video[opencv-headless] @ git+https://github.com/kura-suke/udp_video.git"
```

---

## Requirements

- Python 3.10+
- numpy
- opencv-python (optional for camera/display)

---

# Quick Start

## 1️⃣ Receiver (Server Side)

Create `run_receiver.py`

```python
import time
import cv2
from server import VideoReceiver

def main():
    rx = VideoReceiver(
        bind_ip="0.0.0.0",
        port=5000,
        fec="none",      # none / low / mid / high
        diff="off"       # off / on
    )

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

## 2️⃣ Sender (Client Side)

Create `run_sender.py`

```python
import cv2
from client import VideoSender

def main():
    sender = VideoSender(
        server_ip="127.0.0.1",
        server_port=5000,
        fec="none",      # none / low / mid / high
        diff="off"       # off / on
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

# Multi-PC Usage

Receiver machine:

```python
VideoReceiver(bind_ip="0.0.0.0", port=5000)
```

Sender machine:

```python
VideoSender(server_ip="RECEIVER_IP", server_port=5000)
```

Make sure:

- UDP port 5000 is open
- Firewall allows inbound UDP traffic

---

# Configuration

## FEC Modes

| Mode | Description |
|------|------------|
| none | No error correction |
| low  | 1 parity per 8 chunks (XOR) |
| mid  | 2 parity per group (can recover up to 2 losses depending on pattern) |
| high | Multi-parity (Gaussian elimination based recovery) |

Example:

```python
VideoSender(server_ip="127.0.0.1", fec="high")
```

---

## Differential Encoding (Diff)

When enabled:

- First frame = I-frame (JPEG)
- Subsequent frames = P-frame (block-based residual)

```python
VideoSender(server_ip="127.0.0.1", diff="on")
```

Benefits:

- Reduced bandwidth
- Temporal redundancy exploitation

---

# API Reference

---

## VideoSender

```python
VideoSender(
    server_ip: str,
    server_port: int,
    fec: str = "none",
    diff: str = "off"
)
```

### Methods

```python
start()
```
Start internal sending threads.

```python
send_frame(frame: np.ndarray)
```
Send a single BGR frame.

```python
stop()
```
Stop sender and release resources.

---

## VideoReceiver

```python
VideoReceiver(
    bind_ip: str,
    port: int,
    fec: str = "none",
    diff: str = "off"
)
```

### Methods

```python
start()
```
Start receiving, reassembly, decoding, and display threads.

```python
get_latest_frame()
```
Returns:

```python
{
    "frame_id": int,
    "frame": np.ndarray,
    "recovered": int
}
```

or `None` if no frame is available.

```python
stop()
```
Stop all threads and close socket.

---

# Internal Architecture (High-Level)

The system uses a 4-thread server pipeline:

1. Receive Thread (UDP socket)
2. Reassembly Thread (FEC reconstruction)
3. Decode Thread (Diff or JPEG decoding)
4. Display Thread (OpenCV rendering)

Client side:

1. Capture
2. Encode (JPEG / Diff)
3. FEC packetization
4. UDP send

This modular design enables:

- Easy experimentation
- Replaceable FEC modules
- Research-oriented extensions

---

# Research Context

This library was developed for:

- UDP-based real-time video transmission research
- Error-resilient streaming in unstable environments (e.g., snowy mountains)
- Bandwidth-aware transmission systems
- Differential + FEC hybrid reliability models

---

# License

For research and experimental use.

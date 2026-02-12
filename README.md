# udp-video

UDPベースのリアルタイム映像伝送ライブラリ  
差分符号化（Diff）および Forward Error Correction（FEC）に対応。

不安定なネットワーク環境下での低遅延・高信頼映像伝送の研究を目的として設計されています。

---

## 概要

`udp-video` は、UDPを用いて映像フレームを送信するためのPythonライブラリです。

以下の機能を備えています：

- 差分符号化（Differential Encoding）
- Forward Error Correction（FEC）（none / low / mid / high）
- スレッドベースのモジュール構造
- リアルタイム復号・表示

本プロジェクトは以下の用途を想定しています：

- リアルタイム映像伝送の実験
- UDP信頼性研究
- 帯域最適化研究
- 組み込み・エッジデバイスでのストリーミング
- 不安定ネットワーク環境での映像通信研究

---

## インストール

### 基本インストール

```bash
pip install "udp-video @ git+https://github.com/kura-suke/udp_video.git"
```

### OpenCV込み（カメラ・表示対応）

```bash
pip install "udp-video[opencv] @ git+https://github.com/kura-suke/udp_video.git"
```

### Raspberry Pi（GUIなし環境向け）

```bash
pip install "udp-video[opencv-headless] @ git+https://github.com/kura-suke/udp_video.git"
```

---

## 必要環境

- Python 3.10以上
- numpy
- opencv-python（カメラ・表示使用時）

---

# クイックスタート

## 1️⃣ 受信側（サーバ）

`run_receiver.py` を作成

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
    print("ポート5000で受信開始")

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

実行：

```bash
python run_receiver.py
```

---

## 2️⃣ 送信側（クライアント）

`run_sender.py` を作成

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

実行：

```bash
python run_sender.py
```

---

# 複数PCでの使用

受信側マシン：

```python
VideoReceiver(bind_ip="0.0.0.0", port=5000)
```

送信側マシン：

```python
VideoSender(server_ip="受信側IPアドレス", server_port=5000)
```

注意：

- UDPポート5000を開放すること
- ファイアウォールでUDP通信を許可すること

---

# 設定

## FECモード

| モード | 説明 |
|--------|------|
| none | 誤り訂正なし |
| low  | 8チャンクにつき1パリティ（XOR） |
| mid  | グループあたり2パリティ（条件により最大2損失復元） |
| high | 多重パリティ（ガウス消去法ベース復元） |

例：

```python
VideoSender(server_ip="127.0.0.1", fec="high")
```

---

## 差分符号化（Diff）

有効化すると：

- 最初のフレーム：Iフレーム（JPEG）
- 以降のフレーム：Pフレーム（ブロック差分）

```python
VideoSender(server_ip="127.0.0.1", diff="on")
```

メリット：

- 帯域削減
- 時間方向の冗長性活用

---

# APIリファレンス

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

### メソッド

```python
start()
```
内部送信スレッドを開始。

```python
send_frame(frame: np.ndarray)
```
BGR形式の1フレームを送信。

```python
stop()
```
送信停止・リソース解放。

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

### メソッド

```python
start()
```
受信・再構成・復号・表示スレッドを開始。

```python
get_latest_frame()
```

戻り値：

```python
{
    "frame_id": int,
    "frame": np.ndarray,
    "recovered": int
}
```

フレームが未到着の場合は `None`。

```python
stop()
```
全スレッド停止・ソケットクローズ。

---

# 内部構成（概要）

サーバ側は4スレッド構成：

1. 受信スレッド（UDP）
2. 再構成スレッド（FEC復元）
3. 復号スレッド（Diff / JPEG）
4. 表示スレッド（OpenCV）

クライアント側：

1. キャプチャ
2. 符号化（JPEG / Diff）
3. FECパケット化
4. UDP送信

このモジュール設計により：

- 実験拡張が容易
- FEC差し替え可能
- 研究用途に適した構成

---

# 研究背景

本ライブラリは以下の研究目的で開発されました：

- UDPベースのリアルタイム映像伝送
- 不安定ネットワーク（例：雪山環境）での誤り耐性向上
- 帯域効率を考慮した映像伝送方式
- 差分符号化 + FEC統合モデルの評価

---

# ライセンス

研究・実験用途向け。

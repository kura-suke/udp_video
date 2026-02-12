# simple_reassembler.py
"""
FECなし用のシンプルなフレーム再構成クラス

クライアント側の FEC=none 用パケット
  HEADER_FMT = "!IHH"  # frame_id, chunk_id, total_chunks
に対応して、frame_id ごとにチャンクを集めて 1フレームに復元する。
"""

import struct
from typing import Dict, Any, Optional, Tuple

# クライアントの FEC なしヘッダと合わせる
HEADER_FMT = "!IHH"   # frame_id, chunk_id, total_chunks
HEADER_SIZE = struct.calcsize(HEADER_FMT)#ヘッダサイズ計算


class SimpleFrameReassembler:
    def __init__(self):
        # frame_id -> {"total": int, "chunks": list[bytes], "received": int}
        self.frames: Dict[int, Dict[str, Any]] = {}#udpなのでチャンクが順不同で到着する可能性があるため、フレームごとにチャンクを保存

    def add_packet(self, packet: bytes) -> Optional[Tuple[int, bytes, int]]:
        """
        1つのUDPパケットを追加し、フレームが完成したら
        (frame_id, frame_bytes, recovered) を返す。
        まだ未完成なら None を返す。
        recovered は FECなしなので常に 0。
        """
        if len(packet) < HEADER_SIZE:
            return None

        frame_id, chunk_id, total_chunks = struct.unpack(HEADER_FMT, packet[:HEADER_SIZE])#ヘッダ解析
        payload = packet[HEADER_SIZE:]#ヘッダの後ろの映像データを取得

        st = self.frames.get(frame_id)
        if st is None:
            st = {
                "total": total_chunks,
                "chunks": [None] * total_chunks,
                "received": 0,
            }
            self.frames[frame_id] = st

        # total_chunks が途中で増えるケースへの追従
        if total_chunks > st["total"]:
            extra = total_chunks - st["total"]#増えた分
            st["chunks"].extend([None] * extra)#チャンクリストを拡張
            st["total"] = total_chunks#合計チャンク数を更新

        if 0 <= chunk_id < st["total"]:#チャンクIDが範囲内か確認
            if st["chunks"][chunk_id] is None:#未受信なら
                st["chunks"][chunk_id] = payload#チャンクデータを保存
                st["received"] += 1#受信済みチャンク数をインクリメント

        # すべて揃ったら復元
        if st["received"] == st["total"]:#すべてのチャンクを受信済み
            frame_bytes = b"".join(ch for ch in st["chunks"] if ch is not None)#チャンクを結合してフレームデータを復元
            del self.frames[frame_id]#メモリ解放
            # FECなしなので recovered=0
            return (frame_id, frame_bytes, 0)

        return None

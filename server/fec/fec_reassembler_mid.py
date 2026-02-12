# fec_reassembler_mid.py  --- packet.py 依存なし
import struct
from typing import Dict, List, Optional, Tuple

# === packet.py の依存を削除 ===
HEADER_FMT = "!IHH"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
# ==============================

K = 8
R = 2  # p0: all XOR, p1: even XOR

def _xor_bytes(a: bytes, b: bytes) -> bytes:
    if len(a) < len(b):
        a += b"\x00" * (len(b) - len(a))#長さを合わせる
    elif len(b) < len(a):
        b += b"\x00" * (len(a) - len(b))#長さを合わせる
    return bytes(x ^ y for x, y in zip(a, b))

def _ceil_div(a, b):
    return (a + b - 1) // b#グループ数を計算

def _groups_from_data_total(D: int):#グループの総チャンク数を計算
    if D <= 0:
        return (0, 0)
    G = _ceil_div(D, K)
    T_full = D + G*R
    return (G, T_full)

def _solve_from_total_full(T_full: int):#グループのデータチャンク数を計算
    if T_full <= 0:
        return (0, 0)
    maxG = T_full // (K+R) + 4
    for G in range(1, maxG+1):
        D = T_full - R*G
        if D > 0 and G == _ceil_div(D, K):
            return (D, G)
    return (T_full, 0)

class _FrameState:
    def __init__(self, frame_id: int, D: int, G: int):
        self.frame_id = frame_id
        self.D = max(0, D)
        self.G = max(0, G)

        self.di = []
        remain = self.D
        for _ in range(self.G):
            t = K if remain >= K else remain
            self.di.append(t)
            remain -= t

        self.group_start = []
        cur = 0
        for g in range(self.G):
            self.group_start.append(cur)
            cur += self.di[g] + R

        self.data = [[None]*d for d in self.di]
        self.p0 = [None]*self.G
        self.p1 = [None]*self.G

        self.data_received = 0
        self.recovered = 0
        self._fec_filled = [set() for _ in range(self.G)]

    def _locate(self, cid: int):#チャンクIDからグループとチャンク番号を特定
        for g in range(self.G):
            start = self.group_start[g]
            size = self.di[g] + R
            if start <= cid < start+size:
                local = cid - start
                if local < self.di[g]:
                    return (g, local, False)
                else:
                    return (g, local - self.di[g], True)
        return (None, None, False)

    def _fill_by_fec(self, g: int, i: int, payload: bytes):#FECで復元したチャンクを格納
        if self.data[g][i] is None:
            self.data[g][i] = payload
            self.data_received += 1
            if i not in self._fec_filled[g]:
                self.recovered += 1
                self._fec_filled[g].add(i)

    def _try_recover_group(self, g: int):#グループ内の欠損チャンクをFECで復元
        d = self.di[g]
        missing = [i for i in range(d) if self.data[g][i] is None]
        if not missing:
            return

        p0 = self.p0[g]
        p1 = self.p1[g]

        if len(missing) == 1 and p0:
            need = missing[0]
            acc = p0
            for i in range(d):
                if i != need and self.data[g][i] is not None:
                    acc = _xor_bytes(acc, self.data[g][i])
            self._fill_by_fec(g, need, acc)
            return

        if len(missing) == 2 and p0 and p1:
            a, b = missing
            s_all = p0
            for i in range(d):
                if i not in (a, b) and self.data[g][i] is not None:
                    s_all = _xor_bytes(s_all, self.data[g][i])

            s_even = p1
            for i in range(0, d, 2):
                if i not in (a, b) and self.data[g][i] is not None:
                    s_even = _xor_bytes(s_even, self.data[g][i])

            ae = (a % 2 == 0)
            be = (b % 2 == 0)

            if ae and (not be):
                Da = s_even
                Db = _xor_bytes(s_all, Da)
            elif (not ae) and be:
                Db = s_even
                Da = _xor_bytes(s_all, Db)
            else:
                return

            self._fill_by_fec(g, a, Da)
            self._fill_by_fec(g, b, Db)

    def add_packet(self, pkt: bytes):#チャンクを追加し、フレーム完成時にデータを返す
        if len(pkt) < HEADER_SIZE: return None
        frame_id, cid, total = struct.unpack(HEADER_FMT, pkt[:HEADER_SIZE])
        payload = pkt[HEADER_SIZE:]

        g, li, is_parity = self._locate(cid)
        if g is None:
            return None

        if not is_parity:
            if self.data[g][li] is None:
                self.data[g][li] = payload
                self.data_received += 1
            self._try_recover_group(g)
        else:
            if li == 0:
                self.p0[g] = payload
            else:
                self.p1[g] = payload
            self._try_recover_group(g)

        if self.data_received == self.D:
            out = []
            for gg in range(self.G):
                for i in range(self.di[gg]):
                    if self.data[gg][i] is None:
                        return None
                    out.append(self.data[gg][i])
            return (self.frame_id, b"".join(out), self.recovered)
        return None

class FECMediumReassembler:
    def __init__(self):
        self.frames: Dict[int, _FrameState] = {}
        self.meta: Dict[int, int] = {}  # frame_id → data_total

    def register_meta(self, fid: int, D: int):#フレームが何個のデータチャンクで構成されるか登録
        self.meta[fid] = D

    def _ensure_state(self, fid: int, total: int):#フレーム状態を確保
        st = self.frames.get(fid)
        if st is not None:
            return st

        if fid in self.meta:#メタ情報がある場合はそれを優先
            D = self.meta[fid]
            G, _ = _groups_from_data_total(D)
            st = _FrameState(fid, D, G)
            self.frames[fid] = st
            return st

        D1, G1 = _solve_from_total_full(total)#MATA情報がない場合は総チャンク数から推定
        if G1 > 0:
            st = _FrameState(fid, D1, G1)
            self.frames[fid] = st
            return st

        D2 = total
        G2, _ = _groups_from_data_total(D2)#それでもダメな場合
        st = _FrameState(fid, D2, G2)
        self.frames[fid] = st
        return st

    def add_packet(self, pkt: bytes):#チャンクを追加し、フレーム完成時にデータを返す
        if len(pkt) < HEADER_SIZE: return None
        fid, cid, total = struct.unpack(HEADER_FMT, pkt[:HEADER_SIZE])

        st = self.frames.get(fid)
        if st is None:
            st = self._ensure_state(fid, total)

        res = st.add_packet(pkt)
        if res is not None:
            del self.frames[fid]
            if fid in self.meta:
                del self.meta[fid]
            return res
        return None

# fec_reassembler_high.py  --- packet.py を使わない完全単独版
import struct
from typing import Dict, List, Optional, Tuple

# === packet.py の依存を排除 ===
HEADER_FMT = "!IHH"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
# ===============================

K = 8
R = 4
MASKS = [1,2,3,4,5,6,7,8]

def _xor_bytes(a: bytes, b: bytes) -> bytes:#バイト列のXORを取る
    if len(a) < len(b):
        a += b"\x00" * (len(b) - len(a))
    elif len(b) < len(a):
        b += b"\x00" * (len(a) - len(b))
    return bytes(x^y for x,y in zip(a,b))

def _solve_groups(total: int, k=K, r=R):#チャンク総数からデータチャンク数とグループ数を推定
    T = total
    maxG = T // (k+r) + 3
    for G in range(0, maxG+1):
        D = T - r*G
        if D < 0:
            continue
        if G == 0 and D == 0:
            return (0, 0)
        if G == (D + k - 1) // k:
            return (D, G)
    return (T, 0)

class _FrameState:
    def __init__(self, fid: int, total: int):
        self.frame_id = fid
        self.total_chunks = total
        self.D, self.G = _solve_groups(total)

        self.di = []
        rem = self.D
        for _ in range(self.G):
            t = K if rem >= K else rem
            self.di.append(t)
            rem -= t

        self.group_start = []
        cur = 0
        for g in range(self.G):
            self.group_start.append(cur)
            cur += self.di[g] + R

        self.data = [[None]*d for d in self.di]
        self.par = [[None]*R for _ in range(self.G)]

        self.data_received = 0
        self.recovered = 0

    def _locate(self, cid):#チャンクIDからグループ番号、ローカルID、冗長パケットかどうかを取得
        for g in range(self.G):
            st = self.group_start[g]
            size = self.di[g] + R
            if st <= cid < st+size:
                local = cid - st
                if local < self.di[g]:
                    return g, local, False
                else:
                    return g, local-self.di[g], True
        return None, None, False

    def _recover_group_gauss(self, g: int):#fec復元をガウスの消去法で試みる
        d = self.di[g]
        missing = [i for i in range(d) if self.data[g][i] is None]
        if not missing:
            return

        eq_rows = [b for b in range(R) if self.par[g][b] is not None]
        if not eq_rows:
            return

        m = len(missing)
        if len(eq_rows) < m or m > R:
            return

        rhs = [self.par[g][b] for b in eq_rows]
        for row_i,b in enumerate(eq_rows):
            acc = rhs[row_i]
            for j in range(d):
                if self.data[g][j] is not None:
                    mj = MASKS[j % len(MASKS)]
                    if (mj>>b)&1:
                        acc = _xor_bytes(acc, self.data[g][j])
            rhs[row_i] = acc

        A = [[0]*m for _ in range(len(eq_rows))]
        for rr,b in enumerate(eq_rows):
            for cc,miss_j in enumerate(missing):
                mj = MASKS[miss_j % len(MASKS)]
                A[rr][cc] = 1 if ((mj>>b)&1) else 0

        rows = len(eq_rows)
        cols = m
        pivot_row_for_col = [-1]*cols

        r = 0
        for c in range(cols):
            piv = -1
            for rr in range(r, rows):
                if A[rr][c] == 1:
                    piv = rr
                    break
            if piv == -1:
                continue
            if piv != r:
                A[r], A[piv] = A[piv], A[r]
                rhs[r], rhs[piv] = rhs[piv], rhs[r]

            pivot_row_for_col[c] = r

            for rr in range(rows):
                if rr != r and A[rr][c] == 1:
                    for cc in range(c, cols):
                        A[rr][cc] ^= A[r][cc]
                    rhs[rr] = _xor_bytes(rhs[rr], rhs[r])

            r += 1
            if r == rows:
                break

        rank = sum(1 for pr in pivot_row_for_col if pr != -1)
        if rank < m:
            return

        sol = [b"\x00"]*m
        for c in range(cols-1, -1, -1):
            pr = pivot_row_for_col[c]
            if pr == -1:
                continue
            acc = rhs[pr]
            sol[c] = acc

        for idx,data_i in enumerate(missing):
            if self.data[g][data_i] is None:
                self.data[g][data_i] = sol[idx]
                self.data_received += 1
                self.recovered += 1

    def _try_recover(self, g:int):
        self._recover_group_gauss(g)

    def add_packet(self, pkt: bytes):#フレームを作成、作成できたらデータを返す
        if len(pkt) < HEADER_SIZE:
            return None

        fid, cid, total = struct.unpack(HEADER_FMT, pkt[:HEADER_SIZE])
        payload = pkt[HEADER_SIZE:]

        g, li, is_par = self._locate(cid)
        if g is None:
            return None

        if not is_par:
            if self.data[g][li] is None:
                self.data[g][li] = payload
                self.data_received += 1
        else:
            if 0 <= li < R:
                self.par[g][li] = payload

        self._try_recover(g)

        if self.data_received == self.D:
            out = []
            for gg in range(self.G):
                for i in range(self.di[gg]):
                    if self.data[gg][i] is None:
                        return None
                    out.append(self.data[gg][i])
            return (self.frame_id, b"".join(out), self.recovered)

        return None

class FECHighReassembler:
    def __init__(self):
        self.frames: Dict[int, _FrameState] = {}

    def add_packet(self, pkt: bytes):#チャンクを追加し、フレーム完成時にデータを返す
        if len(pkt) < HEADER_SIZE:
            return None

        fid, cid, total = struct.unpack(HEADER_FMT, pkt[:HEADER_SIZE])

        st = self.frames.get(fid)
        if st is None:
            st = _FrameState(fid, total)
            self.frames[fid] = st

        res = st.add_packet(pkt)
        if res is not None:
            del self.frames[fid]
            return res
        return None

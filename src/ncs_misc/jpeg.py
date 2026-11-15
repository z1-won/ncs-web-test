"""순수 파이썬 기본(baseline) JPEG 해독 — 기타 ④(캡처 화면 작업 표시줄)에 필요한 '아래쪽 몇 행의 밝기'만 꺼낸다.

표준 라이브러리에는 JPEG 해독기가 없고 검수 엔진은 외부 패키지를 쓰지 않는다. 작업 표시줄 판단에는 밝기(Y)면 충분하므로
허프만 복호는 끝까지 하되(비트 흐름을 따라가야 하므로) 역이산코사인변환(IDCT)은 필요한 행에 걸친 Y 블록에만 한다.

지원: SOF0·SOF1(8비트), 성분 1개(회색조) 또는 3개(YCbCr, 임의 표본화), 리스타트 구간.
미지원(→ ValueError): 프로그레시브(SOF2)·무손실·12비트·산술 부호화 — 호출자가 △로 처리한다.
"""

from __future__ import annotations

import math
import struct

ZIGZAG = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21,
          28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54,
          47, 55, 62, 63]
_COS = [[(math.sqrt(0.5) if u == 0 else 1.0) * math.cos((2 * x + 1) * u * math.pi / 16) / 2 for u in range(8)] for x in range(8)]


class _Huffman:
    """표준 maxcode/valptr 방식의 허프만 표."""

    def __init__(self, counts: list[int], symbols: bytes):
        self.symbols = symbols
        self.maxcode, self.valptr, self.mincode = [-1] * 17, [0] * 17, [0] * 17
        code = k = 0
        for length in range(1, 17):
            n = counts[length - 1]
            if n:
                self.valptr[length], self.mincode[length] = k, code
                code += n
                k += n
                self.maxcode[length] = code - 1
            code <<= 1


class _Bits:
    def __init__(self, data: bytes, pos: int):
        self.data, self.pos, self.acc, self.n = data, pos, 0, 0

    def bit(self) -> int:
        if self.n == 0:
            byte = self.data[self.pos]
            self.pos += 1
            if byte == 0xFF:
                nxt = self.data[self.pos]
                if nxt == 0x00:
                    self.pos += 1
                elif 0xD0 <= nxt <= 0xD7:
                    raise ValueError("예상하지 못한 리스타트 표식")
            self.acc, self.n = byte, 8
        self.n -= 1
        return (self.acc >> self.n) & 1

    def bits(self, count: int) -> int:
        v = 0
        for _ in range(count):
            v = (v << 1) | self.bit()
        return v

    def decode(self, table: _Huffman) -> int:
        code = 0
        for length in range(1, 17):
            code = (code << 1) | self.bit()
            if code <= table.maxcode[length]:
                return table.symbols[table.valptr[length] + code - table.mincode[length]]
        raise ValueError("허프만 부호를 찾지 못함")

    def restart(self):
        """리스타트 구간 끝: 남은 비트를 버리고 RSTn 표식을 건너뛴다."""
        self.n = 0
        while self.pos + 1 < len(self.data) and not (self.data[self.pos] == 0xFF and 0xD0 <= self.data[self.pos + 1] <= 0xD7):
            self.pos += 1
        self.pos += 2


def _extend(v: int, t: int) -> int:
    return v - (1 << t) + 1 if t and v < (1 << (t - 1)) else v


def _idct(coef: list[int]) -> list[list[int]]:
    tmp = [[0.0] * 8 for _ in range(8)]
    for y in range(8):
        row = coef[y * 8:y * 8 + 8]
        for x in range(8):
            c = _COS[x]
            tmp[y][x] = sum(c[u] * row[u] for u in range(8))
    out = [[0] * 8 for _ in range(8)]
    for x in range(8):
        col = [tmp[v][x] for v in range(8)]
        for y in range(8):
            c = _COS[y]
            value = sum(c[v] * col[v] for v in range(8)) + 128
            out[y][x] = 0 if value < 0 else 255 if value > 255 else int(value + 0.5)
    return out


def decode_jpeg_rows(data: bytes, rows: range) -> dict[int, list[tuple[int, int, int]]]:
    """원하는 행의 밝기를 (Y, Y, Y)로. 색은 버린다(작업 표시줄 판단은 밝기만 씀)."""
    pos, quant, dc_tables, ac_tables = 2, {}, {}, {}
    frame, restart_interval = None, 0
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        seg = data[pos + 4:pos + 2 + length]
        if marker == 0xDB:
            i = 0
            while i < len(seg):
                precision, tid = seg[i] >> 4, seg[i] & 15
                n = 128 if precision else 64
                raw = seg[i + 1:i + 1 + n]
                quant[tid] = list(struct.unpack(">64H", raw)) if precision else list(raw)
                i += 1 + n
        elif marker in (0xC0, 0xC1):
            if seg[0] != 8:
                raise ValueError("8비트 JPEG만 지원")
            h, w, ncomp = struct.unpack(">HHB", seg[1:6])
            comps = [{"id": seg[6 + 3 * k], "h": seg[7 + 3 * k] >> 4, "v": seg[7 + 3 * k] & 15, "q": seg[8 + 3 * k]} for k in range(ncomp)]
            frame = (w, h, comps)
        elif marker in (0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            raise ValueError("기본(baseline) JPEG만 지원")
        elif marker == 0xC4:
            i = 0
            while i < len(seg):
                cls, tid = seg[i] >> 4, seg[i] & 15
                counts = list(seg[i + 1:i + 17])
                total = sum(counts)
                table = _Huffman(counts, seg[i + 17:i + 17 + total])
                (ac_tables if cls else dc_tables)[tid] = table
                i += 17 + total
        elif marker == 0xDD:
            restart_interval = struct.unpack(">H", seg[:2])[0]
        elif marker == 0xDA:
            if frame is None:
                raise ValueError("SOF 없음")
            return _scan(data, pos + 2 + length, seg, frame, quant, dc_tables, ac_tables, restart_interval, rows)
        elif marker == 0xD9:
            break
        pos += 2 + length
    raise ValueError("스캔을 찾지 못함")


def _scan(data, start, seg, frame, quant, dc_tables, ac_tables, restart_interval, rows):
    w, h, comps = frame
    order = []
    for k in range(seg[0]):
        cid, tables = seg[1 + 2 * k], seg[2 + 2 * k]
        comp = next(c for c in comps if c["id"] == cid)
        order.append((comp, dc_tables[tables >> 4], ac_tables[tables & 15]))
    if len(order) != len(comps):
        raise ValueError("여러 스캔으로 나뉜 JPEG는 지원하지 않음")
    hmax, vmax = max(c["h"] for c in comps), max(c["v"] for c in comps)
    luma = comps[0]
    sx, sy = hmax // luma["h"], vmax // luma["v"]  # 밝기 성분 1픽셀이 화면 몇 픽셀인가(보통 1)
    if len(comps) == 1:  # 비교차(non-interleaved): MCU = 블록 하나
        mcus_x, mcus_y = (w + 7) // 8, (h + 7) // 8
        layout = [(order[0], 1, 1)]
    else:
        mcus_x, mcus_y = (w + 8 * hmax - 1) // (8 * hmax), (h + 8 * vmax - 1) // (8 * vmax)
        layout = [(o, o[0]["h"], o[0]["v"]) for o in order]
    wanted = set(r for r in rows if 0 <= r < h)
    if not wanted:
        return {}
    last_mcu_row = (max(wanted) // (8 * (vmax if len(comps) > 1 else 1)))
    out = {r: [0] * w for r in wanted}
    bits = _Bits(data, start)
    preds = {id(o[0]): 0 for o in order}
    q_luma = quant[luma["q"]]
    count = 0
    for my in range(min(mcus_y, last_mcu_row + 1)):
        for mx in range(mcus_x):
            if restart_interval and count and count % restart_interval == 0:
                bits.restart()
                preds = {k: 0 for k in preds}
            count += 1
            for (comp, dc, ac), hb, vb in layout:
                for by in range(vb):
                    for bx in range(hb):
                        t = bits.decode(dc)
                        diff = _extend(bits.bits(t), t)
                        preds[id(comp)] += diff
                        coef = [0] * 64
                        coef[0] = preds[id(comp)]
                        k = 1
                        while k < 64:
                            rs = bits.decode(ac)
                            r, s = rs >> 4, rs & 15
                            if s == 0:
                                if r != 15:
                                    break
                                k += 16
                                continue
                            k += r
                            if k > 63:
                                break
                            coef[ZIGZAG[k]] = _extend(bits.bits(s), s)
                            k += 1
                        if comp is not luma:
                            continue
                        y0 = ((my * vb + by) * 8) * sy
                        if not any(y0 <= r < y0 + 8 * sy for r in wanted):
                            continue
                        block = _idct([coef[i] * q_luma[_ZPOS[i]] for i in range(64)])
                        x0 = ((mx * hb + bx) * 8) * sx
                        for yy in range(8):
                            for dy in range(sy):
                                r = y0 + yy * sy + dy
                                if r in out:
                                    line = out[r]
                                    for xx in range(8):
                                        for dx in range(sx):
                                            c = x0 + xx * sx + dx
                                            if c < w:
                                                line[c] = block[yy][xx]
    return {r: [(v, v, v) for v in line] for r, line in out.items()}


# 양자화 표는 지그재그 순서로 저장된다 — 자연 순서 i의 계수에는 지그재그 위치 _ZPOS[i]의 양자화 값을 곱한다
_ZPOS = [ZIGZAG.index(i) for i in range(64)]

"""HWP/HWPX 문단 로더. 검수 정책이나 사용자 인터페이스에 의존하지 않는다."""
import struct
import zlib
import zipfile
import re
import io
from xml.etree import ElementTree as ET

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

def detect_format(path):
    with open(path, 'rb') as f:
        head = f.read(8)
    if head == b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1":
        return 'hwp'
    if head[:2] == b'PK':
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        if any(n.startswith('Contents/section') for n in names):
            return 'hwpx'
        raise ValueError(f'zip이지만 hwpx가 아님: {path}')
    raise ValueError(f'hwp/hwpx 둘 다 아님 (머리 바이트 {head!r}): {path}')


def _read_cfb(data):
    hdr = data[:512]
    ssz = 1 << struct.unpack_from("<H", hdr, 0x1E)[0]
    mssz = 1 << struct.unpack_from("<H", hdr, 0x20)[0]
    dir_start = struct.unpack_from("<I", hdr, 0x30)[0]
    mini_cutoff = struct.unpack_from("<I", hdr, 0x38)[0]
    minifat_start = struct.unpack_from("<I", hdr, 0x3C)[0]
    difat_start = struct.unpack_from("<I", hdr, 0x44)[0]
    difat = list(struct.unpack_from("<109I", hdr, 0x4C))
    sec = lambda n: data[(n+1)*ssz: (n+2)*ssz]
    nxt = difat_start
    seen_difat = set()
    while nxt not in (0xFFFFFFFE, 0xFFFFFFFF):
        if nxt in seen_difat:
            raise ValueError("손상된 HWP: DIFAT 순환 참조")
        seen_difat.add(nxt)
        vals = struct.unpack(f"<{ssz//4}I", sec(nxt)); difat += vals[:-1]; nxt = vals[-1]
    fat = []
    for fs in difat:
        if fs not in (0xFFFFFFFE, 0xFFFFFFFF): fat += struct.unpack(f"<{ssz//4}I", sec(fs))
    def chain(start, table):
        out, s, seen = [], start, set()
        while s not in (0xFFFFFFFE, 0xFFFFFFFF):
            if s in seen or s >= len(table):
                raise ValueError("손상된 HWP: 잘못된 섹터 체인")
            seen.add(s)
            out.append(s)
            s = table[s]
        return out
    read_chain = lambda start, size: b"".join(sec(s) for s in chain(start, fat))[:size]
    dirdata = b"".join(sec(s) for s in chain(dir_start, fat))
    entries = []
    for i in range(len(dirdata)//128):
        e = dirdata[i*128:(i+1)*128]
        nlen = struct.unpack_from("<H", e, 0x40)[0]
        entries.append((e[:max(nlen-2, 0)].decode("utf-16le", "ignore"), e[0x42],
                        struct.unpack_from("<I", e, 0x74)[0], struct.unpack_from("<Q", e, 0x78)[0]))
    ministream = read_chain(entries[0][2], entries[0][3])
    minifat = []
    for s in chain(minifat_start, fat): minifat += struct.unpack(f"<{ssz//4}I", sec(s))
    def read_stream(name):
        for n, typ, start, size in entries:
            if n == name and typ == 2:
                if size < mini_cutoff:
                    return b"".join(ministream[s*mssz:(s+1)*mssz] for s in chain(start, minifat))[:size]
                return read_chain(start, size)
    return read_stream, [n for n, t, *_ in entries if t == 2]


def _records(buf):
    """(tag, level, payload) — hwptables와 같은 레코드 정의"""
    i = 0
    while i + 4 <= len(buf):
        h = struct.unpack_from("<I", buf, i)[0]; i += 4
        tag, level, size = h & 0x3FF, (h >> 10) & 0x3FF, h >> 20
        if size == 0xFFF:
            if i + 4 > len(buf):
                raise ValueError("손상된 HWP: 확장 레코드 길이 누락")
            size = struct.unpack_from("<I", buf, i)[0]
            i += 4
        if i + size > len(buf):
            raise ValueError("손상된 HWP: 레코드 잘림")
        yield tag, level, buf[i:i+size]; i += size


def _hwp_para_text(payload):
    out, i, n = [], 0, len(payload)
    while i + 2 <= n:
        c = struct.unpack_from("<H", payload, i)[0]
        if c < 32:
            i += 2 if c in (0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31) else 16
            if c in (9, 10, 13): out.append(" ")
            continue
        out.append(chr(c)); i += 2
    return "".join(out)


def _load_hwp(path):
    with open(path, "rb") as stream:
        data = stream.read()
    read_stream, names = _read_cfb(data)
    flags = struct.unpack_from("<I", read_stream("FileHeader"), 36)[0]
    if flags & 2: raise ValueError("암호화된 hwp는 읽을 수 없음")
    sections = []
    for s in sorted([n for n in names if n.startswith("Section")], key=lambda s: int(s[7:])):
        raw = read_stream(s)
        if flags & 1: raw = zlib.decompress(raw, -15)
        sections.append([_hwp_para_text(p) for tag, lv, p in _records(raw) if tag == 0x43])
    return sections


def _hwpx_para_text(p):
    """변경추적 반영본: deleteBegin~deleteEnd 구간은 버리고, <hp:t> 안 인라인 요소 뒤 tail도 포함.
    표 셀·캡션 안에 중첩된 <hp:p>는 내려가지 않는다 — 그 문단들은 iter(hp:p)에서 따로 나오므로,
    내려가면 바깥 문단에 셀 텍스트가 전부 합쳐지고 같은 글이 중첩 깊이만큼 중복된다."""
    out, state = [], None
    def walk(el):
        nonlocal state
        for ch in el:
            tag = ch.tag.replace(HP, '')
            if tag == 'p': continue
            if tag == 'deleteBegin': state = 'del'
            elif tag in ('deleteEnd', 'insertEnd'): state = None
            elif tag == 'insertBegin': state = 'ins'
            if state != 'del':
                if tag == 't': out.append(ch.text or '')
            walk(ch)
            if state != 'del' and ch.tail and el.tag == HP + 't':
                out.append(ch.tail)
    walk(p)
    return ''.join(out)


def _load_hwpx(path, max_sections=None):
    sections = []
    with zipfile.ZipFile(path) as z:
        names = sorted([n for n in z.namelist() if re.fullmatch(r'Contents/section\d+\.xml', n)],
                       key=lambda n: int(re.search(r'\d+', n).group()))
        for n in names[:max_sections]:
            t = ET.fromstring(z.read(n))
            sections.append([_hwpx_para_text(p) for p in t.iter(HP + 'p')])
    return sections


def load_sections(path, max_sections=None):
    fmt = detect_format(path)
    secs = _load_hwp(path) if fmt == 'hwp' else _load_hwpx(path, max_sections)
    clean = lambda s: re.sub(r'\s+', ' ', s).strip()
    return fmt, [[clean(p) for p in sec] for sec in secs]


def detect_role(sections):
    """내용으로 역할 판별: 개발계획서 vs 학습모듈 원고"""
    head = ' '.join(sections[0][:60]) if sections else ''
    if '개발계획서' in head: return 'plan'
    if '차 례' in head or '차례' in head or '학습모듈의 개요' in head or 'NCS-학습모듈의 위치' in head: return 'manuscript'
    return 'unknown'


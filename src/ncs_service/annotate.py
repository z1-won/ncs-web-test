"""원고 hwpx에 검수 결과를 한글 메모(fieldBegin type=MEMO)로 달아 돌려준다 — 집필진이 한글에서 메모를 따라가며 고치도록.

입력: 원고 hwpx 바이트 + 체크리스트 행(판정이 적합이 아닌 것). 원고 본문은 한 글자도 바꾸지 않는다.

메모는 "결함이 난 자리마다 하나"가 원칙이다. 행의 비고는 체크마다 사례 줄(엔진이 \n 또는 ';'로 나눈 것)을 담고 있으므로,
사례 줄에서 원고 문구(원고 「…」)를 꺼내 그 문구가 있는 문단에 메모를 단다 — 왜(그 사례 줄)와 어떻게(행의 수정 제안)를 함께.
문구가 없는 사례(누락·개수·순서처럼 원고에 없는 것을 말하는 줄)는 행 단위 자리(아래 anchor)에 한데 모아 단다.
같은 문단에 여러 사례가 오면 메모 하나에 합친다. 문단을 못 찾은 행은 문서 첫 문단의 '총괄 메모'에 목록으로 적는다.

문단 찾기(anchor)는 행의 '원고'(그 행이 본 문구)와 region_path(위치 경로)로 한다 — 엔진마다 원고 꼴이 달라(문자열·목록·딕셔너리) 순서대로 시도:
  1. 원고 문자열(또는 목록의 문자열들)과 같은 문단 → 포함 관계(6자 이상)
  2. region_path의 마지막 조각부터: '1-3. 이용정보 제공' 같은 소제목, '학습 1' 같은 머리, '수행 내용 2'(N번째), '참고 자료 > 1번'(N번째 항목)
  3. 못 찾으면 총괄 메모로
메모 XML은 한글이 저장한 실제 파일의 구조를 그대로 따른다(ctrl/fieldBegin[parameters, subList] … ctrl/fieldEnd). 메모 모양은 기본(65535).
메모 날짜는 검사 실행 시각(created_at, 없으면 지금): 한글은 Command의 4·5번째 수(UTC FILETIME 하위·상위 32비트)로 날짜를 보여 주고,
CreateDateTime에는 한국 시각을 끝에 Z를 붙여 적는다(한글이 저장하는 꼴 그대로).
메모 글자는 에디팅기관 에디터 메모와 같게 함초롬돋움 9pt, 장평 97%, 자간 -2%, 행간 160%(MEMO_FONT·MEMO_SIZE_PT·MEMO_RATIO·MEMO_SPACING·MEMO_LINE_SPACING):
header.xml의 글꼴 목록(언어별)·글자 모양(charPr)·문단 모양(paraPr)에 하나씩 추가해 메모 문단만 가리키게 한다. 원고 글자·문단 모양은 바꾸지 않는다.
"""

from __future__ import annotations

import copy
import io
import random
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

from ncs_core.hwpx import HH, HP, para_text, section_names
from ncs_core.text import PASS, visible

from . import export as _export  # 네임스페이스 등록을 공유한다(ET.register_namespace)

AUTHOR = "F02 자동검수"
MAX_MEMO_LINES = 12          # 한 메모에 싣는 최대 줄 수(행이 많이 겹친 문단)
MAX_LINE = 220               # 메모 한 줄 최대 길이
MAX_UNPLACED_LISTED = 40     # 총괄 메모에 나열하는 미배치 행 수
MEMO_FONT = "함초롬돋움"      # 메모 글꼴(에디터 메모 기준). 원고에 이 이름이 없으면 글꼴 목록에 추가한다(한글 기본 글꼴이라 보통 있다)
MEMO_FONT_FALLBACKS = ()     # 대신 쓸 글꼴 이름들(없음)
MEMO_SIZE_PT = 9             # 메모 글자 크기(pt). hwpx height 단위는 1/100pt
MEMO_RATIO = 97              # 장평(%)
MEMO_SPACING = -2            # 자간(%)
MEMO_LINE_SPACING = 160      # 행간(%, 글자에 따라)
HEADER = "Contents/header.xml"
KST = timezone(timedelta(hours=9))
FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


def parse_when(value: str | datetime | None) -> datetime:
    """검사 실행 시각(ISO 문자열 또는 datetime) → 시간대 있는 datetime. 없거나 못 읽으면 지금. 시간대 없는 값은 한국 시각으로 본다."""
    if isinstance(value, datetime):
        when = value
    elif value:
        try:
            when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            when = datetime.now(KST)
    else:
        when = datetime.now(KST)
    return when if when.tzinfo else when.replace(tzinfo=KST)


def filetime_words(when: datetime) -> tuple[int, int]:
    """UTC 시각 → Windows FILETIME(1601-01-01부터 100ns)의 (하위 32비트, 상위 32비트) — 한글 메모 Command의 4·5번째 수."""
    ticks = int((when.astimezone(timezone.utc) - FILETIME_EPOCH).total_seconds() * 10_000_000)
    return ticks & 0xFFFFFFFF, ticks >> 32


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", visible(text or ""))


@dataclass
class Para:
    section: int
    index: int           # 섹션 안 문단 순서(parse_section과 같은 iter 순서)
    element: ET.Element
    text: str            # 보이는 글(변경추적 반영)
    key: str = ""        # 비교용(공백 제거·기호 표시 변환)
    has_text: bool = False

    def __post_init__(self):
        self.key = _norm(self.text)
        self.has_text = bool(self.text.strip())


@dataclass
class Case:
    """메모 하나의 재료: 행 + (그 행의 한 체크 이름, 사례 줄). check가 None이면 행 전체(사례를 쪼개지 못한 것)."""
    row: dict
    check: str | None = None
    line: str | None = None


@dataclass
class Placement:
    cases: list[Case] = field(default_factory=list)

    @property
    def rows(self) -> list[dict]:
        out = []
        for c in self.cases:
            if c.row not in out:
                out.append(c.row)
        return out


CASE_SPLIT = re.compile(r"\n|;\s+")           # 엔진이 사례를 나누는 구분자(줄바꿈, 또는 옛 '; ')
CASE_NUMBER = re.compile(r"^\s*\d+\.\s+")    # ncs_core.notes.lines가 붙인 '1. '
QUOTED_MANUSCRIPT = re.compile(r"원고\s*「(.+?)」")
QUOTED_ANY = re.compile(r"「(.+?)」")


def split_cases(row: dict) -> list[tuple[str, str]]:
    """행의 비고 → [(체크 이름, 사례 줄)]. X·△ 체크만, 머리 줄('N건 중 …', '… 다름 1:')은 사례가 아니므로 뺀다."""
    notes, checks = row.get("비고") or {}, row.get("체크") or {}
    if not isinstance(notes, dict):
        return []
    out = []
    for name, value in checks.items():
        if value not in ("X", "△") or not notes.get(name):
            continue
        for piece in CASE_SPLIT.split(str(notes[name])):
            piece = CASE_NUMBER.sub("", piece).strip()
            if piece:
                out.append((name, piece))
    return out


def case_phrase(line: str) -> str | None:
    """사례 줄에서 원고에 있을 문구. '원고 「…」'를 우선, 없으면 첫 「…」 — 단 '…에는 「…」가 있는데'(기준 문서 문구)는 제외."""
    m = QUOTED_MANUSCRIPT.search(line)
    if m:
        return m.group(1)
    if re.search(r"에는\s*「", line):
        return None
    m = QUOTED_ANY.search(line)
    return m.group(1) if m else None


class Annotator:
    def __init__(self, source: bytes, *, author: str = AUTHOR, created_at: str | datetime | None = None):
        self.author = author
        self.when = parse_when(created_at)
        self.archive = zipfile.ZipFile(io.BytesIO(source))
        self.sections: list[tuple[str, ET.Element]] = []
        self.paras: list[Para] = []
        for index, name in enumerate(section_names(self.archive)):
            root = ET.fromstring(self.archive.read(name))
            self.sections.append((name, root))
            for i, p in enumerate(root.iter(HP + "p")):
                self.paras.append(Para(index, i, p, para_text(p)))
        self.body_section = max(range(len(self.sections)), key=lambda i: sum(1 for p in self.paras if p.section == i)) if self.sections else 0
        existing = sum(1 for p in self.paras for fb in p.element.iter(HP + "fieldBegin") if fb.get("type") == "MEMO")
        self.next_number = existing + 1
        self.placed: dict[int, Placement] = {}   # 문단(전체 순번) → 행들
        self.unplaced: list[dict] = []
        self.header = ET.fromstring(self.archive.read(HEADER))
        self.memo_char_pr = self._register_memo_char_pr()
        self.memo_para_pr = self._register_memo_para_pr()

    # ───────── 메모 글자 모양 ─────────

    def _font_id(self, fontface: ET.Element) -> str:
        """언어별 글꼴 목록(fontface)에서 메모 글꼴 id. 없으면 끝에 추가. fontCnt 속성이 있으면 같이 올린다."""
        fonts = fontface.findall(HH + "font")
        faces = {f.get("face"): f.get("id") for f in fonts}
        for name in (MEMO_FONT, *MEMO_FONT_FALLBACKS):
            if name in faces:
                return faces[name]
        new_id = str(max((int(f.get("id", "0")) for f in fonts), default=-1) + 1)
        ET.SubElement(fontface, HH + "font", {"id": new_id, "face": MEMO_FONT, "type": "TTF", "isEmbedded": "0"})
        if fontface.get("fontCnt") is not None:
            fontface.set("fontCnt", str(len(fonts) + 1))
        return new_id

    def _register_memo_char_pr(self) -> str:
        """header.xml에 메모용 글자 모양(charPr) 하나를 추가하고 그 id를 돌려준다.

        기본 글자 모양(id 0)을 복사해 글꼴(모든 언어)과 크기만 바꾼다 — 굵게·기울임 같은 꾸밈은 떼어 낸다."""
        props = self.header.find(".//" + HH + "charProperties")
        base = props.find(HH + "charPr") if props is not None else None
        if props is None or base is None:
            return "0"
        font_ids = {face.get("lang", "").lower(): self._font_id(face) for face in self.header.iter(HH + "fontface")}
        char_pr = copy.deepcopy(base)
        new_id = str(max(int(c.get("id", "0")) for c in props.findall(HH + "charPr")) + 1)
        char_pr.set("id", new_id)
        char_pr.set("height", str(MEMO_SIZE_PT * 100))
        for tag in ("bold", "italic", "emboss", "engrave", "supscript", "subscript"):
            for child in char_pr.findall(HH + tag):
                char_pr.remove(child)
        ref = char_pr.find(HH + "fontRef")
        if ref is None:
            ref = ET.SubElement(char_pr, HH + "fontRef")
        for lang in ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user"):
            if lang in font_ids:
                ref.set(lang, font_ids[lang])
            elif ref.get(lang) is None and "hangul" in font_ids:
                ref.set(lang, font_ids["hangul"])
        for tag, value in (("ratio", MEMO_RATIO), ("spacing", MEMO_SPACING)):   # 장평·자간: 언어 모두 같은 값
            node = char_pr.find(HH + tag)
            if node is None:
                node = ET.SubElement(char_pr, HH + tag)
            for lang in ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user"):
                node.set(lang, str(value))
        props.append(char_pr)
        if props.get("itemCnt") is not None:
            props.set("itemCnt", str(len(props.findall(HH + "charPr"))))
        return new_id

    def _register_memo_para_pr(self) -> str:
        """header.xml에 메모용 문단 모양(paraPr) 하나를 추가하고 그 id를 돌려준다.

        기본 문단 모양(id 0)을 복사해 행간만 바꾼다(hp:switch 안의 case·default 양쪽 lineSpacing 모두). 줄 격자(snapToGrid)는 끄지 않으면
        행간이 격자에 맞춰져 160%가 안 먹으므로 끈다 — 에디터 메모 문단과 같다."""
        props = self.header.find(".//" + HH + "paraProperties")
        if props is None:  # 합성 원고(테스트 픽스처)처럼 문단 모양 목록이 없으면 글자 모양 목록 옆에 만든다
            parent = next((el for el in self.header.iter() if el.find(HH + "charProperties") is not None), self.header)
            props = ET.SubElement(parent, HH + "paraProperties", {"itemCnt": "0"})
        base = props.find(HH + "paraPr")
        existing = props.findall(HH + "paraPr")
        para_pr = copy.deepcopy(base) if base is not None else ET.Element(HH + "paraPr", {"id": "0", "tabPrIDRef": "0", "condense": "0", "fontLineHeight": "0", "suppressLineNumbers": "0", "checked": "0"})
        new_id = str(max((int(c.get("id", "0")) for c in existing), default=-1) + 1)
        para_pr.set("id", new_id)
        para_pr.set("snapToGrid", "0")
        spacings = list(para_pr.iter(HH + "lineSpacing"))
        if not spacings:
            spacings = [ET.SubElement(para_pr, HH + "lineSpacing")]
        for node in spacings:
            node.set("type", "PERCENT")
            node.set("value", str(MEMO_LINE_SPACING))
            node.set("unit", "HWPUNIT")
        props.append(para_pr)
        if props.get("itemCnt") is not None:
            props.set("itemCnt", str(len(props.findall(HH + "paraPr"))))
        return new_id

    # ───────── 문단 찾기 ─────────

    def _texts_of(self, value) -> list[str]:
        """'원고' 값에서 문단 찾기에 쓸 문자열 후보(긴 것부터)."""
        out: list[str] = []

        def walk(v, depth=0):
            if isinstance(v, str):
                s = re.sub(r"^\[(재료|기기|안전)\]\s*", "", v).strip()
                if len(_norm(s)) >= 2:
                    out.append(s)
            elif isinstance(v, list) and depth < 2:
                for item in v:
                    walk(item, depth + 1)
            elif isinstance(v, dict) and depth < 1:
                for item in v.values():
                    walk(item, depth + 1)

        walk(value)
        return sorted(dict.fromkeys(out), key=len, reverse=True)

    WINDOW = 120   # 위치 경로로 찾은 머리 뒤에서 원고 문구를 먼저 찾는 범위(문단 수)

    def _find_text(self, candidates: list[str], pool: list[Para] | None = None) -> Para | None:
        """후보 문구와 같은 문단 → 포함하는 문단 → 안에 들어가는 문단. pool이 있으면 그 안에서만."""
        paras = [p for p in (pool if pool is not None else self.paras) if p.has_text]
        for cand in candidates:
            key = _norm(cand)
            if not key:
                continue
            exact = [p for p in paras if p.key == key]
            if exact:
                return self._prefer_body(exact)
            if len(key) >= 6:
                contains = [p for p in paras if key in p.key]
                if contains:
                    return self._prefer_body(contains)
                inside = [p for p in paras if len(p.key) >= 6 and p.key in key]
                if inside:
                    return self._prefer_body(inside)
        return None

    def _prefer_body(self, found: list[Para]) -> Para:
        body = [p for p in found if p.section == self.body_section]
        return (body or found)[0]

    def _find_region(self, region_path: str) -> Para | None:
        segments = [s.strip() for s in (region_path or "").split(">")]
        segments = [s for s in segments if s and not re.match(r"^section\d+$", s) and "None" not in s]
        if not segments:
            return None
        body = [p for p in self.paras if p.section == self.body_section and p.has_text]
        start = 0
        anchor: Para | None = None
        for seg in segments:
            base = re.sub(r"\s*\(.*?\)\s*$", "", seg)           # '내비게이터 (학습마다 반복 5회)' → '내비게이터'
            m_nth = re.match(r"^(.*?)\s*(\d+)\s*번?$", base)      # '수행 내용 2', '1번'
            head_key = _norm(base)
            if re.match(r"^\d+-\d+", base):                      # '1-3. 이용정보 제공' / '1-1' → 그 소제목 문단
                code = re.match(r"^\d+-\d+", base).group(0)
                hit = next((p for p in body[start:] if re.match(rf"^{re.escape(code)}(\.|\s|$)", p.text.strip())), None)
            elif re.match(r"^학습\s*\d+$", base):                 # '학습 1' → 본문의 '학습 1' 머리(내비게이터). '학습 1.' '학습 1 ○○하기'도 받는다
                hit = next((p for p in body[start:] if p.key == head_key), None) \
                    or next((p for p in body[start:] if re.match(rf"^{re.escape(head_key)}(\D|$)", p.key)), None)
            elif m_nth and _norm(m_nth.group(1)) in ("수행내용", "학습내용", "평가", "교수학습방법"):
                n = int(m_nth.group(2))
                hits = [p for p in body[start:] if p.key.startswith(_norm(m_nth.group(1)))]
                hit = hits[n - 1] if len(hits) >= n else (hits[0] if hits else None)
            elif m_nth and anchor is not None:                    # '참고 자료 > 1번' → 앞 머리 뒤의 n번째 글 문단
                n = int(m_nth.group(2))
                after = [p for p in body[start:] if p.has_text]
                hit = after[n] if len(after) > n else None
            else:
                hit = next((p for p in body[start:] if p.key == head_key), None) \
                    or next((p for p in body[start:] if head_key and p.key.startswith(head_key)), None)
            if hit is not None:
                anchor = hit
                start = body.index(hit) + 1
        return anchor

    def _locate(self, candidates: list[str], head: Para | None, *, fallback_to_head: bool = True) -> Para | None:
        """위치 경로의 머리 뒤 범위에서 먼저 찾고(같은 문구가 여러 학습에 반복되므로), 없으면 문서 전체, 그래도 없으면 머리 문단."""
        para = None
        if head is not None:
            at = self.paras.index(head)
            para = self._find_text(candidates, self.paras[at:at + self.WINDOW])
        if para is None:
            para = self._find_text(candidates)
        if para is None and fallback_to_head:
            para = head
        return para if para is not None and para.has_text else None

    def place(self, row: dict) -> None:
        """사례 줄마다 원고 문구가 있는 문단에 하나씩 단다. 문구를 못 찾는 사례와 사례로 쪼개지지 않는 행은 행 단위 자리에 한데 단다."""
        head = self._find_region(row.get("region_path", "")) or self._find_region(str(row.get("위치") or ""))
        leftovers: list[Case] = []
        for name, line in split_cases(row):
            phrase = case_phrase(line)
            para = self._locate([phrase], head, fallback_to_head=False) if phrase else None
            if para is None:
                leftovers.append(Case(row, name, line))
            else:
                self.placed.setdefault(self.paras.index(para), Placement()).cases.append(Case(row, name, line))
        if not leftovers and split_cases(row):
            return
        para = self._locate(self._texts_of(row.get("원고")), head)
        if para is None:
            self.unplaced.append(row)
            return
        placement = self.placed.setdefault(self.paras.index(para), Placement())
        placement.cases.extend(leftovers or [Case(row)])

    # ───────── 메모 글 ─────────

    @staticmethod
    def case_lines(cases: list[Case]) -> list[str]:
        """한 문단에 모인 사례들 → 메모 줄. 사례마다 '[항목] 체크: 판정' + '왜: 사례', 같은 행의 사례들 뒤에 '어떻게: 수정 제안' 한 번.
        행 전체 사례(check None)는 memo_lines 그대로."""
        lines: list[str] = []
        groups: list[tuple[dict, list[Case]]] = []
        for case in cases:
            if groups and groups[-1][0] is case.row:
                groups[-1][1].append(case)
            else:
                groups.append((case.row, [case]))
        # 같은 문단에 같은 글의 사례가 여러 행(예: 학습 1·2·3이 같은 비고)에서 오면 한 번만 적고 어느 위치들인지 모아 적는다.
        seen: dict[tuple[str, str], int] = {}       # (머리, 왜) → lines 안의 '왜' 줄 index
        places: dict[tuple[str, str], list[str]] = {}
        for row, group in groups:
            label = row["item_id"].replace("F02-", "")
            whole = [c for c in group if c.check is None]
            if whole:
                block = Annotator.memo_lines(row)
                if block not in [lines[i:i + len(block)] for i in range(len(lines))]:
                    lines.extend(block)
                continue
            added = False
            for case in group:
                value = (row.get("체크") or {}).get(case.check, row["판정"])
                head = f"[{label}] {case.check}: {'판단불가' if value == '△' else '부적합'}"
                why = f"왜: {case.line}"[:MAX_LINE]
                key = (head, why)
                where = str(row.get("위치") or "")
                if key in seen:
                    if where and where not in places[key]:
                        places[key].append(where)
                    continue
                lines.append(head)
                lines.append(why)
                seen[key] = len(lines) - 1
                places[key] = [where] if where else []
                added = True
            suggestion = f"어떻게: {row['수정 제안']}"[:MAX_LINE] if row.get("수정 제안") else None
            if added and suggestion and suggestion not in lines:
                lines.append(suggestion)
        for key, where in places.items():
            if len(where) > 1:  # 여러 위치에서 온 같은 사례: '왜: … (학습 1·2·3)'
                lines[seen[key]] = (lines[seen[key]] + f" ({'·'.join(where)})")[:MAX_LINE]
        return lines

    @staticmethod
    def memo_lines(row: dict) -> list[str]:
        label = row["item_id"].replace("F02-", "")
        lines = [f"[{label}] {row['판정']}"]
        notes = row.get("비고") or {}
        checks = row.get("체크") or {}
        if isinstance(notes, dict):
            for name, value in checks.items():
                if value in ("X", "△") and notes.get(name):
                    lines.append(f"• {name}: {notes[name]}"[:MAX_LINE])
            for name, note in notes.items():
                if name not in checks and note:
                    lines.append(f"• {name}: {note}"[:MAX_LINE])
        elif notes:
            lines.append(f"• {notes}"[:MAX_LINE])
        if row.get("수정 제안"):
            lines.append(f"→ 수정 제안: {row['수정 제안']}"[:MAX_LINE])
        return lines

    def summary_lines(self, rows: list[dict]) -> list[str]:
        fail = sum(1 for r in rows if r["판정"] == "부적합")
        undecided = sum(1 for r in rows if r["판정"] == "판단불가")
        lines = [f"[F02 자동검수 총괄] 부적합 {fail}건 · 판단불가 {undecided}건 — 본문의 메모({len(self.placed)}곳)를 따라가며 확인하세요."
                 " 판단불가는 사람이 확정하는 항목입니다."]
        if self.unplaced:
            lines.append(f"문단을 특정하지 못한 지적 {len(self.unplaced)}건(검수 화면·확인서에서 확인):")
            for r in self.unplaced[:MAX_UNPLACED_LISTED]:
                first = self.memo_lines(r)
                lines.append(f"  {first[0]} @ {r.get('region_path', '')}" + (f" — {first[1][2:]}" if len(first) > 1 else ""))
            if len(self.unplaced) > MAX_UNPLACED_LISTED:
                lines.append(f"  … 외 {len(self.unplaced) - MAX_UNPLACED_LISTED}건")
        return [line[:MAX_LINE * 2] for line in lines]

    # ───────── XML 삽입 ─────────

    def _attach(self, para: Para, lines: list[str]) -> None:
        p = para.element
        runs = p.findall(HP + "run")
        if not runs:
            runs = [ET.SubElement(p, HP + "run", {"charPrIDRef": "0"})]
        first, last = runs[0], runs[-1]
        number = self.next_number
        self.next_number += 1
        begin_id = str(random.randint(10**9, 2**31 - 1))
        field_id = str(random.randint(10**8, 2**31 - 1))
        ctrl = ET.Element(HP + "ctrl")
        begin = ET.SubElement(ctrl, HP + "fieldBegin", {"id": begin_id, "type": "MEMO", "name": "", "editable": "1", "dirty": "0",
                                                        "zorder": str(number), "fieldid": field_id, "metaTag": ""})
        params = ET.SubElement(begin, HP + "parameters", {"cnt": "7", "name": ""})
        ET.SubElement(params, HP + "integerParam", {"name": "Prop"}).text = "0"
        low, high = filetime_words(self.when)
        ET.SubElement(params, HP + "stringParam", {"name": "Command"}).text = f"MEMO/65535/{number}/{low}/{high}/{self.author}/\\;;"
        ET.SubElement(params, HP + "stringParam", {"name": "ID"}).text = f"memo{number}"
        ET.SubElement(params, HP + "integerParam", {"name": "Number"}).text = str(number)
        ET.SubElement(params, HP + "stringParam", {"name": "Author"}).text = self.author
        ET.SubElement(params, HP + "stringParam", {"name": "MemoShapeIDRef"}).text = "65535"
        ET.SubElement(params, HP + "stringParam", {"name": "CreateDateTime"}).text = self.when.astimezone(KST).strftime("%Y-%m-%dT%H:%M:%SZ")
        sub = ET.SubElement(begin, HP + "subList", {"id": "", "textDirection": "HORIZONTAL", "lineWrap": "BREAK", "vertAlign": "TOP",
                                                    "linkListIDRef": "0", "linkListNextIDRef": "0", "textWidth": "0", "textHeight": "0",
                                                    "hasTextRef": "0", "hasNumRef": "0"})
        for line in lines[:MAX_MEMO_LINES] + ([f"… 외 {len(lines) - MAX_MEMO_LINES}줄"] if len(lines) > MAX_MEMO_LINES else []):
            mp = ET.SubElement(sub, HP + "p", {"id": "0", "paraPrIDRef": self.memo_para_pr, "styleIDRef": "0", "pageBreak": "0", "columnBreak": "0", "merged": "0"})
            run = ET.SubElement(mp, HP + "run", {"charPrIDRef": self.memo_char_pr})
            ET.SubElement(run, HP + "t").text = line
        first.insert(0, ctrl)
        end = ET.Element(HP + "ctrl")
        ET.SubElement(end, HP + "fieldEnd", {"beginIDRef": begin_id, "fieldid": field_id})
        last.append(end)

    def build(self, rows: list[dict]) -> bytes:
        rows = [r for r in rows if r.get("판정") and r["판정"] != PASS]
        for row in rows:
            self.place(row)
        for order, placement in sorted(self.placed.items()):
            self._attach(self.paras[order], self.case_lines(placement.cases))
        # 총괄 메모: 본문 섹션의 첫 글 문단(또는 문서 첫 글 문단)
        top = next((p for p in self.paras if p.section == self.body_section and p.has_text), None) or next((p for p in self.paras if p.has_text), None)
        if top is not None:
            self._attach(top, self.summary_lines(rows))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as target:
            section_xml = {name: ET.tostring(root, encoding="utf-8", xml_declaration=True) for name, root in self.sections}
            section_xml[HEADER] = ET.tostring(self.header, encoding="utf-8", xml_declaration=True)
            for item in self.archive.infolist():
                data = section_xml.get(item.filename) or self.archive.read(item.filename)
                compress = zipfile.ZIP_STORED if item.filename == "mimetype" else zipfile.ZIP_DEFLATED
                target.writestr(item, data, compress_type=compress)
        return out.getvalue()


def annotate_hwpx(source: bytes, rows: list[dict], *, author: str = AUTHOR, created_at: str | datetime | None = None) -> tuple[bytes, dict]:
    """메모를 단 hwpx 바이트와 요약 {'placed', 'memos', 'unplaced'}. created_at = 검사 실행 시각(메모 날짜로 쓴다)."""
    worker = Annotator(source, author=author, created_at=created_at)
    content = worker.build(rows)
    return content, {"placed": sum(len(p.rows) for p in worker.placed.values()), "memos": len(worker.placed) + 1,
                     "unplaced": len(worker.unplaced)}

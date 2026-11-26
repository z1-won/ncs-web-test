"""권리 증빙 대조와 판정 — 원고의 그림(ncs_core.figures)과 제출 서류(forms)를 맞춰 모듈별 증빙 제출 현황표와 누락 목록을 만든다.

판정은 원고 검수와 같은 말을 쓴다:
  부적합    서류로 확인되는 누락·불일치 — 목록에 없는 그림, 필요한 증빙 없음, 표기와 목록이 다름, 기한 경과
  판단불가  사람이 봐야 하는 것 — 번호·제목이 조금 다름, 인물 포함 여부, F08 예 2처럼 기준이 갈리는 표기
  적합      위 둘이 없음
제작 방식별로 필요한 증빙(원고 집필 계약서 제4·5·7조, 사진·삽화 제작 계약서 제4·6조, AI 활용 기준 2026.9):
  집필자 직접제작      양도 동의서(F07 붙임 4) — 집필자 단위 서류라 그림별로 대조하지 않고 제출 여부만 본다
  외부 제작의뢰        제작 목록(F06 붙임 1)에 그 그림이 있고, 양도 동의서(F06 붙임 3) 제출
  포괄적 이용허락      이용허락 동의서(F07 붙임 3)의 저작물 표에 그 그림이 있음
  공공누리·공유마당    따로 낼 증빙은 없고 원고 본문에 출처(URL·검색 일자·사용 요건)를 적어야 함
  기개발 학습모듈      따로 낼 증빙은 없고 원고 본문에 기존 학습모듈을 출처로 적어야 함
  사진(직접·의뢰)      인물이 있으면 초상권 동의서(F06 붙임 2) — 인물 포함 여부는 그림을 봐야 알므로 사람 확인
  AI 활용              원고의 AI 활용 줄 + 서약서(F09)와 그 붙임 결과물 현황에 그 그림이 있음
쪽수: 출력본 PDF를 함께 받으면 그림 캡션이 놓인 쪽(pages.figure_pages)과 결과물 현황의 쪽수를 견준다. 다르면 판단불가
(출력본의 줄 읽기는 어림이라 부적합으로 올리지 않는다).
받는 곳: 지적마다 누가 움직여야 하는지를 붙인다 — 서류를 내거나 원고·목록을 고쳐야 하는 것은 개발기관,
같은 것인지 사람이 가려야 하는 것은 에디팅 기관. 결과의 '알림'이 받는 곳별 목록과 보낼 글이다.
캡션 없는 그림: 캡션([그림 N-M])이 없는 그림은 번호·제목이 없어 목록·증빙과 맞출 수 없다. 빼지 않고 현황표에 '대조 불가' 줄(판단불가)로
싣는다 — 본문 그림인데 캡션을 빠뜨린 것인지, 장식·양식 그림인지는 사람이 가린다(에디팅 기관). 찾는 일은 service.uncaptioned_pictures.
기한: 수록 현황 목록은 1차 검토 이후 4주 이내 제출(원고 집필 계약서 제5조 1항). 기한 항목은 언제나 결과에 넣는다
(검증 기준 '기한 경과 항목 알림 누락 0건').
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from ncs_core.figures import Figure

from .forms import METHOD_NAMES, Forms, squash, title_key
from .pages import page_numbers

PASS, FAIL, UNDECIDED = "적합", "부적합", "판단불가"
SUBMITTED, MISSING, TO_CHECK = "제출", "누락", "확인 필요"
DEADLINE_DAYS = 28
PRIMARY = ("author_made", "commissioned", "public_license", "blanket_license", "prior_module")
PUBLIC_SOURCE = re.compile(r"공공누리|공유마당|kogl|gongu", re.I)
PRIOR_SOURCE = re.compile(r"LM\d{8,10}|학습모듈|한국직업능력(연구|개발)원")
AI_MODE_NAMES = {"generated": "생성함", "modified": "수정 보완함"}
DEVELOPER, EDITOR = "개발기관", "에디팅 기관"
RECIPIENTS = (DEVELOPER, EDITOR)
# 에디팅 기관이 가려야 하는 지적 — 두 서류가 가리키는 것이 같은지, 그림에 무엇이 있는지처럼 사람이 봐야 정해지는 것.
# 여기 없는 종류(누락·미표시·미기재)는 서류를 내거나 고쳐야 하므로 개발기관이 받는다
EDITOR_KINDS = frozenset({"제목 다름", "번호 다름", "유형 다름", "출처 확인", "초상권 확인", "활용 AI 다름", "AI 표시 확인",
                          "현황에만 있음", "그림 없음", "쪽수 다름", "쪽 확인", "캡션 없음"})


@dataclass
class Options:
    """화면에서 받는 것 — 표로 읽을 수 없는 서류의 제출 여부와 기한 계산에 쓰는 날짜."""
    first_review_on: date | None = None      # 1차 검토일
    submitted_on: date | None = None         # 수록 현황 목록 제출일(없으면 미제출로 본다)
    today: date | None = None                # 점검일(기본 오늘)
    transfer_author: bool = False            # 집필자 양도 동의서(F07 붙임 4) 제출됨
    transfer_maker: bool = False             # 제작자 양도 동의서(F06 붙임 3) 제출됨
    portrait: str = "unknown"                # 초상권: 'unknown' 확인 안 함 / 'none' 인물 없음 확인 / 'submitted' 동의서 제출
    pledge: bool = False                     # 생성형 AI 결과물 집필자 서약서 제출됨


def _key(label: str) -> str:
    return squash(label)


def _issue(level: str, kind: str, text: str, action: str = "", to: str | None = None) -> dict:
    return {"수준": level, "종류": kind, "내용": text, "조치": action,
            "받는 곳": to or (EDITOR if kind in EDITOR_KINDS else DEVELOPER)}


def _folios(places: list[dict]) -> str:
    """출력본에서 찾은 쪽들 → '4쪽', '4·5쪽', 쪽 번호가 없는 쪽은 'PDF 7번째 쪽'."""
    names = [f"{place['쪽']}쪽" + ("(추정)" if place["추정"] else "") if place["쪽"] else f"PDF {place['물리 쪽']}번째 쪽"
             for place in places]
    return "·".join(names)


def _pick_inclusion(forms: Forms, figures: list[Figure]) -> tuple[dict | None, str]:
    """수록 현황 목록이 여럿이면(모듈별 목록) 이 원고의 그림과 가장 많이 겹치는 것을 고른다."""
    if not forms.inclusion:
        return None, ""
    if len(forms.inclusion) == 1:
        return forms.inclusion[0], ""
    labels = {_key(f.label) for f in figures}
    titles = {title_key(f.title) for f in figures if f.title}

    def overlap(table: dict) -> int:
        return sum((_key(r["label"]) in labels) + (title_key(r["title"]) in titles) for r in table["rows"])

    best = max(forms.inclusion, key=overlap)
    name = best["module"] or best["file"]
    return best, f"수록 현황 목록 {len(forms.inclusion)}개 중 이 원고와 가장 많이 겹치는 목록(‘{name}’)으로 대조했습니다"


class _Known:
    """원고에 있는 그림의 번호와 (번호, 제목) — 서류의 행이 '다른 그림의 것'인지 가린다.

    실제 원고에는 같은 제목의 그림이 다른 번호로 또 나오거나(그림 1-10·1-13 '객실 전화 예약 흐름도'), 같은 번호가 두 번 쓰인 경우가 있다.
    번호나 제목 하나만 같다고 남의 행을 가져오면 빠진 증빙이 '제출'로 보이므로, 다른 그림과 꼭 맞는 행은 그 그림에 남겨 둔다.
    """

    def __init__(self, figures: list[Figure]):
        self.labels = {_key(f.label) for f in figures if f.minor is not None}
        self.pairs = Counter((_key(f.label), title_key(f.title)) for f in figures if f.minor is not None)

    def other_label(self, row: dict, own: tuple[str, str]) -> bool:
        """행에 적힌 번호가 원고의 다른 그림 번호인가."""
        label = _key(row.get("label") or "")
        return bool(label) and label != own[0] and label in self.labels

    def other_pair(self, row: dict, own: tuple[str, str]) -> bool:
        """행의 번호·제목이 원고의 다른 그림과 꼭 맞는가(번호는 같고 제목이 다른 그림)."""
        pair = (_key(row.get("label") or ""), title_key(row.get("title", "")))
        return pair != own and self.pairs[pair] > 0


def _pair_up(figures: list[Figure], rows: list[dict], known: _Known) -> list[tuple[int | None, str]]:
    """원고 그림마다 짝이 되는 목록 행 → [(행 순번, 'same' | 'title' 제목이 다름 | 'label' 번호가 다름 | '')].

    꼭 맞는 것부터 세 번에 나눠 짝짓는다: 번호·제목이 모두 같은 행 → 번호가 같은 행 → 제목이 같은 행.
    한 번에 앞에서부터 짝지으면 앞 그림이 뒤 그림의 행을 먼저 가져가 누락이 엉뚱한 그림에 붙는다.
    """
    matched: list[tuple[int | None, str]] = [(None, "")] * len(figures)
    used: set[int] = set()
    keys = [(_key(f.label), title_key(f.title)) for f in figures]

    def assign(want, how) -> None:
        for n, figure in enumerate(figures):
            if matched[n][0] is not None:
                continue
            for i, row in enumerate(rows):
                if i not in used and want(figure, keys[n], row):
                    matched[n] = (i, how(figure, keys[n], row))
                    used.add(i)
                    break

    def same_label(figure, own, row) -> bool:
        return figure.minor is not None and _key(row["label"]) == own[0]

    assign(lambda figure, own, row: same_label(figure, own, row) and bool(own[1]) and title_key(row["title"]) == own[1],
           lambda figure, own, row: "same")
    assign(lambda figure, own, row: same_label(figure, own, row) and not known.other_pair(row, own),
           lambda figure, own, row: "same" if not own[1] or not title_key(row["title"]) else "title")
    assign(lambda figure, own, row: bool(own[1]) and title_key(row["title"]) == own[1] and not known.other_label(row, own),
           lambda figure, own, row: "same" if not row["label"] or figure.minor is None else "label")
    return matched


def _find_row(rows: list[dict], label: str, title: str, known: _Known | None = None) -> dict | None:
    """제작 목록·동의서·AI 현황에서 그 그림을 가리키는 행 — 번호·제목이 모두 같은 행, 번호가 같은 행, 제목이 같은 행 순서로.

    known을 주면 원고의 다른 그림과 꼭 맞는 행·다른 그림의 번호가 붙은 행은 건너뛴다(_Known).
    """
    own = (_key(label), title_key(title))
    complete = bool(label) and not label.endswith("-")

    def labelled(row: dict) -> bool:
        return complete and bool(row.get("label")) and _key(row["label"]) == own[0]

    def titled(row: dict) -> bool:
        return bool(own[1]) and title_key(row.get("title", "")) == own[1]

    for row in rows:
        if labelled(row) and titled(row):
            return row
    for row in rows:
        if labelled(row) and not (known and known.other_pair(row, own)):
            return row
    for row in rows:
        if titled(row) and not (known and known.other_label(row, own)):
            return row
    return None


def _same_tool(a: str, b: str) -> bool:
    """'ChatGPT' ↔ 'ChatGPT 6.0' — 버전·띄어쓰기는 무시하고 이름이 겹치면 같은 도구로 본다."""
    a, b = (re.sub(r"[\d.\s]+$", "", squash(x)).lower() for x in (a, b))
    return bool(a) and bool(b) and (a in b or b in a)


def _ai_text(figure: Figure | None) -> str:
    if figure is None or figure.ai is None:
        return ""
    mark = figure.ai
    return f"{mark.tool} · {AI_MODE_NAMES[mark.mode]}" + (f" · {mark.on.isoformat()}" if mark.on else "")


def _figure_row(figure: Figure | None, listed: dict | None, how: str, forms: Forms, options: Options,
                has_list: bool, pages: dict[str, list[dict]] | None = None, known: _Known | None = None) -> dict:
    """그림 한 개(원고의 그림, 목록의 행, 또는 둘 다)의 현황표 한 줄."""
    issues: list[dict] = []
    evidence: list[dict] = []
    label = figure.label if figure else listed["label"]
    title = figure.title if figure else listed["title"]
    methods = listed["methods"] if listed else []
    subs = listed["subs"] if listed else {}
    primary = [m for m in methods if m in PRIMARY]

    def need(name: str, state: str, where: str = ""):
        evidence.append({"증빙": name, "상태": state, "근거": where})

    # ── 목록 등재 ──
    if figure and not listed and has_list:
        issues.append(_issue(FAIL, "목록 누락", "원고에 있는 그림이 수록 현황 목록에 없습니다", "수록 현황 목록에 추가하고 제작 방식을 표시"))
    if listed and not figure:
        issues.append(_issue(FAIL, "원고에 없음", f"수록 현황 목록의 ‘{listed['raw']}’이(가) 원고에 없습니다", "원고에서 빠졌으면 목록에서 삭제, 번호·제목이 바뀌었으면 목록을 맞춤"))
    if how == "title":
        issues.append(_issue(UNDECIDED, "제목 다름", f"번호는 같고 제목이 다릅니다 — 원고 「{figure.title}」, 목록 「{listed['title']}」", "같은 그림인지 확인하고 한쪽에 맞춤"))
    if how == "label":
        issues.append(_issue(UNDECIDED, "번호 다름", f"제목은 같고 번호가 다릅니다 — 원고 {figure.label}, 목록 {listed['label'] or '번호 없음'}", "그림 번호를 원고에 맞춤"))
    if figure and figure.minor is None:
        issues.append(_issue(UNDECIDED, "번호 미완성", f"원고의 그림 번호가 비어 있습니다([{figure.label}])", "그림 번호를 채움"))

    # ── 제작 방식 ──
    if listed and not primary:
        issues.append(_issue(FAIL, "제작 방식 미표시", "수록 현황 목록에 저작물 제작 방식이 표시되지 않았습니다", "해당 방식에 ✓ 표시"))
    if len(primary) > 1:
        issues.append(_issue(UNDECIDED, "제작 방식 중복", "제작 방식이 둘 이상 표시되었습니다: " + ", ".join(METHOD_NAMES[m] for m in primary), "하나로 정함"))

    # ── 제작 방식별 증빙 ──
    if "author_made" in primary:
        state = SUBMITTED if options.transfer_author else MISSING
        need("양도 동의서(집필자)", state)
        if state == MISSING:
            issues.append(_issue(FAIL, "증빙 누락", "집필자 직접제작인데 지식재산권 양도 동의서가 제출되지 않았습니다", "원고 집필 계약서 붙임 4 제출"))
    if "commissioned" in primary:
        made = _find_row(forms.production, label, title, known)
        if not forms.production:
            need("제작 목록", MISSING)
            issues.append(_issue(FAIL, "증빙 누락", "외부 제작의뢰인데 사진·삽화 제작 목록이 제출되지 않았습니다", "사진·삽화 제작 계약서 붙임 1 제출"))
        elif made is None:
            need("제작 목록", MISSING)
            issues.append(_issue(FAIL, "증빙 누락", "외부 제작의뢰인데 사진·삽화 제작 목록에 이 그림이 없습니다", "제작 목록에 추가하거나 제작 방식을 고침"))
        else:
            need("제작 목록", SUBMITTED, made["file"])
            kind = subs.get("commissioned", "")
            if kind and made["type"] and kind != made["type"]:
                issues.append(_issue(UNDECIDED, "유형 다름", f"수록 현황 목록은 {kind}, 제작 목록은 {made['type']}(으)로 표시되어 있습니다", "사진·삽화 구분을 맞춤"))
        state = SUBMITTED if options.transfer_maker else MISSING
        need("양도 동의서(제작자)", state)
        if state == MISSING:
            issues.append(_issue(FAIL, "증빙 누락", "외부 제작의뢰인데 제작자의 지식재산권 양도 동의서가 제출되지 않았습니다", "사진·삽화 제작 계약서 붙임 3 제출"))
    if "blanket_license" in primary:
        consent = _find_row(forms.license, label, title, known)
        if consent is None:
            need("이용허락 동의서", MISSING)
            text = "지식재산권 이용허락 동의서에 이 저작물이 없습니다" if forms.license else "지식재산권 이용허락 동의서가 제출되지 않았습니다"
            issues.append(_issue(FAIL, "증빙 누락", "포괄적 이용허락인데 " + text, "원고 집필 계약서 붙임 3 제출(저작물 제목·출처 기재)"))
        else:
            need("이용허락 동의서", SUBMITTED, consent["file"])
    source = figure.source_line if figure else ""
    if "public_license" in primary and figure:
        if not source:
            issues.append(_issue(FAIL, "출처 미표기", "공공누리·공유마당 자료인데 원고에 출처 줄이 없습니다", "출처(URL, 검색 일자, 사용 요건)를 본문에 명시"))
        elif not PUBLIC_SOURCE.search(source):
            issues.append(_issue(UNDECIDED, "출처 확인", f"출처 줄에 공공누리·공유마당 표시가 보이지 않습니다 — 「{source}」", "출처와 사용 요건을 확인"))
    if "prior_module" in primary and figure:
        if not source:
            issues.append(_issue(FAIL, "출처 미표기", "기개발 학습모듈 자료인데 원고에 출처 줄이 없습니다", "기존 학습모듈명을 출처로 제시"))
        elif not PRIOR_SOURCE.search(source):
            issues.append(_issue(UNDECIDED, "출처 확인", f"출처 줄이 기존 학습모듈을 가리키는지 확인이 필요합니다 — 「{source}」", "교육부(연도). 학습모듈명(LM코드). 한국직업능력연구원. p.00. 꼴로 표기"))

    # ── 초상권: 사진으로 표시된 직접제작·외부 제작의뢰 ──
    if any(subs.get(m) == "사진" for m in ("author_made", "commissioned")):
        if options.portrait == "submitted":
            need("초상권 동의서", SUBMITTED)
        elif options.portrait == "none":
            need("초상권 동의서", "해당 없음", "인물 없음 확인")
        else:
            need("초상권 동의서", TO_CHECK)
            issues.append(_issue(UNDECIDED, "초상권 확인", "사진입니다. 인물이 포함되어 있으면 초상권 사용 동의서가 필요합니다", "인물 포함 여부를 확인하고, 있으면 사진·삽화 제작 계약서 붙임 2 제출"))

    # ── AI 활용: 원고 표기 ↔ 목록 ↔ 서약서 결과물 현황 ──
    marked, listed_ai = bool(figure and figure.ai), "ai" in methods
    places = (pages or {}).get(figure.label, []) if figure else []
    page_match = ""
    result = _find_row(forms.ai_results, label, title, known)
    if marked and listed and not listed_ai:
        issues.append(_issue(FAIL, "AI 표시 불일치", f"원고에는 AI 활용 표기가 있는데(「{figure.ai.text}」) 수록 현황 목록의 AI 활용 칸에 표시가 없습니다", "목록의 AI 활용 칸에 ✓ 표시"))
    if listed_ai and figure and not marked:
        issues.append(_issue(FAIL, "AI 표기 누락", "수록 현황 목록에는 AI 활용으로 표시되었는데 원고에 AI 활용 줄이 없습니다", "출처 줄 아래에 ‘○○를 활용하여 생성함/수정 보완함. 일자’ 표기"))
    if marked or listed_ai:
        if not options.pledge:
            need("AI 서약서", MISSING)
            issues.append(_issue(FAIL, "증빙 누락", "AI를 활용한 그림인데 생성형 AI 결과물 집필자 서약서가 제출되지 않았습니다", "서약서와 결과물 현황 제출"))
        elif result is None:
            need("AI 서약서", MISSING)
            issues.append(_issue(FAIL, "현황 누락", "AI를 활용한 그림인데 서약서의 생성형 AI 결과물 현황에 없습니다", "결과물 현황에 결과물 명·쪽수·활용 AI 기재"))
        else:
            need("AI 서약서", SUBMITTED, result["file"])
            if marked and result["tool"] and not _same_tool(figure.ai.tool, result["tool"]):
                issues.append(_issue(UNDECIDED, "활용 AI 다름", f"원고 표기는 「{figure.ai.tool}」, 결과물 현황은 「{result['tool']}」입니다", "같은 도구인지 확인하고 맞춤"))
            if not result["page"].strip():
                issues.append(_issue(UNDECIDED, "쪽수 미기재", "결과물 현황에 학습모듈 해당 쪽수가 비어 있습니다", "쪽수 기재"))
            elif pages is not None and figure:
                wanted = page_numbers(result["page"])
                if not wanted:
                    issues.append(_issue(UNDECIDED, "쪽 확인", f"결과물 현황의 쪽수(「{result['page']}」)에서 쪽 번호를 읽지 못했습니다", "쪽수를 ‘p.12’ 꼴로 기재했는지 확인"))
                elif not places:
                    issues.append(_issue(UNDECIDED, "쪽 확인", "출력본에서 이 그림의 캡션을 찾지 못해 결과물 현황의 쪽수를 대조하지 못했습니다", "출력본이 이 원고의 것인지, 그림 번호가 같은지 확인"))
                elif not any(place["쪽"] for place in places):
                    issues.append(_issue(UNDECIDED, "쪽 확인", f"출력본에서 이 그림이 놓인 쪽({_folios(places)})의 쪽 번호를 읽지 못했습니다", "출력본에서 쪽수를 직접 확인"))
                elif not {str(number) for number in wanted} & {place["쪽"] for place in places}:
                    issues.append(_issue(UNDECIDED, "쪽수 다름", f"결과물 현황의 쪽수는 「{result['page']}」인데 출력본에서는 이 그림이 {_folios(places)}에 있습니다", "결과물 현황의 쪽수를 출력본에 맞춤"))
                else:
                    page_match = "일치"
    elif result is not None:
        issues.append(_issue(UNDECIDED, "AI 표시 확인", f"결과물 현황에는 있는데(「{result['name']}」) 원고 표기와 수록 현황 목록에는 AI 활용 표시가 없습니다", "AI를 쓴 그림이면 원고 표기와 목록을 맞춤"))
    if marked and figure.ai.on is None:
        issues.append(_issue(UNDECIDED, "AI 표기 일자", f"AI 활용 줄에 일자가 없거나 읽히지 않습니다 — 「{figure.ai.text}」", "‘2026. 7. 20.’ 꼴로 일자 표기"))

    levels = {issue["수준"] for issue in issues}
    return {
        "그림 번호": label, "그림명": title, "원고": bool(figure), "목록": bool(listed) if has_list else None,
        "제작 방식": [METHOD_NAMES[m] + (f"({subs[m]})" if subs.get(m) in ("사진", "삽화") else "") for m in methods],
        "방식 코드": methods, "유형": {m: subs[m] for m in subs},
        "출처 줄": source, "AI 표기": _ai_text(figure), "AI 방식": figure.ai.mode if marked else None,
        "AI 도구": figure.ai.tool if marked else None, "AI 일자": figure.ai.on.isoformat() if marked and figure.ai.on else None,
        "결과물 현황": f"{result['name']} · {result['page'] or '쪽수 없음'} · {result['tool'] or '도구 없음'}" if result else "",
        "쪽": _folios(places), "쪽 번호": [place["쪽"] for place in places if place["쪽"]], "쪽수 대조": page_match,
        "증빙": evidence, "지적": issues, "비고": [issue["내용"] for issue in issues],
        "판정": FAIL if FAIL in levels else UNDECIDED if UNDECIDED in levels else PASS,
        "문단": [figure.section, figure.para] if figure else None,
    }


def _uncaptioned_row(picture: dict) -> dict:
    """캡션 없는 그림 한 개의 현황표 한 줄 — 목록·증빙과 맞출 번호·제목이 없어 대조하지 않고 판단불가로 둔다."""
    width, height = picture["mm"]
    size = f"({width}×{height}mm)" if width and height else ""
    near = f" 앞 문단 「{picture['앞 글']}」." if picture.get("앞 글") else ""
    issue = _issue(UNDECIDED, "캡션 없음",
                   f"문단 {picture['para']}의 그림{size}에 캡션([그림 N-M])이 없어 수록 현황 목록·증빙과 대조하지 못했습니다.{near}",
                   "본문 그림이면 캡션을 달고 수록 현황 목록에 올림. 장식·양식 그림이면 그대로 둠")
    return {
        "그림 번호": "", "그림명": f"캡션 없는 그림 — 문단 {picture['para']}{size}", "원고": True, "목록": None, "캡션 없음": True,
        "제작 방식": [], "방식 코드": [], "유형": {}, "출처 줄": "", "AI 표기": "", "AI 방식": None, "AI 도구": None, "AI 일자": None,
        "결과물 현황": "", "쪽": "", "쪽 번호": [], "쪽수 대조": "", "증빙": [], "지적": [issue], "비고": [issue["내용"]],
        "판정": UNDECIDED, "문단": None, "그림 자리": [picture["section"], picture["para"]],
    }


def _deadline(options: Options, has_list: bool) -> dict:
    today = options.today or date.today()
    out = {"1차 검토일": options.first_review_on.isoformat() if options.first_review_on else None,
           "제출일": options.submitted_on.isoformat() if options.submitted_on else None, "점검일": today.isoformat(),
           "기한": None, "판정": UNDECIDED, "내용": ""}
    if options.first_review_on is None:
        out["내용"] = "1차 검토일을 입력하지 않아 제출 기한(1차 검토 이후 4주)을 계산하지 못했습니다"
        return out
    due = options.first_review_on + timedelta(days=DEADLINE_DAYS)
    out["기한"] = due.isoformat()
    if options.submitted_on is not None:
        late = (options.submitted_on - due).days
        if options.submitted_on < options.first_review_on:
            out["내용"] = f"제출일({options.submitted_on})이 1차 검토일({options.first_review_on})보다 앞섭니다. 날짜를 확인하세요"
        elif late > 0:
            out.update(판정=FAIL, 내용=f"수록 현황 목록을 기한({due})보다 {late}일 늦게 제출했습니다")
        else:
            out.update(판정=PASS, 내용=f"수록 현황 목록을 기한({due}) 안에 제출했습니다")
    elif has_list:
        out["내용"] = f"수록 현황 목록은 올라와 있지만 제출일을 입력하지 않아 기한({due}) 준수 여부를 확인하지 못했습니다"
    else:
        left = (due - today).days
        if left < 0:
            out.update(판정=FAIL, 내용=f"수록 현황 목록이 제출되지 않았고 기한({due})이 {-left}일 지났습니다")
        else:
            out["내용"] = f"수록 현황 목록이 아직 제출되지 않았습니다. 기한은 {due}(남은 날 {left}일)입니다"
    return out


def _notices(findings: list[dict], module: str) -> list[dict]:
    """받는 곳별 알림 — 그곳이 움직여야 할 지적 목록과 그대로 보낼 수 있는 글.

    누락을 고치는 곳은 개발기관이지만 에디팅 기관도 알아야 하므로(REQ-02-014 '개발기관·에디팅 기관에 알림'),
    에디팅 기관의 글에는 개발기관에 요청한 건수를 함께 적는다.
    """
    by_recipient = {name: [finding for finding in findings if finding["받는 곳"] == name] for name in RECIPIENTS}
    requested = len(by_recipient[DEVELOPER])
    notices = []
    for name in RECIPIENTS:
        items = by_recipient[name]
        head = f"[권리 증빙 제출 현황 점검] {module or '학습모듈'} — {name}"
        if name == DEVELOPER:
            lead = f"보완할 것이 {len(items)}건 있습니다." if items else "보완할 것이 없습니다."
        else:
            lead = (f"확인할 것이 {len(items)}건 있습니다." if items else "확인할 것이 없습니다.") + f" 개발기관에 보완을 요청한 것은 {requested}건입니다."
        lines = [f"{index}. {item['그림']} — {item['내용']}" + (f" → {item['조치']}" if item["조치"] else "")
                 for index, item in enumerate(items, 1)]
        notices.append({"받는 곳": name, "건수": len(items), "부적합": sum(item["수준"] == FAIL for item in items),
                        "판단불가": sum(item["수준"] == UNDECIDED for item in items), "지적사항": items,
                        "글": "\n".join([head, lead, *lines])})
    return notices


def check(figures: list[Figure], forms: Forms, options: Options | None = None,
          pages: dict[str, list[dict]] | None = None, uncaptioned: list[dict] | None = None) -> dict:
    """현황표와 누락 목록. 반환: {'요약', '기한', '서류', '현황표', '지적사항', '알림', '안내'}.

    pages: 출력본 PDF에서 읽은 그림별 쪽(pages.figure_pages). 주면 결과물 현황의 쪽수를 대조하고 현황표에 쪽을 싣는다.
    uncaptioned: 캡션 없는 그림(service.uncaptioned_pictures). 주면 현황표 끝에 '대조 불가' 줄로 싣는다.
    """
    options = options or Options()
    inclusion, note = _pick_inclusion(forms, figures)
    notes = [note] if note else []
    listed_rows = inclusion["rows"] if inclusion else []
    has_list = inclusion is not None

    known = _Known(figures)
    pairs = _pair_up(figures, listed_rows, known)
    used = {index for index, _ in pairs if index is not None}
    rows = [_figure_row(figure, listed_rows[index] if index is not None else None, how, forms, options, has_list, pages, known)
            for figure, (index, how) in zip(figures, pairs)]
    for index, listed in enumerate(listed_rows):
        if index not in used:
            rows.append(_figure_row(None, listed, "", forms, options, has_list, None, known))

    if not has_list:
        # 목록이 없으면 제작 방식을 몰라 필요한 증빙을 따질 수 없다 — 문제가 안 보인다고 적합으로 두지 않는다.
        # 지적사항에는 '목록 미제출' 한 건으로만 말하고, 그림 줄에는 비고로만 적는다(그림 수만큼 같은 말을 되풀이하지 않게)
        for row in rows:
            row["비고"].append("수록 현황 목록이 없어 제작 방식과 필요한 증빙을 대조하지 못했습니다")
            if row["판정"] == PASS:
                row["판정"] = UNDECIDED

    # 캡션 없는 그림은 제작 방식을 따질 대상이 아니므로 위의 목록 미제출 비고 뒤에 붙인다
    rows += [_uncaptioned_row(picture) for picture in uncaptioned or []]

    deadline = _deadline(options, has_list)
    findings = []
    if not figures:
        findings.append({"그림": "원고", **_issue(UNDECIDED, "그림 없음", "원고에서 그림 캡션([그림 N-M])을 찾지 못했습니다", "원고 파일과 캡션 표기를 확인")})
    if not has_list:
        findings.append({"그림": "수록 현황 목록", **_issue(FAIL if figures else UNDECIDED, "목록 미제출", "사진·삽화 수록 현황 목록을 찾지 못했습니다(올린 서류에 그 표가 없음)", "원고 집필 계약서 붙임 2를 작성해 제출")})
    if deadline["판정"] != PASS:
        # 늦었거나 아직 내지 않은 것은 개발기관이, 날짜를 넣지 않아 계산하지 못한 것은 점검하는 쪽(에디팅 기관)이 움직인다
        waiting = deadline["판정"] == FAIL or (deadline["기한"] is not None and options.submitted_on is None and not has_list)
        findings.append({"그림": "제출 기한", **_issue(deadline["판정"], "기한", deadline["내용"], "1차 검토 이후 4주 이내 제출(원고 집필 계약서 제5조 1항)",
                                                    to=DEVELOPER if waiting else EDITOR)})
    for row in rows:
        name = row["그림명"] if row.get("캡션 없음") else f"[{row['그림 번호']}] {row['그림명']}".strip()
        findings += [{"그림": name, **issue} for issue in row["지적"]]
    # 현황에는 있는데 원고·목록 어디에도 짝이 없는 AI 결과물
    known = {(_key(row["그림 번호"]), title_key(row["그림명"])) for row in rows if not row.get("캡션 없음")}
    for result in forms.ai_results:
        if not any((result["label"] and _key(result["label"]) == label) or title_key(result["title"]) == title for label, title in known):
            findings.append({"그림": result["name"], **_issue(UNDECIDED, "현황에만 있음", "서약서의 결과물 현황에 있는데 원고와 수록 현황 목록에서 찾지 못했습니다", "결과물 명과 그림 번호를 확인")})

    counts = {verdict: sum(row["판정"] == verdict for row in rows) for verdict in (PASS, FAIL, UNDECIDED)}
    missing = sum(issue["수준"] == FAIL for issue in findings)
    overall = FAIL if any(f["수준"] == FAIL for f in findings) else UNDECIDED if findings else PASS
    return {
        "요약": {"판정": overall, "원고 그림": len(figures), "캡션 없는 그림": len(uncaptioned or []),
                "목록 행": len(listed_rows) if has_list else None,
                "학습모듈명": inclusion["module"] if inclusion else "", **counts, "누락": missing,
                "확인 필요": sum(f["수준"] == UNDECIDED for f in findings)},
        "기한": deadline,
        "서류": {"읽은 양식": forms.sources,
                "입력": {"양도 동의서(집필자)": options.transfer_author, "양도 동의서(제작자)": options.transfer_maker,
                        "초상권": options.portrait, "AI 서약서": options.pledge}},
        "현황표": rows, "지적사항": findings,
        "알림": _notices(findings, inclusion["module"] if inclusion else ""), "안내": notes,
    }

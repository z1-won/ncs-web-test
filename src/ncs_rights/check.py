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
기한: 수록 현황 목록은 1차 검토 이후 4주 이내 제출(원고 집필 계약서 제5조 1항). 기한 항목은 언제나 결과에 넣는다
(검증 기준 '기한 경과 항목 알림 누락 0건').
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from ncs_core.figures import Figure

from .forms import METHOD_NAMES, Forms, squash, title_key

PASS, FAIL, UNDECIDED = "적합", "부적합", "판단불가"
SUBMITTED, MISSING, TO_CHECK = "제출", "누락", "확인 필요"
DEADLINE_DAYS = 28
PRIMARY = ("author_made", "commissioned", "public_license", "blanket_license", "prior_module")
PUBLIC_SOURCE = re.compile(r"공공누리|공유마당|kogl|gongu", re.I)
PRIOR_SOURCE = re.compile(r"LM\d{8,10}|학습모듈|한국직업능력(연구|개발)원")
AI_MODE_NAMES = {"generated": "생성함", "modified": "수정 보완함"}


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


def _issue(level: str, kind: str, text: str, action: str = "") -> dict:
    return {"수준": level, "종류": kind, "내용": text, "조치": action}


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


def _match(figure: Figure, rows: list[dict], used: set[int]) -> tuple[int | None, str]:
    """원고 그림과 짝이 되는 목록 행 → (행 순번, 'same' | 'title' 제목이 다름 | 'label' 번호가 다름 | '')."""
    label, title = _key(figure.label), title_key(figure.title)
    for i, row in enumerate(rows):
        if i not in used and figure.minor is not None and _key(row["label"]) == label:
            return i, ("same" if not title or not title_key(row["title"]) or title_key(row["title"]) == title else "title")
    for i, row in enumerate(rows):
        if i not in used and title and title_key(row["title"]) == title:
            return i, ("same" if not row["label"] or figure.minor is None else "label")
    return None, ""


def _find_row(rows: list[dict], label: str, title: str) -> dict | None:
    """제작 목록·동의서·AI 현황에서 그 그림을 가리키는 행 — 번호가 같거나 제목이 같으면."""
    for row in rows:
        if row.get("label") and _key(row["label"]) == _key(label) and not label.endswith("-"):
            return row
    for row in rows:
        if title and title_key(row.get("title", "")) == title_key(title):
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
                has_list: bool) -> dict:
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
        made = _find_row(forms.production, label, title)
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
        consent = _find_row(forms.license, label, title)
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
    result = _find_row(forms.ai_results, label, title)
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
        "증빙": evidence, "지적": issues, "비고": [issue["내용"] for issue in issues],
        "판정": FAIL if FAIL in levels else UNDECIDED if UNDECIDED in levels else PASS,
        "문단": [figure.section, figure.para] if figure else None,
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


def check(figures: list[Figure], forms: Forms, options: Options | None = None) -> dict:
    """현황표와 누락 목록. 반환: {'요약', '기한', '서류', '현황표', '지적사항', '안내'}."""
    options = options or Options()
    inclusion, note = _pick_inclusion(forms, figures)
    notes = [note] if note else []
    listed_rows = inclusion["rows"] if inclusion else []
    has_list = inclusion is not None

    rows, used = [], set()
    for figure in figures:
        index, how = _match(figure, listed_rows, used)
        if index is not None:
            used.add(index)
        rows.append(_figure_row(figure, listed_rows[index] if index is not None else None, how, forms, options, has_list))
    for index, listed in enumerate(listed_rows):
        if index not in used:
            rows.append(_figure_row(None, listed, "", forms, options, has_list))

    if not has_list:
        # 목록이 없으면 제작 방식을 몰라 필요한 증빙을 따질 수 없다 — 문제가 안 보인다고 적합으로 두지 않는다.
        # 지적사항에는 '목록 미제출' 한 건으로만 말하고, 그림 줄에는 비고로만 적는다(그림 수만큼 같은 말을 되풀이하지 않게)
        for row in rows:
            row["비고"].append("수록 현황 목록이 없어 제작 방식과 필요한 증빙을 대조하지 못했습니다")
            if row["판정"] == PASS:
                row["판정"] = UNDECIDED

    deadline = _deadline(options, has_list)
    findings = []
    if not figures:
        findings.append({"그림": "원고", **_issue(UNDECIDED, "그림 없음", "원고에서 그림 캡션([그림 N-M])을 찾지 못했습니다", "원고 파일과 캡션 표기를 확인")})
    if not has_list:
        findings.append({"그림": "수록 현황 목록", **_issue(FAIL if figures else UNDECIDED, "목록 미제출", "사진·삽화 수록 현황 목록을 찾지 못했습니다(올린 서류에 그 표가 없음)", "원고 집필 계약서 붙임 2를 작성해 제출")})
    if deadline["판정"] != PASS:
        findings.append({"그림": "제출 기한", **_issue(deadline["판정"], "기한", deadline["내용"], "1차 검토 이후 4주 이내 제출(원고 집필 계약서 제5조 1항)")})
    for row in rows:
        findings += [{"그림": f"[{row['그림 번호']}] {row['그림명']}".strip(), **issue} for issue in row["지적"]]
    # 현황에는 있는데 원고·목록 어디에도 짝이 없는 AI 결과물
    known = {(_key(row["그림 번호"]), title_key(row["그림명"])) for row in rows}
    for result in forms.ai_results:
        if not any((result["label"] and _key(result["label"]) == label) or title_key(result["title"]) == title for label, title in known):
            findings.append({"그림": result["name"], **_issue(UNDECIDED, "현황에만 있음", "서약서의 결과물 현황에 있는데 원고와 수록 현황 목록에서 찾지 못했습니다", "결과물 명과 그림 번호를 확인")})

    counts = {verdict: sum(row["판정"] == verdict for row in rows) for verdict in (PASS, FAIL, UNDECIDED)}
    missing = sum(issue["수준"] == FAIL for issue in findings)
    overall = FAIL if any(f["수준"] == FAIL for f in findings) else UNDECIDED if findings else PASS
    return {
        "요약": {"판정": overall, "원고 그림": len(figures), "목록 행": len(listed_rows) if has_list else None,
                "학습모듈명": inclusion["module"] if inclusion else "", **counts, "누락": missing,
                "확인 필요": sum(f["수준"] == UNDECIDED for f in findings)},
        "기한": deadline,
        "서류": {"읽은 양식": forms.sources,
                "입력": {"양도 동의서(집필자)": options.transfer_author, "양도 동의서(제작자)": options.transfer_maker,
                        "초상권": options.portrait, "AI 서약서": options.pledge}},
        "현황표": rows, "지적사항": findings, "안내": notes,
    }

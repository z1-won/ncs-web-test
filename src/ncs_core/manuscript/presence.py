"""참고 자료·활용 서식·부록이 본문에 있는지의 근거를 찾는다."""

import re
from itertools import combinations

from .config import DEFAULT_PARSE_CONFIG, ParseConfig
from .patterns import REF_LINE

TAIL_PATTERNS = {"참고 자료": r"참\s*고\s*자\s*료", "활용 서식": r"활\s*용\s*서\s*식", "부록": r"부\s*록"}
BANNER_MIN_RATIO = 5.0  # 제목 배너는 본문 폭의 가로로 긴 띠 그림(실데이터 12:1, 10:1)
BANNER_MIN_WIDTH = 30000  # HWP 단위(1/7200 inch) ≈ 106 mm. 본문 폭 그림만 배너로 본다


def banner_figures(figures) -> list[int]:
    """이름 없는 제목 배너로 보이는 그림의 문단 인덱스. figures: (문단, 이름, 가로, 세로)."""
    return sorted(
        p for p, name, w, h in figures
        if not name and w >= BANNER_MIN_WIDTH and h > 0 and w / h >= BANNER_MIN_RATIO
    )


def section_presence(sections, images, config: ParseConfig = DEFAULT_PARSE_CONFIG, figures=(), *, tables=(), media_complete=False) -> dict:
    """{이름: {'있음': bool|None, '근거': str, 'k': 위치, ['배너만': True], ['end': 끝]}}.

    images: 본문 섹션의 (문단 인덱스, 원본 그림 이름). figures: 본문 섹션의 모든 그림 (문단, 이름 또는 "", 가로, 세로).
    media_complete: 그림 추출을 지원하는 형식일 때만 True. tables는 본문 섹션의 표 목록.
    있음=None은 영역 이름이나 작성 여부를 확정하지 못한 경우다.
    배너만=True는 제목 뒤에 안내문 외 텍스트·표·그림이 없는 경우에만 설정한다.
    """
    raw = sections[1] if len(sections) > 1 else []
    lines = [(i, l) for i, l in enumerate(raw) if l]
    out = {}
    for name, pattern in TAIL_PATTERNS.items():
        found = {"있음": False, "근거": "제목 텍스트·배너 이미지·내용 패턴 어느 것도 없음", "k": None}
        hit = next(((i, l) for i, l in lines if re.fullmatch(pattern, l)), None)
        if hit:  # 1) 제목 텍스트
            found = {"있음": True, "근거": f'제목 텍스트 "{hit[1]}" (section1 p{hit[0]})', "k": hit[0]}
        else:  # 2) 배너 이미지
            compact = pattern.replace(r"\s*", "")
            banner = next(((p, n) for p, n in images if re.search(compact, n.replace(" ", ""))), None)
            if banner:
                found = {"있음": True, "근거": f'배너 이미지 "{banner[1]}" (section1 p{banner[0]})', "k": banner[0]}
        out[name] = found

    # 2) 내용 패턴 — 참고 자료: 참고문헌 꼴 줄이 연속으로 충분히 있으면 존재로 본다
    if not out["참고 자료"]["있음"]:
        run, best = [], []
        for i, l in lines:
            if REF_LINE.match(l):
                run.append(i)
            else:
                if len(run) > len(best):
                    best = run
                run = []
        if len(run) > len(best):
            best = run
        if len(best) >= config.reference_min_lines:
            out["참고 자료"] = {
                "있음": True,
                "근거": f"참고문헌 꼴 줄 {len(best)}개 연속 (section1 p{best[0]}~p{best[-1]}) — 제목은 텍스트가 아님(이미지일 가능성)",
                "k": best[0],
                "end": best[-1],
            }

    development = next((i for i, l in lines if re.search(r"개발\s*이력", l)), len(raw))
    # 개발 이력 제목이 표 첫 셀에 있으면 표를 담는 바깥 문단부터 제외한다.
    development = min([development] + [t["paragraph"] for t in tables
                      if re.fullmatch(r"(?:NCS\s*학습모듈\s*)?개발\s*이력", t.get("cells", {}).get((0, 0), ""))])
    # 개발 이력 앞의 양식 표시는 실제 서식·부록 내용이 아니다.
    def is_content(line):
        return not line.startswith("※") and not re.fullmatch(r"<\s*신규\s*개발\s*학습모듈\s*양식\s*>", line)

    reference = out["참고 자료"]
    anchor = reference.get("end", reference["k"])
    # 텍스트 제목으로 찾았더라도 바로 뒤 참고문헌 구간을 기준점에 포함한다.
    if anchor is not None:
        for i, line in lines:
            if i <= anchor:
                continue
            if REF_LINE.match(line):
                anchor = i
            else:
                break
    unnamed = sorted(set(banner_figures(figures)))
    candidates = [p for p in unnamed if anchor is not None and anchor < p < development
                  and p not in {v["k"] for v in out.values()}]
    names = ("활용 서식", "부록")
    missing = [name for name in names if out[name]["k"] is None]
    # 알려진 제목과 꼬리 순서를 함께 만족하는 배정이 하나일 때만 영역을 식별한다.
    # 제목 없는 배너 하나만 있고 두 항목이 모두 미상인 경우에는 두 배정이 가능하다.
    assignments = []
    if candidates and len(candidates) <= len(missing):
        for slots in combinations(missing, len(candidates)):
            assigned = dict(zip(slots, candidates))
            positions = [assigned.get(name, out[name]["k"]) for name in names]
            known = [pos for pos in positions if pos is not None]
            if known == sorted(set(known)) and all(anchor < pos < development for pos in known):
                assignments.append(assigned)
    if len(assignments) == 1:
        for name, position in assignments[0].items():
            out[name] = {"있음": True, "k": position,
                         "근거": f"이름 없는 배너(section1 p{position}) — 참고 자료·주변 제목 위치와 꼬리 순서로 {name} 영역 식별"}

    # 참고문헌 끝과 확인된 부록 사이의 내용도 활용 서식 영역으로 볼 수 있다.
    # 배너 후보가 여러 개여서 구분되지 않는 경우에는 이 추정으로 덮어쓰지 않는다.
    appendix = out["부록"]["k"]
    if out["활용 서식"]["k"] is None and anchor is not None and appendix is not None and anchor < appendix and not candidates:
        content_positions = [i for i, l in lines if anchor < i < appendix and is_content(l) and not REF_LINE.match(l)]
        content_positions += [p for p, *_ in figures if anchor < p < appendix]
        content_positions += [t["paragraph"] for t in tables if anchor < t["paragraph"] < appendix]
        if content_positions:
            out["활용 서식"] = {"있음": True, "k": min(content_positions), "내용부터": True,
                                 "근거": f"참고 자료 뒤~부록 앞(section1 p{anchor + 1}~p{appendix - 1})의 내용 — 꼬리 구조상 활용 서식 영역"}
    heading_positions = {v["k"] for v in out.values() if v["k"] is not None}
    media_positions = {p for p, *_ in figures} | {p for p, _ in images}
    table_positions = {t["paragraph"] for t in tables}

    for name in ("활용 서식", "부록"):
        found = out[name]
        if not found["있음"]:
            continue
        start = found["k"]
        stop = min([p for p in heading_positions | set(unnamed) | {development, len(raw)} if p > start], default=len(raw))
        content_start = start if found.get("내용부터") else start + 1
        content = [l for i, l in lines if content_start <= i < stop and is_content(l)]
        media = any(content_start <= p < stop for p in media_positions)
        table = any(start <= p < stop for p in table_positions)
        found["end"] = stop - 1
        if content or media or table:
            found.update(있음=True, 근거=found["근거"] + f" — 내용 있음(문단 {len(content)}개, 표 {int(table)}, 그림 {int(media)})")
        elif stop in unnamed and stop not in heading_positions:
            found.update(있음=None, 근거=found["근거"] + " 뒤의 그림이 내용인지 다음 제목인지 확인 필요")
        elif media_complete:
            found.update(있음=False, 배너만=True, 근거=found["근거"] + " 뒤에 내용·표·그림이 없음(안내문 제외)")
        else:
            found.update(있음=None, 근거=found["근거"] + " 뒤에 텍스트가 없으나 그림 추출 정보가 없어 미작성 확정 불가")

    # 확정 제목에 속하지 않는 꼬리 내용은 서식/부록 어느 쪽인지 알 수 없다.
    if anchor is not None:
        # 확정 제목부터 다음 경계까지는 해당 항목의 구간이다. 이름 없는 그림 이후는
        # 그 항목의 연속인지 새 항목인지 알 수 없으므로 미분류 구간으로 남긴다.
        known_ranges = [(v["k"], v["end"]) for n, v in out.items()
                        if n != "참고 자료" and v["k"] is not None and "end" in v]
        def unclassified(p):
            return anchor < p < development and not any(start <= p <= end for start, end in known_ranges)
        unknown_text = [l for i, l in lines if unclassified(i) and not REF_LINE.match(l) and is_content(l)]
        unknown_media = any(unclassified(p) for p in media_positions | table_positions)
    else:
        unknown_text, unknown_media = [], False
    for name in ("활용 서식", "부록"):
        if out[name]["k"] is not None:
            continue
        if anchor is None or not media_complete or unknown_text or unknown_media:
            out[name] = {
                "있음": None, "k": None,
                "근거": "제목을 찾지 못함 — " + (
                    "참고 자료 뒤에 미분류 내용·표·그림이 있어 활용 서식/부록 구분 필요"
                    if unknown_text or unknown_media else
                    "꼬리 구간 또는 그림 추출 정보가 부족하여 미작성 확정 불가"
                ),
            }
    return out

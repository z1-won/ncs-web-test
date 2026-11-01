"""기타 ②: 사진·삽화의 누락 또는 유실 — 학습마다 1행.

누락: [그림 N-M] 캡션 위에 그림 개체가 없음. 그림은 캡션 순서대로 가까운 것부터 짝짓는다(나란히 놓인 두 그림 + 두 캡션).
      그림 대신 표·텍스트(표로 그린 양식)가 있으면 △ — 삽화 누락인지 표로 그린 것인지 사람 확인.
유실: 그림 개체가 가리키는 BinData 파일이 패키지에 없거나 0바이트.
hwp는 그림 목록을 읽지 못해 △.
"""

import re

from ncs_core import O, TRI, X, visible

from .common import row

CAPTION = re.compile(r"^\s*[\[〔\(（]\s*그림\s*\d+\s*[-–—－‐]\s*\d+\s*[\]〕\)）]")


def check_pictures(context) -> list[dict]:
    manuscript, config = context.manuscript, context.config
    section = config.body_section
    paragraphs = manuscript.sections[section]
    if manuscript.format != "hwpx":
        return [row("②", "section1", "", None, {"그림 존재": TRI}, {"그림 존재": "hwp는 그림 개체를 읽지 못함 — hwpx로 확인"})]
    pictures = manuscript.section_pictures(section)
    by_paragraph = {}
    for p, bin_id in pictures:
        by_paragraph.setdefault(p, []).append(bin_id)
    rows = []
    for lesson in context.body["lessons"]:
        a, b = lesson["raw_span"]
        where = f"학습 {lesson['no']}"
        captions = [i for i in range(a, b) if CAPTION.match(paragraphs[i] or "")]
        missing, drawn, lost, details = [], [], [], []
        free = sorted(p for p, _ in pictures if a <= p < b)
        previous = a - 1
        for i in captions:
            above = [p for p in free if i - config.figure_window <= p <= i]  # 나란히 놓인 그림은 앞 캡션보다 위에 있을 수 있다
            floor = max(a, i - config.figure_lookback, previous + 1)  # 앞 캡션 뒤부터만 본다
            previous = i
            if above:
                free.remove(max(above))
                continue
            texty = any((paragraphs[j] or "").strip() and not paragraphs[j].startswith("출처") for j in range(floor, i))
            (drawn if texty else missing).append(i)
            details.append({"문단": i, "캡션": visible(paragraphs[i]),
                            "문제": "캡션 위에 그림 개체 없이 표·텍스트만 있음(표로 그린 양식인지 확인)" if texty else "캡션 위에 그림 개체 없음"})
        for p, bin_id in pictures:
            if not a <= p < b:
                continue
            item = manuscript.binaries.get(bin_id) if bin_id else None
            if item is None or not item.get("bytes"):
                lost.append(p)
                details.append({"문단": p, "BinData": bin_id, "문제": "그림 파일 없음" if item is None else "그림 파일 0바이트"})
        count = sum(1 for p, _ in pictures if a <= p < b)
        checks = {"캡션에 그림 있음": X if missing else TRI if drawn else O, "그림 파일 존재": X if lost else O}
        notes = {}
        if missing or drawn:
            parts = []
            if missing:
                parts.append(f"{len(missing)}개 위에 그림이 없음(" + ", ".join(visible(paragraphs[i])[:14] for i in missing[:3]) + ")")
            if drawn:
                parts.append(f"{len(drawn)}개는 그림 대신 표·텍스트(" + ", ".join(visible(paragraphs[i])[:14] for i in drawn[:3]) + ") — 표로 그린 양식인지 확인")
            notes["캡션에 그림 있음"] = f"캡션 {len(captions)}개 중 " + " · ".join(parts)
        if lost:
            notes["그림 파일 존재"] = f"그림 {count}개 중 {len(lost)}개의 파일이 없거나 비어 있음(p{', p'.join(map(str, lost[:3]))})"
        rows.append(row("②", f"section{section} > {where}", where, {"캡션": len(captions), "그림": count}, checks, notes,
                        "누락된 그림을 넣고, 유실된 그림 파일은 다시 삽입", 상세=details))
    return rows or [row("②", "section1", "", None, {"그림 존재": TRI}, {"그림 존재": "학습 구간을 찾지 못함"})]

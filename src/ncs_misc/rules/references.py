"""기타 ⑦: 활용 서식·부록이 있으면 본문에 '활용 서식 참조' / '부록 참조'라고 기재하였는가. 영역마다 1행."""

import re

from ncs_core import NA, O, TRI, X

from .common import row

PATTERNS = {"활용 서식": re.compile(r"활\s*용\s*서\s*식\s*참\s*조"), "부록": re.compile(r"부\s*록\s*참\s*조")}


def check_references(context) -> list[dict]:
    body = context.manuscript.sections[context.config.body_section]
    rows = []
    for name, pattern in PATTERNS.items():
        found = context.presence.get(name) or {}
        label = f"'{name} 참조' 기재"
        if not found.get("있음"):
            # 영역을 못 찾았는데 본문에 '○○ 참조'가 있으면 영역이 실제로 있을 가능성이 크다(제목이 그림·hwp) → 해당 없음 대신 △
            cited = [i for i, text in enumerate(body) if pattern.search(text or "")]
            if cited:
                rows.append(row("⑦", f"section1 > {name}", "", {"참조 문단": cited[:10], "개수": len(cited)}, {label: TRI},
                                {label: f"본문에 '{name} 참조'가 {len(cited)}곳 있는데 {name} 영역을 찾지 못함 — 영역이 있는지 사람 확인"}))
            else:
                rows.append(row("⑦", f"section1 > {name}", "", None, {label: NA}, {label: f"{name} 영역이 없어 해당 없음"}))
            continue
        start = found.get("k") or 0
        hits = [i for i, text in enumerate(body) if i < start and pattern.search(text or "")]
        checks = {label: O if hits else X}
        notes = {} if hits else {label: f"{name} 영역은 있는데(p{start}) 그 앞 본문에 '{name} 참조'가 없음"}
        rows.append(row("⑦", f"section1 > {name}", "", {"참조 문단": hits[:10], "개수": len(hits)}, checks, notes, f"해당 본문에 '{name} 참조'라고 기재"))
    return rows

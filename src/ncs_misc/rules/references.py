"""기타 ⑦: 활용 서식·부록이 있으면 본문에 '활용 서식 참조' / '부록 참조'라고 기재하였는가. 영역마다 1행."""

import re

from ncs_core import NA, O, X

from .common import row

PATTERNS = {"활용 서식": re.compile(r"활\s*용\s*서\s*식\s*참\s*조"), "부록": re.compile(r"부\s*록\s*참\s*조")}


def check_references(context) -> list[dict]:
    body = context.manuscript.sections[context.config.body_section]
    rows = []
    for name, pattern in PATTERNS.items():
        found = context.presence.get(name) or {}
        label = f"'{name} 참조' 기재"
        if not found.get("있음"):
            rows.append(row("⑦", f"section1 > {name}", "", None, {label: NA}, {label: f"{name} 영역이 없어 해당 없음"}))
            continue
        start = found.get("k") or 0
        hits = [i for i, text in enumerate(body) if i < start and pattern.search(text or "")]
        checks = {label: O if hits else X}
        notes = {} if hits else {label: f"{name} 영역은 있는데(p{start}) 그 앞 본문에 '{name} 참조'가 없음"}
        rows.append(row("⑦", f"section1 > {name}", "", {"참조 문단": hits[:10], "개수": len(hits)}, checks, notes, f"해당 본문에 '{name} 참조'라고 기재"))
    return rows

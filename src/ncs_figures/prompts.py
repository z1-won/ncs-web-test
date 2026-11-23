"""그림 프롬프트 조립 — ncs_figures/prompts/*.md의 '## [이름]' 절 아래 코드 블록이 유일한 원본.

값이 빈 {변수}가 든 줄은 통째로 뺀다(빈칸이 있으면 모델이 추측해 채움). FIG_PROMPT_DIR로 다른 폴더를 쓸 수 있다(프롬프트 시험용).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

SECTION = re.compile(r"^## \[([^\]\n]+)\][^\n]*\n+```[a-z]*\n(.*?)\n```", re.M | re.S)
PLACEHOLDER = re.compile(r"\{([^{}\s\"]+)\}")
ORDER = {"fig_read": ("역할", "그림 맥락", "기록할 것", "판단 기준", "규칙", "출력 형식")}


def prompt_dir() -> Path:
    return Path(os.getenv("FIG_PROMPT_DIR") or Path(__file__).resolve().parent / "prompts")


def sections(name: str) -> dict[str, str]:
    text = (prompt_dir() / f"{name}.md").read_text(encoding="utf-8")
    return {m.group(1): m.group(2) for m in SECTION.finditer(text)}


def fill(template: str, values: dict[str, str]) -> str:
    out = []
    for line in template.splitlines():
        keys = [k for k in PLACEHOLDER.findall(line) if k in values]
        if any(not values[k] for k in keys):
            continue
        for k in keys:
            line = line.replace("{" + k + "}", values[k])
        out.append(line)
    return "\n".join(out)


def build(name: str, values: dict[str, str]) -> tuple[str, str]:
    """(system, user). system = 역할·기준·규칙·출력 형식, user = 맥락(그림마다 다른 글). 그림 자체는 호출 쪽이 붙인다."""
    parts = sections(name)
    context_key = "그림 맥락"
    system = "\n\n".join(parts[k].strip() for k in ORDER[name] if k != context_key and parts.get(k))
    user = fill(parts[context_key], values).strip()
    return system, user

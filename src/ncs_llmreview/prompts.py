"""프롬프트 조립 — 패키지 안 prompts/*.md가 프롬프트의 유일한 원본.

md에서 '## [이름] …' 제목 바로 아래 ``` 코드 블록을 그 이름의 조각으로 읽는다. 값이 빈 {변수}가 든 줄은 통째로 뺀다.
LLM_PROMPT_DIR 환경 변수로 다른 폴더를 쓸 수 있다(프롬프트를 고쳐 보며 시험할 때).
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

TASK_FILES = {
    "perform3_safety": "02_수행3_안전유의.md",
    "eval4_items": "03_평가4_평가항목.md",
    "overview2_prereq": "04_개요2_선수학습.md",
    "misc3_names": "05_기타3_상호상품명.md",
    "perform2_brands": "06_수행2_상표명.md",
    "src_unquoted": "07_출처_문장단위인용.md",
}
COMMON_FILE = "00_공통.md"
SECTION = re.compile(r"^## \[([^\]\n]+)\][^\n]*\n+```[a-z]*\n(.*?)\n```", re.M | re.S)
KINDS = re.compile(r"`\{문제_종류\}`\s*=\s*(.+)")
PLACEHOLDER = re.compile(r"\{([^{}\s\"]+)\}")


def prompt_dir() -> Path:
    return Path(os.getenv("LLM_PROMPT_DIR") or Path(__file__).resolve().parent / "prompts")


@lru_cache(maxsize=None)
def _text(folder: str, name: str) -> str:
    return (Path(folder) / name).read_text(encoding="utf-8")


def text(name: str) -> str:
    return _text(str(prompt_dir()), name)


def sections(name: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in SECTION.finditer(text(name))}


def problem_kinds(task: str) -> list[str]:
    m = KINDS.search(text(TASK_FILES[task]))
    return [k.strip().strip("`").strip() for k in m.group(1).split("|")] if m else []


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


def _values(info: dict) -> dict[str, str]:
    return {"모듈명": info.get("name", ""), "모듈코드": info.get("code", ""), "분야": info.get("field", ""),
            "모듈_목표": info.get("goal", ""), "원고_요약": info.get("summary", ""),
            "분야_공용명칭": ", ".join(info.get("terms") or [])}


def build_system(info: dict) -> str:
    """system — 원고마다 같음(역할·원고 정보·원고 입력·규칙·출력 형식). info: chunks.module_info()."""
    common = sections(COMMON_FILE)
    parts = [common["역할"], fill(common["원고 정보"], _values(info)), common["원고 입력"], common["규칙"], common["출력 형식"]]
    return "\n\n".join(p.strip() for p in parts if p.strip())


def task_block(task: str, info: dict) -> str:
    """검토 항목 하나 — task 파일의 [체크 항목]·[판단 기준]·[예시] + 문제 종류."""
    own = sections(TASK_FILES[task])
    values = {**_values(info), "문제_종류": " | ".join(problem_kinds(task))}
    parts = [f"[검토 항목 {task}]", own["체크 항목"], fill(own["판단 기준"], values)]
    examples = own.get("예시", "")
    if examples:
        parts.append(examples if examples.lstrip().startswith("[예시]") else "[예시]\n" + examples)
    parts.append(f"[문제 종류] {values['문제_종류']}")
    return "\n\n".join(p.strip() for p in parts if p.strip())


def build_request(tasks: list[str], info: dict) -> str:
    """user 둘째 블록 — 이번 호출에서 볼 검토 항목들."""
    head = "[검토 항목] 아래 항목마다 [원고]의 그 항목 조각만 검수한다: " + ", ".join(tasks)
    return "\n\n".join([head, *(task_block(t, info) for t in tasks)])

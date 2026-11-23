"""LLM 검토 실행 — 원고 하나 → 항목별 조각 → 원고 한 덩어리 + 항목 여러 개를 한 번에 Claude → 검증 → 수정 후보 목록.

원고 덩어리([원고])는 고른 항목 전부의 조각을 담고 문단 글은 한 번만 넣는다(여러 항목이 같은 문단을 봐도 한 번).
LLM_REVIEW_BATCH: 한 호출에 넣을 항목 수(기본 0 = 전부 한 번). 나눠 부르면 원고 덩어리는 캐시 읽기로만 다시 냄.
출력이 max_tokens에서 잘리면 항목을 반으로 나눠 다시 부른다.

generate: 테스트용 대역(system, document, request, *, task, tasks) -> {'data','usage','cached','model'}. 없으면 claude.generate_json.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

from . import claude
from .chunks import EXTRACTORS, load, where
from .prompts import build_request, build_system, problem_kinds

TASKS = {  # 화면 순서 — (이름, F02 항목)
    "perform2_brands": ("수행 내용 ② 상표·상품·제조사명", "F02-수행-②"),
    "perform3_safety": ("수행 내용 ③ 안전·유의 사항", "F02-수행-③"),
    "eval4_items": ("평가 ④ 평가 항목", "F02-평가-④"),
    "overview2_prereq": ("개요 ② 선수학습", "F02-개요-②"),
    "misc3_names": ("기타 ③ 상호·상품명(본문)", "F02-기타-③"),
    "src_unquoted": ("출처 표시 없는 인용(어문 자료 문장 단위 · 008)", "REQ-02-008"),
}


def status() -> dict:
    cfg = claude.settings()
    problem = claude.why_not(cfg)
    return {"available": not problem, "problem": problem or None, "model": cfg["model"], "effort": cfg["effort"],
            "tasks": [{"value": key, "label": label, "item_id": item} for key, (label, item) in TASKS.items()]}


def document_text(all_chunks: dict[str, list[dict]]) -> tuple[str, dict[str, dict[int, str]]]:
    """[원고] 덩어리 — 문단(번호·글, 한 번씩) + 항목별 조각(검수 대상은 번호만). → (글, {항목: {n: 그 항목이 본 글}})."""
    paragraphs: dict[int, str] = {}
    targets: dict[str, dict[int, str]] = {}
    pieces: dict[str, list[dict]] = {}
    for task, chunks in all_chunks.items():
        seen = targets.setdefault(task, {})
        pieces[task] = []
        for chunk in chunks:
            numbers, inline = [], []
            for item in chunk["검수 대상"]:
                n, text = item["n"], item["글"]
                seen[n] = text
                if paragraphs.setdefault(n, text) == text:
                    numbers.append(n)
                else:
                    inline.append({"n": n, "글": text})        # 같은 번호인데 이 항목이 본 글이 다를 때만 글째
            piece = {k: v for k, v in chunk.items() if k not in ("검수 대상", "조각") and v}
            piece["검수 대상"] = numbers + inline
            pieces[task].append(piece)
    lines = "\n".join(f"[{n}] {paragraphs[n]}" for n in sorted(paragraphs))
    body = json.dumps(pieces, ensure_ascii=False, separators=(",", ":"))
    return f"[원고]\n문단:\n{lines}\n\n조각: {body}", targets


def _batches(tasks: list[str]) -> list[list[str]]:
    try:
        size = int(os.getenv("LLM_REVIEW_BATCH") or 0)
    except ValueError:
        size = 0
    if size <= 0:
        return [list(tasks)]
    return [tasks[i:i + size] for i in range(0, len(tasks), size)]


def _labels(group: list[str]) -> str:
    return ", ".join(TASKS[t][0] for t in group)


def review_manuscript(manuscript: Path, *, tasks: list[str] | None = None, module_code: str = "",
                      generate: Callable[..., dict] | None = None, progress: Callable[[str], None] | None = None) -> dict:
    """→ {'module', 'model', 'findings', 'usage', 'errors', 'tasks', 'created_at'}."""
    generate = generate or claude.generate_json
    tasks = [t for t in (tasks or list(TASKS)) if t in TASKS]
    if not tasks:
        raise ValueError("검토할 항목이 없습니다")
    doc, code, info = load(manuscript, module_code)
    findings, errors = [], []
    usage = {"calls": 0, "new_calls": 0, "input": 0, "output": 0, "cache_read": 0, "cost_usd": 0.0, "dropped": 0}
    model = claude.settings()["model"]
    started = time.perf_counter()
    all_chunks = {task: EXTRACTORS[task](doc, code) for task in tasks}
    if progress:
        progress(" · ".join(f"{TASKS[t][0]}: 조각 {len(c)}개" for t, c in all_chunks.items()))
    live = [t for t in tasks if all_chunks[t]]                       # 조각이 없는 항목은 묻지 않음
    document, targets = document_text({t: all_chunks[t] for t in live})
    system = build_system(info)
    where_of = {t: {item["n"]: c for c in all_chunks[t] for item in c["검수 대상"]} for t in live}
    queue = _batches(live) if live else []
    while queue:
        group = queue.pop(0)
        usage["calls"] += 1
        try:
            answer = generate(system, document, build_request(group, info), task="batch", tasks=group)
        except claude.ClaudeError as error:
            if "max_tokens" in str(error) and len(group) > 1:
                half = len(group) // 2
                queue[:0] = [group[:half], group[half:]]               # 잘리면 반으로 나눠 다시(원고는 캐시 읽기)
                continue
            errors.append({"항목": _labels(group), "위치": "", "오류": str(error)})
            if any(s in str(error) for s in ("ANTHROPIC_API_KEY", "LLM_ALLOW_UPLOAD", "anthropic 패키지", "모델 이름")):
                raise ValueError(str(error)) from None      # 설정 문제는 끝까지 같은 오류 — 바로 멈춘다
            continue
        model = answer.get("model", model)
        if not answer.get("cached"):
            u = answer.get("usage") or {}
            usage["new_calls"] += 1
            usage["input"] += u.get("input", 0)
            usage["output"] += u.get("output", 0)
            usage["cache_read"] += u.get("cache_read", 0)
            usage["cost_usd"] += claude.cost(model, u) or 0.0
        data = answer.get("data")
        said = data.get("지적") if isinstance(data, dict) else None
        if not isinstance(said, list):
            errors.append({"항목": _labels(group), "위치": "", "오류": "형식 오류 — '지적' 목록이 없음"})
            continue
        usage["dropped"] += sum(1 for f in said if not isinstance(f, dict) or f.get("항목") not in group)
        for task in group:
            label, item_id = TASKS[task]
            mine = [f for f in said if isinstance(f, dict) and f.get("항목") == task]
            pool = {"검수 대상": [{"n": n, "글": g} for n, g in targets[task].items()]}
            kept, dropped = verify_chunk(pool, {"지적": mine}, problem_kinds(task))
            usage["dropped"] += len(dropped)
            for f in kept:
                chunk = where_of[task].get(f["n"], {})
                section, para = where(f["n"])
                findings.append({
                    "task": task, "항목": label, "item_id": item_id, "위치": chunk.get("위치", ""), "블록_제목": chunk.get("블록_제목", ""),
                    "n": f["n"], "구역": section, "문단": para,
                    "수정해야 하는 부분": targets[task].get(f["n"], ""), "인용": f.get("인용", ""),
                    "근거_종류": f.get("문제", ""), "근거": f.get("이유", ""),
                    "수정 방안": f.get("수정 문장", ""), "검증": f.get("검증", ""),
                })
    order = {t: i for i, t in enumerate(tasks)}
    findings.sort(key=lambda f: (order[f["task"]], f["n"]))
    usage["cost_usd"] = round(usage["cost_usd"], 4)
    usage["seconds"] = round(time.perf_counter() - started, 1)
    return {"module": info, "model": model, "tasks": tasks, "item_ids": {t: TASKS[t][1] for t in tasks},
            "chunks": {t: len(all_chunks[t]) for t in tasks}, "findings": findings, "errors": errors, "usage": usage,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}


def verify_chunk(chunk, data, kinds):
    from .verify import verify
    return verify(chunk, data, kinds)


def to_rows(result: dict) -> list[dict]:
    """메모 원고(ncs_service.annotate)용 행 — 지적마다 그 문단에 메모 하나. 판정은 사람 확인(판단불가)."""
    rows = []
    for f in result.get("findings", []):
        check = f"LLM {f['근거_종류'] or '검토'}"
        rows.append({
            "item_id": f["item_id"], "region_path": f"section{f['구역']} > {f['위치']}", "원고": f["수정해야 하는 부분"],
            "체크": {check: "△"}, "판정": "판단불가",
            "비고": {check: f"원고 「{f['인용'] or f['수정해야 하는 부분'][:40]}」 — {f['근거']}"},
            "수정 제안": f["수정 방안"] or None,
        })
    return rows

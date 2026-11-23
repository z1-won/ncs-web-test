"""요구사항정의서 검증 기준(P열) 실측 — REQ-02-001, REQ-02-008.

    PYTHONPATH=src python scripts/measure/measure_req.py [--out 결과.md]

재는 것과 한계(결과 표 아래에도 적는다)
  001-A 자동 입력: 세분류 20010104의 초안(NCS 기준정보로 채움)을 사람이 만든 최종 결과(samples/plan/T03)와 칸 단위로 견준다.
  001-B 점검 탐지: 요소·수행준거를 받아 둔 세분류마다 초안을 만들고, 칸 하나를 일부러 틀리게 한 계획서를 점검에 넣어 잡는지 본다(합성 오류).
  008-A 출처 줄 추출: 표본 원고에서 '출처:'로 시작하는 문단을 따로 세어 출처 검토가 읽은 줄 수와 견준다.
  008-B AI 표기 탐지: 표기 예 꼴(○○를 활용하여 생성함/수정 보완함. YYYY. M. D.)로 만든 맞는 줄과 틀린 줄(정답을 아는 합성 입력)을 넣어 판정을 본다.
합성 입력의 정답은 이 스크립트가 꼴에 따라 정한 것이다. 사람이 실제 원고에 매긴 정답이 아니다.
"""
from __future__ import annotations

import argparse
import copy
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN_FINAL = ROOT / "samples/plan/T03_최종결과_개발계획서_20010104_SW제품기획.hwpx"
MANUSCRIPTS = [ROOT / "samples/LM1203020201_24v3_light.hwpx", ROOT / "samples/LM2001021701_25v1_AIoT_심의본.hwpx",
               *sorted((ROOT / "samples/aiot").glob("*.hwpx"))]
HUMAN_AREAS = ("기본 정보", "변경 전·후 대조표", "총괄표")              # 사람이 채우는 구역(자동 입력 대상이 아님)
HUMAN_CELLS = ("학습 내용명", "능력단위와 학습모듈명")                  # 사람이 짓는 칸. 위치 표의 학습모듈명은 1차 문서에서 비워 둔다(F21)
EDITABLE = ("학습 목표", "학습모듈의 목표")                             # NCS에서 가져오되 문장 띄어쓰기는 고칠 수 있는 칸(F04 2-4)


def cell_group(row: dict) -> str:
    if row["구역"] in HUMAN_AREAS or row["칸"] in HUMAN_CELLS:
        return "사람"
    return "다듬는 칸" if row["칸"] in EDITABLE else "NCS 그대로"


def pct(wrong: int, total: int) -> str:
    return "-" if not total else f"{100 * wrong / total:.2f}%"


# ── REQ-02-001 ────────────────────────────────────────────────────────────────
def plan_from_spec(spec: dict) -> dict:
    from ncs_core import load_document
    from ncs_plan.fill import build_plan
    from ncs_plan.parsers import read_plan

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "plan.hwpx"
        path.write_bytes(build_plan(spec))
        return read_plan(load_document(path).tables)


def measure_fill() -> dict:
    """001-A: 초안(자동 입력) ↔ 사람이 만든 최종 결과(T03)."""
    from ncs_core import load_document
    from ncs_plan.compare import compare_plans
    from ncs_plan.fill import spec_from_catalog
    from ncs_plan.parsers import read_plan

    final = read_plan(load_document(PLAN_FINAL).tables)
    units = sorted({m["코드"][8:10] for m in final.get("모듈") or []})
    draft = plan_from_spec(spec_from_catalog("20010104", units=units or None))
    result = compare_plans(final, draft)
    rows = result["차이"]
    table: dict[tuple, int] = {}
    for row in rows:
        key = (cell_group(row), row["구역"], row["칸"], row["차이"])
        table[key] = table.get(key, 0) + 1
    return {"요약": result["요약"], "차이": rows, "표": table}


def _mutations(spec: dict):
    """(이름, 종류, 고친 spec) — 칸 하나만 틀리게 한다."""
    module = spec["모듈"][0]
    element = module["요소"][0]

    def changed(edit):
        new = copy.deepcopy(spec)
        edit(new["모듈"][0], new["모듈"][0]["요소"][0])
        return new

    yield "능력단위 명칭 낱말 바꿈", "형식", changed(lambda m, e: m.update({"명칭": m["명칭"] + " 관리"}))
    yield "요소 명칭 낱말 바꿈", "형식", changed(lambda m, e: e.update({"명칭": "기초 " + e["명칭"]}))
    if len(module["요소"]) > 1:
        yield "요소 하나 빠짐", "형식", changed(lambda m, e: m["요소"].pop())
    if element["수행준거"]:
        yield "수행준거 하나 빠짐", "형식", changed(lambda m, e: e["수행준거"].pop())
        first = element["수행준거"][0]
        if " " in first:
            yield "수행준거 띄어쓰기 바꿈", "띄어쓰기", changed(lambda m, e: e["수행준거"].__setitem__(0, e["수행준거"][0].replace(" ", "", 1)))
        yield "수행준거 낱말 바꿈", "띄어쓰기", changed(lambda m, e: e["수행준거"].__setitem__(0, "신속하게 " + e["수행준거"][0]))
    if re.search(r"(?<=[가-힣]) (?=[가-힣])", element["명칭"]):      # 가운뎃점 옆의 띄어쓰기는 점검이 일부러 같게 본다 — 한글 사이의 것만 바꾼다
        yield "요소 명칭 띄어쓰기 바꿈", "띄어쓰기", changed(lambda m, e: e.update({"명칭": re.sub(r"(?<=[가-힣]) (?=[가-힣])", "", e["명칭"], count=1)}))


RANK = {"-": 0, "O": 1, "△": 2, "X": 3}


def _check(spec: dict) -> dict:
    """spec → 계획서 → 점검 → {(항목, 체크): 판정}."""
    from ncs_plan.fill import build_plan
    from ncs_plan.pipeline import run_review

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "개발계획서.hwpx"
        path.write_bytes(build_plan(spec))
        result = run_review([path], roles={str(path): "plan"})
    out = {}
    for row in result.checklist:
        for name, value in (row.get("체크") or {}).items():
            key = (row["item_id"], name)      # 같은 체크가 능력단위마다 한 줄씩 나온다 — 가장 나쁜 판정을 남긴다
            if RANK.get(value, 0) >= RANK.get(out.get(key), -1):
                out[key] = value
    return out


def measure_detect() -> dict:
    """001-B: 일부러 틀리게 한 칸을 점검이 잡는가(부적합 X 또는 확인 △로 바뀌면 잡은 것)."""
    from ncs_core.ncs_catalog import catalog
    from ncs_plan.fill import spec_from_catalog

    cat = catalog()
    duties = sorted({u["code"][:8] for u in cat.all_units_with_detail()}) if hasattr(cat, "all_units_with_detail") else None
    if duties is None:
        elements = ROOT / "src/ncs_core/data/ncs_elements.tsv"
        duties = sorted({line.split("\t")[0] for line in elements.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")})
    counts = {"형식": [0, 0], "띄어쓰기": [0, 0]}
    missed, clean_flags, clean_total, skipped = [], 0, 0, []
    for duty in duties:
        try:
            spec = spec_from_catalog(duty)
            base = _check(spec)
        except Exception as error:      # noqa: BLE001 — 못 만든 세분류는 건너뛰고 적는다
            skipped.append(f"{duty}: {str(error)[:60]}")
            continue
        ncs = {key: value for key, value in base.items() if "①" in key[0] or "NCS" in key[1]}
        clean_total += len(ncs)
        clean_flags += sum(1 for value in ncs.values() if value == "X")
        for name, kind, mutated in _mutations(spec):
            after = _check(mutated)
            caught = any(after.get(key) in ("X", "△") and base.get(key) not in ("X", "△") for key in after) or \
                any(after.get(key) == "X" and base.get(key) == "△" for key in after)
            counts[kind][1] += 1
            if not caught:
                counts[kind][0] += 1
                missed.append(f"{duty} {name}")
    return {"세분류": len(duties) - len(skipped), "건너뜀": skipped, "counts": counts, "놓침": missed,
            "고치지 않은 초안의 NCS 대조 체크": clean_total, "그중 부적합": clean_flags}


# ── REQ-02-008 ────────────────────────────────────────────────────────────────
SOURCE_HEAD = re.compile(r"^\s*출\s*처\s*[:：]")


def measure_extract() -> list[dict]:
    """008-A: 원고의 '출처:' 문단 수(따로 셈) ↔ 출처 검토가 읽은 출처 줄 수."""
    from ncs_core import load_document
    from ncs_sources.extract import body_sources, figure_sources, table_sources

    out = []
    for path in MANUSCRIPTS:
        if not path.exists():
            continue
        document = load_document(path)
        raw = set()
        for index, section in enumerate(document.sections):
            for k, paragraph in enumerate(section):
                if SOURCE_HEAD.match(paragraph or ""):
                    raw.add((index, k))
        figures, tables = figure_sources(document), table_sources(document)
        used = {(e["section"], e["source_para"]) for e in figures + tables if e.get("source_para") is not None}
        body = {(e["section"], e["source_para"]) for e in body_sources(document, used) if e.get("source_para") is not None}
        read = used | body
        out.append({"원고": path.name, "출처 문단": len(raw), "읽은 출처 줄": len(read), "놓침": len(raw - read), "더 읽음": len(read - raw),
                    "놓친 예": [document.sections[i][k][:50] for i, k in sorted(raw - read)[:3]],
                    "그림": len(figures), "표": len(tables), "본문": len(body)})
    return out


TOOLS = ["ChatGPT", "Gemini", "Claude", "Notebook LM", "Copilot", "Midjourney"]
ACTIONS = ["생성함", "수정 보완함"]
DATES = ["2026. 7. 20.", "2026. 11. 3.", "2025. 12. 31."]
SOURCES = ["출처: 집필진 제작(2026)", "출처: 한국직업능력연구원(2024). 직업기초능력. p.12."]
CAPTION = "[그림 1-1] 시스템 구성도"


def _ai_cases():
    """(이름, 문단들, 기대) — 기대: '적합'(AI 표기 체크에 X·△ 없음) 또는 '문제'(X나 △가 하나 이상)."""
    for tool in TOOLS:
        for action in ACTIONS:
            for date in DATES:
                source = SOURCES[0] if action == "생성함" else SOURCES[1]
                good = f"{tool}를 활용하여 {action}. {date}"
                yield "표기 예 꼴", [source, good, CAPTION], "적합"
                yield "일자 없음", [source, f"{tool}를 활용하여 {action}.", CAPTION], "문제"
                yield "달력에 없는 날", [source, f"{tool}를 활용하여 {action}. 2026. 2. 30.", CAPTION], "문제"
                yield "출처 줄보다 위", [good, source, CAPTION], "문제"
                yield "출처 줄 안에 적음", [f"출처: 집필진 제작(2026), {tool}를 활용하여 {action}", CAPTION], "문제"
    for source in SOURCES:
        yield "AI 활용 없음", [source, CAPTION], "적합"


def measure_ai() -> dict:
    from ncs_core.source_line import find_ai_marker, find_source_line
    from ncs_sources.checks import check_entry
    from ncs_sources.extract import attach

    total = wrong = 0
    by_case: dict[str, list[int]] = {}
    missed = []
    for name, paragraphs, expected in _ai_cases():
        caption = len(paragraphs) - 1
        source = find_source_line(paragraphs, caption)
        ai = find_ai_marker(paragraphs, caption, source)
        entry = attach({"kind": "그림", "label": "그림 1-1", "caption": CAPTION, "section": 1, "caption_para": caption,
                        "source_para": source, "source_line": paragraphs[source] if source is not None else None,
                        "ai_para": ai, "ai_line": paragraphs[ai] if ai is not None else None, "region": "본문"})
        checks, _, _ = check_entry(entry)
        flagged = any(value in ("X", "△") for key, value in checks.items() if key.startswith("AI") or key == "생성·수정 구분")
        got = "문제" if flagged else "적합"
        total += 1
        tally = by_case.setdefault(name, [0, 0])
        tally[1] += 1
        if got != expected:
            wrong += 1
            tally[0] += 1
            if len(missed) < 10:
                missed.append(f"{name}: {' / '.join(paragraphs)} → {got}(기대 {expected})")
    return {"total": total, "wrong": wrong, "by_case": by_case, "틀린 예": missed}


def report() -> str:
    lines = ["# 검증 기준(P열) 실측: REQ-02-001, REQ-02-008", ""]
    fill = measure_fill()
    s = fill["요약"]
    cells = s["견준 칸"]
    human = sum(n for (group, *_), n in fill["표"].items() if group == "사람")
    base = cells - human
    strict_diff = sum(n for (group, _, _, kind), n in fill["표"].items() if group == "NCS 그대로" and kind != "띄어쓰기만 다름")
    strict_space = sum(n for (group, _, _, kind), n in fill["표"].items() if group == "NCS 그대로" and kind == "띄어쓰기만 다름")
    edit = sum(n for (group, *_), n in fill["표"].items() if group == "다듬는 칸")
    lines += ["## REQ-02-001", "", "### A. 자동 입력 — 초안과 사람이 만든 최종 결과(T03, 세분류 20010104)", "",
              f"견준 칸 {cells}개 가운데 사람이 채우는 칸의 차이 {human}개를 빼고 {base}개를 분모로 삼았다(어림).", "",
              "| 구분 | 차이 | 비율 | 기준 |", "|---|---|---|---|",
              f"| NCS를 그대로 옮기는 칸: 글자가 다르거나 한쪽에만 있음 | {strict_diff} | {pct(strict_diff, base)} | 0.5% 이내 |",
              f"| NCS를 그대로 옮기는 칸: 띄어쓰기만 다름 | {strict_space} | {pct(strict_space, base)} | 5% 이내 |",
              f"| 사람이 다듬을 수 있는 칸(학습 목표, 학습모듈의 목표)의 차이 | {edit} | {pct(edit, base)} | 참고 |", "",
              "| 묶음 | 구역 | 칸 | 차이 | 건수 |", "|---|---|---|---|---|"]
    lines += [f"| {g} | {area} | {name} | {kind} | {n} |" for (g, area, name, kind), n in sorted(fill["표"].items())]
    lines.append("")
    detect = measure_detect()
    lines += ["### B. 점검 탐지 — 칸 하나를 일부러 틀리게 한 계획서(합성)", "",
              f"세분류 {detect['세분류']}개" + (f", 건너뜀 {len(detect['건너뜀'])}개" if detect["건너뜀"] else ""), "",
              "| 종류 | 넣은 오류 | 놓침 | 오차율 | 기준 |", "|---|---|---|---|---|"]
    for kind, limit in (("형식", "0.5%"), ("띄어쓰기", "5%")):
        wrong, total = detect["counts"][kind]
        lines.append(f"| {'형식·필수항목·코드·명칭' if kind == '형식' else '띄어쓰기·용어'} | {total} | {wrong} | {pct(wrong, total)} | {limit} 이내 |")
    lines += ["", f"- 고치지 않은 초안의 NCS 대조 체크 {detect['고치지 않은 초안의 NCS 대조 체크']}개 중 부적합(오탐) {detect['그중 부적합']}개"]
    if detect["놓침"]:
        lines.append("- 놓친 것: " + "; ".join(detect["놓침"][:20]))
    if detect["건너뜀"]:
        lines.append("- 건너뛴 세분류: " + "; ".join(detect["건너뜀"]))
    lines += ["", "## REQ-02-008", "", "### A. 출처 줄 추출 — 표본 원고", "",
              "| 원고 | '출처:' 문단(따로 셈) | 읽은 출처 문단 | 놓침 | 더 읽음 | 그림 | 표 | 본문 출처 줄 |", "|---|---|---|---|---|---|---|---|"]
    extract = measure_extract()
    for row in extract:
        lines.append(f"| {row['원고'][:40]} | {row['출처 문단']} | {row['읽은 출처 줄']} | {row['놓침']} | {row['더 읽음']} | {row['그림']} | {row['표']} | {row['본문']} |")
    raw, diff = sum(r["출처 문단"] for r in extract), sum(r["놓침"] + r["더 읽음"] for r in extract)
    lines += ["", f"- 합계: 출처 문단 {raw}개, 놓침과 더 읽음 {diff}개, 오차율 {pct(diff, raw)} (기준 5% 이내)"]
    lines += [f"- 놓친 예({row['원고'][:20]}): " + " / ".join(row["놓친 예"]) for row in extract if row["놓친 예"]]
    lines.append("")
    ai = measure_ai()
    lines += ["### B. AI 표기 누락·형식 오류 탐지 — 정답을 아는 합성 입력", "", "| 경우 | 수 | 틀림 |", "|---|---|---|"]
    lines += [f"| {name} | {total} | {wrong} |" for name, (wrong, total) in ai["by_case"].items()]
    lines += ["", f"- 합계 {ai['total']}건 중 틀림 {ai['wrong']}건, 오차율 {pct(ai['wrong'], ai['total'])} (기준 5% 이내)"]
    if ai["틀린 예"]:
        lines += ["- 틀린 예:"] + [f"  - {text}" for text in ai["틀린 예"]]
    lines += ["", "## 읽을 때 주의할 점", "",
              "- 001-B와 008-B는 합성 입력이다. 정답은 스크립트가 꼴에 따라 정했고, 사람이 실제 원고에 매긴 정답이 아니다.",
              "- 001-A는 세분류 한 건(20010104)이다. 최종 결과는 사람이 고친 문서라 차이가 모두 자동 입력의 오류는 아니다. 분모는 칸 종류별로 세지 못해 어림이다.",
              "- 008-A는 문단 자리만 견준다. 한 출처 줄을 그림 여럿이 함께 쓰면 한 번으로 센다. 읽은 내용(저자, 연도 등)이 맞는지는 재지 않았다. 참고 자료 목록은 넣지 않았다.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    text = report()
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""여러 원고에 10개 엔진을 모두 돌려 결과를 .xlsx 한 파일로 모은다.

용도: 구현한 규칙이 다른 문서(초고본·수정본·에디팅완료본, hwp·hwpx)에서도 안정적으로 동작하는지 확인.
정답(기대값)이 없으므로 정확도는 판정하지 않고, 판정 분포·버전 간 변화·형식(hwp↔hwpx) 차이·실행 오류를 보여 주며
사람이 채울 '사람 판정' 열을 비워 둔다.

  python scripts/batch_review.py run  --root 폴더 --work 작업폴더 [--budget 150]   # 문서×엔진 단위로 체크포인트(json)
  python scripts/batch_review.py xlsx --root 폴더 --work 작업폴더 --out 결과.xlsx    # 체크포인트를 모아 xlsx 작성

run은 --budget 초가 지나면 새 단위를 시작하지 않고 끝나므로(원격 셸 시간 제한용) 끝날 때까지 반복 실행한다.
표준국어대사전 API는 STDICT_API_KEY가 없으면 자동으로 쓰지 않는다(차례 ②는 △).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import traceback
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ncs_core import FAIL, PASS, UNDECIDED, load_document  # noqa: E402
from ncs_core.sheet import NOT_CHECKED  # noqa: E402
from ncs_service.registry import ENGINES  # noqa: E402

ERROR = "오류"
CODE = re.compile(r"LM\d{10}(?:_\d+v\d+)?")  # 버전(_23v3)이 빠진 파일명도 있다
VERSION_ORDER = ["초고본·원고", "초고본·에디팅완료", "수정본·원고", "수정본·에디팅완료"]
EXCLUDE_WORDS = ("의견서", "개발계획서", "수정내역서")


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


# ──────────────────────────── 문서 목록 ────────────────────────────


@dataclass
class Doc:
    doc_id: str          # 작업 폴더 이름으로 쓰는 식별자
    path: str            # root 기준 상대 경로
    module_code: str
    title: str
    version: str         # 초고본·원고 / 초고본·에디팅완료 / 수정본·원고 / 수정본·에디팅완료 / 기타
    fmt: str             # hwp / hwpx
    size_mb: float
    pair_key: str        # 확장자만 다른 hwp·hwpx 짝을 묶는 키
    duplicate: str       # 같은 내용의 다른 사본으로 보이면 설명, 아니면 ""
    plan: str            # 사용한 개발계획서 상대 경로("" = 없음)
    note: str = ""       # 파일명 보완 등 실행 전 조치


def classify_version(parts: list[str], name: str) -> str:
    joined = " ".join(parts)
    stage = "초고본" if "초고본" in joined else "수정본" if "수정본" in joined else ""
    edited = any(word in joined or word in name for word in ("검수 완료", "에디팅 완료", "검토 완료", "편집 완료", "심의본"))
    if not stage:
        return "기타"
    return f"{stage}·{'에디팅완료' if edited else '원고'}"


def title_of(name: str, code: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"^\(.*?\)\s*\d*\.?\s*", "", stem)          # "(수정본 검토 완료) 6. " 제거
    stem = stem.replace(code, "").strip("_ ")
    stem = re.sub(r"^\d{2}v\d_?", "", stem)                   # "23v3_" 제거
    stem = re.sub(r"\((수정본_)?[가-힣]{2,4}\)\s*(수정)?$", "", stem)  # "(이완기)", "(수정본_이완기) 수정" 제거
    return stem.strip("_ ") or Path(name).stem


def find_plans(root: Path) -> dict[str, dict[str, Path]]:
    """{세분류 8자리: {형식: 경로}}"""
    plans: dict[str, dict[str, Path]] = defaultdict(dict)
    for path in root.rglob("*"):
        if path.suffix.lower() not in (".hwp", ".hwpx") or "개발계획서" not in nfc(path.name):
            continue
        match = re.search(r"\((\d{8})\)", nfc(path.name))
        if match:
            plans[match.group(1)].setdefault(path.suffix.lower()[1:], path)
    return plans


def scan(root: Path) -> list[Doc]:
    plans = find_plans(root)
    docs: list[Doc] = []
    for path in sorted(root.rglob("*"), key=lambda p: nfc(str(p))):
        if path.suffix.lower() not in (".hwp", ".hwpx"):
            continue
        name = nfc(path.name)
        if any(word in name for word in EXCLUDE_WORDS):
            continue
        codes = list(dict.fromkeys(CODE.findall(name)))
        if len(codes) != 1:
            continue
        code = codes[0]
        rel = nfc(str(path.relative_to(root)))
        parts = rel.split("/")[:-1]
        fmt = path.suffix.lower()[1:]
        plan_set = plans.get(code[2:10], {})
        plan = plan_set.get(fmt) or next(iter(plan_set.values()), None)
        pair_key = nfc(str(path.relative_to(root).with_suffix("")))
        docs.append(Doc(
            doc_id="", path=rel, module_code=code, title=title_of(name, code),
            version=classify_version(parts, name), fmt=fmt,
            size_mb=round(path.stat().st_size / 1_048_576, 1), pair_key=pair_key, duplicate="",
            plan=nfc(str(plan.relative_to(root))) if plan else "",
        ))
    # 파일명에 버전(_23v3)이 없는 원고: 같은 능력단위의 다른 파일에서 보완한다(엔진은 완전한 코드를 요구한다)
    full_codes = {c[:12]: c for d in docs for c in [d.module_code] if "_" in c}
    for doc in docs:
        if "_" not in doc.module_code:
            full = full_codes.get(doc.module_code)
            doc.note = (f"파일명에 모듈 코드 버전이 없어 {full}로 보완" if full
                        else "파일명에 모듈 코드 버전이 없고 보완할 형제 파일도 없음 → 엔진 실행 불가")
            if full:
                doc.module_code = full
    # 식별자: 모듈코드(10자리)_버전_형식(_n)
    seen: Counter = Counter()
    for doc in docs:
        base = f"{doc.module_code[:12]}_{doc.version.replace('·', '-')}_{doc.fmt}"
        seen[base] += 1
        doc.doc_id = base if seen[base] == 1 else f"{base}_{seen[base]}"
    # 중복: 같은 모듈·버전·형식이 둘 이상이면 서로를 가리킨다(" 수정.hwpx" 재업로드, 상위 폴더 복사본 등)
    groups: dict[tuple, list[Doc]] = defaultdict(list)
    for doc in docs:
        groups[(doc.module_code, doc.version, doc.fmt)].append(doc)
    for group in groups.values():
        if len(group) > 1:
            for doc in group:
                others = [d.path.split("/")[-1] for d in group if d is not doc]
                doc.duplicate = "같은 모듈·버전의 다른 사본: " + " / ".join(others)
    return docs


# ──────────────────────────── 실행 ────────────────────────────


def item_columns() -> list[tuple[str, str, str, str, bool]]:
    """[(엔진, 구성요소, 번호, 체크 항목, 구현됨)] — 확인서 순서."""
    out = []
    for check, engine in ENGINES.items():
        sheet = import_module(engine.package + ".sheet")
        for item in sheet.ITEMS:
            out.append((check, sheet.COMPONENT, item.no, item.text, bool(item.item_ids)))
    return out


def document_facts(document) -> dict:
    return {
        "format": document.format,
        "sections": len(document.sections),
        "paragraphs": sum(len(s) for s in document.sections),
        "tables": len(document.tables),
        "pictures": len(document.pictures) if document.pictures else 0,
        "numbers": document.numbers is not None,
        "page_breaks": document.page_breaks is not None,
    }


def to_jsonable(value):
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def run_units(root: Path, work: Path, budget: float) -> None:
    started = time.monotonic()
    docs = scan(root)
    work.mkdir(parents=True, exist_ok=True)
    (work / "docs.json").write_text(json.dumps([asdict(d) for d in docs], ensure_ascii=False, indent=1), "utf-8")
    pending = [(d, check) for d in docs for check in ENGINES if not (work / d.doc_id / f"{check}.json").exists()]
    print(f"문서 {len(docs)}개, 남은 단위 {len(pending)}개")
    cache: dict[str, tuple] = {}
    for doc, check in pending:
        if time.monotonic() - started > budget:
            print("시간 예산 소진 — 다시 실행하면 이어서 합니다")
            return
        out_dir = work / doc.doc_id
        out_dir.mkdir(exist_ok=True)
        record = {"doc_id": doc.doc_id, "check": check}
        t0 = time.monotonic()
        try:
            if doc.doc_id not in cache:
                cache.clear()  # 문서 하나만 메모리에 둔다
                load_t0 = time.monotonic()
                manuscript = load_document(root / doc.path)
                plan = load_document(root / doc.plan) if doc.plan else None
                cache[doc.doc_id] = (manuscript, plan)
                (out_dir / "document.json").write_text(json.dumps({
                    **document_facts(manuscript), "load_seconds": round(time.monotonic() - load_t0, 1),
                    "plan_sections": len(plan.sections) if plan else None,
                }, ensure_ascii=False, indent=1), "utf-8")
            manuscript, plan = cache[doc.doc_id]
            module = ENGINES[check].load()
            if "plan" in ENGINES[check].required and plan is None:
                raise ValueError("개발계획서 없음")
            context = module.prepare_review(manuscript, plan, module_code=doc.module_code)
            result = module.evaluate_review(context)
            record.update(ok=True, sheet=result.sheet, findings=len(result.findings), rows=len(result.checklist),
                          diagnostics=to_jsonable(result.diagnostics))
        except Exception as error:  # noqa: BLE001 — 어떤 예외든 결과로 남긴다
            record.update(ok=False, error=f"{type(error).__name__}: {error}", traceback=traceback.format_exc())
        record["seconds"] = round(time.monotonic() - t0, 1)
        (out_dir / f"{check}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), "utf-8")
        state = "OK" if record["ok"] else "ERR"
        print(f"{doc.doc_id:40s} {check:11s} {state} {record['seconds']:6.1f}s")
    print("모든 단위 완료")


# ──────────────────────────── xlsx ────────────────────────────


def load_results(work: Path) -> tuple[list[Doc], dict[str, dict], dict[str, dict]]:
    docs = [Doc(**d) for d in json.loads((work / "docs.json").read_text("utf-8"))]
    results, facts = {}, {}
    for doc in docs:
        folder = work / doc.doc_id
        facts[doc.doc_id] = json.loads((folder / "document.json").read_text("utf-8")) if (folder / "document.json").exists() else {}
        results[doc.doc_id] = {}
        for check in ENGINES:
            file = folder / f"{check}.json"
            if file.exists():
                results[doc.doc_id][check] = json.loads(file.read_text("utf-8"))
    return docs, results, facts


def verdict_of(result: dict | None, no: str, implemented: bool) -> str:
    if result is None:
        return "미실행"
    if not result["ok"]:
        return ERROR
    for row in result["sheet"]:
        if row["번호"] == no:
            return row["검수결과"]
    return NOT_CHECKED if not implemented else "미실행"


def remark_of(result: dict | None, no: str) -> str:
    if not result or not result["ok"]:
        return result["error"] if result else ""
    for row in result["sheet"]:
        if row["번호"] == no:
            return row["비고"]
    return ""


def git_commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "?"


def build_xlsx(root: Path, work: Path, out: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    docs, results, facts = load_results(work)
    columns = item_columns()
    fills = {
        PASS: PatternFill("solid", fgColor="D9EAD3"), FAIL: PatternFill("solid", fgColor="F4CCCC"),
        UNDECIDED: PatternFill("solid", fgColor="FFF2CC"), NOT_CHECKED: PatternFill("solid", fgColor="EEEEEE"),
        ERROR: PatternFill("solid", fgColor="D9D2E9"), "미실행": PatternFill("solid", fgColor="FFFFFF"),
    }
    head_font = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="DDEBF7")
    wrap = Alignment(wrap_text=True, vertical="top")

    wb = Workbook()

    def new_sheet(title: str, header: list[str], widths: dict[int, int] | None = None, header_rows: int = 1):
        ws = wb.create_sheet(title)
        ws.append(header)
        for cell in ws[1]:
            cell.font, cell.fill = head_font, head_fill
        ws.freeze_panes = ws.cell(row=header_rows + 1, column=1)
        for idx, width in (widths or {}).items():
            ws.column_dimensions[get_column_letter(idx)].width = width
        return ws

    def paint(ws, min_row: int, min_col: int):
        for row in ws.iter_rows(min_row=min_row, min_col=min_col):
            for cell in row:
                if cell.value in fills:
                    cell.fill = fills[cell.value]

    verdicts = {d.doc_id: {(c, no): verdict_of(results[d.doc_id].get(c), no, impl) for c, _, no, _, impl in columns} for d in docs}
    label = {(c, no): f"{comp} {no}" for c, comp, no, _, _ in columns}

    # 0. 설정
    ws = wb.active
    ws.title = "설정"
    for row in [
        ("실행 일시", datetime.now().strftime("%Y-%m-%d %H:%M")), ("대상 폴더", nfc(str(root))), ("작업 폴더", nfc(str(work))),
        ("코드 버전", git_commit()), ("문서 수", len(docs)), ("엔진", ", ".join(ENGINES)),
        ("체크 항목", f"{len(columns)}개 (구현 {sum(1 for c in columns if c[4])}개)"),
        ("제외", "파일명에 " + " / ".join(EXCLUDE_WORDS) + " 포함, 모듈코드 없는 파일"),
        ("표준국어대사전 API", "미사용 — 차례 ②는 저장 목록에 없는 단어를 판단불가(△)로 둠"),
        ("판정 값", "적합 / 부적합 / 판단불가 / 미검사(규칙 미구현) / 오류(엔진 예외) / 미실행(체크포인트 없음)"),
        ("주의", "정답이 없는 실험이다. 부적합·판단불가는 원고 문제일 수도, 규칙 오탐일 수도 있다 → '상세비고' 시트의 사람 판정 열로 가린다"),
    ]:
        ws.append(row)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 120

    # 1. 문서목록
    ws = new_sheet("문서목록", ["번호", "문서ID", "모듈코드", "모듈명", "버전", "형식", "크기(MB)", "중복", "개발계획서", "구역 수", "문단 수", "표 수",
                             "그림 수", "자동번호 읽음", "쪽나누기 읽음", "읽기(초)", "경로"],
                   {2: 36, 4: 26, 5: 18, 8: 40, 9: 40, 17: 90})
    for i, d in enumerate(docs, 1):
        f = facts[d.doc_id]
        ws.append([i, d.doc_id, d.module_code, d.title, d.version, d.fmt, d.size_mb, d.duplicate, d.plan.split("/")[-1],
                   f.get("sections"), f.get("paragraphs"), f.get("tables"), f.get("pictures"),
                   "O" if f.get("numbers") else "X" if f else "", "O" if f.get("page_breaks") else "X" if f else "", f.get("load_seconds"), d.path])

    # 2. 실행요약
    ws = new_sheet("실행요약", ["문서ID", "모듈명", "버전", "형식", "적합", "부적합", "판단불가", "미검사", "오류", "지적사항 수", "총 시간(초)"]
                   + [f"{c} (초)" for c in ENGINES], {1: 36, 2: 26, 3: 18})
    for d in docs:
        counts = Counter(verdicts[d.doc_id].values())
        res = results[d.doc_id]
        ws.append([d.doc_id, d.title, d.version, d.fmt, counts[PASS], counts[FAIL], counts[UNDECIDED], counts[NOT_CHECKED], counts[ERROR],
                   sum(r.get("findings", 0) for r in res.values() if r["ok"]),
                   round(sum(r["seconds"] for r in res.values()) + facts[d.doc_id].get("load_seconds", 0), 1)]
                  + [res[c]["seconds"] if c in res else None for c in ENGINES])

    # 3. 판정매트릭스
    ws = new_sheet("판정매트릭스", ["문서ID", "모듈명", "버전", "형식"] + [comp for _, comp, _, _, _ in columns], {1: 36, 2: 26, 3: 18}, header_rows=2)
    ws.append(["", "", "", ""] + [no + ("" if impl else "(미구현)") for _, _, no, _, impl in columns])
    for cell in ws[2]:
        cell.font, cell.fill = head_font, head_fill
    for d in docs:
        ws.append([d.doc_id, d.title, d.version, d.fmt] + [verdicts[d.doc_id][(c, no)] for c, _, no, _, _ in columns])
    for idx in range(5, 5 + len(columns)):
        ws.column_dimensions[get_column_letter(idx)].width = 9
    paint(ws, 3, 5)

    # 4. 항목별집계
    ws = new_sheet("항목별집계", ["엔진", "구성요소", "번호", "체크 항목", "구현", "적합", "부적합", "판단불가", "미검사", "오류",
                               "부적합률(판정 중)", "hwpx 판단불가", "hwp 판단불가", "주요 비고(체크 이름별 건수, 상위 3)"], {4: 60, 14: 90})
    for c, comp, no, text, impl in columns:
        col = Counter(verdicts[d.doc_id][(c, no)] for d in docs)
        decided = col[PASS] + col[FAIL] + col[UNDECIDED]
        tri = {fmt: sum(1 for d in docs if d.fmt == fmt and verdicts[d.doc_id][(c, no)] == UNDECIDED) for fmt in ("hwpx", "hwp")}
        reasons: Counter = Counter()
        for d in docs:
            if verdicts[d.doc_id][(c, no)] in (FAIL, UNDECIDED):
                for line in remark_of(results[d.doc_id].get(c), no).split("\n"):
                    head = line.split(":")[0].strip()
                    if head and not head.startswith("—"):
                        reasons[head] += 1
        ws.append([c, comp, no, text, "O" if impl else "X", col[PASS], col[FAIL], col[UNDECIDED], col[NOT_CHECKED], col[ERROR],
                   f"{col[FAIL] / decided:.0%}" if decided else "", tri["hwpx"], tri["hwp"],
                   " / ".join(f"{k}({v})" for k, v in reasons.most_common(3))])

    # 5. 상세비고
    ws = new_sheet("상세비고", ["문서ID", "모듈명", "버전", "형식", "구성요소", "번호", "판정", "비고", "사람 판정(정확/오탐/미탐)", "메모"],
                   {1: 36, 2: 24, 3: 18, 8: 100, 9: 20, 10: 30})
    for d in docs:
        for c, comp, no, _, impl in columns:
            v = verdicts[d.doc_id][(c, no)]
            if v == NOT_CHECKED:
                continue
            ws.append([d.doc_id, d.title, d.version, d.fmt, comp, no, v, remark_of(results[d.doc_id].get(c), no), "", ""])
    for row in ws.iter_rows(min_row=2):
        row[7].alignment = wrap
    paint(ws, 2, 7)
    ws.auto_filter.ref = ws.dimensions

    # 6. 버전변화 (hwpx만 — 형식 차이를 섞지 않기 위해)
    ws = new_sheet("버전변화", ["모듈코드", "모듈명", "구성요소", "번호"] + VERSION_ORDER + ["변화"], {2: 24, 5: 18, 6: 18, 7: 18, 8: 18, 9: 30})
    by_module: dict[str, dict[str, Doc]] = defaultdict(dict)
    for d in docs:
        if d.fmt == "hwpx" and d.version in VERSION_ORDER:
            by_module[d.module_code].setdefault(d.version, d)  # 사본이 여럿이면 경로순 첫 번째
    for code, stages in sorted(by_module.items()):
        if len(stages) < 2:
            continue
        title = next(iter(stages.values())).title
        for c, comp, no, _, impl in columns:
            if not impl:
                continue
            seq = [verdicts[stages[v].doc_id][(c, no)] if v in stages else "" for v in VERSION_ORDER]
            present = [s for s in seq if s]
            if len(set(present)) > 1:
                ws.append([code, title, comp, no] + seq + [" → ".join(present)])
    paint(ws, 2, 5)
    ws.auto_filter.ref = ws.dimensions

    # 7. 형식비교 (같은 파일의 hwp ↔ hwpx)
    ws = new_sheet("형식비교", ["모듈코드", "모듈명", "버전", "구성요소", "번호", "hwp", "hwpx", "비고(hwp)", "비고(hwpx)"],
                   {2: 24, 3: 18, 8: 60, 9: 60})
    pairs: dict[str, dict[str, Doc]] = defaultdict(dict)
    for d in docs:
        pairs[d.pair_key][d.fmt] = d
    diff_counter: Counter = Counter()
    for key, both in sorted(pairs.items()):
        if len(both) < 2:
            continue
        hwp, hwpx = both["hwp"], both["hwpx"]
        for c, comp, no, _, impl in columns:
            if not impl:
                continue
            a, b = verdicts[hwp.doc_id][(c, no)], verdicts[hwpx.doc_id][(c, no)]
            if a != b:
                diff_counter[(comp, no, f"{a}→{b}")] += 1
                ws.append([hwp.module_code, hwp.title, hwp.version, comp, no, a, b,
                           remark_of(results[hwp.doc_id].get(c), no), remark_of(results[hwpx.doc_id].get(c), no)])
    ws.append([])
    ws.append(["[요약] 항목별 hwp→hwpx 판정 차이 건수"])
    for (comp, no, change), n in sorted(diff_counter.items()):
        ws.append(["", "", "", comp, no, change, n])
    paint(ws, 2, 6)
    for row in ws.iter_rows(min_row=2):
        row[7].alignment = row[8].alignment = wrap

    # 8. 실행오류
    ws = new_sheet("실행오류", ["문서ID", "형식", "엔진", "예외", "traceback"], {1: 36, 4: 60, 5: 120})
    for d in docs:
        for c, r in results[d.doc_id].items():
            if not r["ok"]:
                ws.append([d.doc_id, d.fmt, c, r["error"], r["traceback"]])
    for row in ws.iter_rows(min_row=2):
        row[4].alignment = wrap

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"저장: {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["scan", "run", "xlsx"])
    parser.add_argument("--root", required=True, help="원고·개발계획서가 든 폴더(하위 폴더 포함)")
    parser.add_argument("--work", required=True, help="체크포인트(json) 작업 폴더")
    parser.add_argument("--out", help="xlsx 출력 경로")
    parser.add_argument("--budget", type=float, default=150, help="run: 이 시간(초)이 지나면 새 단위를 시작하지 않는다")
    args = parser.parse_args()
    root, work = Path(args.root), Path(args.work)
    if args.command == "scan":
        for d in scan(root):
            print(f"{d.doc_id:45s} {d.version:12s} {d.size_mb:7.1f}MB  계획서={'O' if d.plan else 'X'}  {d.duplicate}")
    elif args.command == "run":
        run_units(root, work, args.budget)
    else:
        if not args.out:
            parser.error("xlsx에는 --out이 필요합니다")
        build_xlsx(root, work, Path(args.out))


if __name__ == "__main__":
    main()

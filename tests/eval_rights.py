"""권리 증빙 점검(REQ-02-014) 평가 세트 — 누락을 심은 서류 묶음으로 탐지 오차율과 기한 알림 누락을 잰다.

    python tests/eval_rights.py [원고.hwpx …] [--cases 10] [--seed 20261117] [--json 결과.json] [--md 결과.md]

정의서 검증 기준: 증빙 누락 탐지 오차율 5% 이내, 기한(4주) 경과 항목 알림 누락 0건.

평가 세트는 두 갈래다.
  합성 원고   그림마다 출처 줄·AI 표기·제작 방식을 정해 만든 원고 3권. 출처 미표기, AI 표기 불일치까지 심는다
  실제 원고   인자로 준 hwpx(없으면 samples/의 원고). 그림 목록은 원고에서 읽고 서류만 만든다. 번호가 겹치거나 비어 있는
              실제 캡션에서도 목록과 제대로 짝짓는지를 본다
원고마다 '모든 증빙이 갖춰진 서류 묶음'을 만든 뒤 사례마다 누락을 몇 개씩 심는다(목록에서 빼기, 목록에만 있는 행, 제작 방식 지우기,
제작 목록·이용허락 동의서·결과물 현황에서 빼기, 양도 동의서·서약서 미제출, 목록에만 AI 표시). 서류의 표기는 일부러 흔든다
(✓·V·○·●, 제목의 띄어쓰기, 괄호 없는 그림 번호).

정답은 점검 코드를 쓰지 않고 '심은 것'에서 정한다(expected_row). 채점 단위는 현황표의 한 줄(그림 한 개):
그 줄의 부적합 지적 종류가 정답과 같으면 맞음. 오차율 = 틀린 줄 ÷ 전체 줄. 심은 누락별 재현율·정밀도도 함께 낸다.
판단불가(사람 확인)는 채점하지 않는다.

한계: 서류는 실제 제출본이 아니라 양식과 같은 칸 배치로 만든 것이다. 실제 원고의 그림 목록은 점검 코드와 같은 읽기
(ncs_core.figures)에서 왔으므로 캡션을 못 읽은 그림은 이 평가에 잡히지 않는다 — '캡션 수 대조'가 그 어림이다.
"""

import argparse
import json
import random
import re
import sys
import tempfile
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rights_samples as S  # noqa: E402
from ncs_core.documents import load_document  # noqa: E402
from ncs_core.figures import manuscript_figures  # noqa: E402
from ncs_rights.check import Options  # noqa: E402
from ncs_rights.service import run  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FAIL = "부적합"
MARKS = ("✓", "V", "○", "●")
COLUMN = {"author_made": 3, "commissioned": 5, "public_license": 6, "blanket_license": 7, "prior_module": 8, "ai": 9}
GHOST = "원고에 없는 자료"
FIRST_REVIEW, SUBMITTED, TODAY = date(2026, 10, 1), date(2026, 10, 20), date(2026, 11, 17)
RAW_CAPTION = re.compile(r"^\s*[\[〔]\s*그림\s*\d+\s*[-–—－‐]\s*\d*\s*[\]〕]")
AI_LINES = ("ChatGPT를 활용하여 생성함. 2026. 7. 20.", "Gemini를 활용하여 수정 보완함. 2026. 8. 1.")
SOURCES = {"author_made": "출처: 집필진 제작(2026)", "commissioned": "출처: 집필진 제작(2026)",
           "blanket_license": "출처: 홍길동(2024). 직업교육 사례집. 한국출판. p.12.",
           "public_license": "출처: 고용노동부(2025). 직업훈련 통계. 공공누리 홈페이지(https://www.kogl.or.kr)에서 2026. 7. 1. 검색. 공공누리 제1유형.",
           "prior_module": "출처: 교육부(2018). 객실 예약 관리(LM1203020201_16v2). 한국직업능력개발원. p.6."}


# ── 원고 ──────────────────────────────────────────────────────────────────────

def synthetic_manuscript(folder: Path, number: int, rng: random.Random) -> tuple[Path, list[dict]]:
    """합성 원고 1권과 그 그림의 사실(번호·제목·제작 방식·출처 줄 유무·AI 표기 유무)."""
    methods = list(SOURCES)
    figures = []
    for index in range(12):
        method = methods[(index + number) % len(methods)]
        no_source = method in ("public_license", "prior_module") and rng.random() < 0.35      # 출처 미표기를 심는다
        marked = rng.random() < 0.3
        figures.append({"label": f"그림 {index // 4 + 1}-{index % 4 + 1}", "title": f"합성 {number}권 자료 {index + 1}", "method": method,
                        "has_source": not no_source, "marked": marked, "ai_line": AI_LINES[index % 2] if marked else "",
                        "ai_listed": marked and rng.random() < 0.75})                            # 나머지는 AI 표시 불일치
    tuples = [(f["label"], f["title"], SOURCES[f["method"]] if f["has_source"] else "", f["ai_line"]) for f in figures]
    return S.manuscript(folder, tuples, name=f"원고_합성{number}_LM1203020201_24v3.hwpx"), figures


def real_manuscript(path: Path) -> list[dict]:
    """실제 원고의 그림 — 제작 방식은 서류를 낼 것이 있는 세 가지를 돌려 가며 붙인다(출처 줄에 기대는 공공누리·기개발은 쓰지 않는다)."""
    methods = ("author_made", "commissioned", "blanket_license")
    return [{"label": figure.label, "title": figure.title, "method": methods[index % 3], "has_source": bool(figure.source_line),
             "marked": figure.ai is not None, "ai_line": "", "ai_listed": figure.ai is not None}
            for index, figure in enumerate(manuscript_figures(load_document(path)))]


def caption_count(path: Path) -> tuple[int, int]:
    """(점검 코드가 읽은 그림 수, 문단 첫머리가 '[그림 N-M]'인 문단 수) — 캡션을 놓치는지 보는 어림."""
    document = load_document(path)
    raw = sum(bool(RAW_CAPTION.match(text or "")) for paragraphs in document.sections for text in paragraphs)
    return len(manuscript_figures(document)), raw


# ── 사례 ──────────────────────────────────────────────────────────────────────

def new_case(figures: list[dict]) -> dict:
    """아무것도 심지 않은 사례 — 모든 증빙이 갖춰진 상태."""
    return {"rows": [{**figure, "dropped": False, "cleared": False, "in_production": True, "in_license": True, "in_ai": True}
                     for figure in figures],
            "ghosts": 0, "has_list": True, "transfer_author": True, "transfer_maker": True, "pledge": True, "seeded": []}


def seed(case: dict, rng: random.Random, count: int) -> dict:
    """사례에 누락 count가지를 심는다. 같은 그림에 겹쳐 심지 않는다."""
    free = [index for index, row in enumerate(case["rows"])]
    rng.shuffle(free)

    def take(want=lambda row: True):
        for index in free:
            if want(case["rows"][index]):
                free.remove(index)
                return case["rows"][index]
        return None

    kinds = ["drop", "ghost", "clear", "production", "license", "ai_list", "ai_result", "author", "maker", "pledge"]
    rng.shuffle(kinds)
    for kind in kinds[:count]:
        row = None
        if kind == "drop" and (row := take()):
            row["dropped"] = True
        elif kind == "ghost":
            case["ghosts"] += 1
        elif kind == "clear" and (row := take()):
            row["cleared"] = True
        elif kind == "production" and (row := take(lambda r: r["method"] == "commissioned")):
            row["in_production"] = False
        elif kind == "license" and (row := take(lambda r: r["method"] == "blanket_license")):
            row["in_license"] = False
        elif kind == "ai_list" and (row := take(lambda r: not r["marked"])):
            row["ai_listed"] = True                       # 목록에만 AI 표시(원고에는 표기 없음). 결과물 현황에는 있다
        elif kind == "ai_result" and (row := take(lambda r: not r["marked"])):
            row["ai_listed"], row["in_ai"] = True, False   # 목록에 AI 표시 + 결과물 현황에는 없음
        elif kind == "author":
            case["transfer_author"] = False
        elif kind == "maker":
            case["transfer_maker"] = False
        elif kind == "pledge":
            case["pledge"] = False
        else:
            continue
        case["seeded"].append(kind)
    return case


def expected_row(row: dict, case: dict) -> Counter:
    """심은 것에서 정한 정답 — 이 그림 줄에 나와야 하는 부적합 지적의 종류와 개수. (docs/RIGHTS_CHECK.md '제작 방식별로 보는 것')"""
    want: Counter = Counter()
    if not case["has_list"]:
        return want                                     # 목록이 없으면 그림 줄은 판단불가, 부적합은 '목록 미제출' 한 건뿐
    listed = not row["dropped"]
    method = row["method"] if listed and not row["cleared"] else None
    ai_listed = listed and not row["cleared"] and row["ai_listed"]
    if not listed:
        want["목록 누락"] += 1
    if listed and row["cleared"]:
        want["제작 방식 미표시"] += 1
    if method == "author_made" and not case["transfer_author"]:
        want["증빙 누락"] += 1
    if method == "commissioned":
        want["증빙 누락"] += (not row["in_production"]) + (not case["transfer_maker"])
    if method == "blanket_license" and not row["in_license"]:
        want["증빙 누락"] += 1
    if method in ("public_license", "prior_module") and not row["has_source"]:
        want["출처 미표기"] += 1
    if row["marked"] and listed and not ai_listed:
        want["AI 표시 불일치"] += 1
    if ai_listed and not row["marked"]:
        want["AI 표기 누락"] += 1
    if row["marked"] or ai_listed:
        if not case["pledge"]:
            want["증빙 누락"] += 1
        elif not row["in_ai"]:
            want["현황 누락"] += 1
    return +want


def expected_ghost(case: dict) -> Counter:
    return Counter({"원고에 없음": 1, **({} if case["transfer_author"] else {"증빙 누락": 1})})


def _shown(row: dict, index: int) -> str:
    """서류에 적는 제목 칸 — 표기를 흔든다: 다섯째마다 띄어쓰기를 빼고, 일곱째마다 괄호 없이 적는다."""
    title = row["title"].replace(" ", "") if index % 5 == 4 else row["title"]
    return f"{row['label']} {title}" if index % 7 == 6 else f"[{row['label']}] {title}"


def write_forms(folder: Path, case: dict) -> list[Path]:
    """사례 → 제출 서류 파일들(계약서 붙임 2·3 한 파일, 제작 목록, 서약서 붙임)."""
    inclusion, production, licenses, results = [], [], [], []
    for index, row in enumerate(case["rows"]):
        shown = _shown(row, index)
        if not row["dropped"]:
            cells = [""] * 9
            if not row["cleared"]:
                cells[COLUMN[row["method"]] - 2] = MARKS[index % len(MARKS)]
                if row["ai_listed"]:
                    cells[COLUMN["ai"] - 2] = MARKS[(index + 1) % len(MARKS)]
            inclusion.append([str(len(inclusion) + 1), shown, *cells])
        if row["method"] == "commissioned" and row["in_production"]:
            production.append([str(len(production) + 1), shown, "", S.M])
        if row["method"] == "blanket_license" and row["in_license"]:
            licenses.append([str(len(licenses) + 1), shown, "홍길동(2024). 직업교육 사례집. 한국출판. p.12.", "평가용 학습모듈"])
        if (row["marked"] or row["ai_listed"]) and row["in_ai"]:
            results.append([str(len(results) + 1), f"{row['label']} {row['title']}", "p.12", "ChatGPT 6.0" if "ChatGPT" in row["ai_line"] or not row["ai_line"] else "Gemini", ""])
    for number in range(1, case["ghosts"] + 1):
        cells = [""] * 9
        cells[COLUMN["author_made"] - 2] = S.M
        inclusion.append([str(len(inclusion) + 1), f"[그림 9-{number}] {GHOST} {number}", *cells])
    files = []
    if case["has_list"]:
        files.append(S.form(folder, "원고집필계약서_붙임.hwpx", S.inclusion_table(inclusion, module="평가용 학습모듈"), S.license_table(licenses)))
    else:
        files.append(S.form(folder, "이용허락동의서.hwpx", S.license_table(licenses)))
    files.append(S.form(folder, "사진삽화_제작목록.hwpx", S.production_table(production)))
    files.append(S.form(folder, "AI서약서.hwpx", S.ai_table(results + [["9", "그림 OOOO", "p.00", "ChatGPT 6.0", ""]])))
    return files


def score(case: dict, report: dict) -> dict:
    """현황표의 줄마다 부적합 지적 종류를 정답과 견준다 → {'rows', 'wrong', 'seeded', 'found', 'extra', 'misses': […]}."""
    rows, count = report["현황표"], len(case["rows"])
    wrong = seeded = found = extra = 0
    misses = []

    def judge(name: str, want: Counter, got: Counter):
        nonlocal wrong, seeded, found, extra
        seeded += sum(want.values())
        found += sum((want & got).values())
        extra += sum((got - want).values())
        if want != got:
            wrong += 1
            misses.append({"그림": name, "정답": dict(want), "결과": dict(got)})

    def kinds(row: dict) -> Counter:
        return Counter(issue["종류"] for issue in row["지적"] if issue["수준"] == FAIL)

    # 번호와 제목이 똑같은 그림이 원고에 두 번 있으면(실제 원고에 있다) 어느 쪽이 목록의 행과 짝인지 가릴 수 없다 —
    # 그런 그림들은 한 묶음으로 보고 정답과 결과를 순서 없이 견준다
    groups: dict[tuple[str, str], list[int]] = {}
    for index, truth in enumerate(case["rows"]):
        groups.setdefault((truth["label"], truth["title"]), []).append(index)
    for (label, title), members in groups.items():
        wants = sorted((expected_row(case["rows"][i], case) for i in members), key=lambda c: sorted(c.items()))
        gots = sorted((kinds(rows[i]) for i in members), key=lambda c: sorted(c.items()))
        for want, got in zip(wants, gots):
            judge(f"[{label}] {title}", want, got)
    ghosts = 0
    for row in rows[count:]:                              # 원고에 없는 목록 행 — 심은 것(ghost)이 아니면 짝짓기 실패에서 나온 오탐
        is_ghost = GHOST.replace(" ", "") in row["그림명"].replace(" ", "")
        ghosts += is_ghost
        judge(f"목록만: [{row['그림 번호']}] {row['그림명']}", expected_ghost(case) if is_ghost else Counter(), kinds(row))
    for number in range(ghosts, case["ghosts"]):          # 심었는데 현황표에 안 나온 것
        judge(f"목록만: {GHOST} (빠짐)", expected_ghost(case), Counter())
    top = Counter(f["종류"] for f in report["지적사항"] if f["수준"] == FAIL and f["그림"] == "수록 현황 목록")
    if not case["has_list"] or top:
        judge("수록 현황 목록", Counter() if case["has_list"] else Counter({"목록 미제출": 1}), top)
    return {"rows": count + max(ghosts, case["ghosts"]) + (len(rows) - count - ghosts) + (not case["has_list"] or bool(top)),
            "wrong": wrong, "seeded": seeded, "found": found, "extra": extra, "misses": misses}


def evaluate(name: str, manuscript: Path, figures: list[dict], cases: int, rng: random.Random) -> dict:
    total = Counter()
    details = []
    plans = [new_case(figures)] + [seed(new_case(figures), rng, rng.randint(3, 6)) for _ in range(cases)]
    without_list = new_case(figures)
    without_list["has_list"], without_list["seeded"] = False, ["no_list"]
    for number, case in enumerate(plans + [without_list]):
        with tempfile.TemporaryDirectory() as folder:
            report = run(manuscript, write_forms(Path(folder), case), Options(
                first_review_on=FIRST_REVIEW, submitted_on=SUBMITTED, today=TODAY, portrait="none",
                transfer_author=case["transfer_author"], transfer_maker=case["transfer_maker"], pledge=case["pledge"]))
        result = score(case, report)
        total.update({key: result[key] for key in ("rows", "wrong", "seeded", "found", "extra")})
        details.append({"사례": number, "심은 것": case["seeded"], **{key: result[key] for key in ("rows", "wrong", "seeded", "found", "extra")},
                        "틀린 줄": result["misses"]})
    return {"원고": name, "그림": len(figures), "사례": len(details), **total, "사례별": details}


# ── 기한 ──────────────────────────────────────────────────────────────────────

def deadline_cases() -> list[dict]:
    """(1차 검토일, 제출일, 점검일, 목록 유무) → 기한이 지났는가. 경계(28일째·29일째)를 넣는다."""
    first, due = FIRST_REVIEW, FIRST_REVIEW + timedelta(days=28)
    cases = []
    for offset in (-27, -1, 0, 1, 2, 30):                                   # 제출일 = 기한 ± 며칠
        cases.append({"제출일": due + timedelta(days=offset), "점검일": TODAY, "목록": True, "경과": offset > 0})
    for offset in (-10, -1, 0, 1, 15, 90):                                  # 미제출, 점검일 = 기한 ± 며칠
        cases.append({"제출일": None, "점검일": due + timedelta(days=offset), "목록": False, "경과": offset > 0})
    return [{"1차 검토일": first, **case} for case in cases]


def evaluate_deadline(folder: Path) -> dict:
    manuscript, figures = synthetic_manuscript(folder, 0, random.Random(0))
    missed, false, rows = 0, 0, []
    for index, item in enumerate(deadline_cases()):
        case = new_case(figures)
        case["has_list"] = item["목록"]
        sub = folder / f"d{index}"
        sub.mkdir()
        report = run(manuscript, write_forms(sub, case), Options(
            first_review_on=item["1차 검토일"], submitted_on=item["제출일"], today=item["점검일"], portrait="none",
            transfer_author=True, transfer_maker=True, pledge=True))
        alerted = any(f["종류"] == "기한" and f["수준"] == FAIL for f in report["지적사항"])
        in_notice = any(f["종류"] == "기한" and f["수준"] == FAIL for notice in report["알림"] for f in notice["지적사항"])
        missed += item["경과"] and not (alerted and in_notice)
        false += alerted and not item["경과"]
        rows.append({"제출일": str(item["제출일"] or "미제출"), "점검일": str(item["점검일"]), "기한": report["기한"]["기한"],
                     "경과(정답)": item["경과"], "알림": alerted})
    return {"사례": len(rows), "경과": sum(row["경과(정답)"] for row in rows), "알림 누락": missed, "잘못된 알림": false, "사례별": rows}


# ── 실행 ──────────────────────────────────────────────────────────────────────

def default_manuscripts() -> list[Path]:
    return sorted(path for path in (ROOT / "samples").rglob("*.hwpx") if path.name.startswith("LM"))


def rate(part: int, whole: int) -> str:
    return f"{part / whole * 100:.1f}%" if whole else "—"


def markdown(result: dict) -> str:
    lines = ["| 원고 | 그림 | 사례 | 채점한 줄 | 틀린 줄 | 오차율 | 심은 누락 | 찾음 | 재현율 | 심지 않은 부적합 | 정밀도 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for item in result["원고별"] + [result["합계"]]:
        lines.append(f"| {item['원고']} | {item.get('그림', '')} | {item['사례']} | {item['rows']} | {item['wrong']} | {rate(item['wrong'], item['rows'])} "
                     f"| {item['seeded']} | {item['found']} | {rate(item['found'], item['seeded'])} | {item['extra']} "
                     f"| {rate(item['found'], item['found'] + item['extra'])} |")
    deadline = result["기한"]
    lines += ["", f"기한: {deadline['사례']}사례 중 경과 {deadline['경과']}건 — 알림 누락 {deadline['알림 누락']}건, 잘못된 알림 {deadline['잘못된 알림']}건", ""]
    lines += [f"캡션 수 대조 — {item['원고']}: 읽은 그림 {item['읽은 그림']}개, '[그림 N-M]'으로 시작하는 문단 {item['캡션 문단']}개" for item in result["캡션 수 대조"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="권리 증빙 점검 평가 세트(REQ-02-014)")
    parser.add_argument("manuscripts", type=Path, nargs="*", help="실제 원고 hwpx(없으면 samples/의 LM*.hwpx)")
    parser.add_argument("--cases", type=int, default=10, help="원고마다 누락을 심은 사례 수(기본 10)")
    parser.add_argument("--seed", type=int, default=20261117)
    parser.add_argument("--json", type=Path, help="사례별 결과까지 이 파일로")
    parser.add_argument("--md", type=Path, help="요약 표를 이 파일로")
    args = parser.parse_args(argv)
    rng = random.Random(args.seed)
    per, captions = [], []
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        for number in (1, 2, 3):
            manuscript, figures = synthetic_manuscript(folder, number, rng)
            per.append(evaluate(f"합성 {number}권", manuscript, figures, args.cases, rng))
        for path in args.manuscripts or default_manuscripts():
            per.append(evaluate(path.name, path, real_manuscript(path), args.cases, rng))
            read, raw = caption_count(path)
            captions.append({"원고": path.name, "읽은 그림": read, "캡션 문단": raw})
        deadline = evaluate_deadline(folder)
    total = Counter()
    for item in per:
        total.update({key: item[key] for key in ("사례", "rows", "wrong", "seeded", "found", "extra")})
    result = {"seed": args.seed, "원고별": per, "합계": {"원고": "합계", **total}, "기한": deadline, "캡션 수 대조": captions,
              "오차율": total["wrong"] / total["rows"] if total["rows"] else None}
    text = markdown(result)
    print(text)
    if args.md:
        args.md.write_text(text + "\n", encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""검사 결과를 항목별 JSON과 ZIP으로 저장한다. 파일 이름 규칙은 두 패키지가 같다.

<out_dir>/<코드>_<YYYYMMDD-HHMMSS>_<이름>_<임의 6~8자>/   실행별 폴더(시각·검수 이름으로 찾고, 임의 꼬리로 겹치지 않게)
    <코드>_<항목 꼬리말>.json   항목별 체크리스트
    <코드>_<이름>_00_요약.json  검수결과(적합/부적합/판단불가) 종합과 항목별 집계
    <코드>_<이름>_지적사항.json  X·△만
    <코드>_<이름>_전체.json     모든 체크리스트 행
    <코드>_<이름>_진단.json     입력·읽기 상태
    <코드>_<이름>_검수확인서.json  F02 확인서 표(항목 번호별 적합/부적합/판단불가)
    <코드>_<이름>_검수결과.zip
"""

import json
import tempfile
import zipfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from .models import ReviewResult, SavedReport
from .module_code import validate_module_code
from .text import FAIL, PASS, UNDECIDED, VERDICTS


def overall_verdict(verdicts) -> str:
    """행 판정들의 종합: 부적합이 하나라도 있으면 부적합, 없고 판단불가가 있으면 판단불가, 나머지는 적합."""
    verdicts = list(verdicts)
    if FAIL in verdicts:
        return FAIL
    if UNDECIDED in verdicts:
        return UNDECIDED
    return PASS


def _buckets(result: ReviewResult, item_files: Sequence[tuple[str, str]], other_tail: str) -> dict[str, list]:
    """체크리스트 행을 항목별 파일 꼬리말로 나눈다. item_files에 없는 item_id는 other_tail로 모인다."""
    buckets: dict[str, list] = {tail: [] for _, tail in item_files}
    by_length = sorted(item_files, key=lambda pair: -len(pair[0]))
    for row in result.checklist:
        tail = next((t for prefix, t in by_length if row["item_id"].startswith(prefix)), other_tail)
        buckets.setdefault(tail, []).append(row)
    return buckets


def report_summary(result: ReviewResult, *, name: str, item_files: Sequence[tuple[str, str]], other_tail: str) -> dict:
    """파일을 만들지 않고 기존 보고서와 동일한 요약을 계산한다. save_report와 DB 이력 저장이 함께 쓴다."""
    buckets = _buckets(result, item_files, other_tail)
    items = {}
    for tail, rows in buckets.items():
        verdicts = [row["판정"] for row in rows]
        items[tail] = {
            "검수결과": overall_verdict(verdicts),
            "행 수": {v: verdicts.count(v) for v in VERDICTS},
            "파일": f"{result.module_code}_{tail}.json",
        }
    return {"검수결과": overall_verdict(row["판정"] for row in result.checklist), "항목": items}


def save_report(
    result: ReviewResult,
    out_dir,
    *,
    name: str,
    item_files: Sequence[tuple[str, str]],
    other_tail: str,
    per_run_dir: bool = True,
) -> SavedReport:
    """name: 결과 이름('차례'/'위치'). item_files: (item_id 접두, 파일 꼬리말).

    per_run_dir=True이면 실행마다 새 하위 폴더를 만들어 이전 결과를 덮어쓰지 않는다.
    False이면 out_dir에 바로 쓰고 같은 코드의 이전 결과를 갱신한다.
    item_files에 없는 item_id는 other_tail 파일로 모인다.
    """
    code = validate_module_code(result.module_code)
    root = Path(out_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if per_run_dir:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        directory = Path(tempfile.mkdtemp(prefix=f"{code}_{stamp}_{name}_", dir=root))
    else:
        directory = root

    buckets = _buckets(result, item_files, other_tail)
    paths: list[Path] = []

    def write(tail: str, value) -> Path:
        path = directory / f"{code}_{tail}.json"
        path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
        paths.append(path)
        return path

    for tail, rows in buckets.items():
        write(tail, rows)
    # 요약은 report_summary 한 곳에서 계산한다(DB 이력 저장과 같은 값).
    summary = report_summary(result, name=name, item_files=item_files, other_tail=other_tail)
    write(f"{name}_00_요약", summary)
    write(f"{name}_지적사항", result.findings)
    write(f"{name}_전체", result.checklist)
    write(f"{name}_진단", result.diagnostics)
    write(f"{name}_검수확인서", result.sheet)

    zip_path = directory / f"{code}_{name}_검수결과.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, path.name)
    return SavedReport(directory, zip_path, summary)

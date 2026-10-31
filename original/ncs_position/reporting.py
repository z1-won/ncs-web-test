"""검사 결과를 기존 이름과 JSON 구조로 저장한다."""

import json
import tempfile
import zipfile
from pathlib import Path

from .models import ReviewResult, SavedReport
from .module_code import validate_module_code

ITEM_FILES = (
    ("F02-위치-①", "위치①_대중소분류명칭"),
    ("F02-위치-②③④", "위치②③④_세분류능력단위학습모듈"),
    ("F02-위치-⑤", "위치⑤_굵게음영"),
)


def save_results(result: ReviewResult, out_dir: str | Path = "결과") -> SavedReport:
    """실행별 하위 폴더에 저장하여 기존 결과 덮어쓰기와 오래된 ZIP 재사용을 막는다.

    새로운 item_id는 '위치_기타'로 자동 수집된다.
    """
    code = validate_module_code(result.module_code)
    root = Path(out_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=f"{code}_", dir=root))
    buckets = {tail: [] for _, tail in ITEM_FILES}
    for item in result.checklist:
        tail = next(
            (
                tail
                for prefix, tail in sorted(ITEM_FILES, key=lambda x: -len(x[0]))
                if item["item_id"].startswith(prefix)
            ),
            "위치_기타",
        )
        buckets.setdefault(tail, []).append(item)
    paths = []
    summary = {}

    def write(name, value):
        path = directory / f"{code}_{name}.json"
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        paths.append(path)
        return path

    for tail, items in buckets.items():
        path = write(tail, items)
        verdicts = [item["판정"] for item in items]
        summary[tail] = {v: verdicts.count(v) for v in ("반영", "미반영", "판단불가")}
        summary[tail]["파일"] = path.name
    for name, value in (
        ("위치_00_요약", summary),
        ("위치_지적사항", result.findings),
        ("위치_전체", result.checklist),
    ):
        write(name, value)
    zip_path = directory / f"{code}_위치_검수결과.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, path.name)
    return SavedReport(directory, zip_path, summary)

"""위치 검수 결과 저장. 파일 이름 규칙은 ncs_core.reporting과 같다."""

from ncs_core import ReviewResult, SavedReport, save_report

ITEM_FILES = (
    ("F02-위치-①", "위치①_대중소분류명칭"),
    ("F02-위치-②③④", "위치②③④_세분류능력단위학습모듈"),
    ("F02-위치-⑤", "위치⑤_굵게음영"),
)


def save_results(result: ReviewResult, out_dir="결과", *, per_run_dir: bool = True) -> SavedReport:
    return save_report(
        result, out_dir, name="위치", item_files=ITEM_FILES, other_tail="위치_기타", per_run_dir=per_run_dir
    )

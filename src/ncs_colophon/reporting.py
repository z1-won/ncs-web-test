"""판권 검수 결과 저장."""

from ncs_core import ReviewResult, SavedReport, report_summary, save_report

REPORT_NAME = "판권"
ITEM_FILES = (("F02-판권-①", "판권①_개발이력판권"),)


def summary(result: ReviewResult) -> dict:
    return report_summary(result, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타")


def save_results(result: ReviewResult, out_dir="결과", *, per_run_dir: bool = True) -> SavedReport:
    return save_report(result, out_dir, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타", per_run_dir=per_run_dir)

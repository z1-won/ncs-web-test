"""기타 검수 결과 저장."""

from ncs_core import ReviewResult, SavedReport, report_summary, save_report

REPORT_NAME = "기타"
ITEM_FILES = (
    ("F02-기타-①", "기타①_새쪽시작"),
    ("F02-기타-②", "기타②_그림누락유실"),
    ("F02-기타-⑥", "기타⑥_지식수행비율"),
    ("F02-기타-⑦", "기타⑦_서식부록참조"),
)


def summary(result: ReviewResult) -> dict:
    return report_summary(result, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타")


def save_results(result: ReviewResult, out_dir="결과", *, per_run_dir: bool = True) -> SavedReport:
    return save_report(result, out_dir, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타", per_run_dir=per_run_dir)

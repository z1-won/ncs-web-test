"""참고 자료 검수 결과 저장."""

from ncs_core import ReviewResult, SavedReport, report_summary, save_report

REPORT_NAME = "참고자료"
ITEM_FILES = (
    ("F02-참고자료-①", "참고자료①_본문인용수록"),
    ("F02-참고자료-②", "참고자료②_서지형식"),
    ("F02-참고자료-③", "참고자료③_나열순서"),
    ("F02-참고자료-④", "참고자료④_옛모듈출처"),
)


def summary(result: ReviewResult) -> dict:
    return report_summary(result, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타")


def save_results(result: ReviewResult, out_dir="결과", *, per_run_dir: bool = True) -> SavedReport:
    return save_report(result, out_dir, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타", per_run_dir=per_run_dir)

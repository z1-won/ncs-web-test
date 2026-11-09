"""개발계획서 점검 결과 저장."""

from ncs_core import ReviewResult, SavedReport, report_summary, save_report

REPORT_NAME = "계획서"
ITEM_FILES = (
    ("PLAN-①", "계획서①_NCS목록대조"), ("PLAN-②", "계획서②_학습모듈코드명칭"), ("PLAN-③", "계획서③_학습모듈목표"),
    ("PLAN-④", "계획서④_학습명요소배정"), ("PLAN-⑤", "계획서⑤_요소코드"), ("PLAN-⑥", "계획서⑥_학습목표수행준거"),
    ("PLAN-⑦", "계획서⑦_학습내용명"), ("PLAN-⑧", "계획서⑧_필수기재"), ("PLAN-⑨", "계획서⑨_변경전후대조표"),
)


def summary(result: ReviewResult) -> dict:
    return report_summary(result, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타")


def save_results(result: ReviewResult, out_dir="결과", *, per_run_dir: bool = True) -> SavedReport:
    return save_report(result, out_dir, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타", per_run_dir=per_run_dir)

"""평가 검수 결과의 요약과 저장."""
from ncs_core import ReviewResult, SavedReport, report_summary, save_report

REPORT_NAME = "평가"
ITEM_FILES = (("F02-평가-①", "평가①_학습내용명"), ("F02-평가-②", "평가②_준거학습목표"), ("F02-평가-③", "평가③_평가방법수"), ("F02-평가-⑤", "평가⑤_방법별피드백"))


def summary(result: ReviewResult) -> dict:
    return report_summary(result, name=REPORT_NAME, item_files=ITEM_FILES, other_tail="평가_기타")


def save_results(result: ReviewResult, out_dir="결과", *, per_run_dir: bool = True) -> SavedReport:
    return save_report(result, out_dir, name=REPORT_NAME, item_files=ITEM_FILES,
                       other_tail="평가_기타", per_run_dir=per_run_dir)

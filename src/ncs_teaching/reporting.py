"""교수·학습 방법 검수 결과 저장. 파일 이름 규칙은 ncs_core.reporting과 같다."""

from ncs_core import ReviewResult, SavedReport, report_summary, save_report

REPORT_NAME = "교수학습"
ITEM_FILES = (
    ("F02-교수학습-①", "교수학습①_교수방법개수"),
    ("F02-교수학습-②", "교수학습②_교수방법종결"),
    ("F02-교수학습-③", "교수학습③_학습방법개수"),
    ("F02-교수학습-④", "교수학습④_학습방법종결"),
)


def summary(result: ReviewResult) -> dict:
    return report_summary(result, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타")


def save_results(result: ReviewResult, out_dir="결과", *, per_run_dir: bool = True) -> SavedReport:
    return save_report(result, out_dir, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타", per_run_dir=per_run_dir)

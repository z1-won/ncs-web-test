"""수행 내용 검수 결과 저장. 파일 이름 규칙은 ncs_core.reporting과 같다."""

from ncs_core import ReviewResult, SavedReport, report_summary, save_report

REPORT_NAME = "수행"  # 저장 파일 이름과 DB 이력에 쓰는 보고서 이름
ITEM_FILES = (
    ("F02-수행-①", "수행①_제목하기"),
    ("F02-수행-④", "수행④_한다종결"),
)


def summary(result: ReviewResult) -> dict:
    """파일을 만들지 않고 요약만 계산한다. DB 이력 저장이 쓴다."""
    return report_summary(result, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타")


def save_results(result: ReviewResult, out_dir="결과", *, per_run_dir: bool = True) -> SavedReport:
    return save_report(
        result, out_dir, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타", per_run_dir=per_run_dir
    )

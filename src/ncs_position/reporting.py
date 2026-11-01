"""위치 검수 결과 저장. 파일 이름 규칙은 ncs_core.reporting과 같다."""

from ncs_core import ReviewResult, SavedReport, report_summary, save_report

REPORT_NAME = "위치"  # 저장 파일 이름과 DB 이력에 쓰는 보고서 이름
ITEM_FILES = (
    ("F02-위치-①", "위치①_대중소분류명칭"),
    ("F02-위치-②③④", "위치②③④_세분류능력단위학습모듈"),
    ("F02-위치-⑤", "위치⑤_굵게음영"),
)


def summary(result: ReviewResult) -> dict:
    """파일을 만들지 않고 요약만 계산한다. DB 이력 저장이 쓴다."""
    return report_summary(result, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타")


def save_results(result: ReviewResult, out_dir="결과", *, per_run_dir: bool = True) -> SavedReport:
    return save_report(
        result, out_dir, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타", per_run_dir=per_run_dir
    )

"""차례 검수 결과 저장. 파일 이름 규칙은 ncs_core.reporting과 같다."""

from ncs_core import ReviewResult, SavedReport, report_summary, save_report

REPORT_NAME = "차례"  # 저장 파일 이름과 DB 이력에 쓰는 보고서 이름
ITEM_FILES = (
    ("F02-차례-①", "차례①_학습명"),
    ("F02-차례-②", "차례②_학습내용명_행동명사"),
    ("F02-차례-③", "차례③_학습명내용명_5곳일치"),
    ("F02-차례-④", "차례④_교수평가_위치"),
    ("F02-차례-⑤", "차례⑤_참고자료"),
    ("F02-차례-⑥", "차례⑥_활용서식부록"),
)


def summary(result: ReviewResult) -> dict:
    """파일을 만들지 않고 요약만 계산한다. DB 이력 저장이 쓴다."""
    return report_summary(result, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타")


def save_results(result: ReviewResult, out_dir="결과", *, per_run_dir: bool = True) -> SavedReport:
    return save_report(
        result, out_dir, name=REPORT_NAME, item_files=ITEM_FILES, other_tail=f"{REPORT_NAME}_기타", per_run_dir=per_run_dir
    )

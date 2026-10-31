"""개요 검수 결과 저장. 파일 이름 규칙은 ncs_core.reporting과 같다."""

from ncs_core import ReviewResult, SavedReport, save_report

ITEM_FILES = (
    ("F02-개요-①", "개요①_목표"),
    ("F02-개요-②", "개요②_선수학습"),
    ("F02-개요-⑤", "개요⑤_학습명내용명"),
    ("F02-개요-⑥", "개요⑥_요소코드명칭"),
    ("F02-개요-⑧", "개요⑧_핵심용어"),
)


def save_results(result: ReviewResult, out_dir="결과", *, per_run_dir: bool = True) -> SavedReport:
    return save_report(
        result, out_dir, name="개요", item_files=ITEM_FILES, other_tail="개요_기타", per_run_dir=per_run_dir
    )

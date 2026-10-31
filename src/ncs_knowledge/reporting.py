"""필요 지식 검수 결과 저장. 파일 이름 규칙은 ncs_core.reporting과 같다."""

from ncs_core import ReviewResult, SavedReport, save_report

ITEM_FILES = (
    ("F02-필요지식-①", "필요지식①_내비게이터_코드번호"),
    ("F02-필요지식-②", "필요지식②_내비게이터_하기종결"),
    ("F02-필요지식-③", "필요지식③_내비게이터_차례내용체계일치"),
    ("F02-필요지식-④", "필요지식④_학습내용명_차례내용체계일치"),
    ("F02-필요지식-⑤", "필요지식⑤_학습목표_개발계획서일치"),
    ("F02-필요지식-⑥", "필요지식⑥_번호체계"),
    ("F02-필요지식-⑦", "필요지식⑦_그림표번호"),
    ("F02-필요지식-⑧", "필요지식⑧_출처표기"),
)


def save_results(result: ReviewResult, out_dir="결과", *, per_run_dir: bool = True) -> SavedReport:
    return save_report(
        result, out_dir, name="필요지식", item_files=ITEM_FILES, other_tail="필요지식_기타", per_run_dir=per_run_dir
    )

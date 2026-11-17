"""권리 증빙 점검 실행 — 원고와 제출 서류 파일을 읽어 check()에 넘긴다. 웹과 명령행이 함께 쓰는 입구.

    python -m ncs_rights 원고.hwpx 서류1.hwp 서류2.hwpx --first-review 2026-10-01 --submitted 2026-10-20 --pledge --print 출력본.pdf
"""

from __future__ import annotations

from pathlib import Path

from ncs_core.documents import load_document
from ncs_core.figures import manuscript_figures

from .check import Options, check
from .forms import read_forms
from .pages import figure_pages

FORM_SUFFIXES = (".hwp", ".hwpx")


def _read_print(path: Path) -> tuple[dict | None, dict | None, str]:
    """출력본 PDF → (그림별 쪽, 결과의 '출력본' 칸, 안내). 읽지 못하면 쪽 대조 없이 계속하도록 (None, None, 이유)."""
    from ncs_core.pdf import load_pdf

    try:
        pdf = load_pdf(path)
    except ValueError as error:      # PDF가 아님, 글자를 못 뽑음, pypdf 없음(PdfUnavailable)
        return None, None, f"{path.name}: 출력본을 읽지 못해 쪽수를 대조하지 않았습니다({error})"
    pages = figure_pages(pdf)
    info = {"파일": path.name, "쪽": len(pdf.pages), "캡션 찾은 그림": len(pages), "모듈 코드": pdf.module_code}
    return pages, info, "" if pages else f"{path.name}: 출력본에서 그림 캡션을 하나도 찾지 못했습니다"


def run(manuscript: str | Path, forms: list[str | Path] = (), options: Options | None = None, *,
        print_copy: str | Path | None = None) -> dict:
    """현황표와 누락 목록(check의 반환) + '원고'(파일 이름·형식) + '출력본'. 읽지 못하는 서류는 '안내'에 적고 나머지로 계속한다.

    print_copy: 출력본 PDF(선택). 주면 그림이 놓인 쪽을 읽어 생성형 AI 결과물 현황의 쪽수와 대조한다.
    """
    manuscript = Path(manuscript)
    try:
        document = load_document(manuscript)
    except Exception as error:       # 원고를 읽지 못하면 점검할 것이 없다 — 파일 이름을 붙여 알린다
        raise ValueError(f"원고를 읽지 못했습니다({manuscript.name}): {error}") from None
    loaded, unread = [], []
    for path in map(Path, forms):
        if path.suffix.lower() not in FORM_SUFFIXES:
            unread.append(f"{path.name}: 한글 파일(hwp·hwpx)만 읽습니다")
            continue
        try:
            loaded.append((path.name, load_document(path)))
        except Exception as error:
            unread.append(f"{path.name}: 읽지 못했습니다({error})")
    pages, print_info, print_note = _read_print(Path(print_copy)) if print_copy else (None, None, "")
    report = check(manuscript_figures(document), read_forms(loaded), options, pages)
    report["원고"] = {"파일": manuscript.name, "형식": document.format}
    report["출력본"] = print_info
    if print_note:
        report["안내"].append(print_note)
    report["서류"]["올린 파일"] = [name for name, _ in loaded]
    report["안내"] += unread
    if loaded and not report["서류"]["읽은 양식"]:
        report["안내"].append("올린 서류에서 수록 현황 목록·제작 목록·이용허락 동의서·AI 결과물 현황 표를 찾지 못했습니다")
    return report

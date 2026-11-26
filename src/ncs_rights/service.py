"""권리 증빙 점검 실행 — 원고와 제출 서류 파일을 읽어 check()에 넘긴다. 웹과 명령행이 함께 쓰는 입구.

    python -m ncs_rights 원고.hwpx 서류1.hwp 서류2.hwpx --first-review 2026-10-01 --submitted 2026-10-20 --pledge --print 출력본.pdf
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ncs_core.documents import load_document
from ncs_core.figures import Figure, manuscript_figures
from ncs_core.pictures import CAPTION_BEFORE, MAX_CAPTION_GAP, picture_records

from .check import Options, check
from .forms import read_forms
from .pages import figure_pages

FORM_SUFFIXES = (".hwp", ".hwpx")
# 양식 그림으로 보고 빼는 크기 — 그림 검수(ncs_figures.config)의 '양식 후보'와 같은 값: 쪽 전체(표지·간지)와 띠(배너)
PAGE_MM = (200, 280)
BANNER_MAX_HEIGHT_MM = 15
NEAR_CLIP = 30


def uncaptioned_pictures(document, figures: list[Figure], is_template: Callable[[bytes], bool] | None = None) -> list[dict]:
    """캡션([그림 N-M])이 붙지 않은 그림 개체 → [{'section', 'para', 'mm', 'px', '앞 글'}], 문서 순서대로.

    캡션이 붙은 그림: 같은 구역에서 그림 문단 아래 MAX_CAPTION_GAP 문단 안, 또는 위 CAPTION_BEFORE 문단 안에 원고의 그림 캡션
    (manuscript_figures가 읽은 것 — 본문의 참조 문장은 캡션이 아님)이 있는 것. 쪽 전체 그림과 띠(배너)는 양식 그림이라 뺀다.
    is_template: 그림 파일 바이트 → 양식 그림인가. 크기로 못 가리는 양식 그림(높이 16mm 제목 띠 등)을 더 뺀다 — 양식 그림 목록은
    그림 검수(ncs_figures)의 것이라 이 패키지가 직접 읽지 않고, 둘을 다 아는 웹 층이 넘겨준다.
    그림 개체를 읽지 못하는 원고(오래된 hwp 등)는 빈 목록이다.
    """
    captions: dict[int, list[int]] = {}
    for figure in figures:
        captions.setdefault(figure.section, []).append(figure.para)
    out = []
    for record in picture_records(document):
        section, para = record["section"], record["para"]
        if any(para - CAPTION_BEFORE <= caption <= para + MAX_CAPTION_GAP for caption in captions.get(section, ())):
            continue
        width, height = record["mm"]
        if (width >= PAGE_MM[0] and height >= PAGE_MM[1]) or (height and height <= BANNER_MAX_HEIGHT_MM):
            continue
        if is_template is not None and record["data"] and is_template(record["data"]):
            continue
        paragraphs = document.sections[section]
        before = next((text.strip() for text in reversed(paragraphs[:para]) if (text or "").strip()), "")
        out.append({"section": section, "para": para, "mm": (width, height), "px": record["px"],
                    "앞 글": before[:NEAR_CLIP] + ("…" if len(before) > NEAR_CLIP else "")})
    return out


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
        print_copy: str | Path | None = None, is_template: Callable[[bytes], bool] | None = None) -> dict:
    """현황표와 누락 목록(check의 반환) + '원고'(파일 이름·형식) + '출력본'. 읽지 못하는 서류는 '안내'에 적고 나머지로 계속한다.

    print_copy: 출력본 PDF(선택). 주면 그림이 놓인 쪽을 읽어 생성형 AI 결과물 현황의 쪽수와 대조한다.
    is_template: 양식 그림 판별(선택, uncaptioned_pictures). 없으면 캡션 없는 그림에서 크기로만 양식 그림을 뺀다.
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
    figures = manuscript_figures(document)
    report = check(figures, read_forms(loaded), options, pages, uncaptioned_pictures(document, figures, is_template))
    report["원고"] = {"파일": manuscript.name, "형식": document.format}
    report["출력본"] = print_info
    if print_note:
        report["안내"].append(print_note)
    report["서류"]["올린 파일"] = [name for name, _ in loaded]
    report["안내"] += unread
    if loaded and not report["서류"]["읽은 양식"]:
        report["안내"].append("올린 서류에서 수록 현황 목록·제작 목록·이용허락 동의서·AI 결과물 현황 표를 찾지 못했습니다")
    return report

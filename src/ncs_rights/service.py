"""권리 증빙 점검 실행 — 원고와 제출 서류 파일을 읽어 check()에 넘긴다. 웹과 명령행이 함께 쓰는 입구.

    python -m ncs_rights 원고.hwpx 서류1.hwp 서류2.hwpx --first-review 2026-10-01 --submitted 2026-10-20 --pledge
"""

from __future__ import annotations

from pathlib import Path

from ncs_core.documents import load_document
from ncs_core.figures import manuscript_figures

from .check import Options, check
from .forms import read_forms

FORM_SUFFIXES = (".hwp", ".hwpx")


def run(manuscript: str | Path, forms: list[str | Path] = (), options: Options | None = None) -> dict:
    """현황표와 누락 목록(check의 반환) + '원고'(파일 이름·형식). 읽지 못하는 서류는 '안내'에 적고 나머지로 계속한다."""
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
    report = check(manuscript_figures(document), read_forms(loaded), options)
    report["원고"] = {"파일": manuscript.name, "형식": document.format}
    report["서류"]["올린 파일"] = [name for name, _ in loaded]
    report["안내"] += unread
    if loaded and not report["서류"]["읽은 양식"]:
        report["안내"].append("올린 서류에서 수록 현황 목록·제작 목록·이용허락 동의서·AI 결과물 현황 표를 찾지 못했습니다")
    return report

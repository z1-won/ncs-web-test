"""005 점검 등록표 — 실행 순서와 필요한 자원. 점검 함수는 모두 같은 모양: (item, res, cfg, prior) -> list[CheckOutcome].

prior: 앞 점검이 남긴 값(예: ④가 찾은 같은 그림 prior['matches']를 위험도 규칙이 쓴다). 필요한 자원이 없으면 등록표가
점검 함수를 부르지 않고 '미실행' 결과를 만든다(자원이 없는 것은 오류가 아니다).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..models import CheckOutcome
from .. import marks
from . import ai_marker, caption, db_match, pending, source, submission, third_party


@dataclass(frozen=True)
class CheckSpec:
    key: str
    names: tuple[str, ...]                      # 이 점검이 내는 체크 이름(미실행일 때 이 이름으로 표시)
    needs: frozenset[str]                       # Resources의 필드 이름
    applies_to: frozenset[str]                  # 그림 종류
    run: Callable[..., list[CheckOutcome]]
    skip_reason: str = ""


BODY = frozenset({"본문 그림"})
CHECKED = frozenset({"본문 그림", "캡션 없는 그림"})

CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec("source", ("①출처 있음", "①출처 형식", "①출처 요건"), frozenset(), CHECKED, source.check_source),
    CheckSpec("ai_marker", ("⑦AI 표기",), frozenset(), BODY, ai_marker.check_ai_marker),
    CheckSpec("third_party", ("⑨제3자 원본",), frozenset(), BODY, third_party.check_third_party),
    CheckSpec("db", ("④DB 대조",), frozenset({"lookup"}), CHECKED, db_match.check_db, "그림 DB 미연결(db build로 만들고 --db로 지정)"),
    CheckSpec("caption", ("③캡션 일치",), frozenset({"asker"}), BODY, caption.check_caption, "그림 판독 모델을 켜지 않음(--vlm)"),
    CheckSpec("status_list", ("⑥수록 현황", "⑥증빙"), frozenset({"submissions"}), BODY, submission.check_status, "제출 서류(수록 현황 목록)를 넣지 않음"),
    CheckSpec("ai_list", ("⑦AI 현황 대조",), frozenset({"submissions"}), BODY, submission.check_ai_list, "제출 서류(서약서)를 넣지 않음"),
    CheckSpec("similar", ("⑧AI 결과물 유사",), frozenset({"lookup"}), BODY, submission.check_similar, "그림 DB 미연결"),
    CheckSpec("marks", ("②마크·워터마크",), frozenset({"marks"}), CHECKED, marks.check_marks, "OCR을 쓸 수 없음(Windows 내장 OCR 또는 PaddleOCR이 있어야 함, FIG_OCR=0이면 끔)"),
    # ⑦생성·수정 구분은 ④·⑧(DB)·서약서 결과를 모아 보므로 맨 뒤
    CheckSpec("ai_action", ("⑦생성·수정 구분",), frozenset(), BODY, third_party.check_ai_action),
)


def run_checks(item, res, cfg, checks=CHECKS, *, module_name: str = "", module_code: str = "") -> tuple[list[CheckOutcome], dict]:
    """등록표 순서대로 실행. (결과 목록, prior). module_code: 검수 중인 원고의 모듈(④에서 자기 그림을 빼는 데 씀)."""
    prior: dict = {"module_name": module_name, "module_code": module_code}
    out: list[CheckOutcome] = []
    for spec in checks:
        if item.kind not in spec.applies_to:
            continue
        missing = [need for need in spec.needs if getattr(res, need, None) is None]
        if missing:
            out.extend(CheckOutcome(name, None, skipped=spec.skip_reason or f"자원 없음: {', '.join(missing)}") for name in spec.names)
            continue
        out.extend(spec.run(item, res, cfg, prior))
    return out, prior

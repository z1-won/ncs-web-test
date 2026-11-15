"""문서 선택·엔진 실행·저장을 조정한다. 검사와 저장은 별도 단계다."""

from pathlib import Path

from ncs_core import SavedReport, select_documents

from .models import ExecutedReview, ReviewRequest
from .registry import get_engine


# 선택 입력 역할 → 엔진 prepare_review의 인자 이름 ('print'는 내장 함수 이름이라 print_copy로 받는다)
OPTIONAL_KWARGS = {"print": "print_copy"}


def execute_review(request: ReviewRequest) -> ExecutedReview:
    engine = get_engine(request.check)
    module = engine.load()
    if request.config is not None and not isinstance(request.config, module.CheckConfig):
        raise ValueError(f"{request.check} 검수의 config는 {engine.package}.CheckConfig여야 합니다")
    prepare_options = {"module_code": request.module_code}
    if request.config is not None:
        prepare_options["config"] = request.config
    evaluate_options = {} if request.rules is None else {"rules": request.rules}
    documents = select_documents(request.paths, request.roles, required=engine.required)
    for role in engine.optional:  # 선택 입력(출력본 PDF 등)은 그 역할을 받겠다고 선언한 엔진에만 넘긴다
        if role in documents:
            prepare_options[OPTIONAL_KWARGS.get(role, role)] = documents[role]
    manuscript = documents.get("manuscript")
    layout = getattr(manuscript, "layout", None) or {}
    try:
        context = module.prepare_review(manuscript, documents.get("plan"), **prepare_options)
    except ValueError as error:
        # 구역을 못 나눈 원고는 엔진이 '차례를 읽지 못했습니다' 같은 다른 오류를 낸다 — 진짜 원인을 함께 알린다
        if layout.get("결과") in ("실패", "확인 못 함"):
            raise ValueError(f"{error} (원고의 구역을 나누지 못했습니다: {layout['설명']})") from error
        raise
    result = module.evaluate_review(context, **evaluate_options)
    if layout:
        result.diagnostics["구역 맞춤"] = dict(layout)   # 앞부분/본문을 어떻게 나눴는지(실패했으면 그 이유) — 판정이 이상할 때 먼저 볼 곳
    return ExecutedReview(request.check, result)


def persist_review(review: ExecutedReview, out_dir: str | Path) -> SavedReport:
    return get_engine(review.check).load().save_results(review.result, out_dir)

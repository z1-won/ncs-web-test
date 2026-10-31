"""문서 선택·엔진 실행·저장을 조정한다. 검사와 저장은 별도 단계다."""

from pathlib import Path

from ncs_core import SavedReport, select_documents

from .models import ExecutedReview, ReviewRequest
from .registry import get_engine


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
    context = module.prepare_review(
        documents["manuscript"], documents.get("plan"), **prepare_options
    )
    return ExecutedReview(request.check, module.evaluate_review(context, **evaluate_options))


def persist_review(review: ExecutedReview, out_dir: str | Path) -> SavedReport:
    return get_engine(review.check).load().save_results(review.result, out_dir)

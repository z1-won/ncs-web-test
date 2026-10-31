"""문서 선택·엔진 실행·저장을 조정한다. 검사와 저장은 별도 단계다."""

from pathlib import Path

from ncs_core import SavedReport, select_documents

from .models import ExecutedReview, ReviewRequest
from .registry import get_engine


def execute_review(request: ReviewRequest) -> ExecutedReview:
    engine = get_engine(request.check)
    documents = select_documents(request.paths, request.roles, required=engine.required)
    module = engine.load()
    context = module.prepare_review(
        documents["manuscript"], documents.get("plan"), module_code=request.module_code
    )
    return ExecutedReview(request.check, module.evaluate_review(context))


def persist_review(review: ExecutedReview, out_dir: str | Path) -> SavedReport:
    return get_engine(review.check).load().save_results(review.result, out_dir)

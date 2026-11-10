"""입력 파일의 역할 판별과 검증. 사용자 인터페이스와 독립적이다."""

import hashlib
from pathlib import Path

from .documents import Document, load_document

ROLE_LABELS = {"manuscript": "원고", "plan": "개발계획서"}
MANUSCRIPT_MARKERS = ("차 례", "차례", "학습모듈의 개요", "NCS-학습모듈의 위치")


def detect_role(sections: list[list[str]], head_lines: int = 60) -> str:
    """첫 섹션 머리 문단으로 역할을 판별한다: 'plan' / 'manuscript' / 'unknown'."""
    head = " ".join(sections[0][:head_lines]) if sections else ""
    if "개발계획서" in head:
        return "plan"
    if any(marker in head for marker in MANUSCRIPT_MARKERS):
        return "manuscript"
    return "unknown"


def file_digest(path) -> bytes:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


def validate_distinct(paths: dict[str, str | Path]) -> None:
    """역할별 경로가 존재하고 비어 있지 않으며 서로 다른 내용인지 확인한다."""
    for role, path in paths.items():
        label = ROLE_LABELS.get(role, role)
        if not path:
            raise ValueError(f"{label} 파일 경로를 지정하세요")
        path = Path(path)
        if not path.is_file():
            raise ValueError(f"{label} 파일을 찾을 수 없습니다: {Path(path).name}")
        if path.stat().st_size == 0:
            raise ValueError(f"{label} 파일이 비어 있습니다: {Path(path).name}")
    digests = {role: file_digest(path) for role, path in paths.items()}
    if len(set(digests.values())) != len(digests):
        raise ValueError("입력 파일들의 내용이 동일합니다. 실제 원고와 개발계획서를 각각 선택하세요")


def select_documents(
    paths,
    roles: dict | None = None,
    *,
    required: tuple[str, ...] = ("manuscript",),
) -> dict[str, Document]:
    """경로 목록을 읽어 {'manuscript': Document, 'plan': Document}로 나눈다.

    roles={경로: 'plan'|'manuscript'}로 자동 판별을 덮어쓴다.
    required에 있는 역할이 없거나, 한 역할에 파일이 둘 이상이면 ValueError.
    """
    overrides = {str(Path(p).resolve()): r for p, r in (roles or {}).items()}
    if set(overrides.values()) - set(ROLE_LABELS):
        raise ValueError("roles 값은 'manuscript' 또는 'plan'이어야 합니다")
    documents: dict[str, Document] = {}
    seen: set[str] = set()
    for path in paths:
        key = str(Path(path).resolve())
        if key in seen:
            raise ValueError(f"같은 입력 파일이 중복 지정되었습니다: {Path(path).name}")
        seen.add(key)
        document = load_document(path)
        role = overrides.get(key, detect_role(document.sections))
        if role not in ROLE_LABELS:
            raise ValueError(f"파일 역할을 판단하지 못했습니다: {path}. roles로 역할을 지정하세요")
        if role in documents:
            raise ValueError(f"{ROLE_LABELS[role]} 파일이 둘 이상입니다. 역할마다 한 개씩 선택하세요")
        documents[role] = document
    unused = overrides.keys() - seen
    if unused:
        raise ValueError(f"roles에 입력 목록에 없는 경로가 있습니다: {sorted(unused)}")
    for role in required:
        if role not in documents:
            raise ValueError(f"{ROLE_LABELS[role]} 파일이 필요합니다")
    if len(documents) > 1:
        validate_distinct({role: doc.path for role, doc in documents.items()})
    return documents

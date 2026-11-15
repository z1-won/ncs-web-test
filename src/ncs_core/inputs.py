"""입력 파일을 역할(원고·개발계획서·출력본)별로 읽고 검증한다. 역할은 호출자가 정하며 내용으로 추측하지 않는다. 사용자 인터페이스와 독립적이다."""

import hashlib
from pathlib import Path

from .documents import Document, load_document
from .pdf import PdfDocument, is_pdf, load_pdf

ROLE_LABELS = {"manuscript": "원고", "plan": "개발계획서", "print": "출력본"}  # print: 원고를 한글에서 PDF로 저장한 것(쪽수 확인용, 선택)
DOCUMENT_ROLES = ("manuscript", "plan")   # hwp/hwpx가 맡는 역할. 역할을 지정하지 않은 파일은 이 순서로 채운다


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
) -> dict[str, Document | PdfDocument]:
    """경로 목록을 읽어 {'manuscript': Document, 'plan': Document, 'print': PdfDocument}로 나눈다.

    역할은 호출자가 정한다 — 파일 내용을 보고 추측하지 않는다.
    - roles={경로: 'manuscript'|'plan'|'print'}로 지정한 파일은 그 역할(화면의 업로드 칸, CLI의 --manuscript/--plan).
    - 지정하지 않은 hwp/hwpx는 넣은 순서대로 남은 역할을 맡는다: required에 있는 역할 먼저, 그다음 원고 → 개발계획서.
      (원고 검수는 '원고, 개발계획서' 순, 개발계획서 점검은 required=('plan',)이라 파일 하나가 곧 개발계획서.)
    - PDF는 언제나 'print'(출력본)이며 다른 역할을 줄 수 없다.
    required에 있는 역할이 없거나, 한 역할에 파일이 둘 이상이면 ValueError.
    """
    overrides = {str(Path(p).resolve()): r for p, r in (roles or {}).items()}
    if set(overrides.values()) - set(ROLE_LABELS):
        raise ValueError("roles 값은 'manuscript', 'plan', 'print' 중 하나여야 합니다")
    order = [r for r in required if r in DOCUMENT_ROLES] + [r for r in DOCUMENT_ROLES if r not in required]
    open_roles = [r for r in order if r not in overrides.values()]   # 순서대로 채울, 아직 주인이 없는 역할
    documents: dict[str, Document | PdfDocument] = {}
    seen: set[str] = set()
    for path in paths:
        key = str(Path(path).resolve())
        if key in seen:
            raise ValueError(f"같은 입력 파일이 중복 지정되었습니다: {Path(path).name}")
        seen.add(key)
        if is_pdf(path):
            if overrides.get(key, "print") != "print":
                raise ValueError(f"PDF는 출력본으로만 받습니다. 원고·개발계획서는 hwp/hwpx로 올리세요: {Path(path).name}")
            document = load_pdf(path)
            role = "print"
        else:
            if overrides.get(key) == "print":
                raise ValueError(f"출력본은 PDF여야 합니다: {Path(path).name}")
            document = load_document(path)
            if key in overrides:
                role = overrides[key]
            elif open_roles:
                role = open_roles.pop(0)
            else:
                raise ValueError(f"원고·개발계획서는 역할마다 한 개씩만 받습니다. 남는 파일: {Path(path).name}")
        if role in documents:
            raise ValueError(f"{ROLE_LABELS[role]} 파일이 둘 이상입니다. 역할마다 한 개씩 선택하세요")
        documents[role] = document
    unused = overrides.keys() - seen
    if unused:
        raise ValueError(f"roles에 입력 목록에 없는 경로가 있습니다: {sorted(Path(p).name for p in unused)}")
    for role in required:
        if role not in documents:
            raise ValueError(f"{ROLE_LABELS[role]} 파일이 필요합니다")
    if len(documents) > 1:
        validate_distinct({role: doc.path for role, doc in documents.items()})
    return documents

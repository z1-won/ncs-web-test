"""입력 경로 검증. 사용자 인터페이스와 독립적이다."""

from pathlib import Path
import hashlib


def file_digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


def validate_document_paths(paths):
    labels = {"plan": "개발계획서", "manuscript": "원고"}
    for role, label in labels.items():
        if not paths.get(role):
            raise ValueError(f"{label} 파일 경로를 지정하세요.")
        path = Path(paths[role])
        if not path.is_file():
            raise ValueError(f"{label} 파일을 찾을 수 없습니다: {path}")
        if path.stat().st_size == 0:
            raise ValueError(f"{label} 파일이 비어 있습니다: {path}")

    if file_digest(paths["plan"]) == file_digest(paths["manuscript"]):
        raise ValueError(
            "개발계획서와 원고의 파일 내용이 동일합니다. "
            "실제 원고를 선택한 뒤 입력 셀을 다시 실행하세요."
        )

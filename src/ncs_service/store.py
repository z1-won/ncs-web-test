"""검수 결과 저장소. 파일 폴더(FileStore)와 PostgreSQL 이력(PostgresStore) 두 구현이 같은 호출 모양을 갖는다.

웹 서버는 open_store()로 하나를 고른 뒤 save()만 부른다. 이력 조회(list/get/export_zip)는
supports_history가 True인 저장소만 제공한다. HTTP·업로드 객체는 여기 들어오지 않는다.
검수 CLI는 save_cli_review()로 같은 저장소를 쓴다(--out을 주면 폴더, 안 주면 open_store 규칙).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .models import ExecutedReview
from .service import persist_review

UploadedInput = tuple[str, Path]  # (사용자가 올린 파일 이름, 임시 저장 경로)
DEFAULT_OUT = "결과"


@dataclass(frozen=True)
class StoredReview:
    """저장 결과. run_id는 DB 이력, directory·zip_path는 파일 저장일 때만 채워진다."""

    summary: dict
    run_id: str | None = None
    directory: Path | None = None
    zip_path: Path | None = None


class FileStore:
    """실행별 폴더에 JSON·ZIP을 쓴다. 이력 조회는 없다(원고 보관도 없다)."""

    supports_history = False

    def get_manuscript(self, run_id: str) -> tuple[str, bytes] | None:
        return None

    def __init__(self, out_dir: str | Path = "결과"):
        self.out_dir = Path(out_dir).expanduser().resolve()

    def prepare(self) -> None:
        """시작 시 준비 작업. 폴더는 저장 시점에 만들므로 할 일이 없다."""

    def save(self, review: ExecutedReview, uploads: list[UploadedInput] = (), group_id: str | None = None,
             *, source: str = "web") -> StoredReview:
        # 출처(source)는 이력에만 남는 값이라 파일 저장에서는 쓰지 않는다. 전체 실행 묶음은 묶음 id 폴더 아래에 모아 둔다(이력 조회는 없지만 폴더만 봐도 한 묶음이 보이게)
        target = self.out_dir / group_id if group_id else self.out_dir
        saved = persist_review(review, target)
        return StoredReview(saved.summary, directory=saved.directory, zip_path=saved.zip_path)


class PostgresStore:
    """PostgreSQL에 이력을 쓰고 읽는다. psycopg는 실제 호출 시점에만 import한다."""

    supports_history = True

    def __init__(self, dsn: str):
        self.dsn = dsn

    def prepare(self) -> list[str]:
        from . import postgres

        return postgres.migrate(self.dsn)

    def save(self, review: ExecutedReview, uploads: list[UploadedInput] = (), group_id: str | None = None,
             *, source: str = "web") -> StoredReview:
        from . import postgres

        inputs = postgres.input_metadata(review.result.diagnostics, list(uploads))
        run_id, summary = postgres.save_review(self.dsn, review, inputs, group_id, source=source)
        return StoredReview(summary, run_id=run_id)

    def list_reviews(self, **filters) -> list[dict]:
        from . import postgres

        return postgres.list_reviews(self.dsn, **filters)

    def get_review(self, run_id: str) -> dict | None:
        from . import postgres

        return postgres.get_review(self.dsn, run_id)

    def delete_review(self, run_id: str) -> bool:
        from . import postgres

        return postgres.delete_review(self.dsn, run_id)

    # 전체 실행 묶음(group_id) — 이력 화면에서 한 줄로 보이고 한 번에 열고 지운다
    def list_groups(self, **filters) -> list[dict]:
        from . import postgres

        return postgres.list_groups(self.dsn, **filters)

    def get_group(self, group_id: str) -> dict | None:
        from . import postgres

        return postgres.get_group(self.dsn, group_id)

    def delete_group(self, group_id: str) -> bool:
        from . import postgres

        return postgres.delete_group(self.dsn, group_id)

    def get_manuscript(self, run_id: str) -> tuple[str, bytes] | None:
        """실행과 함께 보관된 원고 hwpx (파일 이름, 바이트). 이력에서 '수정 메모 원고'를 다시 만들 때 쓴다."""
        from . import postgres

        return postgres.get_manuscript(self.dsn, run_id)

    def export_zip(self, run_id: str) -> tuple[bytes, str] | None:
        """저장된 이력을 해당 엔진의 save_results로 다시 만들어 (ZIP 바이트, 파일 이름)을 돌려준다."""
        from ncs_core.models import ReviewResult

        from . import postgres

        found = self.get_review(run_id)
        if found is None:
            return None
        result = ReviewResult(found["module_code"], found["전체"], found["지적사항"], found["진단"],
                              sheet=found["검수확인서"])
        with tempfile.TemporaryDirectory(prefix="ncs_export_") as folder:
            saved = postgres.reporting_for(found["check"]).save_results(result, folder)
            return saved.zip_path.read_bytes(), saved.zip_path.name


def open_store(*, out_dir: str | Path = DEFAULT_OUT, database_url: str | None = None) -> FileStore | PostgresStore:
    """DATABASE_URL이 있으면 PostgresStore, 없으면 FileStore. 선택은 이 한 곳에서만 한다."""
    return PostgresStore(database_url) if database_url else FileStore(out_dir)


def save_cli_review(review: ExecutedReview, paths, *, out: str | Path | None = None,
                    database_url: str | None = None) -> StoredReview:
    """검수 CLI 한 건을 저장한다.

    --out을 주면(out) 언제나 그 폴더에 파일로 쓴다. 안 주면 웹 서버와 같은 규칙이다: DATABASE_URL이 있으면 DB 이력에만
    남기고(폴더를 만들지 않는다), 없으면 실행 위치의 '결과' 폴더에 쓴다. 이력의 출처는 'cli'.
    paths는 명령에 준 입력 파일 경로 — 이력에 파일 이름·해시를 남기고 원고 hwpx를 보관하는 데 쓴다.
    DB에 쓰지 못하면(드라이버 없음·접속 실패) ValueError로 올려 CLI가 메시지로 보여 주게 한다.
    """
    store = open_store(out_dir=out or DEFAULT_OUT, database_url=None if out else database_url)
    uploads = [(Path(path).name, Path(path)) for path in paths]
    try:
        store.prepare()
        return store.save(review, uploads, source="cli")
    except ModuleNotFoundError as error:
        if error.name != "psycopg":
            raise
        raise ValueError('DATABASE_URL이 설정됐지만 psycopg가 없습니다 — pip install -e ".[web]" 로 설치하거나 --out 폴더를 지정하세요') from error
    except Exception as error:
        if type(error).__module__.split(".")[0] != "psycopg":
            raise
        detail = (str(error).splitlines() or [""])[0]
        raise ValueError(f"DB 이력 저장 실패({type(error).__name__}): {detail} — DB 상태를 확인하거나 --out 폴더를 지정하세요") from error


def saved_location(stored: StoredReview) -> str:
    """저장된 곳을 한 줄로 — 파일이면 ZIP 경로, DB면 이력 id."""
    return str(stored.zip_path) if stored.zip_path is not None else f"DB 이력 {stored.run_id}"

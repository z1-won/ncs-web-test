"""업로드 보관함 — '전체 실행'이 파일을 한 번만 올리고 여러 검수에서 다시 쓰기 위한 임시 저장.

흐름: POST /api/uploads → 토큰 발급(파일은 서버 임시 폴더에) → POST /api/review upload=<토큰> 여러 번 → DELETE /api/uploads/<토큰>.
토큰은 URL-safe 난수(추측 불가)이고 만료 시간이 지나면 다음 접근 때 폴더와 함께 지워진다. 메모리·디스크에만 있고 DB에 남지 않는다.
"""

from __future__ import annotations

import secrets
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

DEFAULT_TTL = 10 * 60          # 초. 전체 실행은 보통 1~2분 안에 끝난다
DEFAULT_MAX_BYTES = 200 << 20  # 보관함 한 건의 파일 합계 상한(200MB)


@dataclass
class Upload:
    token: str
    group_id: str                 # 이 업로드로 실행한 검수들을 이력에서 한 묶음으로 묶는 id
    directory: Path
    files: list[tuple[str, Path]]  # (올린 파일 이름, 저장 경로)
    expires_at: float
    roles: dict[str, str | None] = field(default_factory=dict)  # {'manuscript': 파일명, 'plan': 파일명|None, 'print': 출력본 PDF 파일명|None}


class UploadStore:
    def __init__(self, *, ttl: float = DEFAULT_TTL, max_bytes: int = DEFAULT_MAX_BYTES):
        self.ttl = ttl
        self.max_bytes = max_bytes
        self._items: dict[str, Upload] = {}
        self._lock = threading.Lock()

    def put(self, files: list[tuple[str, bytes]]) -> Upload:
        """(파일 이름, 내용) 목록을 임시 폴더에 쓰고 토큰을 발급한다. 빈 파일은 건너뛴다."""
        self.sweep()
        if sum(len(content) for _, content in files) > self.max_bytes:
            raise ValueError(f"업로드 용량이 상한({self.max_bytes >> 20}MB)을 넘습니다")
        directory = Path(tempfile.mkdtemp(prefix="ncs_upload_"))
        saved = []
        for index, (filename, content) in enumerate(files):
            if not filename:
                continue  # 파일을 고르지 않은 빈 입력 칸은 브라우저가 이름 없는 부분으로 보낸다
            name = Path(filename).name
            if name in ("", ".", ".."):
                shutil.rmtree(directory, ignore_errors=True)
                raise ValueError("유효하지 않은 업로드 파일명입니다")
            if not content:
                continue
            folder = directory / str(index)   # 같은 이름의 파일도 서로 덮어쓰지 않게 한다
            folder.mkdir()
            path = folder / name
            path.write_bytes(content)
            saved.append((name, path))
        if not saved:
            shutil.rmtree(directory, ignore_errors=True)
            raise ValueError("업로드된 파일이 없습니다")
        upload = Upload(secrets.token_urlsafe(24), str(uuid4()), directory, saved, time.monotonic() + self.ttl)
        with self._lock:
            self._items[upload.token] = upload
        return upload

    def get(self, token: str) -> Upload | None:
        """토큰에 해당하는 업로드. 없거나 만료되었으면 None(만료분은 지운다)."""
        self.sweep()
        with self._lock:
            return self._items.get(token)

    def touch(self, token: str) -> Upload | None:
        """get과 같고, 있으면 만료 시각을 지금부터 ttl 뒤로 미룬다 — 그림을 한 장씩 업스케일하는 동안 토큰이 끊기지 않게."""
        upload = self.get(token)
        if upload is not None:
            upload.expires_at = time.monotonic() + self.ttl
        return upload

    def release(self, token: str) -> bool:
        with self._lock:
            upload = self._items.pop(token, None)
        if upload is None:
            return False
        shutil.rmtree(upload.directory, ignore_errors=True)
        return True

    def sweep(self) -> int:
        """만료된 업로드를 지운다. 지운 개수를 돌려준다."""
        now = time.monotonic()
        with self._lock:
            expired = [token for token, item in self._items.items() if item.expires_at <= now]
            removed = [self._items.pop(token) for token in expired]
        for upload in removed:
            shutil.rmtree(upload.directory, ignore_errors=True)
        return len(removed)

    def clear(self) -> None:
        with self._lock:
            items = list(self._items.values())
            self._items.clear()
        for upload in items:
            shutil.rmtree(upload.directory, ignore_errors=True)

    def __len__(self) -> int:
        return len(self._items)

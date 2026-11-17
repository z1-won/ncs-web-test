"""이미지 레코드(JSON) 읽기·검사 — 이미지 저작권 DB(REQ-02-010)에 넣기 전 단계. DB와 psycopg에 의존하지 않는다.

이미지 추출(REQ-02-009)과 공공누리 수집(REQ-02-012)이 이 형식으로 내보내면 image_db.load_records가 그대로 적재한다.
형식 설명과 예시는 docs/IMAGE_RECORD.md, docs/examples/image_records/.

레코드 1건 = 그림 파일 1개:
  {sha256 | file, filename, title, format, width_px, height_px, byte_size, kind, keywords: [...],
   upscaled: {file, format, width_px, height_px, engine},
   placements: [{module_code, module_name, page, label, caption, source_line, source_template, context_text,
                 lesson_no, para_index, width_mm, height_mm}],
   links: [{unit_code, element_code, criterion_no, placement}],
   rights: {category, ownership, reuse_scope, release_class,
            license: {scheme, kogl_type, kogl_ai, cc, note}, conditions: {…},
            author, source_org, source_url, retrieved_on, credit_line,
            ai: {used, usage, mode, tool, date, original_source, pledge_submitted, tos_scope}}}

여기서 하는 일:
  - 형식 검사: 모르는 키, 허용값 밖의 코드, 형이 다른 값은 모두 사유를 모아 RecordError로 돌려준다(한 건의 사유를 한 번에).
  - 파일 읽기: file(JSON 파일 기준 상대 경로)을 읽어 sha256·크기·형식·픽셀을 채우고, 적힌 sha256과 다르면 거부한다.
  - 파생값 채우기: 공공누리 유형·CC 유형 → 이용조건 4개와 라이선스 체계, AI 활용 유형(1~5) → 활용 방식.
    사람이 조건을 따로 적다가 유형과 어긋나는 일을 없애려는 것이다. 적었는데 유형과 다르면 거부한다.
기관 확정(status·confirmed_by …)은 적재로 할 수 없다 — 적재되는 값은 모두 '자동 태깅'이고 확정은 확정 화면에서 한다.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ncs_core.pictures import image_header

from . import image_terms

SCHEMA = "ncs-image-record/0.3"

SHA256 = re.compile(r"[0-9a-f]{64}")
CONDITIONS = ("attribution", "non_commercial", "no_derivatives", "share_alike")
CONDITION_NAMES = dict(zip(CONDITIONS, ("출처표시", "상업적 이용금지", "변경금지", "동일조건변경허락")))

ASSET_KEYS = {"sha256", "file", "content", "filename", "title", "format", "width_px", "height_px", "byte_size",
              "kind", "keywords", "upscaled", "placements", "links", "rights"}
UPSCALED_KEYS = {"file", "content", "format", "width_px", "height_px", "engine"}
PLACEMENT_TEXT = ("module_name", "caption", "source_line", "source_template", "context_text")
PLACEMENT_KEYS = {"module_code", "label", "page", "lesson_no", "para_index", "width_mm", "height_mm", *PLACEMENT_TEXT}
LINK_KEYS = {"unit_code", "element_code", "criterion_no", "placement"}
RIGHTS_TEXT = ("author", "source_org", "source_url", "credit_line")
RIGHTS_KEYS = {"category", "ownership", "reuse_scope", "release_class", "license", "conditions", "retrieved_on",
               "ai", *RIGHTS_TEXT}
LICENSE_KEYS = {"scheme", "kogl_type", "kogl_ai", "cc", "note"}
AI_KEYS = {"used", "usage", "mode", "tool", "date", "original_source", "pledge_submitted", "tos_scope"}
CONFIRMATION_KEYS = {"status", "confirmed_by", "confirmed_at", "version"}


class RecordError(ValueError):
    """레코드 1건이 형식에 맞지 않는다. reasons는 사람이 읽는 사유 목록."""

    def __init__(self, reasons: list[str]):
        super().__init__(" / ".join(reasons))
        self.reasons = reasons


@dataclass
class NormalRecord:
    """검사를 통과한 레코드 — 표의 열 이름으로 정리한 값들. rights는 레코드가 적은 묶음만 담는다(없으면 None)."""
    asset: dict
    placements: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)      # 'placement'는 placements의 순번(없으면 None)
    rights: dict | None = None


class _Checker:
    """사유를 모으며 값을 꺼내는 도우미. where는 사유 앞에 붙는 자리 이름('placements[0]' 등)."""

    def __init__(self, reasons: list[str]):
        self.reasons = reasons

    def fail(self, where: str, message: str):
        self.reasons.append(f"{where}: {message}" if where else message)

    def mapping(self, value, where: str, allowed: set[str]) -> dict:
        if not isinstance(value, dict):
            self.fail(where, "객체({…})여야 합니다")
            return {}
        unknown = sorted(set(value) - allowed)
        if unknown:
            self.fail(where, "모르는 키 " + ", ".join(unknown))
        return value

    def text(self, source: dict, key: str, where: str) -> str | None:
        value = source.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            self.fail(where, f"{key}는 문자열이어야 합니다")
            return None
        return value.strip() or None

    def integer(self, source: dict, key: str, where: str, *, minimum: int = 1) -> int | None:
        value = source.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            self.fail(where, f"{key}는 {minimum} 이상의 정수여야 합니다")
            return None
        return value

    def number(self, source: dict, key: str, where: str) -> float | None:
        value = source.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            self.fail(where, f"{key}는 0보다 큰 수여야 합니다")
            return None
        return float(value)

    def boolean(self, source: dict, key: str, where: str) -> bool | None:
        value = source.get(key)
        if value is None:
            return None
        if not isinstance(value, bool):
            self.fail(where, f"{key}는 true/false여야 합니다")
            return None
        return value

    def code(self, source: dict, key: str, where: str, terms: dict) -> str | None:
        value = source.get(key)
        if value is None:
            return None
        if value not in terms:
            names = ", ".join(f"{code}({name if isinstance(name, str) else code})" for code, name in terms.items())
            self.fail(where, f"{key} '{value}'는 허용값이 아닙니다 — {names}")
            return None
        return value

    def day(self, source: dict, key: str, where: str) -> date | None:
        value = source.get(key)
        if value is None:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            self.fail(where, f"{key}는 YYYY-MM-DD 날짜여야 합니다")
            return None


def _read_file(check: _Checker, source: dict, where: str, base_dir: Path | None) -> bytes | None:
    """content(바이트) 또는 file(base_dir 기준 상대 경로)에서 그림 파일을 읽는다."""
    content = source.get("content")
    if content is not None:
        if not isinstance(content, (bytes, bytearray)):
            check.fail(where, "content는 바이트여야 합니다(JSON에서는 file로 경로를 적습니다)")
            return None
        return bytes(content)
    name = source.get("file")
    if name is None:
        return None
    if not isinstance(name, str) or not name.strip():
        check.fail(where, "file은 경로 문자열이어야 합니다")
        return None
    if base_dir is None:
        check.fail(where, "file을 읽을 기준 폴더가 없습니다")
        return None
    base = base_dir.resolve()
    path = (base / name).resolve()
    if not path.is_relative_to(base):                     # '../'로 기준 폴더 밖 파일을 가리키지 못하게 한다
        check.fail(where, f"file '{name}'이 기준 폴더 밖을 가리킵니다")
        return None
    if not path.is_file():
        check.fail(where, f"file '{name}'을 찾을 수 없습니다")
        return None
    return path.read_bytes()


def _asset(check: _Checker, record: dict, base_dir: Path | None) -> dict:
    content = _read_file(check, record, "", base_dir)
    sha256 = record.get("sha256")
    if sha256 is not None:
        sha256 = sha256.strip().lower() if isinstance(sha256, str) else ""
        if not SHA256.fullmatch(sha256):
            check.fail("", "sha256은 16진 64자여야 합니다")
            sha256 = None
    if content is not None:
        actual = hashlib.sha256(content).hexdigest()
        if sha256 and sha256 != actual:
            check.fail("", f"sha256이 파일 내용과 다릅니다(파일 {actual[:12]}…, 적힌 값 {sha256[:12]}…)")
        sha256 = actual
    elif sha256 is None and not any("sha256" in reason for reason in check.reasons):
        check.fail("", "sha256 또는 file이 필요합니다")

    asset = {
        "sha256": sha256,
        "filename": check.text(record, "filename", ""),
        "title": check.text(record, "title", ""),
        "format": check.text(record, "format", ""),
        "width_px": check.integer(record, "width_px", ""),
        "height_px": check.integer(record, "height_px", ""),
        "byte_size": check.integer(record, "byte_size", "", minimum=0),
        "content": content,
        "kind": check.code(record, "kind", "", image_terms.KIND),
        "keywords": _keywords(check, record.get("keywords")),
    }
    if content is not None:
        asset["byte_size"] = len(content)
        _fill_from_header(asset, content, "format", "width_px", "height_px")
        if asset["filename"] is None and isinstance(record.get("file"), str):
            asset["filename"] = Path(record["file"]).name

    upscaled = record.get("upscaled")
    asset.update({"upscaled_content": None, "upscaled_format": None, "upscaled_width_px": None,
                  "upscaled_height_px": None, "upscale_engine": None})
    if upscaled is not None:
        upscaled = check.mapping(upscaled, "upscaled", UPSCALED_KEYS)
        data = _read_file(check, upscaled, "upscaled", base_dir)
        if data is None and upscaled and not any(reason.startswith("upscaled") for reason in check.reasons):
            check.fail("upscaled", "업스케일본 file이 필요합니다")
        asset.update({
            "upscaled_content": data,
            "upscaled_format": check.text(upscaled, "format", "upscaled"),
            "upscaled_width_px": check.integer(upscaled, "width_px", "upscaled"),
            "upscaled_height_px": check.integer(upscaled, "height_px", "upscaled"),
            "upscale_engine": check.text(upscaled, "engine", "upscaled"),
        })
        if data is not None:
            _fill_from_header(asset, data, "upscaled_format", "upscaled_width_px", "upscaled_height_px")
    return asset


def _fill_from_header(asset: dict, data: bytes, format_key: str, width_key: str, height_key: str):
    """적지 않은 형식·픽셀을 그림 파일 머리에서 읽어 채운다. 적은 값은 건드리지 않는다."""
    header = image_header(data)
    if header:
        for key, value in zip((format_key, width_key, height_key), header):
            if asset[key] is None:
                asset[key] = value


def _keywords(check: _Checker, value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(word, str) for word in value):
        check.fail("", "keywords는 문자열 목록이어야 합니다")
        return []
    return list(dict.fromkeys(word.strip() for word in value if word.strip()))   # 순서 유지, 중복 제거


def _placements(check: _Checker, value) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        check.fail("placements", "목록([…])이어야 합니다")
        return []
    placements, seen = [], set()
    for index, item in enumerate(value):
        where = f"placements[{index}]"
        item = check.mapping(item, where, PLACEMENT_KEYS)
        module_code = check.text(item, "module_code", where)
        if module_code is None and not any(reason.startswith(where + ": module_code") for reason in check.reasons):
            check.fail(where, "module_code가 필요합니다")
        para_index = check.integer(item, "para_index", where, minimum=0)
        placement = {
            "module_code": module_code,
            "label": check.text(item, "label", where) or "",
            "page": check.integer(item, "page", where),
            "lesson_no": check.integer(item, "lesson_no", where),
            "para_index": para_index or 0,
            "width_mm": check.number(item, "width_mm", where),
            "height_mm": check.number(item, "height_mm", where),
            **{key: check.text(item, key, where) for key in PLACEMENT_TEXT},
        }
        spot = (placement["module_code"], placement["label"], placement["para_index"])
        if spot in seen:
            check.fail(where, "같은 수록 위치(module_code·label·para_index)가 레코드 안에 두 번 있습니다")
        seen.add(spot)
        placements.append(placement)
    return placements


def _links(check: _Checker, value, placement_count: int) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        check.fail("links", "목록([…])이어야 합니다")
        return []
    links = {}
    for index, item in enumerate(value):
        where = f"links[{index}]"
        item = check.mapping(item, where, LINK_KEYS)
        unit_code = check.text(item, "unit_code", where)
        if unit_code is None and not any(reason.startswith(where + ": unit_code") for reason in check.reasons):
            check.fail(where, "unit_code가 필요합니다")
        placement = check.integer(item, "placement", where, minimum=0)
        if placement is not None and placement >= placement_count:
            check.fail(where, f"placement {placement}번 수록 위치가 없습니다(0부터 {placement_count - 1}까지)")
            placement = None
        link = {"unit_code": unit_code, "element_code": check.text(item, "element_code", where) or "",
                "criterion_no": check.text(item, "criterion_no", where) or "", "placement": placement}
        links.setdefault((link["unit_code"], link["element_code"], link["criterion_no"]), link)   # 같은 연결은 한 번만
    return list(links.values())


def _license(check: _Checker, rights: dict) -> dict:
    """라이선스 묶음 9열 — 체계, 공공누리 유형·AI유형, CC 유형, 메모, 이용조건 4개. 조건은 유형에서 정해진다."""
    where = "rights.license"
    source = check.mapping(rights.get("license") or {}, where, LICENSE_KEYS)
    given = check.mapping(rights.get("conditions") or {}, "rights.conditions", set(CONDITIONS))
    given = {key: check.boolean(given, key, "rights.conditions") for key in CONDITIONS if given.get(key) is not None}

    scheme = check.code(source, "scheme", where, image_terms.LICENSE_SCHEME)
    kogl_type = source.get("kogl_type")
    if kogl_type is not None and (isinstance(kogl_type, bool) or kogl_type not in image_terms.KOGL_CONDITIONS):
        check.fail(where, "kogl_type은 0~4여야 합니다(공공누리 제0~4유형)")
        kogl_type = None
    cc = check.code(source, "cc", where, {code: code.upper() for code in image_terms.CC_LICENSE})
    kogl_ai = check.boolean(source, "kogl_ai", where) or False

    if kogl_type is not None and cc is not None:
        check.fail(where, "공공누리 유형과 CC 유형을 함께 적을 수 없습니다")
    derived_scheme = "kogl" if kogl_type is not None else "cc" if cc is not None else None
    if derived_scheme and scheme not in (None, derived_scheme):
        check.fail(where, f"scheme '{scheme}'이 유형과 맞지 않습니다({derived_scheme}여야 함)")
    if scheme == "kogl" and kogl_type is None:
        check.fail(where, "공공누리(kogl)는 kogl_type이 필요합니다")
    if scheme == "cc" and cc is None:
        check.fail(where, "CCL(cc)은 cc 유형이 필요합니다")
    if kogl_ai and kogl_type not in (1, 2, 3, 4):
        check.fail(where, "AI유형(kogl_ai)은 제1~4유형과만 함께 표시됩니다")

    if kogl_type is not None:
        fixed = dict(zip(CONDITIONS, (*image_terms.KOGL_CONDITIONS[kogl_type], False)))
    elif cc is not None:
        fixed = dict(zip(CONDITIONS, image_terms.CC_LICENSE[cc]))
    else:
        fixed = None
    if fixed is None:
        conditions = {key: given.get(key) for key in CONDITIONS}
    else:
        conditions = fixed
        for key, value in given.items():
            if value is not None and value != fixed[key]:
                check.fail("rights.conditions",
                           f"{CONDITION_NAMES[key]}({key})가 라이선스 유형과 다릅니다 — 유형에 따르면 {str(fixed[key]).lower()}")
    return {"license_scheme": scheme or derived_scheme, "kogl_type": kogl_type, "kogl_ai": kogl_ai, "cc_license": cc,
            "license_note": check.text(source, "note", where), **conditions}


def _ai(check: _Checker, source) -> dict:
    """AI 기준 필드 8열. used를 적지 않았더라도 다른 AI 필드가 있으면 쓴 것으로 본다."""
    where = "rights.ai"
    source = check.mapping(source, where, AI_KEYS)
    usage = source.get("usage")
    if usage is not None and (isinstance(usage, bool) or usage not in image_terms.AI_USAGE):
        check.fail(where, "usage는 1~5여야 합니다(AI 도구 사용 표기 예 번호)")
        usage = None
    mode = check.code(source, "mode", where, image_terms.AI_MODE)
    if usage is not None:
        expected = image_terms.AI_USAGE[usage][1]
        if mode is not None and mode != expected:
            check.fail(where, f"usage {usage}({image_terms.AI_USAGE[usage][0]})는 "
                              f"'{image_terms.AI_MODE[expected]}'인데 mode가 '{image_terms.AI_MODE[mode]}'입니다")
        mode = expected
    fields = {
        "ai_usage": usage, "ai_mode": mode, "ai_tool": check.text(source, "tool", where),
        "ai_date": check.day(source, "date", where),
        "ai_original_source": check.text(source, "original_source", where),
        "ai_pledge_submitted": check.boolean(source, "pledge_submitted", where),
        "ai_tos_scope": check.text(source, "tos_scope", where),
    }
    used = check.boolean(source, "used", where)
    filled = any(value is not None for value in fields.values())
    if used is False and filled:
        check.fail(where, "used가 false인데 다른 AI 필드가 채워져 있습니다")
    return {"ai_used": filled if used is None else used, **fields}


def _rights(check: _Checker, value) -> dict | None:
    if value is None:
        return None
    confirmation = sorted(CONFIRMATION_KEYS & set(value)) if isinstance(value, dict) else []
    if confirmation:
        check.fail("rights", "기관 확정은 적재로 할 수 없습니다(" + ", ".join(confirmation) + " 삭제) — 확정 화면에서 합니다")
        value = {key: item for key, item in value.items() if key not in CONFIRMATION_KEYS}
    source = check.mapping(value, "rights", RIGHTS_KEYS)
    rights = {}
    for key, terms in (("category", image_terms.CATEGORY), ("ownership", image_terms.OWNERSHIP),
                       ("reuse_scope", image_terms.REUSE_SCOPE), ("release_class", image_terms.RELEASE_CLASS)):
        code = check.code(source, key, "rights", terms)
        if code is not None:
            rights[key] = code
    for key in RIGHTS_TEXT:
        text = check.text(source, key, "rights")
        if text is not None:
            rights[key] = text
    retrieved_on = check.day(source, "retrieved_on", "rights")
    if retrieved_on is not None:
        rights["retrieved_on"] = retrieved_on
    if source.get("license") is not None or source.get("conditions") is not None:
        rights.update(_license(check, source))
    if source.get("ai") is not None:
        rights.update(_ai(check, source["ai"]))
    if rights.get("ownership") == "kogl" and rights.get("kogl_type") is None:
        check.fail("rights", "귀속이 공공누리 조건(kogl)이면 license.kogl_type이 필요합니다")
    return rights


LICENSE_COLUMNS = ("license_scheme", "kogl_type", "kogl_ai", "cc_license", "license_note", *CONDITIONS)
AI_COLUMNS = ("ai_used", "ai_usage", "ai_mode", "ai_tool", "ai_date", "ai_original_source", "ai_pledge_submitted",
              "ai_tos_scope")
CLEARABLE = ("category", "ownership", "release_class", "retrieved_on", *RIGHTS_TEXT)


def rights_changes(value) -> dict:
    """확정 화면의 권리 정보 수정 요청 → 바꿀 열 {열: 값}. 모양은 레코드의 rights와 같다(같은 검사·같은 파생값).

    레코드와 다른 점 하나: 값을 null로 적으면 그 칸을 비운다. license: null은 라이선스 묶음 전체를,
    ai: null은 AI 묶음 전체를 비우고(AI 미사용), reuse_scope: null은 '미확인'으로 되돌린다.
    """
    reasons: list[str] = []
    changes = _rights(_Checker(reasons), value if value is not None else {}) or {}
    if isinstance(value, dict):
        for key in CLEARABLE:
            if key in value and value[key] is None:
                changes[key] = None
        if "reuse_scope" in value and value["reuse_scope"] is None:
            changes["reuse_scope"] = "unknown"
        if "license" in value and value["license"] is None and value.get("conditions") is None:
            changes.update({column: None for column in LICENSE_COLUMNS}, kogl_ai=False)
        if "ai" in value and value["ai"] is None:
            changes.update({column: None for column in AI_COLUMNS}, ai_used=False)
    if reasons:
        raise RecordError(reasons)
    if not changes:
        raise RecordError(["바꿀 내용이 없습니다"])
    return changes


def normalize(record, *, base_dir: str | Path | None = None) -> NormalRecord:
    """레코드 1건을 검사해 표의 열 이름으로 정리한다. 맞지 않으면 사유를 모두 모아 RecordError."""
    reasons: list[str] = []
    check = _Checker(reasons)
    if not isinstance(record, dict):
        raise RecordError(["레코드는 객체({…})여야 합니다"])
    check.mapping(record, "", ASSET_KEYS)
    asset = _asset(check, record, Path(base_dir) if base_dir is not None else None)
    placements = _placements(check, record.get("placements"))
    links = _links(check, record.get("links"), len(placements))
    rights = _rights(check, record.get("rights"))
    if reasons:
        raise RecordError(reasons)
    return NormalRecord(asset, placements, links, rights)


def read_records(path: str | Path) -> tuple[list, Path]:
    """레코드 JSON 파일 → (레코드 목록, file 경로의 기준 폴더). {"schema": …, "records": […]} 또는 목록 그대로."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        schema = data.get("schema")
        if schema != SCHEMA:
            raise ValueError(f"schema가 '{SCHEMA}'여야 합니다(파일: {schema!r})")
        data = data.get("records")
    if not isinstance(data, list):
        raise ValueError("records는 목록([…])이어야 합니다")
    return data, path.parent

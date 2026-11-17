"""공공누리 이미지 샘플 수집 JSON(0.1-PoC) 적재 — REQ-02-012. 과업 안내의 입력 예시
(`Input/REQ-02-012/T01_공공누리 이미지 메타데이터_JSON 키-값 예시.json`) 형식을 그대로 받아 이미지 레코드로 바꾼다.

    {"schema_version": "0.1-PoC", "dataset": …, "collected_at": …,
     "items": [{"image_id", "title", "file": {"name", "format", "width_px", "height_px"},
                "ncs_link": {"lm_code", "unit_name", "element", "performance_criteria", "match_keywords": […]},
                "kogl": {"type": "제1유형", "ai_type_combined": false, "conditions": {…}},
                "source": {"original_org", "original_url", "retrieved_at", "credit_line"},
                "status": {"tagging", "confirmed_by", "db_target"}}]}

바꾸는 규칙:
  그림 파일     file.name으로 함께 올린 그림을 찾는다. 그림의 동일성(sha256)은 파일에서만 나오므로 **그림 파일이 없는 건은 거부**한다.
                형식·픽셀은 파일에서 읽고, JSON에 적힌 값과 다르면 안내로 알린다
  공공누리      type('제0유형'~'제4유형') → 유형 번호, ai_type_combined → AI유형 병행. conditions는 유형에서 정해지는 값과 같아야 한다
                (다르면 거부 — 유형·이용조건 태깅 정확도의 근거). AI유형이 병행돼도 조건은 함께 표시된 유형 그대로다
  출처 문구     credit_line은 적힌 것을 쓰지 않고 URL·검색일·유형에서 만든다(예시와 같은 꼴):
                '공공누리 홈페이지(URL)에서 2026. 10. 16. 검색. 공공누리 제1유형.' 적힌 문구가 이것과 다르면 안내로 알린다
  수행준거      lm_code에서 능력단위 코드를 얻고(NCS 목록에 있으면 버전까지), element·performance_criteria의 글이
                NCS 요소·수행준거와 맞으면 코드로 잇는다. 못 찾으면 능력단위까지만 잇고 안내로 알린다. match_keywords는 주요 키워드로
  권리 정보     분류 = 공공누리·공유마당, 귀속 = 공공누리 조건, 제2~4유형은 산출물 분류 = 원 조건 승계(REQ-04-006).
                확정 상태는 언제나 '자동 태깅'으로 들어간다 — status.confirmed_by가 적혀 있어도 확정은 확정 화면에서 한다
  고유번호      image_id → source_id(수집 목록과 DB의 그림을 맞춰 보는 이름표)
예시 파일의 자리표시('(예시) …', '(해당 자료 URL)')가 남아 있는 건은 거부한다.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from ncs_core.ncs_catalog import catalog
from ncs_core.pictures import image_header

SCHEMA_VERSION = "0.1-PoC"
KOGL_HOSTS = ("kogl.or.kr", "kogl.go.kr")        # 실제 포털은 or.kr, F14 집필 양식의 예시는 go.kr — 둘 다 받아들인다
TYPE = re.compile(r"^\s*(?:제)?\s*([0-4])\s*(?:유형)?\s*$")
PLACEHOLDER = re.compile(r"\(\s*예시\s*\)|\(\s*해당\s*자료")
CONDITIONS = ("attribution", "non_commercial", "no_derivatives")
FORMAT_ALIASES = {"jpg": "jpeg", "jpeg-progressive": "jpeg"}


def is_dataset(data) -> bool:
    """공공누리 수집 JSON인가 — schema_version이 0.1-PoC이고 items가 있다."""
    return isinstance(data, dict) and "items" in data and str(data.get("schema_version", "")).strip() == SCHEMA_VERSION


def credit_line(url: str, retrieved_on: date, kogl_type: int) -> str:
    """원고에 적는 출처 문구(F14 '전자 자료·검색' 골격 + 공공누리 유형)."""
    return (f"공공누리 홈페이지({url})에서 {retrieved_on.year}. {retrieved_on.month}. {retrieved_on.day}. 검색. "
            f"공공누리 제{kogl_type}유형.")


def _squash(text: str) -> str:
    return re.sub(r"[\W_]+", "", str(text or "")).lower()


def _link(ncs: dict, notes: list[str], reasons: list[str]) -> dict | None:
    """ncs_link → 수행준거 연결 1건. 능력단위를 알 수 없으면 None."""
    lm_code = str(ncs.get("lm_code") or "").strip()
    if not lm_code:
        notes.append("ncs_link.lm_code가 없어 수행준거에 잇지 않았습니다")
        return None
    digits = re.sub(r"^LM", "", lm_code, flags=re.IGNORECASE).lower()
    if not re.fullmatch(r"\d{10}(_\d+v\d+)?", digits):
        reasons.append(f"ncs_link.lm_code '{lm_code}'는 LM + 숫자 10자리(+ _NNvN) 꼴이어야 합니다")
        return None
    found = catalog()
    unit = found.unit(digits) if found else None
    unit_code = unit.code if unit else digits
    if unit is None:
        notes.append(f"능력단위 {digits}을(를) NCS 목록에서 찾지 못해 적힌 코드 그대로 이었습니다")
    link = {"unit_code": unit_code}
    element_name, criterion = str(ncs.get("element") or "").strip(), str(ncs.get("performance_criteria") or "").strip()
    detail = found.unit_detail(digits) if found else None
    if not (element_name or criterion):
        return link
    if detail is None:
        notes.append("이 능력단위의 요소·수행준거 표가 없어 능력단위까지만 이었습니다(scripts/data/build_ncs_elements.py)")
        return link
    element = next((e for e in detail["elements"] if element_name and _squash(e["name"]) == _squash(element_name)), None)
    for candidate in ([element] if element else detail["elements"]):
        for text in candidate["criteria"] if criterion else []:
            number = re.match(r"^\s*(\d+\.\d+)\s*(.*)$", text)
            if number and _squash(number.group(2)) == _squash(criterion):
                return {**link, "element_code": candidate["code"], "criterion_no": number.group(1)}
    if element is not None:
        if criterion:
            notes.append("수행준거 글이 NCS와 달라 능력단위요소까지만 이었습니다")
        return {**link, "element_code": element["code"]}
    notes.append("능력단위요소·수행준거 글이 NCS와 달라 능력단위까지만 이었습니다")
    return link


def convert_item(item, base_dir: Path | None) -> tuple[dict | None, list[str], list[str]]:
    """수집 JSON의 항목 1건 → (이미지 레코드 또는 None, 거부 사유, 안내)."""
    reasons: list[str] = []
    notes: list[str] = []
    if not isinstance(item, dict):
        return None, ["항목은 객체({…})여야 합니다"], notes

    def part(name: str) -> dict:
        value = item.get(name)
        if value is None:
            return {}
        if not isinstance(value, dict):
            reasons.append(f"{name}은(는) 객체({{…}})여야 합니다")
            return {}
        return value

    file, ncs, kogl, source, status = (part(name) for name in ("file", "ncs_link", "kogl", "source", "status"))
    title = str(item.get("title") or "").strip()
    org, url = str(source.get("original_org") or "").strip(), str(source.get("original_url") or "").strip()
    if any(PLACEHOLDER.search(text) for text in (title, org, url)):
        reasons.append("예시 파일의 자리표시('(예시) …', '(해당 자료 URL)')가 남아 있습니다 — 실제 값으로 바꿔 주세요")

    # ── 그림 파일 ──
    name = str(file.get("name") or "").strip()
    record: dict = {"source_id": str(item.get("image_id") or "").strip() or None, "title": title or None}
    if not name:
        reasons.append("file.name(그림 파일 이름)이 필요합니다")
    else:
        record["file"] = Path(name.replace("\\", "/")).name
        path = (base_dir / record["file"]) if base_dir is not None else None
        if path is None or not path.is_file():
            reasons.append(f"그림 파일 '{record['file']}'이(가) 함께 올라오지 않았습니다 — 그림 파일이 있어야 적재할 수 있습니다")
        else:
            header = image_header(path.read_bytes())
            if header is None:
                notes.append(f"'{record['file']}'의 형식·크기를 읽지 못했습니다(png·jpeg·bmp만 읽음)")
            else:
                actual, width, height = header
                declared = str(file.get("format") or "").strip().lower()
                if declared and FORMAT_ALIASES.get(declared, declared) != FORMAT_ALIASES.get(actual, actual):
                    notes.append(f"file.format은 {declared}인데 실제 파일은 {actual}입니다(실제 값으로 넣음)")
                if file.get("width_px") and file.get("height_px") and (file["width_px"], file["height_px"]) != (width, height):
                    notes.append(f"적힌 크기 {file['width_px']}×{file['height_px']}px와 실제 {width}×{height}px가 다릅니다(실제 값으로 넣음)")
    keywords = ncs.get("match_keywords")
    if keywords is not None:
        if isinstance(keywords, list) and all(isinstance(word, str) for word in keywords):
            record["keywords"] = keywords
        else:
            reasons.append("ncs_link.match_keywords는 문자열 목록이어야 합니다")

    # ── 공공누리 유형·조건 ──
    found = TYPE.match(str(kogl.get("type"))) if kogl.get("type") is not None and not isinstance(kogl.get("type"), bool) else None
    kogl_type = int(found.group(1)) if found else None
    if kogl_type is None:
        reasons.append(f"kogl.type '{kogl.get('type')}'은(는) 제0유형~제4유형 중 하나여야 합니다")
    combined = kogl.get("ai_type_combined")
    if combined is not None and not isinstance(combined, bool):
        reasons.append("kogl.ai_type_combined는 true/false여야 합니다")
        combined = None
    conditions = kogl.get("conditions")
    if conditions is not None and not isinstance(conditions, dict):
        reasons.append("kogl.conditions는 객체({…})여야 합니다")
        conditions = None

    # ── 출처 ──
    retrieved_on = None
    try:
        retrieved_on = date.fromisoformat(str(source.get("retrieved_at") or ""))
    except ValueError:
        reasons.append("source.retrieved_at(검색일)은 YYYY-MM-DD 날짜여야 합니다")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or re.search(r"\s", url):
        reasons.append("source.original_url은 http(s) 주소여야 합니다")
    elif not any(parsed.netloc == host or parsed.netloc.endswith("." + host) for host in KOGL_HOSTS):
        notes.append(f"출처 주소가 공공누리({' / '.join(KOGL_HOSTS)})가 아닙니다 — 공공누리 자료 페이지 주소인지 확인하세요")
    if not org:
        reasons.append("source.original_org(원 출처 기관)이 필요합니다")

    link = _link(ncs, notes, reasons)
    if status.get("confirmed_by"):
        notes.append("status.confirmed_by는 쓰지 않았습니다 — 기관 확정은 확정 화면에서 합니다")
    if reasons:
        return None, reasons, notes

    made = credit_line(url, retrieved_on, kogl_type)
    written = str(source.get("credit_line") or "").strip()
    if written and _squash(written) != _squash(made):
        notes.append(f"적힌 출처 문구 대신 URL·검색일·유형으로 만든 문구를 넣었습니다 — 「{made}」")
    record["rights"] = {
        "category": "public_license", "ownership": "kogl",
        "license": {"kogl_type": kogl_type, "kogl_ai": bool(combined)},
        **({"conditions": {key: conditions[key] for key in CONDITIONS if key in conditions}} if conditions else {}),
        **({"release_class": "inherit"} if kogl_type >= 2 else {}),
        "source_org": org, "source_url": url, "retrieved_on": retrieved_on.isoformat(), "credit_line": made,
    }
    if link is not None:
        record["links"] = [link]
    return record, reasons, notes


def convert(data: dict, base_dir: str | Path | None) -> tuple[list[dict], list[int], list[dict], list[dict]]:
    """수집 JSON → (이미지 레코드들, 각 레코드의 원래 항목 순번, 거부 [{'index','sha256','reasons'}], 안내 [{'index','image_id','notes'}])."""
    base = Path(base_dir) if base_dir is not None else None
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("items는 목록([…])이어야 합니다")
    records, indexes, rejected, notes = [], [], [], []
    for index, item in enumerate(items):
        record, reasons, item_notes = convert_item(item, base)
        if record is None:
            rejected.append({"index": index, "sha256": None, "reasons": reasons})
        else:
            records.append(record)
            indexes.append(index)
        if item_notes:
            notes.append({"index": index, "image_id": item.get("image_id") if isinstance(item, dict) else None, "notes": item_notes})
    return records, indexes, rejected, notes


def run(dsn: str | None, data: dict, *, base_dir: str | Path | None, by: str = "", check_only: bool = False) -> dict:
    """수집 JSON을 검사하거나(check_only) 적재한다. 반환은 image_db의 적재 보고서와 같은 모양 + '안내' + '형식'.

    거부의 index는 수집 JSON의 items 순번이다(레코드로 바꾸다 거부된 건과 적재하다 거부된 건을 한 목록으로).
    """
    from . import image_db

    records, indexes, rejected, notes = convert(data, base_dir)
    total = len(records) + len(rejected)

    def original(items: list[dict]) -> list[dict]:
        return [{**item, "index": indexes[item["index"]]} for item in items]

    if check_only:
        checked = image_db.check_records(records, base_dir=base_dir)
        rejected = sorted(rejected + original(checked["거부"]), key=lambda item: item["index"])
        return {"형식": f"공공누리 수집 JSON({SCHEMA_VERSION})", "전체": total, "통과": total - len(rejected),
                "거부": rejected, "안내": notes}
    if dsn is None:
        raise ValueError("적재하려면 데이터베이스(DATABASE_URL)가 필요합니다")
    report = image_db.load_records(dsn, records, changed_by=by, base_dir=base_dir)
    report.rejected = sorted(rejected + original(report.rejected), key=lambda item: item["index"])
    report.total = total
    return {"형식": f"공공누리 수집 JSON({SCHEMA_VERSION})", **report.as_dict(), "안내": notes}

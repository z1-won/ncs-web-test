"""Claude 호출 — 공식 anthropic SDK.

환경 변수(저장소 루트 .env도 읽는다 — 이미 있는 환경 변수는 덮어쓰지 않음)
  ANTHROPIC_API_KEY   없으면 LLM 검토가 꺼진다(화면에 이유 표시)
  LLM_ALLOW_UPLOAD    "1"이어야 원고 글을 보낸다(기관의 외부 전송 승인 — 코어 LLM과 같은 스위치)
  LLM_REVIEW_MODEL    기본 claude-sonnet-5-5
  LLM_REVIEW_EFFORT   기본 medium (low | medium | high | xhigh | max)
  LLM_CACHE_DIR       기본 <저장소>/.llm_cache — 그 아래 llmreview/에 응답 캐시와 usage.jsonl

요청: system(원고마다 같음) → user 첫 블록 [원고](프롬프트 캐시) → user 둘째 블록 [검토 항목].
원고 블록까지가 같은 접두라서 같은 원고를 다시 부르면(항목을 나눠 부를 때, 다시 검토할 때) 원고는 캐시 읽기 값만 냄.
구조화 출력(JSON 스키마), temperature 안 보냄, 거절 대비 서버 대체 모델. 같은 요청은 디스크 캐시에서 다시 읽어 토큰을 안 씀.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_EFFORT = "medium"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
ROOT = Path(__file__).resolve().parents[2]
PRICES = {"claude-sonnet-5-5": (2.0, 10.0, 0.10, 2.5), "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0)}   # 100만 토큰당 USD(입력, 출력, 캐시 읽기, 캐시 쓰기)
_ENV_LOADED = False


class ClaudeError(RuntimeError):
    pass


def _load_dotenv() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def settings() -> dict:
    _load_dotenv()
    return {"model": os.getenv("LLM_REVIEW_MODEL") or DEFAULT_MODEL, "effort": os.getenv("LLM_REVIEW_EFFORT") or DEFAULT_EFFORT,
            "has_key": bool(os.getenv("ANTHROPIC_API_KEY")), "allow_upload": os.getenv("LLM_ALLOW_UPLOAD", "") == "1",
            "cache_dir": Path(os.getenv("LLM_CACHE_DIR") or ROOT / ".llm_cache") / "llmreview"}


def why_not(cfg: dict | None = None) -> str:
    cfg = cfg or settings()
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return "anthropic 패키지가 없습니다 — pip install -r requirements/web.txt"
    if not cfg["has_key"]:
        return "ANTHROPIC_API_KEY가 없습니다 — 저장소 루트 .env에 넣고 서버를 다시 켜세요"
    if not cfg["allow_upload"]:
        return "원고 외부 전송이 승인되지 않았습니다 — 승인 후 .env에 LLM_ALLOW_UPLOAD=1"
    return ""


def schema(tasks: list[str] | None = None) -> dict:
    task = {"type": "string", "enum": list(tasks)} if tasks else {"type": "string"}
    item = {"type": "object",
            "properties": {"항목": task, "n": {"type": "integer"}, "문제": {"type": "string"}, "인용": {"type": "string"},
                           "이유": {"type": "string"}, "수정 문장": {"type": "string"}},
            "required": ["항목", "n", "문제", "인용", "이유", "수정 문장"], "additionalProperties": False}
    return {"type": "object", "properties": {"지적": {"type": "array", "items": item}}, "required": ["지적"], "additionalProperties": False}


def cost(model: str, usage: dict) -> float | None:
    price = PRICES.get(model)
    if not price:
        return None
    fresh = usage.get("input", 0) - usage.get("cache_read", 0) - usage.get("cache_write", 0)
    return (fresh * price[0] + usage.get("output", 0) * price[1] + usage.get("cache_read", 0) * price[2]
            + usage.get("cache_write", 0) * price[3]) / 1_000_000


def _parse(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def generate_json(system: str, document: str, request: str, *, task: str, tasks: list[str] | None = None,
                  out_schema: dict | None = None) -> dict:
    """→ {'data', 'usage', 'cached', 'model'}. document = [원고](캐시), request = [검토 항목]. 키·승인이 없으면 ClaudeError.
    out_schema: 출력 JSON 스키마(없으면 schema(tasks) — '지적' 목록). 의견 반영 검토·문장 추천처럼 답 모양이 다른 기능이 준다."""
    cfg = settings()
    model, effort = cfg["model"], cfg["effort"]
    out_schema = out_schema or schema(tasks)
    digest = hashlib.sha256(json.dumps(["claude", model, system, document, request, effort, out_schema],
                                       ensure_ascii=False).encode("utf-8")).hexdigest()[:32]
    path = cfg["cache_dir"] / task / f"{digest}.json"
    if path.is_file():
        return {**json.loads(path.read_text(encoding="utf-8")), "cached": True}
    problem = why_not(cfg)
    if problem:
        raise ClaudeError(problem)
    import anthropic
    client = anthropic.Anthropic(max_retries=5, timeout=600)
    try:
        resp = client.beta.messages.create(
            model=model, max_tokens=16000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": [
                {"type": "text", "text": document, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": request}]}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": out_schema}},
            betas=[FALLBACK_BETA], fallbacks="default",
        )
    except anthropic.AuthenticationError:
        raise ClaudeError("ANTHROPIC_API_KEY가 틀림(401)") from None
    except anthropic.PermissionDeniedError as e:
        raise ClaudeError(f"권한 없음(403): {e.message}") from None
    except anthropic.NotFoundError:
        raise ClaudeError(f"모델 이름이 없음: {model}") from None
    except anthropic.BadRequestError as e:
        raise ClaudeError(f"요청 오류(400): {e.message}") from None
    except anthropic.RateLimitError as e:
        raise ClaudeError(f"한도 초과(429): {e.message}") from None
    except anthropic.APIStatusError as e:
        raise ClaudeError(f"Claude {e.status_code}: {e.message}") from None
    except anthropic.APIConnectionError:
        raise ClaudeError("Claude 연결 실패") from None
    u = resp.usage
    usage = {"input": (u.input_tokens or 0) + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0),
             "output": u.output_tokens or 0, "cache_read": u.cache_read_input_tokens or 0,
             "cache_write": u.cache_creation_input_tokens or 0, "finish": resp.stop_reason, "served_by": resp.model}
    cfg["cache_dir"].mkdir(parents=True, exist_ok=True)
    with open(cfg["cache_dir"] / "usage.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "task": task, "model": model, **usage}, ensure_ascii=False) + "\n")
    if resp.stop_reason == "refusal":
        raise ClaudeError("모델이 답하지 않음(refusal) — 대체 모델까지 거절")
    if resp.stop_reason == "max_tokens":
        raise ClaudeError("출력이 max_tokens에서 잘림")
    raw = "".join(b.text for b in resp.content if b.type == "text")
    try:
        data = _parse(raw)
    except json.JSONDecodeError as error:
        raise ClaudeError(f"JSON이 아닌 응답: {raw[:200]}") from error
    result = {"data": data, "usage": usage, "model": model}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return {**result, "cached": False}

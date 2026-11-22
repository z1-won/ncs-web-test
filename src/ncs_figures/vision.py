"""그림을 보는 모델(VLM) 호출 — 모델을 바꿔 끼울 수 있게 '제공자:모델' 이름으로 고른다(예: anthropic:claude-sonnet-5-5).

지금 구현한 제공자: anthropic(공식 SDK). 다른 모델로 비교 시험할 때는 같은 VisionModel 모양의 클래스를 PROVIDERS에 더하면 된다
(예: openai — 설계서 5.3.4 M4). 판독·점검 코드는 제공자를 모른다.

외부 전송 규칙(설계서 5.7): LLM_ALLOW_UPLOAD=1(원고 반출 승인) 그리고 LLM_ALLOW_IMAGE_UPLOAD=1(그림 반출 승인)이어야 보낸다.
그림마다의 전송 표시(기본 모두 허용, 사람이 정한 값·FIG_TRANSFER_OTHERS로 막음)는 호출하는 쪽(reading.py)이 먼저 본다. LLM_LOCAL_ONLY=1이면 아무것도 보내지 않는다.
보내는 그림: 원본을 PNG로 바꾸고 긴 변이 MAX_SIDE를 넘으면 줄이기만 한다(키우지 않음 — 업스케일본은 글자를 지어낼 수 있음).
같은 (제공자, 모델, 프롬프트, 그림)은 캐시(<저장소>/.llm_cache/figures)에서 다시 읽어 토큰을 쓰지 않는다.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPEC = "anthropic:claude-sonnet-5-5"
MAX_SIDE = 1568
# 100만 토큰당 USD(입력, 출력) — 비용 '추정'용. 실제 차감은 각 회사 콘솔에서 확인
PRICES = {"claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0), "claude-haiku-5-5": (0.10, 0.50)}
_ENV_LOADED = False


class VisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class VisionAnswer:
    data: dict
    model: str                      # "제공자:모델"
    cached: bool
    usage: dict = field(default_factory=dict)
    seconds: float = 0.0


class VisionModel(Protocol):
    name: str

    def ask(self, *, task: str, system: str, text: str, image_png: bytes, schema: dict) -> VisionAnswer: ...


def load_dotenv() -> None:
    """저장소 루트 .env를 한 번 읽는다(이미 있는 환경 변수는 덮어쓰지 않음)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    path = ROOT / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def why_not_send() -> str:
    """그림을 밖으로 보내면 안 되는 이유(없으면 '')."""
    load_dotenv()
    if os.getenv("LLM_LOCAL_ONLY") == "1":
        return "로컬 전용 모드(LLM_LOCAL_ONLY=1) — 외부 모델 호출 안 함"
    if os.getenv("LLM_ALLOW_UPLOAD", "") != "1":
        return "원고 외부 전송 미승인 — .env에 LLM_ALLOW_UPLOAD=1"
    if os.getenv("LLM_ALLOW_IMAGE_UPLOAD", "") != "1":
        return "그림 외부 전송 미승인 — 승인 후 .env에 LLM_ALLOW_IMAGE_UPLOAD=1"
    return ""


def vision_status(spec: str | None = None) -> dict:
    """화면용: 그림 모델을 쓸 수 있나, 못 쓰면 왜, 어떤 모델, 그림을 보내나(기본 전부 — FIG_TRANSFER_OTHERS로 막을 수 있음)."""
    load_dotenv()
    spec = spec or os.getenv("FIG_VISION_MODEL") or DEFAULT_SPEC
    problem = why_not_send()
    if not problem and spec.startswith("anthropic:") and not os.getenv("ANTHROPIC_API_KEY"):
        problem = "ANTHROPIC_API_KEY가 없습니다 — 저장소 루트 .env에 넣으세요"
    others = os.getenv("FIG_TRANSFER_OTHERS", "").strip() or "허용"
    return {"available": not problem, "problem": problem or None, "model": spec, "transfer_others": others,
            "price_note": "그림 1장(판독+캡션 판정) 약 $0.017 — Sonnet 5.5 기준 실측"}


def png_for_model(data: bytes, max_side: int = MAX_SIDE) -> bytes:
    from PIL import Image
    image = Image.open(io.BytesIO(data))
    image.load()
    if image.mode in ("RGBA", "LA", "P", "PA"):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, "white")
        canvas.paste(rgba, mask=rgba.getchannel("A"))
        image = canvas
    else:
        image = image.convert("RGB")
    if max(image.size) > max_side:
        image.thumbnail((max_side, max_side), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def cost(model: str, usage: dict) -> float | None:
    price = PRICES.get(model.split(":", 1)[-1])
    if not price:
        return None
    return (usage.get("input", 0) * price[0] + usage.get("output", 0) * price[1]) / 1_000_000


class _Cached:
    """캐시·사용량 기록을 맡는 바탕. 하위 클래스는 _call만 구현한다."""

    provider = ""

    def __init__(self, model: str):
        self.model = model
        self.name = f"{self.provider}:{model}"
        self.cache_dir = Path(os.getenv("LLM_CACHE_DIR") or ROOT / ".llm_cache") / "figures"

    def ask(self, *, task: str, system: str, text: str, image_png: bytes, schema: dict) -> VisionAnswer:
        key = hashlib.sha256(json.dumps([self.name, task, system, text, hashlib.sha256(image_png).hexdigest(), schema],
                                        ensure_ascii=False).encode("utf-8")).hexdigest()[:32]
        path = self.cache_dir / task / f"{key}.json"
        if path.is_file():
            saved = json.loads(path.read_text(encoding="utf-8"))
            return VisionAnswer(saved["data"], saved["model"], True, saved.get("usage", {}), saved.get("seconds", 0.0))
        problem = why_not_send()
        if problem:
            raise VisionError(problem)
        started = time.perf_counter()
        data, usage = self._call(system=system, text=text, image_png=image_png, schema=schema)
        seconds = round(time.perf_counter() - started, 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"data": data, "model": self.name, "usage": usage, "seconds": seconds, "task": task,
                                    "at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False, indent=1), encoding="utf-8")
        with open(self.cache_dir / "usage.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "task": task, "model": self.name, **usage}, ensure_ascii=False) + "\n")
        return VisionAnswer(data, self.name, False, usage, seconds)

    def _call(self, *, system: str, text: str, image_png: bytes, schema: dict) -> tuple[dict, dict]:
        raise NotImplementedError


class AnthropicVision(_Cached):
    """Claude — 구조화 출력(JSON 스키마), 거절 시 서버 대체 모델, temperature 안 보냄."""

    provider = "anthropic"

    def _call(self, *, system, text, image_png, schema):
        load_dotenv()
        try:
            import anthropic
        except ImportError:
            raise VisionError("anthropic 패키지가 없습니다 — pip install -r requirements/web.txt") from None
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise VisionError("ANTHROPIC_API_KEY가 없습니다 — 저장소 루트 .env에 넣으세요")
        client = anthropic.Anthropic(max_retries=5, timeout=300)
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": base64.b64encode(image_png).decode()}},
                   {"type": "text", "text": text}]
        try:
            resp = client.beta.messages.create(
                model=self.model, max_tokens=4000,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content}],
                output_config={"effort": os.getenv("FIG_VISION_EFFORT") or "medium", "format": {"type": "json_schema", "schema": schema}},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            )
        except anthropic.AuthenticationError:
            raise VisionError("ANTHROPIC_API_KEY가 틀림(401)") from None
        except anthropic.NotFoundError:
            raise VisionError(f"모델 이름이 없음: {self.model}") from None
        except anthropic.BadRequestError as e:
            raise VisionError(f"요청 오류(400): {e.message}") from None
        except anthropic.RateLimitError as e:
            raise VisionError(f"한도 초과(429): {e.message}") from None
        except anthropic.APIStatusError as e:
            raise VisionError(f"Claude {e.status_code}: {e.message}") from None
        except anthropic.APIConnectionError:
            raise VisionError("Claude 연결 실패") from None
        u = resp.usage
        usage = {"input": (u.input_tokens or 0) + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0),
                 "output": u.output_tokens or 0, "served_by": resp.model, "stop": resp.stop_reason}
        if resp.stop_reason == "refusal":
            raise VisionError("모델이 답하지 않음(refusal)")
        raw = "".join(b.text for b in resp.content if b.type == "text")
        try:
            return json.loads(raw), usage
        except json.JSONDecodeError:
            raise VisionError(f"JSON이 아닌 응답: {raw[:200]}") from None


class FakeVision:
    """시험용 — answer(task, text) -> dict. 외부로 아무것도 보내지 않는다."""

    def __init__(self, answer: Callable[[str, str], dict], name: str = "fake:model"):
        self.answer, self.name, self.calls = answer, name, []

    def ask(self, *, task, system, text, image_png, schema) -> VisionAnswer:
        self.calls.append((task, text, hashlib.sha256(image_png).hexdigest()))
        return VisionAnswer(self.answer(task, text), self.name, False, {"input": 1000, "output": 100})


PROVIDERS: dict[str, type] = {"anthropic": AnthropicVision}


def load_model(spec: str | None = None) -> VisionModel:
    """'제공자:모델' → VisionModel. 비우면 FIG_VISION_MODEL, 그것도 없으면 anthropic:claude-sonnet-5-5."""
    load_dotenv()
    spec = spec or os.getenv("FIG_VISION_MODEL") or DEFAULT_SPEC
    provider, _, model = spec.partition(":")
    if provider not in PROVIDERS or not model:
        raise ValueError(f"모르는 그림 모델: {spec} (가능한 제공자: {', '.join(PROVIDERS)} — 예: {DEFAULT_SPEC})")
    return PROVIDERS[provider](model)

"""생성형 AI(LLM) 호출 — 규칙으로 판단할 수 없는 항목(수행 ②③, 평가 ④, 기타 ③)의 '사람 확인(△) 후보'를 만드는 데만 쓴다.

원칙
- LLM 결과는 자동 X를 내지 않는다. 후보와 근거 문장을 △로 보고하고 사람이 확정한다.
- 원고 전문이 아니라 규칙이 골라낸 최소한의 문단만 보낸다. 보내기 전에 LLM_ALLOW_UPLOAD=1(반출 승인)이 있어야 한다.
- 같은 입력은 다시 묻지 않는다(캐시: 모델·프롬프트 해시 → 응답). 재검수 비용이 0에 가깝다.
- 결정적 출력: temperature 0, JSON 객체 응답.

환경 변수(.env)
  LLM_API_KEY        (없으면 OPENAI_API_KEY) — 키가 없으면 LLM 규칙은 △ "LLM 미설정"
  LLM_MODEL          기본 gpt-5.4-mini
  LLM_BASE_URL       기본 https://api.openai.com/v1  (OpenAI 호환 서버면 교체 가능)
  LLM_ALLOW_UPLOAD   "1"이어야 원고 텍스트를 전송한다(기관의 외부 전송 승인). 아니면 △ "반출 미승인"
  LLM_CACHE_DIR      기본 <저장소>/.llm_cache (git 제외). 응답 json + usage.jsonl(토큰 사용량)
  LLM_TIMEOUT        초, 기본 60
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1"

# LLM을 부를 수 있는 작업의 허용 목록. 여기 없는 task는 키·승인이 있어도 호출하지 않는다(LlmError).
# 새 항목에 LLM을 붙일 때는 코드 리뷰로 이 목록에 추가한다 — 어떤 코드가 원고를 외부로 보내는지 한 곳에서 보이게.
# 운영 중 임시로 좁히려면 .env에 LLM_ALLOWED_TASKS=perform2_brands 처럼 쉼표 목록으로 덮어쓸 수 있다(넓히는 건 불가).
ALLOWED_TASKS = frozenset({
    "perform2_brands",   # 수행 내용 ② 재료·기기의 상표·상품·제조사명 노출
})


class LlmError(RuntimeError):
    pass


@dataclass(frozen=True)
class LlmSettings:
    api_key: str | None
    model: str
    base_url: str
    allow_upload: bool
    cache_dir: Path
    timeout: float

    @property
    def ready(self) -> bool:
        return bool(self.api_key) and self.allow_upload

    @property
    def why_not(self) -> str:
        if not self.api_key:
            return "LLM 미설정 — .env에 LLM_API_KEY(또는 OPENAI_API_KEY)가 없음"
        if not self.allow_upload:
            return "원고 외부 전송 미승인 — 승인 후 .env에 LLM_ALLOW_UPLOAD=1"
        return ""


def settings() -> LlmSettings:
    root = Path(__file__).resolve().parents[2]
    return LlmSettings(
        api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or None,
        model=os.getenv("LLM_MODEL", DEFAULT_MODEL),
        base_url=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        allow_upload=os.getenv("LLM_ALLOW_UPLOAD", "") == "1",
        cache_dir=Path(os.getenv("LLM_CACHE_DIR") or root / ".llm_cache"),
        timeout=float(os.getenv("LLM_TIMEOUT", "60")),
    )


@dataclass(frozen=True)
class LlmAnswer:
    data: dict            # 모델이 돌려준 JSON 객체
    model: str
    cached: bool
    input_tokens: int
    output_tokens: int


def task_allowed(task: str) -> bool:
    """코드의 허용 목록 ∩ (있으면) 환경 변수 LLM_ALLOWED_TASKS."""
    if task not in ALLOWED_TASKS:
        return False
    narrowed = os.getenv("LLM_ALLOWED_TASKS")
    return True if not narrowed else task in {t.strip() for t in narrowed.split(",") if t.strip()}


def _cache_key(model: str, system: str, user: str) -> str:
    return hashlib.sha256(f"{model}\n\x00{system}\n\x00{user}".encode("utf-8")).hexdigest()


def ask_json(task: str, system: str, user: str, *, cfg: LlmSettings | None = None, max_output_tokens: int = 1500) -> LlmAnswer:
    """system/user 프롬프트로 JSON 객체 하나를 받는다. 키·승인이 없으면 LlmError(이유는 settings().why_not).

    task는 캐시·사용량 기록의 분류 이름(예: 'perform2_brands'). 같은 (model, system, user)는 캐시에서 돌려준다.
    """
    cfg = cfg or settings()
    if not task_allowed(task):
        raise LlmError(f"LLM 호출이 허용되지 않은 작업: {task} (ncs_core.llm.ALLOWED_TASKS)")
    if not cfg.ready:
        raise LlmError(cfg.why_not)
    key = _cache_key(cfg.model, system, user)
    cache_file = cfg.cache_dir / task / f"{key}.json"
    if cache_file.is_file():
        saved = json.loads(cache_file.read_text(encoding="utf-8"))
        return LlmAnswer(saved["data"], saved["model"], True, saved.get("input_tokens", 0), saved.get("output_tokens", 0))
    body = {
        "model": cfg.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_completion_tokens": max_output_tokens,
    }
    payload = _post(cfg, "/chat/completions", body)
    try:
        content = payload["choices"][0]["message"]["content"]
        data = json.loads(content)
        usage = payload.get("usage") or {}
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise LlmError(f"응답을 JSON으로 읽지 못함: {error}") from None
    answer = LlmAnswer(data, payload.get("model", cfg.model), False, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({"data": data, "model": answer.model, "input_tokens": answer.input_tokens,
                                      "output_tokens": answer.output_tokens, "task": task, "at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
    with (cfg.cache_dir / "usage.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "task": task, "model": answer.model,
                              "input_tokens": answer.input_tokens, "output_tokens": answer.output_tokens}, ensure_ascii=False) + "\n")
    return answer


def _post(cfg: LlmSettings, path: str, body: dict, retries: int = 2) -> dict:
    request = urllib.request.Request(
        cfg.base_url + path, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json", "User-Agent": "ncs-f02-review/0.1"},
    )
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=cfg.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            text = error.read().decode("utf-8", "replace")[:300]
            last = LlmError(f"HTTP {error.code}: {text}")
            if error.code in (401, 403, 400):
                break  # 키·요청 문제는 재시도 의미 없음
        except (urllib.error.URLError, TimeoutError) as error:
            last = LlmError(f"연결 실패: {error}")
        time.sleep(1.5 * (attempt + 1))
    raise last or LlmError("알 수 없는 오류")


def usage_summary(cfg: LlmSettings | None = None) -> dict:
    """usage.jsonl 합계 — {'calls', 'input_tokens', 'output_tokens'}."""
    cfg = cfg or settings()
    log = cfg.cache_dir / "usage.jsonl"
    total = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
    if log.is_file():
        for line in log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                total["calls"] += 1
                total["input_tokens"] += row.get("input_tokens", 0)
                total["output_tokens"] += row.get("output_tokens", 0)
    return total

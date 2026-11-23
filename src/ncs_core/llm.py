"""생성형 AI(LLM) 호출 — 규칙으로 판단할 수 없는 항목(수행 ②③, 평가 ④)의 '사람 확인(△) 후보'를 만드는 데만 쓴다.

원칙
- LLM 결과는 자동 X를 내지 않는다. 후보와 근거 문장을 △로 보고하고 사람이 확정한다.
- 원고 전문이 아니라 규칙이 골라낸 최소한의 문단만 보낸다. 보내기 전에 LLM_ALLOW_UPLOAD=1(반출 승인)이 있어야 한다.
- 같은 입력은 다시 묻지 않는다(캐시: 모델·프롬프트 해시 → 응답). 재검수 비용이 0에 가깝다.
- 결정적 출력: temperature 0, JSON 객체 응답.

제공자 두 가지를 부른다. 어느 쪽인지는 LLM_PROVIDER로 정하고, 없으면 키·모델 이름으로 알아낸다('sk-ant-…' 키나 'claude…' 모델 → anthropic).
  openai     OpenAI 호환 API  POST {base}/chat/completions  (Authorization: Bearer, temperature 0, response_format json_object)
  anthropic  Claude API       POST {base}/messages          (x-api-key, anthropic-version) — 표본 추출 값(temperature)은 보내지 않는다
             (최신 Claude 모델은 받지 않는다). JSON만 내라는 지시는 프롬프트가 하고, 응답 글에서 JSON 객체를 꺼내 읽는다.
             모델이 요청을 거절하면(stop_reason refusal) LlmError — 규칙은 그 항목을 △로 둔다.
키와 제공자가 어긋나면(Claude 키인데 OpenAI 주소 등) 키를 보내지 않고 "LLM 미설정"으로 멈춘다 — 다른 회사 서버로 키가 나가지 않게.

환경 변수(.env)
  LLM_API_KEY        (없으면 OPENAI_API_KEY, 그다음 ANTHROPIC_API_KEY) — 키가 없으면 LLM 규칙은 △ "LLM 미설정"
  LLM_PROVIDER       openai | anthropic. 없으면 키·모델 이름으로 정한다
  LLM_MODEL          기본 gpt-5.4-mini(openai) / claude-opus-5-5(anthropic). 'sonnet-5.5'처럼 줄여 적은 Claude 이름은 'claude-sonnet-5-5'로 읽는다
  LLM_BASE_URL       기본 https://api.openai.com/v1 / https://api.anthropic.com/v1  (호환 서버면 교체 가능)
  LLM_EFFORT         Claude의 추론 노력(low|medium|high|xhigh|max, 기본 low — 줄 단위 후보 판단용). 빈 값이면 보내지 않는다
  LLM_ALLOW_UPLOAD   "1"이어야 원고 텍스트를 전송한다(기관의 외부 전송 승인). 아니면 △ "반출 미승인"
  LLM_CACHE_TTL_DAYS 캐시 보관 일수(기본 30). 캐시 파일에는 원고 문장이 평문으로 남으므로 지난 것은 호출 때마다 지운다. 0이면 캐시 안 씀
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

OPENAI, ANTHROPIC = "openai", "anthropic"
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
ANTHROPIC_DEFAULT_MODEL = "claude-opus-5-5"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2026-10-21"
ANTHROPIC_KEY_PREFIX = "sk-ant-"
ANTHROPIC_JSON_TRIES = 2        # 응답 글에서 JSON 객체를 못 읽으면 다시 묻는 횟수(처음 포함)
ANTHROPIC_MAX_TOKENS = 16000   # 추론(thinking) 토큰도 이 한도에 들어가므로 응답 한도(max_output_tokens)보다 넉넉히 준다
# 안전 분류기가 거절했을 때 서버가 다른 모델로 같은 요청을 이어 주는 기능(서버 측 fallback)을 받는 모델
ANTHROPIC_FALLBACK_BETA = "server-side-fallback-2026-07-01"
ANTHROPIC_FALLBACK_MODELS = ("claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")

# LLM을 부를 수 있는 작업의 허용 목록. 여기 없는 task는 키·승인이 있어도 호출하지 않는다(LlmError).
# 새 항목에 LLM을 붙일 때는 코드 리뷰로 이 목록에 추가한다 — 어떤 코드가 원고를 외부로 보내는지 한 곳에서 보이게.
# 운영 중 임시로 좁히려면 .env에 LLM_ALLOWED_TASKS=perform2_brands 처럼 쉼표 목록으로 덮어쓸 수 있다(넓히는 건 불가).
ALLOWED_TASKS = frozenset({
    "perform2_brands",   # 수행 내용 ② 재료·기기의 상표·상품·제조사명 노출
    "perform3_safety",   # 수행 내용 ③ 안전·유의 사항이 추상적인가 — 블록의 안전·유의 사항 줄만 보낸다
    "evaluation4_items", # 평가 ④ 평가 항목이 학습 목표와 연관된 구체적 내용인가 — 학습의 학습 목표와 평가 항목만 보낸다
    "opinion_reflection", # 검토의견 반영 검토(REQ-02-003) 의견이 원고에 반영됐는가 — 의견 줄과 의견이 가리키는 범위에서 고른 문단만 보낸다
    "sentence_suggest",  # 문장 추천(REQ-02-004) 규칙에 걸린 문장의 정정 후보 — 걸린 문장 줄만 보낸다
    "sentence_wording",  # 문장 추천(REQ-02-004) 규정 꼴은 맞지만 낱말이 어색한 문장 후보 — 같은 종류의 문장 줄만 보낸다
})


# 검수 실행 때는 LLM을 부르지 않는다. 이 항목들은 화면의 'LLM 검토'(Claude, ncs_llmreview)가 보고 확인서 행에 합친다.
PENDING = "LLM 검토 전 — 결과 아래 'LLM 검토' 버튼으로 확인"


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
    cache_ttl_days: float = 30.0
    provider: str = OPENAI
    effort: str = ""

    @property
    def mismatch(self) -> str:
        """키와 보낼 곳이 어긋났으면 그 이유(없으면 빈 글) — 어긋난 채로는 키를 보내지 않는다."""
        claude_key = bool(self.api_key) and self.api_key.startswith(ANTHROPIC_KEY_PREFIX)
        if claude_key and self.provider != ANTHROPIC:
            return "Claude(Anthropic) 키인데 제공자가 openai로 지정됨 — LLM_PROVIDER를 지우거나 anthropic으로"
        if claude_key and "openai.com" in self.base_url:
            return "Claude(Anthropic) 키인데 LLM_BASE_URL이 OpenAI 주소 — LLM_BASE_URL을 지울 것"
        if self.api_key and not claude_key and self.provider == ANTHROPIC and "anthropic.com" in self.base_url:
            return "제공자가 anthropic인데 키가 Claude 키('sk-ant-…')가 아님"
        return ""

    @property
    def ready(self) -> bool:
        return bool(self.api_key) and self.allow_upload and not self.mismatch

    @property
    def why_not(self) -> str:
        if not self.api_key:
            return "LLM 미설정 — .env에 LLM_API_KEY(또는 OPENAI_API_KEY)가 없음"   # 이 문구는 골든 결과에 들어 있다 — 바꾸면 골든을 다시 만든다
        if self.mismatch:
            return f"LLM 미설정 — {self.mismatch}"
        if not self.allow_upload:
            return "원고 외부 전송 미승인 — 승인 후 .env에 LLM_ALLOW_UPLOAD=1"
        return ""


def claude_model_id(name: str) -> str:
    """줄여 적은 Claude 모델 이름을 API 모델 ID로: 'sonnet-5.5' → 'claude-sonnet-5-5'. 이미 'claude-…'면 점만 줄표로."""
    name = name.strip().lower().replace(".", "-").replace(" ", "-")
    return name if name.startswith("claude-") else f"claude-{name}"


def settings() -> LlmSettings:
    root = Path(__file__).resolve().parents[2]
    key = (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or "").strip() or None   # CRLF .env의 줄 끝 문자 제거
    model = os.getenv("LLM_MODEL", "").strip()
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider not in (OPENAI, ANTHROPIC):
        claude = (key or "").startswith(ANTHROPIC_KEY_PREFIX) or model.lower().startswith("claude")
        provider = ANTHROPIC if claude else OPENAI
    if provider == ANTHROPIC:
        model = claude_model_id(model) if model else ANTHROPIC_DEFAULT_MODEL
        base_url = os.getenv("LLM_BASE_URL") or ANTHROPIC_BASE_URL
    else:
        model = model or DEFAULT_MODEL
        base_url = os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL
    return LlmSettings(
        api_key=key,
        model=model,
        base_url=base_url.rstrip("/"),
        allow_upload=os.getenv("LLM_ALLOW_UPLOAD", "") == "1",
        cache_dir=Path(os.getenv("LLM_CACHE_DIR") or root / ".llm_cache"),
        timeout=float(os.getenv("LLM_TIMEOUT", "60")),
        cache_ttl_days=float(os.getenv("LLM_CACHE_TTL_DAYS", "30")),
        provider=provider,
        effort=os.getenv("LLM_EFFORT", "low").strip().lower(),
    )


def prune_cache(cfg: LlmSettings | None = None, *, now: float | None = None) -> int:
    """보관 일수를 넘긴 캐시 파일(원고 문장 포함)을 지운다. 지운 개수를 돌려준다. usage.jsonl(토큰 수만)은 남긴다."""
    cfg = cfg or settings()
    if not cfg.cache_dir.is_dir():
        return 0
    cutoff = (now if now is not None else time.time()) - cfg.cache_ttl_days * 86400
    removed = 0
    for file in cfg.cache_dir.glob("*/*.json"):
        try:
            if file.stat().st_mtime < cutoff:
                file.unlink()
                removed += 1
        except OSError:
            continue
    return removed


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
    prune_cache(cfg)
    key = _cache_key(cfg.model, system, user)
    cache_file = cfg.cache_dir / task / f"{key}.json"
    if cfg.cache_ttl_days > 0 and cache_file.is_file():
        saved = json.loads(cache_file.read_text(encoding="utf-8"))
        return LlmAnswer(saved["data"], saved["model"], True, saved.get("input_tokens", 0), saved.get("output_tokens", 0))
    if cfg.provider == ANTHROPIC:
        data, model, tokens_in, tokens_out = _ask_anthropic(cfg, system, user, max_output_tokens)
    else:
        data, model, tokens_in, tokens_out = _ask_openai(cfg, system, user, max_output_tokens)
    answer = LlmAnswer(data, model, False, tokens_in, tokens_out)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    if cfg.cache_ttl_days > 0:
        cache_file.write_text(json.dumps({"data": data, "model": answer.model, "input_tokens": answer.input_tokens,
                                          "output_tokens": answer.output_tokens, "task": task, "at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                                         ensure_ascii=False, indent=1), encoding="utf-8")
    with (cfg.cache_dir / "usage.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "task": task, "model": answer.model,
                              "input_tokens": answer.input_tokens, "output_tokens": answer.output_tokens}, ensure_ascii=False) + "\n")
    return answer


def _ask_openai(cfg: LlmSettings, system: str, user: str, max_output_tokens: int) -> tuple[dict, str, int, int]:
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
    return data, payload.get("model", cfg.model), int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))


def _ask_anthropic(cfg: LlmSettings, system: str, user: str, max_output_tokens: int) -> tuple[dict, str, int, int]:
    """Claude API(Messages). temperature 등 표본 추출 값은 보내지 않는다. 응답의 text 블록에서 JSON 객체를 꺼낸다."""
    body: dict = {
        "model": cfg.model,
        "max_tokens": max(max_output_tokens, ANTHROPIC_MAX_TOKENS),
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if cfg.effort:
        body["output_config"] = {"effort": cfg.effort}
    if cfg.model in ANTHROPIC_FALLBACK_MODELS:
        body["fallbacks"] = "default"
    for attempt in range(ANTHROPIC_JSON_TRIES):
        payload = _post(cfg, "/messages", body)
        if not isinstance(payload, dict):
            raise LlmError("응답을 JSON으로 읽지 못함: 객체가 아님")
        reason = payload.get("stop_reason")
        if reason == "refusal":
            category = (payload.get("stop_details") or {}).get("category") or "분류 없음"
            raise LlmError(f"모델이 요청을 거절함({category})")
        if reason == "max_tokens":
            raise LlmError("응답이 길이 한도에서 잘림(max_tokens)")
        blocks = payload.get("content") or []
        text = "".join(block.get("text") or "" for block in blocks if isinstance(block, dict) and block.get("type") == "text")
        try:
            data = _json_object(text)
            break
        except LlmError:      # 가끔 JSON이 아닌 글이 온다(temperature를 못 정하므로) — 한 번 더 묻고, 또 그러면 오류로 올린다
            if attempt + 1 == ANTHROPIC_JSON_TRIES:
                raise
    usage = payload.get("usage") or {}
    tokens_in = sum(int(usage.get(name) or 0) for name in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return data, str(payload.get("model") or cfg.model), tokens_in, int(usage.get("output_tokens") or 0)


def _json_object(text: str) -> dict:
    """모델 글에서 JSON 객체 하나를 읽는다 — 글 전체가 JSON이면 그대로, 코드 울타리나 앞뒤 말이 붙었으면 첫 '{'부터 마지막 '}'까지."""
    text = (text or "").strip()
    for candidate in (text, text[text.find("{"): text.rfind("}") + 1] if "{" in text and "}" in text else ""):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise LlmError("응답을 JSON으로 읽지 못함: JSON 객체가 없음")


def _headers(cfg: LlmSettings) -> dict[str, str]:
    common = {"Content-Type": "application/json", "User-Agent": "ncs-f02-review/0.1"}
    if cfg.provider == ANTHROPIC:
        headers = {"x-api-key": cfg.api_key or "", "anthropic-version": ANTHROPIC_VERSION, **common}
        if cfg.model in ANTHROPIC_FALLBACK_MODELS:
            headers["anthropic-beta"] = ANTHROPIC_FALLBACK_BETA
        return headers
    return {"Authorization": f"Bearer {cfg.api_key}", **common}


def _post(cfg: LlmSettings, path: str, body: dict, retries: int = 2) -> dict:
    request = urllib.request.Request(cfg.base_url + path, data=json.dumps(body).encode("utf-8"), method="POST", headers=_headers(cfg))
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=cfg.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            text = error.read().decode("utf-8", "replace")[:300]
            last = LlmError(f"HTTP {error.code}: {text}")
            if error.code in (401, 403, 400, 404):
                break  # 키·요청·모델 이름 문제는 재시도 의미 없음
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


def line_findings(task: str, system: str, user: str, lines: list[str], *, asker=None) -> tuple[list[dict], str]:
    """번호 붙인 줄 목록을 물어 '지적할 줄'만 받는 후보 규칙의 공통 부분 → (지적 목록, 모델 이름).

    lines는 프롬프트에서 1부터 번호를 붙인 줄(지적을 받을 수 있는 줄)이고, user는 그 번호가 들어간 실제 질문 글이다.
    모델 출력 {"findings": [{"line": 번호, …}]} 중 실제 줄 번호를 가리키는 것만 남긴다(환각 방지). 줄마다 첫 지적만 쓴다.
    돌려주는 지적: {'line', '원문', 'kind', 'reason', 'suggestion'}.
    asker: 테스트에서 LLM 대신 넣는 함수((lines) → {'data': {...}, 'model': …}). 키·승인이 없거나 호출이 실패하면 LlmError.
    """
    answer = asker(lines) if asker is not None else ask_json(task, system, user).__dict__
    out, seen = [], set()
    for finding in (answer.get("data") or {}).get("findings") or []:
        try:
            no = int(finding.get("line"))
        except (AttributeError, TypeError, ValueError):
            continue
        if not 1 <= no <= len(lines) or no in seen:
            continue
        seen.add(no)
        out.append({"line": no, "원문": lines[no - 1], "kind": str(finding.get("kind") or ""),
                    "reason": str(finding.get("reason") or ""), "suggestion": str(finding.get("suggestion") or "")})
    return sorted(out, key=lambda f: f["line"]), str(answer.get("model") or settings().model)

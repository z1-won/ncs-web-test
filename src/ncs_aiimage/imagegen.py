"""사진·삽화를 만드는 이미지 생성 엔진(REQ-02-006 ① AI 생성) — 서버에 직접 올리는 공개 모델. 외부 서비스로 보내는 것이 없다.

기본은 꺼짐이다. 켜려면 NCS_IMAGEGEN_ENGINE=diffusers 와 선택 설치(requirements/imagegen.txt: torch, diffusers 등)가 필요하다.
  NCS_IMAGEGEN_MODEL     모델(허깅페이스 ID 또는 폴더). 기본 stabilityai/stable-diffusion-xl-base-1.0(CreativeML Open RAIL++-M, 16비트 파일 약 7GB).
                         다른 모델을 쓰면 그 모델의 라이선스를 확인한다. black-forest-labs/FLUX.1-schnell(Apache 2.0)은 약 34GB의 메모리가 필요해
                         메모리 16GB인 개발용 컴퓨터에서는 올라가지 않았다(2026-11-25)
  NCS_IMAGEGEN_DEVICE    mps | cuda | cpu. 없으면 쓸 수 있는 것을 고른다
  NCS_IMAGEGEN_STEPS     추론 단계 수, NCS_IMAGEGEN_GUIDANCE 안내 세기. 없으면 모델 계열의 기본값(FAMILIES): Stable Diffusion XL 30단계·6.0,
                         몇 단계로 줄인 모델(schnell, turbo, klein, lightning) 4단계·0.0
  NCS_IMAGEGEN_VARIANT   받을 파일의 종류(fp16 등). 없으면 계열의 기본값(Stable Diffusion XL은 fp16 — 32비트 파일까지 받지 않게). none이면 지정하지 않는다
모델 계열에 따라 제한 문구를 보내는 방법이 다르다(ncs_aiimage.prompt.for_model): Stable Diffusion 계열은 부정 프롬프트로, 그 밖은 글 끝의 제한 문구로.
  NCS_IMAGEGEN_TOOL      AI 활용 줄에 적을 도구 이름(기본은 모델 이름에서 어림)
모델은 처음 만들 때 한 번 올리고(수 GB ~ 수십 GB의 메모리), 한 번에 한 장씩 만든다(잠금). 모델을 못 올리면 꺼진 것으로 보고 까닭을 status에 남긴다.
runner(프롬프트, 가로, 세로, 시드) → PNG 바이트: 테스트가 엔진 대신 넣는 함수. 같은 프롬프트와 시드는 같은 그림이 되도록 시드를 돌려준다.
진행 상황: generate(job=…)에 화면이 정한 작업 번호를 주면 progress(job)가 몇 번째 장의 몇 단계인지, 걸린 시간과 남은 시간(어림)을 돌려주고,
cancel(job)이 다음 단계에서 멈추게 한다(Cancelled). 한 장에 몇 분이 걸리므로 화면이 2초마다 묻는다. 작업 기록은 이 프로세스의 메모리에만 있다.
"""

from __future__ import annotations

import io
import os
import random
import threading
import time
from dataclasses import dataclass

ENGINE_ENV = "NCS_IMAGEGEN_ENGINE"
DEFAULT_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
# 모델 계열별 기본값 — 이름으로 알아본다. negative: 부정 프롬프트를 받는가(글 인코더가 CLIP뿐이라 긴 글과 부정문을 읽지 못하는 계열)
FAMILIES = {
    "sdxl": {"steps": 30, "guidance": 6.0, "variant": "fp16", "negative": True, "tool": "Stable Diffusion XL"},
    "distilled": {"steps": 4, "guidance": 0.0, "variant": "", "negative": False, "tool": ""},
}
SHAPES = {"landscape": (1024, 768), "portrait": (768, 1024), "square": (1024, 1024)}
SHAPE_NAMES = {"landscape": "가로", "portrait": "세로", "square": "정사각"}
MAX_COUNT = 4

_lock = threading.Lock()
_loaded: tuple[str, object] | None = None       # (모델, 파이프라인 또는 못 올린 까닭)
_jobs: dict[str, dict] = {}                     # 작업 번호 → 진행 상황(progress). 메모리에만 둔다
_jobs_lock = threading.Lock()
MAX_JOBS = 50
JOB_STATES = {"waiting": "앞의 요청이 끝나기를 기다리는 중", "loading": "이미지 모델을 올리는 중", "running": "그림을 만드는 중",
              "done": "완료", "cancelled": "취소됨", "error": "실패"}


class EngineOff(RuntimeError):
    """엔진이 꺼져 있거나 모델을 올리지 못함 — 화면에 그대로 보일 까닭."""


class Cancelled(RuntimeError):
    """사용자가 그림 만들기를 취소했다(cancel). 만들던 그림은 버린다."""


def _job_update(job: str | None, **values) -> None:
    if not job:
        return
    with _jobs_lock:
        entry = _jobs.get(job)
        if entry is None:
            while len(_jobs) >= MAX_JOBS:           # 오래된 기록부터 지운다(넣은 순서)
                _jobs.pop(next(iter(_jobs)))
            entry = _jobs[job] = {"state": "waiting", "image": 0, "count": 0, "step": 0, "steps": 0, "started": time.monotonic(),
                                  "running_since": None, "finished": None, "cancel": False, "error": ""}
        entry.update(values)


def _cancel_requested(job: str | None) -> bool:
    with _jobs_lock:
        return bool(job and _jobs.get(job, {}).get("cancel"))


def progress(job: str) -> dict | None:
    """작업의 진행 상황 — {"state", "상태", "image"(지금 만드는 장, 1부터), "count", "step", "steps", "percent", "elapsed", "remaining"}. 모르는 작업이면 None.

    percent: 끝난 단계 ÷ 전체 단계(장수 × 단계 수). remaining: 지금까지의 단계당 시간으로 어림한 남은 초(단계를 하나도 못 끝냈으면 None).
    """
    with _jobs_lock:
        entry = dict(_jobs[job]) if job in _jobs else None
    if entry is None:
        return None
    now = entry["finished"] or time.monotonic()
    total = entry["count"] * entry["steps"]
    done = max(0, entry["image"] - 1) * entry["steps"] + entry["step"] if total else 0
    if entry["state"] == "done":
        done = total
    remaining = None
    if entry["state"] == "running" and entry["running_since"] is not None and 0 < done < total:
        remaining = round((now - entry["running_since"]) / done * (total - done))
    return {"state": entry["state"], "상태": JOB_STATES[entry["state"]], "image": entry["image"], "count": entry["count"], "step": entry["step"],
            "steps": entry["steps"], "percent": round(done / total * 100) if total else 0, "elapsed": round(now - entry["started"]),
            "remaining": remaining, "error": entry["error"]}


def cancel(job: str) -> bool:
    """작업을 멈추게 한다 — 만드는 중이면 다음 단계에서, 기다리는 중이면 차례가 왔을 때. 모르는 작업이거나 이미 끝났으면 False."""
    with _jobs_lock:
        entry = _jobs.get(job)
        if entry is None or entry["state"] in ("done", "cancelled", "error"):
            return False
        entry["cancel"] = True
        return True


@dataclass(frozen=True)
class Generated:
    png: bytes
    seed: int
    width: int
    height: int


def model_name() -> str:
    return os.getenv("NCS_IMAGEGEN_MODEL", "").strip() or DEFAULT_MODEL


def family(name: str | None = None) -> str:
    """모델 이름 → 계열('sdxl' | 'distilled'). 몇 단계로 줄인 모델(turbo 등)은 Stable Diffusion XL에서 나왔어도 'distilled'의 단계 수를 쓴다."""
    last = (name or model_name()).lower()
    if any(word in last for word in ("schnell", "turbo", "klein", "lightning")):
        return "distilled"
    return "sdxl" if "stable-diffusion-xl" in last or "sdxl" in last else "distilled"


def settings(name: str | None = None) -> dict:
    """이 모델로 만들 때 쓰는 값 — {"family", "steps", "guidance", "variant", "negative"}. 환경 변수가 계열의 기본값을 덮는다."""
    kind = family(name)
    base = FAMILIES[kind]
    variant = os.getenv("NCS_IMAGEGEN_VARIANT", "").strip().lower() or base["variant"]
    return {"family": kind, "steps": int(os.getenv("NCS_IMAGEGEN_STEPS", "") or base["steps"]),
            "guidance": float(os.getenv("NCS_IMAGEGEN_GUIDANCE", "") or base["guidance"]),
            "variant": "" if variant == "none" else variant, "negative": base["negative"]}


def tool_name() -> str:
    """AI 활용 줄에 적을 도구 이름의 기본값. 마침표는 숫자 사이에만 쓸 수 있어(ncs_core.figures.clean_tool) 모델 이름에서 뺀다."""
    given = os.getenv("NCS_IMAGEGEN_TOOL", "").strip()
    if given:
        return given[:40]
    last = model_name().rstrip("/").split("/")[-1]
    if FAMILIES[family()]["tool"]:
        return FAMILIES[family()]["tool"]
    return "FLUX" if "flux" in last.lower() else " ".join(last.replace(".", " ").replace(",", " ").replace("-", " ").replace("_", " ").split())[:40]


def _why_off() -> str:
    engine = os.getenv(ENGINE_ENV, "").strip().lower()
    if not engine:
        return f"이미지 생성 엔진이 꺼져 있습니다({ENGINE_ENV} 미설정)"
    if engine != "diffusers":
        return f"알 수 없는 엔진입니다({ENGINE_ENV}={engine}). 쓸 수 있는 값: diffusers"
    try:
        import diffusers  # noqa: F401
        import torch  # noqa: F401
    except ImportError as error:
        return f"이미지 생성에 필요한 프로그램이 설치되어 있지 않습니다({error.name}). requirements/imagegen.txt를 설치해야 합니다"
    if _loaded is not None and _loaded[0] == model_name() and isinstance(_loaded[1], str):
        return f"모델을 올리지 못했습니다: {_loaded[1]}"
    return ""


def status() -> dict:
    why = _why_off()
    return {"사용 가능": not why, "이유": why, "모델": model_name() if not why else "", "도구": tool_name(), "설정": settings(),
            "모양": [{"shape": shape, "이름": SHAPE_NAMES[shape], "width": size[0], "height": size[1]} for shape, size in SHAPES.items()],
            "최대 장수": MAX_COUNT}


def _device(torch) -> str:
    given = os.getenv("NCS_IMAGEGEN_DEVICE", "").strip().lower()
    if given:
        return given
    if torch.cuda.is_available():
        return "cuda"
    return "mps" if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available() else "cpu"


def _explain(name: str, error: Exception) -> str:
    """모델을 못 올린 까닭을 할 일과 함께 적는다. 접근 동의가 필요한 모델(FLUX.1 schnell 등)은 로그인 없이 받으면 '없는 모델'이라고 나온다."""
    text = f"{type(error).__name__}: {error}"
    if "not a valid model identifier" in text or "gated" in text.lower() or "401" in text or "403" in text:
        return (f"모델 {name}을(를) 내려받지 못했습니다. 허깅페이스에서 접근 동의가 필요한 모델일 수 있습니다 — "
                f"① https://huggingface.co/{name} 에 로그인해 접근 조건에 동의하고 ② 터미널에서 `hf auth login`으로 토큰을 넣은 뒤 다시 실행합니다"
                "(또는 환경 변수 HF_TOKEN). 모델 이름이 틀렸을 때도 같은 오류가 납니다")
    if "out of memory" in text.lower() or isinstance(error, MemoryError):
        return f"메모리가 모자라 모델 {name}을(를) 올리지 못했습니다. 더 작은 모델을 NCS_IMAGEGEN_MODEL로 지정해 보세요(그 모델의 라이선스 확인)"
    return text[:300]


def _pipeline():
    """모델을 한 번만 올린다. 못 올리면 까닭을 적어 두고 EngineOff."""
    global _loaded
    name = model_name()
    if _loaded is None or _loaded[0] != name:
        try:
            import torch
            from diffusers import AutoPipelineForText2Image

            device = _device(torch)
            variant = settings(name)["variant"]
            pipe = AutoPipelineForText2Image.from_pretrained(name, dtype=torch.float32 if device == "cpu" else torch.float16,      # diffusers 0.43: torch_dtype는 곧 없어진다
                                                             **({"variant": variant, "use_safetensors": True} if variant else {}))
            pipe = pipe.to(device)
            if device == "mps":
                pipe.enable_attention_slicing()      # 통합 메모리가 넉넉하지 않은 맥에서 메모리 최고치를 낮춘다(diffusers의 mps 안내)
            _loaded = (name, (pipe, torch))
        except Exception as error:      # noqa: BLE001 — 설치 안 됨, 모델 없음(내려받기·접근 동의 필요), 메모리 부족 모두 '꺼짐'으로 다룬다
            _loaded = (name, _explain(name, error))
    if isinstance(_loaded[1], str):
        raise EngineOff(f"모델을 올리지 못했습니다: {_loaded[1]}")
    return _loaded[1]


def _run(prompt: str, width: int, height: int, seed: int, job: str | None = None) -> bytes:
    from .prompt import for_model

    _job_update(job, state="loading")
    pipe, torch = _pipeline()
    use = settings()
    sent = for_model(prompt, negative=use["negative"])
    extra = {"negative_prompt": sent["negative"]} if sent["negative"] else {}
    if job:
        with _jobs_lock:
            since = _jobs[job]["running_since"] or time.monotonic()
        _job_update(job, state="running", step=0, running_since=since)

        def on_step(pipeline, step, _timestep, kwargs):      # diffusers가 단계가 끝날 때마다 부른다(step은 0부터)
            _job_update(job, step=step + 1)
            if _cancel_requested(job):
                pipeline._interrupt = True                   # 남은 단계를 건너뛴다 — 나온 그림은 아래에서 버린다
            return kwargs

        extra["callback_on_step_end"] = on_step
    image = pipe(prompt=sent["prompt"], width=width, height=height, num_inference_steps=use["steps"], guidance_scale=use["guidance"],
                 generator=torch.Generator("cpu").manual_seed(seed), **extra).images[0]
    if _cancel_requested(job):
        raise Cancelled("그림 만들기를 취소했습니다")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    if getattr(pipe, "device", None) is not None and str(pipe.device).startswith("mps"):
        torch.mps.empty_cache()      # 여러 장을 이어 만들 때 장마다 느려졌다(16GB 맥, 단계마다 3.75초 → 5.40초) — 장 사이에 mps가 잡아 둔 메모리를 돌려준다
    return buffer.getvalue()


def sent_to_model(prompt: str) -> dict:
    """compose가 만든 글이 지금 모델에 실제로 어떻게 가는가 → {"prompt", "negative", "note"}(ncs_aiimage.prompt.for_model). 화면과 점검 스크립트가 보여 준다."""
    from .prompt import for_model

    return for_model(prompt, negative=settings()["negative"])


def generate(prompt: str, *, count: int = 2, seed: int | None = None, shape: str = "landscape", runner=None, job: str | None = None) -> list[Generated]:
    """프롬프트(모델에 보낼 글 전부) → 그림 count장. seed를 주면 seed, seed+1, …로 만든다(같은 입력은 같은 그림).

    job: 화면이 정한 작업 번호. 주면 progress(job)로 진행 상황을 볼 수 있고 cancel(job)로 멈출 수 있다(멈추면 Cancelled).
    runner를 준 경우(테스트)에는 단계는 모르고 몇 번째 장인지만 남긴다."""
    if shape not in SHAPES:
        raise ValueError(f"shape는 {', '.join(SHAPES)} 가운데 하나여야 합니다")
    if not 1 <= count <= MAX_COUNT:
        raise ValueError(f"한 번에 1~{MAX_COUNT}장을 만들 수 있습니다")
    if not (prompt or "").strip():
        raise ValueError("프롬프트가 있어야 합니다")
    if runner is None:
        why = _why_off()
        if why:
            raise EngineOff(why)
        runner = _run
    width, height = SHAPES[shape]
    first = random.SystemRandom().randrange(2**31) if seed is None else int(seed)
    engine = runner is _run
    _job_update(job, state="waiting", count=count, steps=settings()["steps"] if engine else 0)
    out = []
    try:
        with _lock:
            for offset in range(count):
                if _cancel_requested(job):
                    raise Cancelled("그림 만들기를 취소했습니다")
                _job_update(job, image=offset + 1, step=0, **({} if engine else {"state": "running"}))
                png = _run(prompt, width, height, first + offset, job) if engine else runner(prompt, width, height, first + offset)
                out.append(Generated(png, first + offset, width, height))
    except Cancelled:
        _job_update(job, state="cancelled", finished=time.monotonic())
        raise
    except Exception as error:
        _job_update(job, state="error", finished=time.monotonic(), error=str(error)[:300])
        raise
    _job_update(job, state="done", finished=time.monotonic())
    return out

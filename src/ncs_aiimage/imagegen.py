"""사진·삽화를 만드는 이미지 생성 엔진(REQ-02-006 ① AI 생성) — 서버에 직접 올리는 공개 모델. 외부 서비스로 보내는 것이 없다.

기본은 꺼짐이다. 켜려면 NCS_IMAGEGEN_ENGINE=diffusers 와 선택 설치(requirements/imagegen.txt: torch, diffusers 등)가 필요하다.
  NCS_IMAGEGEN_MODEL     모델(허깅페이스 ID 또는 폴더). 기본 black-forest-labs/FLUX.1-schnell(Apache 2.0). 다른 모델을 쓰면 그 모델의 라이선스를 확인한다
  NCS_IMAGEGEN_DEVICE    mps | cuda | cpu. 없으면 쓸 수 있는 것을 고른다
  NCS_IMAGEGEN_STEPS     추론 단계 수(기본 4 — schnell처럼 줄인 모델 기준). NCS_IMAGEGEN_GUIDANCE 안내 세기(기본 0.0)
  NCS_IMAGEGEN_TOOL      AI 활용 줄에 적을 도구 이름(기본은 모델 이름에서 어림)
모델은 처음 만들 때 한 번 올리고(수 GB ~ 수십 GB의 메모리), 한 번에 한 장씩 만든다(잠금). 모델을 못 올리면 꺼진 것으로 보고 까닭을 status에 남긴다.
runner(프롬프트, 가로, 세로, 시드) → PNG 바이트: 테스트가 엔진 대신 넣는 함수. 같은 프롬프트와 시드는 같은 그림이 되도록 시드를 돌려준다.
"""

from __future__ import annotations

import io
import os
import random
import threading
from dataclasses import dataclass

ENGINE_ENV = "NCS_IMAGEGEN_ENGINE"
DEFAULT_MODEL = "black-forest-labs/FLUX.1-schnell"
SHAPES = {"landscape": (1024, 768), "portrait": (768, 1024), "square": (1024, 1024)}
SHAPE_NAMES = {"landscape": "가로", "portrait": "세로", "square": "정사각"}
MAX_COUNT = 4

_lock = threading.Lock()
_loaded: tuple[str, object] | None = None       # (모델, 파이프라인 또는 못 올린 까닭)


class EngineOff(RuntimeError):
    """엔진이 꺼져 있거나 모델을 올리지 못함 — 화면에 그대로 보일 까닭."""


@dataclass(frozen=True)
class Generated:
    png: bytes
    seed: int
    width: int
    height: int


def model_name() -> str:
    return os.getenv("NCS_IMAGEGEN_MODEL", "").strip() or DEFAULT_MODEL


def tool_name() -> str:
    """AI 활용 줄에 적을 도구 이름의 기본값. 마침표는 숫자 사이에만 쓸 수 있어(ncs_core.figures.clean_tool) 모델 이름에서 뺀다."""
    given = os.getenv("NCS_IMAGEGEN_TOOL", "").strip()
    if given:
        return given[:40]
    last = model_name().rstrip("/").split("/")[-1]
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
    return {"사용 가능": not why, "이유": why, "모델": model_name() if not why else "", "도구": tool_name(),
            "모양": [{"shape": shape, "이름": SHAPE_NAMES[shape], "width": size[0], "height": size[1]} for shape, size in SHAPES.items()],
            "최대 장수": MAX_COUNT}


def _device(torch) -> str:
    given = os.getenv("NCS_IMAGEGEN_DEVICE", "").strip().lower()
    if given:
        return given
    if torch.cuda.is_available():
        return "cuda"
    return "mps" if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available() else "cpu"


def _pipeline():
    """모델을 한 번만 올린다. 못 올리면 까닭을 적어 두고 EngineOff."""
    global _loaded
    name = model_name()
    if _loaded is None or _loaded[0] != name:
        try:
            import torch
            from diffusers import AutoPipelineForText2Image

            device = _device(torch)
            pipe = AutoPipelineForText2Image.from_pretrained(name, torch_dtype=torch.float32 if device == "cpu" else torch.float16)
            _loaded = (name, (pipe.to(device), torch))
        except Exception as error:      # noqa: BLE001 — 설치 안 됨, 모델 없음(내려받기·접근 동의 필요), 메모리 부족 모두 '꺼짐'으로 다룬다
            _loaded = (name, f"{type(error).__name__}: {error}"[:300])
    if isinstance(_loaded[1], str):
        raise EngineOff(f"모델을 올리지 못했습니다: {_loaded[1]}")
    return _loaded[1]


def _run(prompt: str, width: int, height: int, seed: int) -> bytes:
    pipe, torch = _pipeline()
    image = pipe(prompt=prompt, width=width, height=height, num_inference_steps=int(os.getenv("NCS_IMAGEGEN_STEPS", "4") or 4),
                 guidance_scale=float(os.getenv("NCS_IMAGEGEN_GUIDANCE", "0") or 0), generator=torch.Generator("cpu").manual_seed(seed)).images[0]
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def generate(prompt: str, *, count: int = 2, seed: int | None = None, shape: str = "landscape", runner=None) -> list[Generated]:
    """프롬프트(모델에 보낼 글 전부) → 그림 count장. seed를 주면 seed, seed+1, …로 만든다(같은 입력은 같은 그림)."""
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
    out = []
    with _lock:
        for offset in range(count):
            out.append(Generated(runner(prompt, width, height, first + offset), first + offset, width, height))
    return out

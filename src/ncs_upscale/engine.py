"""업스케일 엔진 — ncnn-vulkan 실행 파일(waifu2x · Real-ESRGAN)을 폴더 단위로 한 번에 부른다.

세 엔진 모두 '-i 입력 -o 출력 -s 배율' 모양이 같고, 엔진마다 다른 옵션(모델 지정, 잡음 제거)은 Engine.args 한 곳에만 둔다.
특히 -n은 Real-ESRGAN에서는 모델 이름, waifu2x에서는 잡음 제거 단계라 뜻이 다르다.

실행 파일 위치: 환경 변수 NCS_UPSCALE_TOOLS(도구 폴더) 또는 기본값 <저장소 위 폴더>/tools.
  tools/waifu2x-ncnn-vulkan/**/waifu2x-ncnn-vulkan.exe
  tools/realesrgan-ncnn-vulkan/**/realesrgan-ncnn-vulkan.exe

Intel 내장 GPU(Iris Plus)에서 도표 4장(평균 약 27만 px)으로 잰 한 장당 시간:
  waifu2x-photo x2 약 20초 / esrgan-fast 약 3초 / esrgan-best 약 115초.
Real-CUGAN은 같은 GPU에서 검은 그림·번진 글자가 나와 넣지 않았다.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

TOOLS_ENV = "NCS_UPSCALE_TOOLS"
DEFAULT_TOOLS = Path(__file__).resolve().parents[3] / "tools"


@dataclass(frozen=True)
class Engine:
    name: str
    folder: str                 # 도구 폴더 아래 엔진 폴더
    exe: str                    # 실행 파일 이름
    args: tuple[str, ...]       # 엔진별 옵션. '{dir}'은 실행 파일이 있는 폴더로 바뀐다
    scales: tuple[int, ...]     # 지원 배율(작은 것부터)
    note: str = ""

    def pick_scale(self, need: float, max_scale: int) -> int:
        """need배 이상인 배율 중 가장 작은 것. max_scale 안에 없으면 max_scale 이하의 가장 큰 배율."""
        usable = [s for s in self.scales if s <= max_scale] or [min(self.scales)]
        return next((s for s in usable if s >= need), max(usable))

    def find_exe(self, tools: Path | None = None) -> Path:
        root = Path(tools or os.environ.get(TOOLS_ENV) or DEFAULT_TOOLS) / self.folder
        found = sorted(root.rglob(self.exe)) if root.is_dir() else []
        if not found:
            raise FileNotFoundError(f"{self.exe}를 찾지 못함: {root} (도구 폴더는 --tools 또는 {TOOLS_ENV}로 지정)")
        return found[0]

    def command(self, exe: Path, src: Path, out: Path, scale: int) -> list[str]:
        extra = [a.replace("{dir}", str(exe.parent)) for a in self.args]
        return [str(exe), "-i", str(src), "-o", str(out), "-s", str(scale), "-f", "png", *extra]

    def run(self, src: Path, out: Path, scale: int, tools: Path | None = None, timeout: float | None = None) -> None:
        """src 폴더의 PNG를 모두 scale배로 키워 out 폴더에 같은 이름으로 저장한다.
        timeout(초)을 넘기면 엔진 프로세스를 끝내고 TimeoutError — GPU 드라이버가 멈추면 엔진이 끝나지 않는 경우가 있다."""
        exe = self.find_exe(tools)
        try:
            result = subprocess.run(self.command(exe, src, out, scale), capture_output=True, text=True, errors="replace",
                                    timeout=timeout)
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"{self.name}가 {timeout:.0f}초 안에 끝나지 않아 중단함") from None
        if result.returncode != 0:
            tail = "\n".join((result.stderr or "").strip().splitlines()[-5:])
            raise RuntimeError(f"{self.name} 실행 실패(종료 코드 {result.returncode}): {tail}")


ENGINES = {
    "waifu2x-photo": Engine(
        "waifu2x-photo", "waifu2x-ncnn-vulkan", "waifu2x-ncnn-vulkan.exe",
        ("-n", "0", "-m", "{dir}/models-upconv_7_photo"), (2, 4),
        "waifu2x upconv_7_photo, 잡음 제거 0 — 지어내는 디테일이 가장 적음(원본 색 번짐은 그대로 커짐). x4는 x2를 두 번 해서 약 4배 느림"),
    "esrgan-fast": Engine(
        "esrgan-fast", "realesrgan-ncnn-vulkan", "realesrgan-ncnn-vulkan.exe",
        ("-n", "realesr-animevideov3", "-m", "{dir}/models"), (2, 3, 4),
        "Real-ESRGAN realesr-animevideov3 — 가장 빠름, 글자 가장자리 색 번짐을 지움"),
    "esrgan-best": Engine(
        "esrgan-best", "realesrgan-ncnn-vulkan", "realesrgan-ncnn-vulkan.exe",
        ("-n", "realesrgan-x4plus", "-m", "{dir}/models"), (4,),
        "Real-ESRGAN x4plus — 깔끔하지만 느림"),
}
DEFAULT_ENGINE = "waifu2x-photo"

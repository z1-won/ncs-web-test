"""사진·삽화 생성 엔진(REQ-02-006 ①, ncs_aiimage/imagegen.py)이 이 컴퓨터에서 도는지 본다 — 모델을 올리고 그림을 만들어 걸린 시간을 찍는다.

  pip install -r requirements/imagegen.txt
  NCS_IMAGEGEN_ENGINE=diffusers PYTHONPATH=src python scripts/probe/imagegen_probe.py --out _workspace_probe/imagegen [--count 2] [--kind photo] [--shape landscape]
  선택: --scene "영어 장면 글"  --seed 1  환경 변수 NCS_IMAGEGEN_MODEL(기본 stabilityai/stable-diffusion-xl-base-1.0), NCS_IMAGEGEN_DEVICE,
        NCS_IMAGEGEN_STEPS, NCS_IMAGEGEN_GUIDANCE, NCS_IMAGEGEN_VARIANT
외부로 보내는 것은 없다(모델을 처음 내려받을 때만 허깅페이스에 접속한다 — 모델에 따라 접근 동의와 토큰(HF_TOKEN)이 필요하다).
기본 모델은 처음에 16비트 파일 약 7GB를 받는다. FLUX.1 schnell(120억 매개변수)은 메모리가 약 34GB 필요해 16GB 컴퓨터에서는 올라가지 않는다.
프롬프트 검사(얼굴, 상표, 화풍)와 고정 제한 문구는 화면과 같은 코드(ncs_aiimage.prompt)를 거친다.
"""

import argparse
import time
from pathlib import Path

from ncs_aiimage import imagegen, prompt

SCENES = {
    "photo": "A welder seen from behind wearing a welding helmet and leather gloves, working at a steel workbench in a tidy workshop",
    "illustration": "A red fire extinguisher standing next to a workshop door, with a pair of safety gloves on a shelf",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--kind", choices=prompt.KINDS, default="photo")
    parser.add_argument("--shape", choices=list(imagegen.SHAPES), default="landscape")
    parser.add_argument("--scene", default="")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    state = imagegen.status()
    print("상태:", {key: state[key] for key in ("사용 가능", "이유", "모델", "도구", "설정")})
    if not state["사용 가능"]:
        raise SystemExit(1)
    scene = args.scene or SCENES[args.kind]
    checked = prompt.check(scene)
    if not checked["ok"]:
        raise SystemExit("프롬프트 검사에서 떨어졌습니다: " + " / ".join(problem["reason"] for problem in checked["problems"]))
    sent = prompt.compose(scene, args.kind)
    actual = imagegen.sent_to_model(sent)
    print("모델에 보내는 글:", actual["prompt"])
    if actual["negative"]:
        print("넣지 말 것(부정 프롬프트):", actual["negative"])
    if actual["note"]:
        print("알림:", actual["note"])
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        made = imagegen.generate(sent, count=args.count, seed=args.seed, shape=args.shape)
    except imagegen.EngineOff as error:
        raise SystemExit(str(error)) from None
    took = time.monotonic() - started
    for one in made:
        path = args.out / f"{args.kind}_{one.seed}.png"
        path.write_bytes(one.png)
        print(f"  {path} ({one.width}×{one.height}px, {len(one.png) // 1024}KB)")
    print(f"{len(made)}장에 {took:.0f}초(모델을 내려받고 올리는 시간 포함). 같은 서버에서 두 번째부터는 올리는 시간이 빠집니다.")
    print(f"150mm 폭에 놓으면 {round(made[0].width / (150 / 25.4))} DPI — 300 DPI가 되는 폭은 {int(made[0].width / 300 * 25.4)}mm입니다(더 크게 놓으려면 업스케일링).")


if __name__ == "__main__":
    main()

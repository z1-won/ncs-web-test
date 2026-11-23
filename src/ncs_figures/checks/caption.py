"""③ 캡션 일치 — 그림을 보는 모델(Resources.asker = VisionModel)로 그림이 캡션 내용을 보여 주는지 본다.

설계 8.3 ③-1: 원래는 그림-캡션 유사도 점수로 먼저 거르고 애매한 것만 모델에 보내지만, 점수 기준(임계값)을 실험으로 정하기 전에는
모든 본문 그림을 모델에 보낸다. 모델 결과는 후보 — match면 O, mismatch·uncertain·검증 실패는 △(자동 X 없음).
"""

from __future__ import annotations

from ncs_core.text import O, TRI

from ..models import CheckOutcome
from ..reading import judge_caption

NAME = "③캡션 일치"


def check_caption(item, res, cfg, prior) -> list[CheckOutcome]:
    recorded = getattr(res.asker, "recorded", None)       # 웹: 그림 판독 버튼으로 이미 받은 판정(새로 부르지 않음)
    result = recorded(item) if recorded else judge_caption(item, res.asker, module_name=prior.get("module_name", ""))
    prior.setdefault("model_calls", []).append(result)
    if result["status"] != "완료":
        return [CheckOutcome(NAME, None, skipped=result.get("reason", "모델 판독 못 함"))]
    model = result["model"]
    prior["caption_verdict"] = result["판정"] if result["검증"] == "통과" else "검증 실패"   # 위험도는 mismatch만 올린다
    if result["검증"] != "통과":
        return [CheckOutcome(NAME, TRI, f"모델 답을 쓰지 않음 — {result['검증']} (위험도에는 넣지 않음)", model=model)]
    if result["판정"] == "match":
        return [CheckOutcome(NAME, O, f"캡션과 맞음: {result['근거']}", model=model)]
    if result["판정"] == "mismatch":
        return [CheckOutcome(NAME, TRI, f"캡션과 다를 수 있음 — {result['근거']}", suggestion="그림과 캡션이 같은 내용을 가리키는지 확인", model=model)]
    return [CheckOutcome(NAME, TRI, f"판단 근거 부족 — {result['근거']} (위험도에는 넣지 않음)", model=model)]

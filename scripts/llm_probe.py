"""LLM 연결 점검 — 키·모델·JSON 응답·캐시가 동작하는지 합성 문장으로 확인한다(실제 원고는 보내지 않는다).

  set -a; source .env; set +a
  python scripts/llm_probe.py            # 합성 재료·기기 목록으로 수행 ② 프롬프트 1회 호출
  python scripts/llm_probe.py --usage    # 지금까지의 토큰 사용량 합계

출력에 키는 나오지 않는다. 비용 추정은 gpt-5.4-mini 표준 요금(입력 $0.75/M, 출력 $4.5/M) 기준.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ncs_core import llm  # noqa: E402
from ncs_perform.rules.brands import SYSTEM, TASK  # noqa: E402

SAMPLE = """1. [재료] 커피 원두, 생수, 일회용 컵
2. [재료] 코카콜라 1.5L, 설탕 시럽
3. [기기] 노트북, 레이저 프린터
4. [기기] 삼성 갤럭시 탭 S9, 바코드 스캐너
5. [기기] POS 시스템(오피스 365 설치)"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--usage", action="store_true")
    args = parser.parse_args()
    cfg = llm.settings()
    print(f"모델 {cfg.model} · 서버 {cfg.base_url} · 키 {'있음' if cfg.api_key else '없음'} · 반출 승인 {'1' if cfg.allow_upload else '없음'} · 캐시 {cfg.cache_dir}")
    if args.usage:
        total = llm.usage_summary(cfg)
        cost = total["input_tokens"] / 1e6 * 0.75 + total["output_tokens"] / 1e6 * 4.5
        print(f"호출 {total['calls']}회 · 입력 {total['input_tokens']:,} · 출력 {total['output_tokens']:,} 토큰 · 약 ${cost:.4f}")
        return
    if not cfg.ready:
        sys.exit(cfg.why_not)
    try:
        answer = llm.ask_json(TASK + "_probe", SYSTEM, SAMPLE)
    except llm.LlmError as error:
        sys.exit(f"실패: {error}")
    print(f"응답 모델 {answer.model} · 캐시 {'적중' if answer.cached else '아님'} · 토큰 입력 {answer.input_tokens} / 출력 {answer.output_tokens}")
    for f in answer.data.get("findings", []):
        print(f"  줄 {f.get('line')}: 「{f.get('text')}」 {f.get('kind')} ({f.get('confidence')}) → {f.get('generic')} — {f.get('reason')}")
    print("기대: 코카콜라·삼성 갤럭시 탭 S9·오피스 365는 잡고, 커피 원두·노트북·POS 시스템은 잡지 않아야 함")


if __name__ == "__main__":
    main()

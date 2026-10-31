"""골든 결과 재생성: python3 tests/make_golden.py

판정 정책을 **의도적으로** 바꿨을 때만 실행한다. 생기는 diff가 "무엇이 바뀌었는지"의 기록이므로
docs/CONSISTENCY_REVIEW.md의 '의도적으로 바꾼 동작' 표와 함께 커밋한다. 구조만 바꾸는 리팩토링에서는 실행하지 않는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from golden_cases import GOLDEN, cases, dumps, observe  # noqa: E402


def main() -> None:
    GOLDEN.mkdir(exist_ok=True)
    changed = 0
    for name, request in cases():
        path = GOLDEN / f"{name}.json"
        text = dumps(observe(request))
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
            changed += 1
    print(f"골든 {sum(1 for _ in cases())}건 중 {changed}건 갱신 → {GOLDEN}")


if __name__ == "__main__":
    main()

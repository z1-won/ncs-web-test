"""python -m ncs_plan 개발계획서.hwpx [--module-code LM...] [--out 결과]"""

from ncs_service.cli import run_cli


def main() -> None:
    run_cli("plan", "개발계획서 점검 ①~⑨ (REQ-02-001)")


if __name__ == "__main__":
    main()

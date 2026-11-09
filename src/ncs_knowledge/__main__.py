"""python -m ncs_knowledge 원고.hwpx [개발계획서.hwp] [--module-code LM...] [--out 결과]"""

from ncs_service.cli import run_cli


def main() -> None:
    run_cli("knowledge", "F02 필요 지식 ①~⑧ 검수")


if __name__ == "__main__":
    main()

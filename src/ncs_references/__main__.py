"""python -m ncs_references 원고.hwpx [--module-code LM...] [--out 결과]"""

from ncs_service.cli import run_cli


def main() -> None:
    run_cli("references", "F02 참고 자료 ①②③ 검수")


if __name__ == "__main__":
    main()

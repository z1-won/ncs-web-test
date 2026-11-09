"""python -m ncs_perform 원고.hwpx [--module-code LM...] [--out 결과]"""

from ncs_service.cli import run_cli


def main() -> None:
    run_cli("perform", "F02 수행 내용 ①·④ 검수")


if __name__ == "__main__":
    main()

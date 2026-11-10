"""python -m ncs_colophon 원고.hwpx [--module-code LM...] [--out 결과]"""

from ncs_service.cli import run_cli


def main() -> None:
    run_cli("colophon", "F02 개발 이력 및 판권 ① 검수")


if __name__ == "__main__":
    main()

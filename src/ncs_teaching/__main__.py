"""python -m ncs_teaching 원고.hwpx [--module-code LM...] [--out 결과]"""

from ncs_service.cli import run_cli


def main() -> None:
    run_cli("teaching", "F02 교수·학습 방법 ①~④ 검수")


if __name__ == "__main__":
    main()

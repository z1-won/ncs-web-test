"""python -m ncs_toc 원고.hwpx [개발계획서.hwpx] [--module-code LM...] [--out 결과]"""

from ncs_service.cli import run_cli


def main() -> None:
    run_cli("toc", "F02 차례 ①~⑥ 검수")


if __name__ == "__main__":
    main()

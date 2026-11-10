"""python -m ncs_position 원고.hwpx 개발계획서.hwpx [--module-code LM...] [--out 결과]"""

from ncs_service.cli import run_cli


def main() -> None:
    run_cli("position", "F02 NCS-학습모듈의 위치 ①~⑤ 검수")


if __name__ == "__main__":
    main()

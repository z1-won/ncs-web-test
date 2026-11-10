"""hwpx 원고에서 문구가 든 문단의 원본 XML을 보여 준다 — 파서가 읽은 글과 원고의 실제 구조를 대조할 때 쓴다.

  python .claude/skills/f02-case-triage/scripts/para_xml.py 원고.hwpx "찾을 문구" [--max 3] [--width 4000]

찾기는 변경 추적 반영본(ncs_core.hwpx.para_text) 기준이다. 원시 XML을 문자열로 검색하면 삭제된 옛 글이 먼저 걸리므로
반드시 반영본으로 찾는다. 출력의 '구역 파일'은 zip 안의 Contents/sectionN.xml이고, 엔진이 쓰는 ms.sections[0|1]
(normalize_sections를 거친 앞부분/본문)과는 번호가 다를 수 있다.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))

from ncs_core.hwpx import HP, para_text, section_names  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", help="원고 hwpx")
    parser.add_argument("needle", help="문단 글(반영본)에 들어 있는 문구")
    parser.add_argument("--max", type=int, default=3, help="보여 줄 문단 수")
    parser.add_argument("--width", type=int, default=4000, help="문단마다 보여 줄 XML 길이")
    args = parser.parse_args()
    shown = 0
    with zipfile.ZipFile(args.path) as archive:
        for name in section_names(archive):
            root = ET.fromstring(archive.read(name))
            for index, paragraph in enumerate(root.iter(HP + "p")):
                text = para_text(paragraph)
                if args.needle not in text:
                    continue
                xml = ET.tostring(paragraph, encoding="unicode")
                marks = [m for m in ("deleteBegin", "insertBegin", "fieldBegin", "tbl", "lineBreak", "tab") if f":{m}" in xml or f"}}{m}" in xml]
                print(f"== 구역 파일 {name}, 그 파일 안 문단 {index}")
                print(f"   반영본 글: {text!r}")
                print(f"   든 요소: {', '.join(marks) or '없음'}")
                print(xml[: args.width])
                print()
                shown += 1
                if shown >= args.max:
                    return
    if not shown:
        print("문구가 든 문단이 없음 — 반영본 기준으로 찾으므로 삭제된 글은 나오지 않는다. 공백·특수문자를 줄여 다시 찾는다.")


if __name__ == "__main__":
    main()

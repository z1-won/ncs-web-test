"""본문 구조 보조: 학습 내용(N-M) 구간·머리말, hwpx 표 셀 문단 집합."""

import re
import zipfile
from xml.etree import ElementTree as ET

from ncs_core.hwpx import HP, section_names

from .config import DEFAULT_CONFIG, CheckConfig

HEAD_MARK = {
    "필요 지식": re.compile(r"^필\s*요\s*지\s*식$"),
    "수행 내용": re.compile(r"^수\s*행\s*내\s*용$"),
    "수행 순서": re.compile(r"^수\s*행\s*순\s*서$"),
    "학습 목표": re.compile(r"^학\s*습\s*목\s*표$"),
    "재료": re.compile(r"^재\s*료(\s*\(.*\))?$"),
    "기기": re.compile(r"^기\s*기\s*\(장비\)$|^기기\s*\(장비\s*\)$|^기기$"),
    "안전": re.compile(r"^안\s*전(\s*\(.*\))?$"),
    "교수·학습 방법": re.compile(r"^교수\s*\W{0,3}\s*학습\s*방법$"),
    "평가": re.compile(r"^평\s*가$"),
}
MEMO_LINE = re.compile(r"^[★▶※]")           # 에디터 메모·주석 줄
GOAL_LINE = re.compile(r"^[•·▪ㆍ‧◦○\-]")   # 학습 목표 글머리


def mark(line: str) -> str | None:
    for name, pattern in HEAD_MARK.items():
        if pattern.match(line):
            return name
    return None


def unit_regions(body: dict, config: CheckConfig = DEFAULT_CONFIG) -> list[dict]:
    """학습 내용(N-M) 구간 목록.

    [{'no','sub','text','k0'(제목 lines 인덱스),'k1'(다음 제목/학습 끝),'lesson'(놓인 학습 번호),
      'goal':[학습 목표 문장], 'goal_k'('학습 목표' 줄 인덱스 또는 None)}]
    """
    lines, out = body["lines"], []
    subs = sorted(body["subs"], key=lambda s: s["k"])
    for j, sub in enumerate(subs):
        lesson = next((no for no, a, b in body["spans"] if a <= sub["k"] < b), None)
        k1 = subs[j + 1]["k"] if j + 1 < len(subs) else next((b for no, a, b in body["spans"] if a <= sub["k"] < b), len(lines))
        for k in range(sub["k"] + 1, k1):  # 교수·학습 방법 제목이 먼저 나오면 거기서 끊음(학습 끝)
            if mark(lines[k][1]) == "교수·학습 방법":
                k1 = k
                break
        goal, goal_k = [], None
        for k in range(sub["k"] + 1, min(sub["k"] + 1 + config.goal_lookahead, k1)):
            if mark(lines[k][1]) == "학습 목표":
                goal_k = k
                for kk in range(k + 1, k1):
                    text = lines[kk][1]
                    if mark(text) or MEMO_LINE.match(text):
                        break
                    if GOAL_LINE.match(text) or re.search(r"있다\.?$", text):
                        goal.append(text)
                    else:
                        break
                break
        out.append({"no": sub["no"], "sub": sub["sub"], "text": sub["text"], "k0": sub["k"], "k1": k1, "lesson": lesson, "goal": goal, "goal_k": goal_k})
    return out


def cell_paragraphs(path, section: int) -> set[int] | None:
    """hwpx: 해당 섹션에서 표 셀 안에 든 문단의 인덱스(ncs_core.hwpx와 같은 순회 순서). hwp면 None."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = section_names(archive)
            if section >= len(names):
                return set()
            root = ET.fromstring(archive.read(names[section]))
    except zipfile.BadZipFile:
        return None
    parents = {child: parent for parent in root.iter() for child in parent}
    out = set()
    for index, paragraph in enumerate(root.iter(HP + "p")):
        current = parents.get(paragraph)
        while current is not None:
            if current.tag == HP + "tbl":
                out.add(index)
                break
            current = parents.get(current)
    return out

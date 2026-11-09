"""검증용 합성 HWPX(원고·개발계획서)와 출력본 PDF를 만든다. 실제 양식의 최소 골격만 흉내 낸다."""

import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HH = "http://www.hancom.co.kr/hwpml/2011/head"
HC = "http://www.hancom.co.kr/hwpml/2011/core"

# charPr: 0 보통(함초롬), 1 KoPub돋움체 Bold, 2 KoPub돋움체 보통
HEADER = f"""<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="{HH}" xmlns:hc="{HC}">
 <hh:refList>
  <hh:fontfaces>
   <hh:fontface lang="HANGUL"><hh:font id="0" face="함초롬돋움"/><hh:font id="1" face="KoPub돋움체"/></hh:fontface>
  </hh:fontfaces>
  <hh:borderFills>
   <hh:borderFill id="1"><hc:fillBrush><hc:winBrush faceColor="none"/></hc:fillBrush></hh:borderFill>
   <hh:borderFill id="2"><hc:fillBrush><hc:winBrush faceColor="#D9D9D9"/></hc:fillBrush></hh:borderFill>
   <hh:borderFill id="3"><hc:fillBrush><hc:winBrush faceColor="#FFFFFF"/></hc:fillBrush></hh:borderFill>
  </hh:borderFills>
  <hh:charProperties>
   <hh:charPr id="0"><hh:fontRef hangul="0"/></hh:charPr>
   <hh:charPr id="1"><hh:fontRef hangul="1"/><hh:bold/></hh:charPr>
   <hh:charPr id="2"><hh:fontRef hangul="1"/></hh:charPr>
  </hh:charProperties>
 </hh:refList>
</hh:head>
"""


def p(text, char=0):
    return f'<hp:p><hp:run charPrIDRef="{char}"><hp:t>{escape(text)}</hp:t></hp:run></hp:p>'


def table(rows, styles=None):
    """rows: [[텍스트, ...]]. styles: {(r,c): (charPr, borderFill)}"""
    styles = styles or {}
    out = [f'<hp:tbl rowCnt="{len(rows)}" colCnt="{len(rows[0])}">']
    for r, row in enumerate(rows):
        out.append("<hp:tr>")
        for c, text in enumerate(row):
            char, fill = styles.get((r, c), (0, 1))
            out.append(
                f'<hp:tc borderFillIDRef="{fill}"><hp:subList>{p(text, char)}</hp:subList>'
                f'<hp:cellAddr rowAddr="{r}" colAddr="{c}"/></hp:tc>'
            )
        out.append("</hp:tr>")
    out.append("</hp:tbl>")
    return "<hp:p><hp:run><hp:t></hp:t>" + "".join(out) + "</hp:run></hp:p>"


def image(name):
    return f'<hp:p><hp:run><hp:pic><hp:shapeComment>원본 그림의 이름: {escape(name)}</hp:shapeComment></hp:pic></hp:run></hp:p>'


def section(parts):
    return f'<?xml version="1.0" encoding="UTF-8"?><hp:sec xmlns:hp="{HP}">{"".join(parts)}</hp:sec>'


def write_hwpx(path, sections):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/header.xml", HEADER)
        for i, parts in enumerate(sections):
            z.writestr(f"Contents/section{i}.xml", section(parts))


CLASS_ROWS = [["대분류", "중분류", "소분류"], ["20. 정보통신", "01. 정보기술", "02. 정보기술개발"]]
POS_ROWS = [
    ["세분류", "능력단위", "학습모듈명"],
    ["응용SW엔지니어링", "요구사항 확인", "요구사항 확인"],
    ["", "화면 구현", "화면 구현"],
    ["데이터베이스엔지니어링", "DB 설계", "DB 설계"],
]
POS_STYLES = {(2, 1): (1, 2), (2, 2): (1, 2), (0, 0): (0, 3), (1, 0): (0, 2)}


def manuscript(variant="ok"):
    pua = "" if variant == "pua" else "·"
    front = [
        p("차 례"),
        p("학습 1. 요구사항 확인하기 1"),
        p("1-1. 현행 시스템 분석 3"),
        p("1-2. 요구사항 정의 7"),
        p(f"• 교수{pua}학습 방법 10"),
        p("• 평가 12"),
        p("학습 2. 화면 구현하기 15" if variant != "name" else "학습 2. 화면 만들기 15"),
        p("2-1. UI 요구사항 확인 16"),
        p("• 교수·학습 방법 20"),
        p("• 평가 22"),
        p("참고 자료 40"),
        p("활용 서식 42"),
        p("학습모듈의 개요"),
        p("[NCS-학습모듈의 위치]"),
        p("대분류"),
        p("20. 정보통신"),
        p("중분류"),
        p("01. 정보기술"),
        p("소분류"),
        p("02. 정보기술개발" if variant != "class" else "02. 정보기술운영"),
        table(CLASS_ROWS),
        table(POS_ROWS if variant != "pos" else [POS_ROWS[0], POS_ROWS[1], POS_ROWS[3], POS_ROWS[2]], POS_STYLES),
        p("학습모듈의 내용 체계"),
        p("1. 요구사항 확인하기"),
        p("1-1. 현행 시스템 분석"),
        p("1-2. 요구사항 정의"),
        p("2. 화면 구현하기"),
        p("2-1. UI 요구사항 확인"),
        p("핵심 용어"),
    ]
    eval_tables = lambda subs: [
        table([["학습 내용", "학습 목표", "평가 항목"]] + [[s, "목표", "항목"] for s in subs]),
        table([["학습 내용", "평가 항목", "평가 방법"]] + [[s, "항목", "방법"] for s in subs]),
    ]
    body = [
        p("학습 1"), p("요구사항 확인하기"), p("학습 2"), p("화면 구현하기"),
        p("1-1. 현행 시스템 분석"), p("현행 시스템을 분석한다."), p("1-2. 요구사항 정의"), p("요구사항을 정의한다."),
        p("교수·학습 방법"), p("강의와 실습을 병행한다."), p("평 가"),
        *eval_tables(["현행 시스템 분석", "요구사항 정의"]),
        p("학습 1"), p("요구사항 확인하기"), p("학습 2"), p("화면 구현하기"),
        p("2-1. UI 요구사항 확인"), p("UI 요구사항을 확인한다."),
        p("교수·학습 방법"), p("실습 중심으로 진행한다."), p("평 가"),
        *eval_tables(["UI 요구사항 확인"] if variant != "eval" else ["UI 요구 확인"]),
        p("참고 자료"),
        p("• 홍길동(2020). 소프트웨어 공학. 출판사."),
        p("• 김철수(2019). 요구공학. 출판사."),
        p("• 이영희(2021). UI 설계. 출판사."),
        image("활용 서식 배너.png"),
        p("서식 1. 요구사항 목록"), p("서식 2. 화면 정의서"), p("서식 3. 검토 의견서"),
        p("개발 이력"),
    ]
    return [front, body]


def plan():
    return [
        [
            p("NCS 학습모듈 개발계획서"),
            p("능력단위 코드번호"),
            p("1203020201_24v3"),
            p("①-b 학습 모듈명"),
            p("요구사항 확인"),
            p("1203020201_24v3.1"),
            p("요구사항 확인하기"),
            p("1. 요구사항 확인하기"),
            p("1-1. 현행 시스템 분석"),
            p("1-2. 요구사항 정의"),
            p("1203020201_24v3.2"),
            p("화면 구현하기"),
            p("2. 화면 구현하기"),
            p("2-1. UI 요구사항 확인"),
            p("NCS (수정 금지)"),
            p("[NCS-학습모듈의 위치]"),
            p("대분류"), p("20. 정보통신"), p("중분류"), p("01. 정보기술"), p("소분류"), p("02. 정보기술개발"),
            table(CLASS_ROWS),
            table(POS_ROWS),
        ]
    ]


# --- 출력본 PDF -------------------------------------------------------------------
# 원고_ok의 차례 쪽수(학습 1 → 1쪽, 1-1 → 3쪽, … 활용 서식 → 42쪽)와 맞는 45쪽짜리 PDF.
# 물리 쪽 0·1·2(표지·차례·개요)에는 쪽 번호가 없고, 본문은 꼬리말 가운데에 쪽 번호, 머리말에 학습명이 매 쪽 반복된다.
# fpdf2와 한글 글꼴이 있을 때만 만든다(개발용). 글꼴은 FIXTURE_FONT 환경 변수 또는 아래 후보에서 찾는다.
FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "C:/Windows/Fonts/malgun.ttf",
)
PRINT_HEADINGS = {  # folio → 그 쪽 본문 첫 줄들 (차례와 같은 쪽수)
    1: ["학습 1", "요구사항 확인하기", "학습 2", "화면 구현하기"],
    3: ["1-1. 현행 시스템 분석", "학습 목표", "현행 시스템을 분석할 수 있다."],
    7: ["1-2. 요구사항 정의", "요구사항을 정의한다."],
    10: ["교수·학습 방법", "강의와 실습을 병행한다."],
    12: ["평 가", "평가 준거"],
    15: ["학습 1", "요구사항 확인하기", "학습 2", "화면 구현하기"],
    16: ["2-1. UI 요구사항 확인", "UI 요구사항을 확인한다."],
    20: ["교수·학습 방법", "실습 중심으로 진행한다."],
    22: ["평 가", "평가 준거"],
    40: ["참고 자료", "• 홍길동(2020). 소프트웨어 공학. 출판사."],
    42: ["활용 서식", "서식 1. 요구사항 목록"],
}
LAST_FOLIO = 42


def print_copy_pdf(path: Path) -> bool:
    import os
    try:
        from fpdf import FPDF
    except ImportError:
        print("fpdf2가 없어 출력본 PDF는 건너뜀 (pip install fpdf2)")
        return False
    font = os.environ.get("FIXTURE_FONT") or next((f for f in FONT_CANDIDATES if Path(f).is_file()), None)
    if not font:
        print("한글 글꼴을 찾지 못해 출력본 PDF는 건너뜀 (FIXTURE_FONT=글꼴 경로)")
        return False
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_font("K", "", font)
    pdf.set_font("K", size=11)
    front = [["NCS 학습모듈", "요구사항 확인", "LM1203020201_24v3"],
             ["차 례", "학습 1. 요구사항 확인하기 1", "1-1. 현행 시스템 분석 3", "1-2. 요구사항 정의 7", "• 교수·학습 방법 10", "• 평가 12",
              "학습 2. 화면 구현하기 15", "2-1. UI 요구사항 확인 16", "• 교수·학습 방법 20", "• 평가 22", "참고 자료 40", "활용 서식 42"],
             ["학습모듈의 개요", "학습모듈의 내용 체계", "1. 요구사항 확인하기", "1-1. 현행 시스템 분석", "1-2. 요구사항 정의", "2. 화면 구현하기", "2-1. UI 요구사항 확인"]]
    for lines in front:
        pdf.add_page()
        pdf.set_y(40)
        for line in lines:
            pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")
    lesson = 1
    for folio in range(1, LAST_FOLIO + 1):
        if folio >= 15:
            lesson = 2
        pdf.add_page()
        pdf.set_y(8)                       # 달리는 머리말(위 띠): 학습명이 매 쪽 반복 — 본문 검색에서 빠져야 한다
        pdf.cell(0, 6, f"학습 {lesson} {'요구사항 확인하기' if lesson == 1 else '화면 구현하기'}", align="R")
        pdf.set_y(40)
        for line in PRINT_HEADINGS.get(folio, [f"본문 {folio}쪽 내용이다."]):
            pdf.cell(0, 8, line, new_x="LMARGIN", new_y="NEXT")
        if folio == 4:                      # 아래 띠에 걸친 그림 캡션은 본문으로 되돌려야 한다
            pdf.set_y(276)
            pdf.cell(0, 6, "[그림 1-1] 현행 시스템 구성도")
        pdf.set_y(284)                      # 꼬리말(아래 띠): 쪽 번호
        pdf.cell(0, 6, str(folio), align="C")
    pdf.output(str(path))
    return True


def main(out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_hwpx(out / "개발계획서_LM1203020201_24v3.hwpx", plan())
    for variant in ("ok", "pua", "name", "class", "pos", "eval"):
        write_hwpx(out / f"원고_{variant}_LM1203020201_24v3.hwpx", manuscript(variant))
    print_copy_pdf(out / "출력본_ok_LM1203020201_24v3.pdf")
    print("fixtures:", sorted(f.name for f in out.iterdir()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "fixtures")

"""권리 증빙 점검(REQ-02-014) 시험용 합성 파일 — 원고(hwpx, 그림 파일 포함)와 작성된 제출 서류(hwpx).

표의 칸 배치는 실제 양식(원고 집필 계약서 붙임 2·3, 사진·삽화 제작 계약서 붙임 1, 서약서 붙임)과 같게 만든다:
수록 현황 목록은 3줄 머리(제작 방식 › 묶음 › 사진/삽화) 아래 순번·제목·✓ 칸 9개.
"""

import struct
import zipfile
import zlib
from pathlib import Path

from make_fixtures import HEADER, p, section, table

HC = "http://www.hancom.co.kr/hwpml/2011/core"
MODULE = "LM1203020201_24v3"
MANUSCRIPT_NAME = f"원고_{MODULE}.hwpx"

# (그림 번호, 그림명, 출처 줄, AI 줄) — 목록·서류와의 관계는 inclusion_rows()의 주석
FIGURES = [
    ("그림 1-1", "NCS학습모듈 개념도", "출처: 집필진 제작(2026)", "ChatGPT를 활용하여 생성함. 2026. 7. 20."),
    ("그림 1-2", "NCS학습모듈 활용 예시", "출처: 홍길동(2024). 직업교육 사례집. 한국출판. p.12.", ""),
    ("그림 1-3", "NCS학습모듈 개발 프로세스", "출처: 집필진 제작(2026)", ""),
    ("그림 2-1", "NCS학습모듈 활용 통계", "출처: 집필진 제작(2026)", ""),
    ("그림 2-2", "실습실 배치도", "출처: 집필진 제작(2026)", ""),
    ("그림 2-3", "연도별 훈련 참여 현황", "출처: 고용노동부(2025). 직업훈련 통계. 공공누리 홈페이지(https://www.kogl.or.kr)에서 2026. 7. 1. 검색. 공공누리 제1유형.", ""),
    ("그림 2-4", "능력단위 구성", "출처: 교육부(2018). 객실 예약 관리(LM1203020201_16v2). 한국직업능력개발원. p.6.", ""),
    ("그림 2-5", "목록에 없는 그림", "출처: 집필진 제작(2026)", ""),
]


def png(seed: int, width: int = 40, height: int = 30) -> bytes:
    """내용이 seed마다 다른 작은 PNG."""
    data = b"".join(b"\x00" + b"".join(bytes(((seed * 37) % 256, (x * 5) % 256, (y * 7) % 256)) for x in range(width)) for y in range(height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(data, 9)) + chunk(b"IEND", b""))


def _pic(bin_id: str, width: int = 14400, height: int = 10800) -> str:
    return (f'<hp:p><hp:run charPrIDRef="0"><hp:pic><hp:sz width="{width}" height="{height}"/>'
            f'<hc:img binaryItemIDRef="{bin_id}"/></hp:pic></hp:run></hp:p>')


def _write(path: Path, parts: list[str], images: dict[str, bytes] | None = None) -> Path:
    images = images or {}
    manifest = ('<?xml version="1.0" encoding="UTF-8"?><opf:package xmlns:opf="http://www.idpf.org/2007/opf/"><opf:manifest>'
                + "".join(f'<opf:item id="{name}" href="BinData/{name}.png" media-type="image/png" isEmbeded="1"/>' for name in images)
                + "</opf:manifest></opf:package>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/header.xml", HEADER)
        z.writestr("Contents/content.hpf", manifest)
        z.writestr("Contents/section0.xml", section(parts).replace("<hp:sec ", f'<hp:sec xmlns:hc="{HC}" ', 1))
        for name, data in images.items():
            z.writestr(f"BinData/{name}.png", data)
    return path


def manuscript(folder: Path, figures=FIGURES, name: str = MANUSCRIPT_NAME, loose=()) -> Path:
    """그림 → 출처 줄 → (AI 줄) → 캡션 순서로 놓은 원고. 본문에는 그림을 가리키는 문장도 넣는다(캡션으로 세면 안 됨).

    loose: 캡션 없이 원고 끝에 놓을 그림의 크기 [(가로, 세로)](HWP 단위, 7200 = 1인치). 그림마다 앞에 본문 문단 넷을 둔다."""
    parts, images = [p("학습 1. 학습모듈 이해하기"), p("학습모듈의 구조는 [그림 1-1]과 같이 나타낸다.")], {}
    for index, (label, title, source, ai) in enumerate(figures, 1):
        images[f"image{index}"] = png(index)
        parts += [_pic(f"image{index}"), p(source)] + ([p(ai)] if ai else []) + [p(f"[{label}] {title}"), p("이어지는 본문 문장이다.")]
    for index, (width, height) in enumerate(loose, 1):
        images[f"loose{index}"] = png(100 + index)
        parts += [p("캡션 없는 그림 앞의 본문 문장이다.")] * 3 + [p(f"설비 {index}의 모습은 [그림 1-1]과 같이 다음과 같다."), _pic(f"loose{index}", width, height)]
    return _write(folder / name, parts, images)


M = "✓"


def inclusion_rows() -> list[list[str]]:
    """수록 현황 목록의 자료 행 — [순번, 제목, 직접(사진), 직접(삽화), 의뢰(사진), 의뢰(삽화), 공공, 포괄, 기개발, AI(업스케일·도식), AI(기타)]."""
    def row(no, title, *marked):
        return [str(no), title] + [M if col in marked else "" for col in range(2, 11)]
    return [
        row(1, "[그림 1-1] NCS학습모듈 개념도", 2, 9),          # 직접제작(사진) + AI
        row(2, "[그림 1-2] NCS학습모듈 활용 예시", 7),           # 포괄적 이용허락
        row(3, "[그림 1-3] NCS학습모듈 개발 프로세스", 2),       # 직접제작(사진)
        row(4, "[그림 2-1] NCS학습모듈 활용 통계", 3),           # 직접제작(삽화)
        row(5, "[그림 2-2] 실습실 배치도", 5),                   # 외부 제작의뢰(삽화)
        row(6, "[그림 2-3] 연도별 훈련 참여 현황", 6),           # 공공누리
        row(7, "[그림 2-4] 능력단위 구성", 8),                   # 기개발 학습모듈
        row(8, "[그림 3-1] 원고에 없는 그림", 3),                # 원고에 없음
    ]


def inclusion_table(rows=None, module: str = "객실 예약 관리") -> str:
    head = [
        [f"NCS학습모듈명: {module}"] + [""] * 10,
        ["순번", "시각적 자료 제목 (NCS학습모듈 내 그림제목 및 번호)", "저작물 제작 방식(해당 방식에 ✓ 표시)"] + [""] * 8,
        ["", "", "집필자 직접제작", "", "외부 제작의뢰", "", "공공 누리, 공유 마당", "포괄적 이용 허락", "기개발 학습 모듈", "AI 활용", ""],
        ["", "", "사진", "삽화", "사진", "삽화", "", "", "", "업스케일링, 도식, 도표 생성", "기타"],
    ]
    return table(head + (inclusion_rows() if rows is None else rows))


def production_table(rows=None) -> str:
    rows = [["1", "[그림 2-2] 실습실 배치도", "", M]] if rows is None else rows
    return table([["순번", "저작물명", "자료 유형", ""], ["", "", "사진", "삽화"]] + rows + [["합 계", "", "", ""]])


def license_table(rows=None) -> str:
    rows = [["1", "[그림 1-2] NCS학습모듈 활용 예시", "홍길동(2024). 직업교육 사례집. 한국출판. p.12.", "객실 예약 관리"]] if rows is None else rows
    return table([["순번", "저작물 제목", "출처 (구체적으로 제시)", "저작물 활용 NCS학습모듈명"]] + rows)


def ai_table(rows=None) -> str:
    rows = [["1", "그림 1-1 NCS학습모듈 개념도", "p.12", "ChatGPT 6.0", ""], ["2", "그림 OOOO", "p.00", "ChatGPT 6.0", ""]] if rows is None else rows
    return table([["순번", "결과물 명", "학습모듈 해당 쪽수", "활용 AI", "비고"]] + rows)


def form(folder: Path, name: str, *tables: str) -> Path:
    return _write(folder / name, [p("제출 서류")] + list(tables))


def full_forms(folder: Path) -> list[Path]:
    """모든 증빙이 갖춰진 한 묶음 — 계약서 한 파일에 붙임 2·3이 함께, 제작 목록과 서약서는 따로."""
    return [form(folder, "원고집필계약서_붙임.hwpx", inclusion_table(), license_table()),
            form(folder, "사진삽화_제작목록.hwpx", production_table()),
            form(folder, "AI서약서.hwpx", ai_table())]

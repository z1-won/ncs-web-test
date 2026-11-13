"""B 엔진 읽기 수정(2026-11-05) — SW제품기획 최종본 10종에서 사람이 통과시켰는데 엔진이 잘못 읽어 X·△가 나던 경우를 작게 재현한다.
각 수정마다 '진짜 위반은 여전히 잡는지'도 함께 본다."""

import unittest
from pathlib import Path
from types import SimpleNamespace

from ncs_perform.blocks import split_perform_blocks


class PerformHeadTests(unittest.TestCase):
    def test_table_column_head_is_not_a_block(self):
        """본문 표 열 제목 '수행 내용'(게시자/구독자 표)은 블록이 아니다(0408)."""
        paragraphs = ["1-1. 요구사항 분석", "수행 내용", "게시자", "지식의 등록", "구독자", "열람",
                      "수행 내용", "요구사항 분석하기", "재료·자료", "• 명세서", "기기(장비·공구)", "• 컴퓨터",
                      "안전·유의 사항", "• 보안 준수", "수행 순서", "\U000f02b1 요구사항을 분석한다."]
        blocks = split_perform_blocks(paragraphs, table_paragraphs=frozenset({1, 2, 3, 4, 5}))
        self.assertEqual([b["title"] for b in blocks], ["요구사항 분석하기"])
        self.assertEqual(blocks[0]["소제목 누락"], [])

    def test_real_head_inside_frame_is_kept(self):
        """진짜 머리가 틀(표) 안에 있어도 뒤에 소제목이 오면 블록이다 — 제목이 틀리면 ①이 여전히 잡는다."""
        paragraphs = ["1-1. 분석", "수행 내용", "/", "요구사항 분석", "재료·자료", "• 명세서", "수행 순서", "\U000f02b1 분석."]
        blocks = split_perform_blocks(paragraphs, table_paragraphs=frozenset({1, 2, 3}))
        self.assertEqual([b["title"] for b in blocks], ["요구사항 분석"])



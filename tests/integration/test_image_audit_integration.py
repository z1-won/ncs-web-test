"""NCS_TEST_DATABASE_URL을 지정하면 이미지 저작권 DB 점검(ncs_service.image_audit, REQ-02-010 검증 기준)을 실제 PostgreSQL로 검사한다.

DB에 다른 자료가 섞여 있어도 되게, 점검 결과는 테스트가 그림을 넣기 전과 넣은 뒤의 차이로 본다.
"""

import hashlib
import os
import unittest
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from ncs_service import image_audit, image_store
from ncs_service.image_db import load_records
from ncs_service.postgres import migrate

DSN = os.getenv("NCS_TEST_DATABASE_URL")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (64).to_bytes(4, "big") + (48).to_bytes(4, "big") + b"\x08\x02\x00\x00\x00"
OWN = {"category": "author_made", "ownership": "government"}
KOGL = {"category": "public_license", "ownership": "kogl", "license": {"kogl_type": 1}, "source_org": "예시기관",
        "source_url": "https://www.kogl.or.kr/x", "retrieved_on": "2026-11-17", "credit_line": "공공누리 제1유형."}


@unittest.skipUnless(DSN, "NCS_TEST_DATABASE_URL 미설정")
class ImageAuditIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.used: list[str] = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        with psycopg.connect(DSN) as connection:
            connection.execute("DELETE FROM image_assets WHERE sha256 = ANY(%s)", (self.used,))

    def add(self, rights: dict | None = None, confirm: bool = False) -> str:
        content = PNG + uuid4().bytes
        self.used.append(hashlib.sha256(content).hexdigest())
        report = load_records(DSN, [{"content": content, **({"rights": rights} if rights else {})}], changed_by="적재")
        self.assertEqual(report.rejected, [])
        with psycopg.connect(DSN) as connection:
            image_id = str(connection.execute("SELECT id FROM image_assets WHERE sha256 = %s", (self.used[-1],)).fetchone()[0])
        if confirm:
            image_store.confirm(DSN, image_id, by="에디팅기관")
        return image_id

    def test_exposure_is_zero_and_counts_follow_what_was_loaded(self):
        before = image_audit.audit(DSN)
        cleared = self.add({**OWN, "reuse_scope": "all"}, confirm=True)
        unknown = self.add(OWN, confirm=True)                                   # 확정했지만 재사용 범위 미확인
        private = self.add({**OWN, "reuse_scope": "all", "release_class": "private"}, confirm=True)
        self.add({**KOGL, "reuse_scope": "all"})                                # 자동 태깅
        self.add()                                                              # 권리 정보 없음
        after = image_audit.audit(DSN)

        def grown(name: str) -> int:
            return after["건수"][name] - before["건수"][name]

        self.assertEqual([grown(name) for name in ("그림", "권리 정보 있음", "기관 확정", "자동 태깅", "확정이지만 재사용 범위 미확인", "비공개", "추천 대상")],
                         [5, 4, 3, 1, 1, 1, 1])
        self.assertEqual((after["추천 노출"]["노출"], after["판정"]["추천 노출 0건"]), (0, True))
        by_path = {path["경로"]: path["나온 그림"] for path in after["추천 노출"]["경로별"]}
        earlier = {path["경로"]: path["나온 그림"] for path in before["추천 노출"]["경로별"]}
        self.assertEqual([by_path[name] - earlier[name] for name in by_path], [2, 1, 1], "뷰에는 비공개도 있고, 조회하는 두 길이 그것을 거른다")

        with psycopg.connect(DSN, row_factory=dict_row) as connection:          # 새는 그림이 있으면 잡는다는 것
            leaked = image_audit._exposed(connection, [cleared, unknown, private])
        self.assertEqual({item["id"]: (item["reuse_scope"], item["release_class"]) for item in leaked},
                         {unknown: ("unknown", None), private: ("all", "private")})

    def test_required_items_are_counted_only_where_they_apply(self):
        def items(result: dict, scope: str) -> dict:
            return {item["항목"]: (item["해당"], item["충족"]) for item in result["필수 항목"][scope]["항목별"]}

        before = image_audit.audit(DSN)
        owned = self.add({**OWN, "reuse_scope": "all"}, confirm=True)           # 직접제작: 양도 동의서가 있어야 한다
        self.add({**KOGL, "reuse_scope": "all"}, confirm=True)                  # 공공누리: 낼 증빙 없음, 출처는 다 있음
        self.add({**OWN, "ai": {"mode": "generated", "tool": "ChatGPT"}})       # 자동 태깅, AI 일자·서약서 없음
        after = image_audit.audit(DSN)

        def grown(scope: str, name: str) -> tuple[int, int]:
            return tuple(new - old for new, old in zip(items(after, scope)[name], items(before, scope)[name]))

        self.assertEqual(grown("기관 확정", "분류 체계"), (2, 2))
        self.assertEqual(grown("기관 확정", "양도 동의서(직접제작·제작의뢰)"), (1, 0))
        self.assertEqual(grown("기관 확정", "원 출처 기관·URL·검색일(공공누리)"), (1, 1))
        self.assertEqual(grown("기관 확정", "이용조건(라이선스 유형이 있는 자료)"), (1, 1))
        self.assertEqual(grown("전체", "AI 활용 방식·도구·일자(AI 활용 그림)"), (1, 0))
        self.assertEqual(grown("전체", "AI 서약서(AI 활용 그림)"), (1, 0))
        self.assertEqual(grown("전체", "재사용 범위"), (3, 2))

        image_store.register_evidence(DSN, owned, "transfer_consent", by="에디팅기관", file_ref="양도동의서.pdf")
        self.assertEqual(tuple(new - old for new, old in zip(
            items(image_audit.audit(DSN), "기관 확정")["양도 동의서(직접제작·제작의뢰)"], items(before, "기관 확정")["양도 동의서(직접제작·제작의뢰)"])), (1, 1))
        report = image_audit.text_report(after)
        self.assertIn("[추천 노출] 나오면 안 되는 그림 0건", report)
        self.assertIn("[필수 항목 — 기관 확정]", report)


if __name__ == "__main__":
    unittest.main()

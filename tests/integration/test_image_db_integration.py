"""NCS_TEST_DATABASE_URL을 지정하면 이미지 저작권 DB(006_image_db, REQ-02-010)의 제약과 뷰를 실제 PostgreSQL에서 검사한다."""

import hashlib
import os
import unittest
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from ncs_service.images import image_terms
from ncs_service.postgres import migrate

DSN = os.getenv("NCS_TEST_DATABASE_URL")
TABLES = ("image_assets", "image_placements", "image_rights", "image_evidence", "image_ncs_links", "image_history")
CONDITIONS = ("attribution", "non_commercial", "no_derivatives", "share_alike")
CONFIRMED = dict(status="confirmed", confirmed_by="에디팅기관", confirmed_at="2026-11-17T09:00+09:00",
                 category="author_made", ownership="government")


def kogl(kogl_type: int, **override) -> dict:
    """공공누리 제N유형의 권리 열 — 조건은 image_terms.KOGL_CONDITIONS에서."""
    return {"license_scheme": "kogl", "kogl_type": kogl_type,
            **dict(zip(CONDITIONS, (*image_terms.KOGL_CONDITIONS[kogl_type], False))), **override}


def cc(code: str, **override) -> dict:
    return {"license_scheme": "cc", "cc_license": code, **dict(zip(CONDITIONS, image_terms.CC_LICENSE[code])), **override}


@unittest.skipUnless(DSN, "NCS_TEST_DATABASE_URL 미설정")
class ImageDbIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.connection = psycopg.connect(DSN)   # 테스트마다 트랜잭션 하나 — 끝나면 되돌려 DB에 아무것도 남기지 않는다

    def tearDown(self):
        self.connection.rollback()
        self.connection.close()

    def insert(self, table: str, **columns):
        self.connection.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
            tuple(columns.values()))

    def asset(self, seed: str = "", **columns) -> str:
        image_id = str(uuid4())
        self.insert("image_assets", id=image_id, sha256=hashlib.sha256((seed or image_id).encode()).hexdigest(), **columns)
        return image_id

    def placement(self, image_id: str, module_code: str, label: str, **columns) -> str:
        placement_id = str(uuid4())
        self.insert("image_placements", id=placement_id, image_id=image_id, module_code=module_code, label=label, **columns)
        return placement_id

    def rights(self, image_id: str, **columns):
        self.insert("image_rights", image_id=image_id, **columns)

    def refused(self, error, action, constraint: str | None = None):
        with self.assertRaises(error) as caught:
            with self.connection.transaction():      # savepoint — 실패해도 바깥 트랜잭션은 계속 쓴다
                action()
        if constraint:
            self.assertEqual(caught.exception.diag.constraint_name, constraint)

    def rejected(self, constraint: str, **columns):
        """columns로 권리 정보를 넣으면 constraint 위반으로 거부된다."""
        image_id = self.asset()
        self.refused(psycopg.errors.CheckViolation, lambda: self.rights(image_id, **columns), constraint)

    def count(self, table: str, image_id: str) -> int:
        return self.connection.execute(f"SELECT count(*) FROM {table} WHERE image_id = %s", (image_id,)).fetchone()[0]

    def recommendable(self) -> set[str]:
        return {str(row[0]) for row in self.connection.execute("SELECT id FROM v_image_recommendable").fetchall()}

    # ── 적용 ──
    def test_tables_view_and_version_row_exist(self):
        found = {row[0] for row in self.connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()").fetchall()}
        self.assertLessEqual({*TABLES, "v_image_recommendable"}, found)
        self.assertEqual(self.connection.execute(
            "SELECT count(*) FROM schema_version WHERE name = '006_image_db'").fetchone()[0], 1)

    def test_migrate_twice_applies_nothing_new(self):
        self.assertEqual(migrate(DSN), [])

    # ── 그림 파일 ──
    def test_same_file_is_stored_once(self):
        self.asset("같은 그림")
        self.refused(psycopg.errors.UniqueViolation, lambda: self.asset("같은 그림"))

    def test_sha256_must_be_64_hex(self):
        self.refused(psycopg.errors.CheckViolation,
                     lambda: self.insert("image_assets", id=str(uuid4()), sha256="abc"))

    def test_file_upscaled_copy_and_keywords_are_kept(self):
        """과업 안내 010 데이터셋 예시의 jpeg·주요 키워드, 009의 '업스케일링 후 DB에 저장'."""
        image_id = self.asset(title="연회장 배치도", format="jpeg", width_px=640, height_px=480, content=b"\xff\xd8original",
                              upscaled_content=b"\x89PNGupscaled", upscaled_format="png", upscaled_width_px=1280,
                              upscaled_height_px=960, upscale_engine="esrgan-fast", keywords=["연회", "배치도"])
        row = self.connection.execute(
            "SELECT content, upscaled_content, keywords FROM image_assets WHERE id = %s", (image_id,)).fetchone()
        self.assertEqual((bytes(row[0]), bytes(row[1]), row[2]), (b"\xff\xd8original", b"\x89PNGupscaled", ["연회", "배치도"]))
        found = self.connection.execute("SELECT id FROM image_assets WHERE keywords @> %s", (["배치도"],)).fetchall()
        self.assertEqual([str(r[0]) for r in found], [image_id])
        self.assertEqual(self.connection.execute(
            "SELECT keywords FROM image_assets WHERE id = %s", (self.asset(),)).fetchone()[0], [])
        # 업스케일본 없이 업스케일 정보만 적을 수 없다
        self.refused(psycopg.errors.CheckViolation, lambda: self.asset(upscale_engine="esrgan-fast"),
                     "image_assets_upscaled_check")

    # ── 수록 위치 ──
    def test_every_placement_of_one_image_is_recorded(self):
        image_id = self.asset("여러 모듈에 실린 그림")
        first = self.placement(image_id, "LM1203020201_24v3", "그림 1-1", module_name="객실 예약 관리", page=12,
                               caption="객실 유형", source_line="출처: 집필진 제작(2026)", lesson_no=1, para_index=40,
                               context_text="객실 유형은 [그림 1-1]과 같이 구분한다.", width_mm=120, height_mm=80)
        self.placement(image_id, "LM1203020201_24v3", "그림 2-3", page=58, para_index=310)     # 같은 모듈의 다른 자리
        self.placement(image_id, "LM1203020202_24v3", "그림 1-2", page=9, para_index=22)       # 다른 모듈
        self.placement(image_id, "LM1203020202_24v3", "", para_index=77)                       # 캡션 없는 그림
        self.placement(image_id, "LM1203020202_24v3", "", para_index=91)
        self.assertEqual(self.count("image_placements", image_id), 5)
        self.refused(psycopg.errors.UniqueViolation,                                           # 같은 자리를 두 번 적지 않는다
                     lambda: self.placement(image_id, "LM1203020201_24v3", "그림 1-1", para_index=40))
        reused = self.connection.execute(
            "SELECT count(DISTINCT module_code) FROM image_placements WHERE image_id = %s", (image_id,)).fetchone()[0]
        self.assertEqual(reused, 2, "sha256 하나로 재사용된 모듈 수를 셀 수 있어야 한다(REQ-02-005 ④)")
        row = self.connection.execute(
            "SELECT page, caption, context_text, width_mm FROM image_placements WHERE id = %s", (first,)).fetchone()
        self.assertEqual(row[:3], (12, "객실 유형", "객실 유형은 [그림 1-1]과 같이 구분한다."))
        self.assertEqual(float(row[3]), 120.0)

    # ── 권리 정보 ──
    def test_defaults_are_auto_tagged_and_scope_unknown(self):
        image_id = self.asset()
        self.rights(image_id)
        row = self.connection.execute(
            "SELECT status, reuse_scope, version, ai_used, kogl_ai, license_scheme, release_class "
            "FROM image_rights WHERE image_id = %s", (image_id,)).fetchone()
        self.assertEqual(row, ("auto", "unknown", 1, False, False, None, None))

    def test_confirmation_needs_required_fields(self):
        self.rejected("image_rights_confirmed_check", status="confirmed")
        self.rejected("image_rights_confirmed_check", **{**CONFIRMED, "ownership": None})       # 귀속 없음
        self.rejected("image_rights_confirmed_check", status="auto", confirmed_by="에디팅기관")  # 확정이 아닌데 확정자

    def test_every_kogl_type_accepts_only_its_own_conditions(self):
        for kogl_type in image_terms.KOGL_CONDITIONS:
            with self.subTest(kogl_type=kogl_type):
                self.rights(self.asset(), **kogl(kogl_type))
                self.rejected("image_rights_kogl_conditions_check",
                              **kogl(kogl_type, non_commercial=not kogl(kogl_type)["non_commercial"]))
        self.rejected("image_rights_kogl_conditions_check", license_scheme="kogl", kogl_type=1)   # 유형만 있고 조건을 비움
        self.rejected("image_rights_kogl_conditions_check", **kogl(1, share_alike=True))

    def test_ai_type_goes_with_types_1_to_4_and_keeps_their_conditions(self):
        self.rights(self.asset(), **kogl(4, kogl_ai=True))
        self.rejected("image_rights_kogl_ai_check", **kogl(0, kogl_ai=True))
        self.rejected("image_rights_kogl_ai_check", kogl_ai=True)
        # AI유형이 함께 표시돼도 상업적 이용금지를 풀 수 없다
        self.rejected("image_rights_kogl_conditions_check", **kogl(4, kogl_ai=True, non_commercial=False))

    def test_every_cc_license_accepts_only_its_own_conditions(self):
        for code in image_terms.CC_LICENSE:
            with self.subTest(cc_license=code):
                self.rights(self.asset(), **cc(code))
                self.rejected("image_rights_cc_conditions_check", **cc(code, no_derivatives=not cc(code)["no_derivatives"]))
        self.rejected("image_rights_cc_conditions_check", license_scheme="cc", cc_license="by")   # 조건을 비움

    def test_license_scheme_agrees_with_the_type_columns(self):
        for scheme in ("expired", "donated", "other"):          # 유형 열이 없는 체계 — 내용은 license_note에
            self.rights(self.asset(), license_scheme=scheme, license_note="공유마당 보호기간 만료 저작물")
        self.rejected("image_rights_license_columns_check", license_scheme="kogl")                 # 공공누리인데 유형 없음
        self.rejected("image_rights_license_columns_check", **{**kogl(1), "license_scheme": None})  # 유형은 있는데 체계 없음
        self.rejected("image_rights_license_columns_check", **{**cc("by"), "license_scheme": "other"})
        self.rejected("image_rights_license_columns_check", **{**kogl(1), "cc_license": "by"})      # 두 체계를 함께 적음

    def test_kogl_ownership_needs_a_type(self):
        self.rejected("image_rights_kogl_ownership_check", ownership="kogl")
        self.rights(self.asset(), ownership="kogl", **kogl(1))

    def test_ai_fields_only_when_ai_is_used(self):
        self.rejected("image_rights_ai_fields_check", ai_tool="도구 이름")
        for usage, (_, mode) in image_terms.AI_USAGE.items():
            with self.subTest(usage=usage):
                self.rights(self.asset(), ai_used=True, ai_usage=usage, ai_mode=mode, ai_tool="도구 이름")
                other = next(m for m in image_terms.AI_MODE if m != mode)
                self.rejected("image_rights_ai_usage_mode_check", ai_used=True, ai_usage=usage, ai_mode=other)

    def test_every_allowed_code_is_accepted_and_others_rejected(self):
        for column, terms in (("category", image_terms.CATEGORY), ("reuse_scope", image_terms.REUSE_SCOPE),
                              ("release_class", image_terms.RELEASE_CLASS)):
            for code in terms:
                with self.subTest(column=column, code=code):
                    self.rights(self.asset(), **{column: code})
        for column, value in (("category", "집필자 직접제작"), ("ownership", "etc"), ("reuse_scope", "미확인"),
                              ("release_class", "공개 가능"), ("license_scheme", "CCL"), ("cc_license", "BY")):
            with self.subTest(column=column, value=value):
                image_id = self.asset()
                self.refused(psycopg.errors.CheckViolation, lambda: self.rights(image_id, **{column: value}))
        for code in image_terms.KIND:
            self.asset(kind=code)
        self.refused(psycopg.errors.CheckViolation, lambda: self.asset(kind="사진"))

    # ── 추천용 뷰 ──
    def test_recommendable_view_shows_only_confirmed_with_known_scope(self):
        shown, shown_limited, unknown_scope, auto, no_rights = (self.asset() for _ in range(5))
        self.rights(shown, **CONFIRMED, reuse_scope="all")
        self.rights(shown_limited, **CONFIRMED, reuse_scope="module_only")
        self.rights(unknown_scope, **CONFIRMED)                       # 확정했지만 재사용 범위 미확인
        self.rights(auto, category="author_made", ownership="government", reuse_scope="all")   # 자동 태깅만
        listed = self.recommendable()
        self.assertLessEqual({shown, shown_limited}, listed)
        self.assertFalse({unknown_scope, auto, no_rights} & listed, "권리 미확인 이미지가 추천 목록에 나왔습니다")

    def test_recommendable_view_carries_source_and_license_but_not_the_file(self):
        """REQ-04-006: 이미지 DB에서 나가는 것에는 원본 출처와 원본 라이선스 유형이 함께 따라간다."""
        image_id = self.asset(title="기후 변화 도표", content=b"file", upscaled_content=b"big", keywords=["기후"])
        self.rights(image_id, **{**CONFIRMED, "category": "public_license", "ownership": "kogl"}, reuse_scope="all",
                    release_class="inherit", source_org="기상청", source_url="https://www.kogl.or.kr/",
                    credit_line="출처: 기상청(2026).", **kogl(2, kogl_ai=True))
        cursor = self.connection.execute("SELECT * FROM v_image_recommendable WHERE id = %s", (image_id,))
        row = dict(zip([column.name for column in cursor.description], cursor.fetchone()))
        self.assertEqual(
            {name: row[name] for name in ("title", "keywords", "has_upscaled", "license_scheme", "kogl_type", "kogl_ai",
                                          "non_commercial", "source_org", "credit_line", "release_class")},
            {"title": "기후 변화 도표", "keywords": ["기후"], "has_upscaled": True, "license_scheme": "kogl",
             "kogl_type": 2, "kogl_ai": True, "non_commercial": True, "source_org": "기상청",
             "credit_line": "출처: 기상청(2026).", "release_class": "inherit"})
        self.assertFalse({"content", "upscaled_content"} & set(row))

    # ── 딸린 표 ──
    def test_links_evidence_history_and_cascade(self):
        image_id = self.asset()
        unit = "1203020201_24v3"
        placement_id = self.placement(image_id, "LM" + unit, "그림 1-1")
        for element, criterion in ((f"{unit}.1", "1.1"), (f"{unit}.1", "1.2"), ("", "")):
            self.insert("image_ncs_links", id=str(uuid4()), image_id=image_id, placement_id=placement_id,
                        unit_code=unit, element_code=element, criterion_no=criterion)
        self.refused(psycopg.errors.UniqueViolation,                  # 같은 수행준거에 두 번 잇지 않는다
                     lambda: self.insert("image_ncs_links", id=str(uuid4()), image_id=image_id, unit_code=unit,
                                         element_code=f"{unit}.1", criterion_no="1.1"))
        for kind in image_terms.EVIDENCE_KIND:
            self.insert("image_evidence", id=str(uuid4()), image_id=image_id, kind=kind, file_ref=f"{kind}.pdf",
                        submitted_on="2026-11-17")
        self.refused(psycopg.errors.CheckViolation,
                     lambda: self.insert("image_evidence", id=str(uuid4()), image_id=image_id, kind="기타"))
        for action in image_terms.HISTORY_ACTION:
            self.insert("image_history", image_id=image_id, changed_by="에디팅기관", action=action, version=1,
                        changes=Jsonb({"reuse_scope": ["unknown", "all"]}))
        self.rights(image_id)
        tables = ("image_placements", "image_rights", "image_evidence", "image_ncs_links", "image_history")
        self.assertEqual([self.count(table, image_id) for table in tables],
                         [1, 1, len(image_terms.EVIDENCE_KIND), 3, len(image_terms.HISTORY_ACTION)])

        # 수록 위치만 지우면 수행준거 연결은 남고 자리만 비운다
        self.connection.execute("DELETE FROM image_placements WHERE id = %s", (placement_id,))
        self.assertEqual(self.connection.execute(
            "SELECT count(*), count(placement_id) FROM image_ncs_links WHERE image_id = %s", (image_id,)).fetchone(), (3, 0))
        self.connection.execute("DELETE FROM image_assets WHERE id = %s", (image_id,))
        self.assertEqual([self.count(table, image_id) for table in tables], [0, 0, 0, 0, 0],
                         "이미지를 지우면 딸린 행도 함께 지워져야 합니다")


if __name__ == "__main__":
    unittest.main()

"""이미지 저작권 DB(REQ-02-010)의 허용값 — 코드 ↔ 화면·문서에 쓰는 이름.

DB에는 코드(ASCII)만 저장한다. 한글 이름은 가운뎃점 꼴·자소 분리(NFD)로 같은 값이 달라질 수 있어서다.
허용값을 바꾸면 migrations.py에 다음 번호로 CHECK 제약을 다시 거는 항목을 추가한다
(tests/service/test_migrations.py가 여기와 SQL의 값 목록이 같은지 본다).
근거: 「NCS PoC 과업 안내」(요구사항정의서 V0.23) REQ-02-010·REQ-04-006, 원고 집필 계약서 붙임2(분류 체계)·제4조·제7조, AI 도구 사용 표기 예(2026.9).
"""

# 확정 상태 — 자동 태깅(REQ-02-009 결과 그대로) / 기관 확정(에디팅 기관·직능연이 확인)
STATUS = {
    "auto": "자동 태깅",
    "confirmed": "기관 확정",
}

# 분류 체계(원고 집필 계약서 붙임2)
CATEGORY = {
    "author_made": "집필자 직접제작",
    "commissioned": "외부 제작의뢰",
    "public_license": "공공누리·공유마당",
    "blanket_license": "포괄적 이용허락",
    "prior_module": "기개발 학습모듈",
}

# 권리 귀속
OWNERSHIP = {
    "government": "정부(교육부) 귀속",
    "licensed": "이용허락 한정",
    "kogl": "공공누리 조건",
}

# 재사용 가능 범위 — unknown은 추천(REQ-02-011)에 노출하지 않는다(v_image_recommendable)
REUSE_SCOPE = {
    "all": "전체",
    "module_only": "해당 학습모듈 한정",
    "unknown": "미확인",
}

# 산출물 분류(REQ-04-006) — 실제 개방 여부와 공공누리 유형 지정은 직능연(교육부)이 결정한다. 여기는 기록·분류까지
RELEASE_CLASS = {
    "open": "공개 가능",
    "inherit": "원 조건 승계",
    "private": "비공개",
}

# 라이선스 체계 — 공공누리(kogl_type), CC(cc_license), 보호기간 만료·기증 저작물(공유마당), 그 밖(license_note에 적는다)
LICENSE_SCHEME = {
    "kogl": "공공누리",
    "cc": "CCL",
    "expired": "보호기간 만료 저작물",
    "donated": "기증 저작물",
    "other": "기타",
}

# CC 라이선스 → (저작자표시, 비영리, 변경금지, 동일조건변경허락)
CC_LICENSE = {
    "by": (True, False, False, False),
    "by-sa": (True, False, False, True),
    "by-nd": (True, False, True, False),
    "by-nc": (True, True, False, False),
    "by-nc-sa": (True, True, False, True),
    "by-nc-nd": (True, True, True, False),
    "cc0": (False, False, False, False),
}

# 이미지 유형(REQ-02-009 유형 분류)
KIND = {
    "photo": "사진",
    "illustration": "삽화",
    "table": "도표",
    "graph": "그래프",
    "screenshot": "화면 캡처",
    "other": "기타",
}

# AI 활용 방식 — 표기 문구 '○○를 활용하여 생성함 / 수정 보완함'
AI_MODE = {
    "generated": "생성함",
    "modified": "수정 보완함",
}

# AI 활용 유형(AI 도구 사용 표기 예 1~5) → 활용 방식. 1·4는 생성, 2·3·5는 수정 보완(REQ-02-006 ①②)
AI_USAGE = {
    1: ("집필진 작성 내용 기반 AI 생성", "generated"),
    2: ("집필진 삽화 AI 수정 보완", "modified"),
    3: ("기존 이미지 보정", "modified"),
    4: ("AI 창작", "generated"),
    5: ("원본 사진 AI 수정", "modified"),
}

# 권리 증빙 종류(REQ-02-014)
EVIDENCE_KIND = {
    "transfer_consent": "양도 동의서",
    "license_consent": "이용허락 동의서",
    "portrait_consent": "초상권 동의서",
    "ai_pledge": "생성형 AI 결과물 집필자 서약서",
}

# 변경 이력의 동작
HISTORY_ACTION = {
    "created": "등록",
    "updated": "수정",
    "confirmed": "기관 확정",
    "unconfirmed": "확정 취소",
    "evidence_added": "증빙 추가",
    "evidence_removed": "증빙 삭제",
}

# 공공누리 유형 번호 → (출처표시, 상업적 이용금지, 변경금지). 제0유형은 조건 없음.
# AI유형은 제1~4유형과 함께 표시될 수 있고(kogl_ai), 그때도 조건은 함께 표시된 유형의 것을 그대로 따른다.
KOGL_CONDITIONS = {
    0: (False, False, False),
    1: (True, False, False),
    2: (True, True, False),
    3: (True, False, True),
    4: (True, True, True),
}

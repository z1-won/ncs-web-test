"""PostgreSQL 스키마와 번호 마이그레이션 목록. SQL 텍스트만 두고 psycopg를 import하지 않는다.

규칙: 적용된 항목은 수정하지 않고 다음 번호를 뒤에 추가한다. 모든 문장은 IF (NOT) EXISTS로 보호한다.
check_name의 허용값은 registry.ENGINES가 검증하므로 SQL에 엔진 이름을 적지 않는다 (tests/service/test_migrations.py).
"""

# 001: 최초 스키마. check_name의 허용값은 Python(registry.ENGINES)이 검증하므로 DB 제약으로 두지 않는다 — 엔진을
# 추가할 때 DB를 바꿀 필요가 없게 하기 위해서다.
SCHEMA = """
CREATE TABLE IF NOT EXISTS review_runs (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    check_name text NOT NULL,
    module_code text NOT NULL,
    verdict text NOT NULL,
    engine_version text,
    source text NOT NULL DEFAULT 'web' CHECK (source IN ('web', 'import'))
);
CREATE INDEX IF NOT EXISTS review_runs_created_idx ON review_runs (created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS review_runs_module_idx ON review_runs (module_code, created_at DESC);
CREATE INDEX IF NOT EXISTS review_runs_check_idx ON review_runs (check_name, created_at DESC);
CREATE INDEX IF NOT EXISTS review_runs_verdict_idx ON review_runs (verdict, created_at DESC);
CREATE TABLE IF NOT EXISTS review_results (
    run_id uuid PRIMARY KEY REFERENCES review_runs(id) ON DELETE CASCADE,
    summary jsonb NOT NULL,
    sheet jsonb NOT NULL,
    diagnostics jsonb NOT NULL,
    findings jsonb NOT NULL,
    checklist jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS review_inputs (
    run_id uuid NOT NULL REFERENCES review_runs(id) ON DELETE CASCADE,
    role text NOT NULL,
    filename text NOT NULL,
    sha256 text,
    byte_size bigint,
    PRIMARY KEY (run_id, role)
);
"""

# 006: 이미지 저작권 DB(REQ-02-010) — 추출·수집된 이미지의 권리 정보를 기관이 확정·보관한다.
# 기준: 「NCS PoC 과업 안내」(요구사항정의서 V0.23)의 REQ-02-010·009 수행예시와 REQ-04-006.
#   데이터셋 예시 = 학습모듈명 > [그림 N] > {그림명, 출처, 페이지, 그림 크기, jpeg, 공공누리 유형, 그림 사용 문장, 주요 키워드}
#   image_assets      그림 파일 1개 = 1행. 같은 파일은 sha256으로 한 번만(재사용 탐지 REQ-02-005 ④의 열쇠).
#                     파일 자체(content)와 업스케일본(upscaled_content — 009 '업스케일링 후 DB에 저장')을 함께 둔다
#   image_placements  1:N. 수록 위치 — 어느 학습모듈의 몇 쪽·몇 번 그림으로 실렸는가(그림명·출처 줄·그림 사용 문장).
#                     같은 그림이 여러 모듈·여러 자리에 실리면 자리마다 1행
#   image_rights      1:1. 분류 체계·권리 귀속·재사용 범위·라이선스(공공누리/CC/만료/기증)·AI 기준 필드·확정 상태·버전
#   image_evidence    1:N. 양도·이용허락·초상권 동의서, AI 서약서(REQ-02-014가 채운다)
#   image_ncs_links   1:N. 능력단위·요소·수행준거 연결(이미지 하나가 여러 수행준거에 쓰일 수 있다)
#   image_history     변경 이력(누가·언제·무엇을)
#   v_image_recommendable  기관 확정 + 재사용 범위가 정해진 것만 — 추천(REQ-02-011)은 이 뷰만 본다('미확인 추천 노출 0건')
# 허용값은 코드(ASCII)로 저장하고 이름은 ncs_service.images.image_terms에 둔다. 값 목록이 서로 같은지는 test_migrations가 검사한다.
# 필수 항목(정의서 '구조·형식 정확성 99.5%')은 제약으로 보장한다: 확정하려면 분류·귀속·확정자·확정 시각이 있어야 하고,
# 이용조건은 라이선스 유형에서 정해지는 값과 달라질 수 없으며, AI를 쓰지 않은 이미지에 AI 필드를 채울 수 없다.
IMAGE_DB = """
CREATE TABLE IF NOT EXISTS image_assets (
    id uuid PRIMARY KEY,
    sha256 text NOT NULL UNIQUE CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    filename text,
    title text,
    format text,
    width_px integer CHECK (width_px > 0),
    height_px integer CHECK (height_px > 0),
    byte_size bigint CHECK (byte_size >= 0),
    content bytea,
    upscaled_content bytea,
    upscaled_format text,
    upscaled_width_px integer CHECK (upscaled_width_px > 0),
    upscaled_height_px integer CHECK (upscaled_height_px > 0),
    upscale_engine text,
    kind text CHECK (kind IN ('photo', 'illustration', 'table', 'graph', 'screenshot', 'other')),
    keywords text[] NOT NULL DEFAULT '{}',
    CONSTRAINT image_assets_upscaled_check CHECK (
        upscaled_content IS NOT NULL
        OR (upscaled_format IS NULL AND upscaled_width_px IS NULL AND upscaled_height_px IS NULL AND upscale_engine IS NULL))
);
CREATE INDEX IF NOT EXISTS image_assets_keywords_idx ON image_assets USING gin (keywords);
CREATE TABLE IF NOT EXISTS image_placements (
    id uuid PRIMARY KEY,
    image_id uuid NOT NULL REFERENCES image_assets(id) ON DELETE CASCADE,
    module_code text NOT NULL,
    module_name text,
    page integer CHECK (page > 0),
    label text NOT NULL DEFAULT '',
    caption text,
    source_line text,
    source_template text,
    context_text text,
    lesson_no integer CHECK (lesson_no > 0),
    para_index integer NOT NULL DEFAULT 0 CHECK (para_index >= 0),
    width_mm numeric(7, 2) CHECK (width_mm > 0),
    height_mm numeric(7, 2) CHECK (height_mm > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (image_id, module_code, label, para_index)
);
CREATE INDEX IF NOT EXISTS image_placements_module_idx ON image_placements (module_code, page, label);
CREATE TABLE IF NOT EXISTS image_rights (
    image_id uuid PRIMARY KEY REFERENCES image_assets(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'auto' CHECK (status IN ('auto', 'confirmed')),
    confirmed_by text,
    confirmed_at timestamptz,
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    updated_at timestamptz NOT NULL DEFAULT now(),
    category text CHECK (category IN ('author_made', 'commissioned', 'public_license', 'blanket_license', 'prior_module')),
    ownership text CHECK (ownership IN ('government', 'licensed', 'kogl')),
    reuse_scope text NOT NULL DEFAULT 'unknown' CHECK (reuse_scope IN ('all', 'module_only', 'unknown')),
    release_class text CHECK (release_class IN ('open', 'inherit', 'private')),
    license_scheme text CHECK (license_scheme IN ('kogl', 'cc', 'expired', 'donated', 'other')),
    kogl_type smallint CHECK (kogl_type BETWEEN 0 AND 4),
    kogl_ai boolean NOT NULL DEFAULT false,
    cc_license text CHECK (cc_license IN ('by', 'by-sa', 'by-nd', 'by-nc', 'by-nc-sa', 'by-nc-nd', 'cc0')),
    license_note text,
    attribution boolean,
    non_commercial boolean,
    no_derivatives boolean,
    share_alike boolean,
    author text,
    source_org text,
    source_url text,
    retrieved_on date,
    credit_line text,
    ai_used boolean NOT NULL DEFAULT false,
    ai_usage smallint CHECK (ai_usage BETWEEN 1 AND 5),
    ai_mode text CHECK (ai_mode IN ('generated', 'modified')),
    ai_tool text,
    ai_date date,
    ai_original_source text,
    ai_pledge_submitted boolean,
    ai_tos_scope text,
    CONSTRAINT image_rights_confirmed_check CHECK (
        (status = 'confirmed' AND confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL
            AND category IS NOT NULL AND ownership IS NOT NULL)
        OR (status = 'auto' AND confirmed_by IS NULL AND confirmed_at IS NULL)),
    CONSTRAINT image_rights_license_columns_check CHECK (
        (license_scheme IS NOT DISTINCT FROM 'kogl') = (kogl_type IS NOT NULL)
        AND (license_scheme IS NOT DISTINCT FROM 'cc') = (cc_license IS NOT NULL)),
    CONSTRAINT image_rights_kogl_conditions_check CHECK (
        kogl_type IS NULL
        OR (attribution IS NOT DISTINCT FROM (kogl_type >= 1)
            AND non_commercial IS NOT DISTINCT FROM (kogl_type IN (2, 4))
            AND no_derivatives IS NOT DISTINCT FROM (kogl_type IN (3, 4))
            AND share_alike IS NOT DISTINCT FROM false)),
    CONSTRAINT image_rights_cc_conditions_check CHECK (
        cc_license IS NULL
        OR (attribution IS NOT DISTINCT FROM (cc_license <> 'cc0')
            AND non_commercial IS NOT DISTINCT FROM (cc_license IN ('by-nc', 'by-nc-sa', 'by-nc-nd'))
            AND no_derivatives IS NOT DISTINCT FROM (cc_license IN ('by-nd', 'by-nc-nd'))
            AND share_alike IS NOT DISTINCT FROM (cc_license IN ('by-sa', 'by-nc-sa')))),
    CONSTRAINT image_rights_kogl_ai_check CHECK (NOT kogl_ai OR COALESCE(kogl_type, 0) BETWEEN 1 AND 4),
    CONSTRAINT image_rights_kogl_ownership_check CHECK (ownership IS DISTINCT FROM 'kogl' OR kogl_type IS NOT NULL),
    CONSTRAINT image_rights_ai_fields_check CHECK (
        ai_used OR (ai_usage IS NULL AND ai_mode IS NULL AND ai_tool IS NULL AND ai_date IS NULL
            AND ai_original_source IS NULL AND ai_pledge_submitted IS NULL AND ai_tos_scope IS NULL)),
    CONSTRAINT image_rights_ai_usage_mode_check CHECK (
        ai_usage IS NULL OR ai_mode IS NULL OR (ai_mode = 'generated') = (ai_usage IN (1, 4)))
);
CREATE INDEX IF NOT EXISTS image_rights_status_idx ON image_rights (status, reuse_scope);
CREATE TABLE IF NOT EXISTS image_evidence (
    id uuid PRIMARY KEY,
    image_id uuid NOT NULL REFERENCES image_assets(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('transfer_consent', 'license_consent', 'portrait_consent', 'ai_pledge')),
    file_ref text,
    file_sha256 text CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
    submitted_on date,
    note text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS image_evidence_image_idx ON image_evidence (image_id, kind);
CREATE TABLE IF NOT EXISTS image_ncs_links (
    id uuid PRIMARY KEY,
    image_id uuid NOT NULL REFERENCES image_assets(id) ON DELETE CASCADE,
    placement_id uuid REFERENCES image_placements(id) ON DELETE SET NULL,
    unit_code text NOT NULL,
    element_code text NOT NULL DEFAULT '',
    criterion_no text NOT NULL DEFAULT '',
    UNIQUE (image_id, unit_code, element_code, criterion_no)
);
CREATE INDEX IF NOT EXISTS image_ncs_links_unit_idx ON image_ncs_links (unit_code, element_code, criterion_no);
CREATE TABLE IF NOT EXISTS image_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    image_id uuid NOT NULL REFERENCES image_assets(id) ON DELETE CASCADE,
    changed_at timestamptz NOT NULL DEFAULT now(),
    changed_by text NOT NULL,
    action text NOT NULL CHECK (action IN ('created', 'updated', 'confirmed', 'unconfirmed', 'evidence_added', 'evidence_removed')),
    version integer,
    changes jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS image_history_image_idx ON image_history (image_id, changed_at DESC, id DESC);
CREATE OR REPLACE VIEW v_image_recommendable AS
SELECT a.id, a.sha256, a.filename, a.title, a.format, a.width_px, a.height_px, a.kind, a.keywords,
       (a.upscaled_content IS NOT NULL) AS has_upscaled,
       r.category, r.ownership, r.reuse_scope, r.release_class,
       r.license_scheme, r.kogl_type, r.kogl_ai, r.cc_license, r.license_note,
       r.attribution, r.non_commercial, r.no_derivatives, r.share_alike,
       r.author, r.source_org, r.source_url, r.retrieved_on, r.credit_line,
       r.ai_used, r.ai_mode, r.ai_tool, r.confirmed_by, r.confirmed_at, r.version
FROM image_assets a JOIN image_rights r ON r.image_id = a.id
WHERE r.status = 'confirmed' AND r.reuse_scope <> 'unknown'
"""

# 번호 순서로 한 번씩만 적용되는 스키마 변경. 적용된 항목은 수정하지 않고 새 번호를 뒤에 붙인다.
# 002: 초기 설치본에 있던 check_name CHECK 제약 제거(이름은 PostgreSQL 자동 명명 규칙 <표>_<열>_check).
MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("001_initial", SCHEMA),
    ("002_drop_check_name_constraint",
     "ALTER TABLE review_runs DROP CONSTRAINT IF EXISTS review_runs_check_name_check"),
    # 003: '전체 실행'(한 번 올린 파일로 구성요소 10개를 차례로 검수) 묶음 id. 단독 실행은 NULL.
    ("003_group_id",
     "ALTER TABLE review_runs ADD COLUMN IF NOT EXISTS group_id uuid;\n"
     "CREATE INDEX IF NOT EXISTS review_runs_group_idx ON review_runs (group_id, created_at)"),
    # 004: 원고 hwpx 보관 — 이력에서 '수정 메모 원고'를 다시 내려받기 위해. sha256으로 중복 제거(전체 실행 10건이 같은 원고를 가리킨다).
    # review_inputs.sha256으로 잇는다. 실행을 지울 때 더 이상 참조되지 않는 파일은 postgres.delete_*가 함께 지운다(보관 기간 = 이력 보관 기간).
    ("004_review_files",
     "CREATE TABLE IF NOT EXISTS review_files (\n"
     "    sha256 text PRIMARY KEY,\n"
     "    filename text NOT NULL,\n"
     "    content bytea NOT NULL,\n"
     "    byte_size bigint NOT NULL,\n"
     "    created_at timestamptz NOT NULL DEFAULT now()\n"
     ")"),
    # 005: 실행 출처에 'cli' 추가 — 검수 CLI(ncs-toc 등)도 DATABASE_URL이 있으면 이력에 남긴다. 화면의 이력과 구분하려는 값이다.
    # CHECK 제약은 값을 늘릴 수 없어 지우고 다시 건다(이름은 PostgreSQL 자동 명명 규칙 <표>_<열>_check).
    ("005_source_cli",
     "ALTER TABLE IF EXISTS review_runs DROP CONSTRAINT IF EXISTS review_runs_source_check;\n"
     "ALTER TABLE IF EXISTS review_runs ADD CONSTRAINT review_runs_source_check "
     "CHECK (source IN ('web', 'import', 'cli'))"),
    ("006_image_db", IMAGE_DB),
    # 007: 수집 자료의 고유번호(공공누리 샘플 JSON의 image_id — 'KOGL-SAMPLE-0001'). 그림의 동일성은 여전히 sha256으로 보고,
    # 이 값은 수집 목록과 DB의 그림을 사람이 맞춰 볼 때 쓰는 이름표다(REQ-02-012). 같은 번호가 두 그림에 붙어도 막지 않는다.
    ("007_image_source_id",
     "ALTER TABLE IF EXISTS image_assets ADD COLUMN IF NOT EXISTS source_id text;\n"
     "CREATE INDEX IF NOT EXISTS image_assets_source_id_idx ON image_assets (source_id)"),
    # 008: 그림 임베딩 벡터(REQ-02-011) — 그림 자체를 문맥과 맞춰 보기 위한 것. 모델을 바꿔도 되게 (그림, 모델)마다 한 벌.
    # 벡터는 이 컴퓨터에서 계산한 것이고(ncs_recommend.embed) PoC 규모라 확장(pgvector) 없이 real[]로 두고 파이썬에서 견준다.
    ("008_image_embeddings",
     "CREATE TABLE IF NOT EXISTS image_embeddings (\n"
     "    image_id uuid NOT NULL REFERENCES image_assets(id) ON DELETE CASCADE,\n"
     "    model text NOT NULL,\n"
     "    dim integer NOT NULL CHECK (dim > 0),\n"
     "    vector real[] NOT NULL,\n"
     "    created_at timestamptz NOT NULL DEFAULT now(),\n"
     "    PRIMARY KEY (image_id, model)\n"
     ")"),
    # 009: 원고 분량 산정(REQ-02-013) 이력 — 집필료 정산 근거라 언제·어느 원고를·어떤 단가와 계약 분량으로 산정했는지 남긴다.
    # 검수 이력(review_runs)은 항목별 판정 구조라 모양이 달라 따로 둔다. 원고 파일은 보관하지 않고 이름·sha256·크기만 남긴다
    # (같은 원고인지 확인하는 데는 해시면 충분하다). 목록에 쓰는 값(분량·단가·집필료)은 열로, 산정표 전체는 result에 둔다.
    ("009_volume_runs",
     "CREATE TABLE IF NOT EXISTS volume_runs (\n"
     "    id uuid PRIMARY KEY,\n"
     "    created_at timestamptz NOT NULL DEFAULT now(),\n"
     "    module_code text NOT NULL DEFAULT '',\n"
     "    manuscript text NOT NULL,\n"
     "    sha256 text,\n"
     "    byte_size bigint,\n"
     "    pages integer NOT NULL,\n"
     "    unit_price integer NOT NULL,\n"
     "    fee bigint NOT NULL,\n"
     "    estimated boolean NOT NULL DEFAULT false,\n"
     "    params jsonb NOT NULL,\n"
     "    inputs jsonb NOT NULL,\n"
     "    result jsonb NOT NULL,\n"
     "    engine_version text,\n"
     "    source text NOT NULL DEFAULT 'web'\n"
     ");\n"
     "CREATE INDEX IF NOT EXISTS volume_runs_created_idx ON volume_runs (created_at DESC, id DESC);\n"
     "CREATE INDEX IF NOT EXISTS volume_runs_module_idx ON volume_runs (module_code, created_at DESC)"),
    # 010: 원고 진행 현황(REQ-02-007)에 쓰는 개수 기록 — 의견 반영 검토(opinion)와 권리 증빙 점검(rights)은 결과를 보관하지 않으므로
    # 원고별 진행도(총 의견·반영·미반영, 판정·누락 수)를 보여 줄 숫자만 남긴다. 의견 문장·원고 문단·지적 내용은 넣지 않는다
    # (counts의 모양은 ncs_service.workflow.progress.summarize_opinion·summarize_rights). files는 올린 파일의 역할과 이름뿐이다.
    ("010_work_records",
     "CREATE TABLE IF NOT EXISTS work_records (\n"
     "    id uuid PRIMARY KEY,\n"
     "    created_at timestamptz NOT NULL DEFAULT now(),\n"
     "    kind text NOT NULL,\n"
     "    module_code text NOT NULL DEFAULT '',\n"
     "    manuscript text NOT NULL,\n"
     "    counts jsonb NOT NULL,\n"
     "    files jsonb NOT NULL,\n"
     "    source text NOT NULL DEFAULT 'web'\n"
     ");\n"
     "CREATE INDEX IF NOT EXISTS work_records_module_idx ON work_records (module_code, created_at DESC)"),
    # 011: 원고 진행 현황의 단계 완료 표시 — 기록으로 미룬 값 대신 담당자(에디터)가 실제로 끝낸 단계를 직접 표시한다.
    #   manuscript_stages         원고(모듈 코드) × 단계(1~7)의 지금 상태. 완료로 표시한 사람·시각·메모. 되돌리면 행을 지운다
    #   manuscript_stage_history  표시·되돌림 이력(누가·언제·무엇을). 지우지 않는다
    #   review_runs.work_stage    원고 검수를 돌릴 때 고른 단계(2 초고본·3 수정본·6 최종본). 고르지 않으면 NULL
    ("011_manuscript_stages",
     "CREATE TABLE IF NOT EXISTS manuscript_stages (\n"
     "    module_code text NOT NULL,\n"
     "    stage smallint NOT NULL CHECK (stage BETWEEN 1 AND 7),\n"
     "    done_by text NOT NULL,\n"
     "    done_at timestamptz NOT NULL DEFAULT now(),\n"
     "    note text NOT NULL DEFAULT '',\n"
     "    PRIMARY KEY (module_code, stage)\n"
     ");\n"
     "CREATE TABLE IF NOT EXISTS manuscript_stage_history (\n"
     "    id uuid PRIMARY KEY,\n"
     "    module_code text NOT NULL,\n"
     "    stage smallint NOT NULL CHECK (stage BETWEEN 1 AND 7),\n"
     "    action text NOT NULL CHECK (action IN ('done', 'undone')),\n"
     "    changed_by text NOT NULL,\n"
     "    changed_at timestamptz NOT NULL DEFAULT now(),\n"
     "    note text NOT NULL DEFAULT ''\n"
     ");\n"
     "CREATE INDEX IF NOT EXISTS manuscript_stage_history_idx ON manuscript_stage_history (module_code, changed_at DESC);\n"
     "ALTER TABLE review_runs ADD COLUMN IF NOT EXISTS work_stage smallint"),
    # 012: 계정과 로그인 세션(ncs_service.auth.accounts) — 회원가입 없이 관리자가 계정을 만든다. 비밀번호는 scrypt 값만, 세션은 토큰의 sha256만 둔다.
    # 역할 허용값은 ncs_service.auth.accounts.ROLES와 같아야 한다(test_accounts가 검사한다).
    ("012_accounts",
     "CREATE TABLE IF NOT EXISTS accounts (\n"
     "    id uuid PRIMARY KEY,\n"
     "    login text NOT NULL UNIQUE,\n"
     "    name text NOT NULL,\n"
     "    role text NOT NULL CHECK (role IN ('krivet', 'author', 'editor', 'reviewer', 'committee')),\n"
     "    org text NOT NULL DEFAULT '',\n"
     "    password_hash text NOT NULL,\n"
     "    active boolean NOT NULL DEFAULT true,\n"
     "    created_at timestamptz NOT NULL DEFAULT now()\n"
     ");\n"
     "CREATE TABLE IF NOT EXISTS account_sessions (\n"
     "    token_hash text PRIMARY KEY,\n"
     "    account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,\n"
     "    created_at timestamptz NOT NULL DEFAULT now(),\n"
     "    expires_at timestamptz NOT NULL\n"
     ");\n"
     "CREATE INDEX IF NOT EXISTS account_sessions_account_idx ON account_sessions (account_id)"),
    # 013: 세분류 건(ncs_service.workflow.cases) — 건(세분류 + 사업 연도) → 권(학습모듈, 담당 집필자) → 판본(제출한 원고 파일) → 사건(누가·언제·무엇을).
    # 단계의 상태는 저장하지 않고 사건을 접어서 얻는다(ncs_service.workflow.flow.states). 단계 key와 행동은 flow가 검증한다 — SQL에 적으면 단계가 바뀔 때마다 DB를 바꿔야 한다.
    # 사건은 건에도 권에도 붙는다(volume_id가 비면 건 단위). 심의의 단위가 정해져도 표는 그대로다. seq는 같은 시각의 사건 순서를 가른다.
    # 판본의 원고 파일은 지우는 기한 없이 보관한다(2026-11-21 결정). 개선 유형 허용값은 flow.IMPROVEMENTS와 같아야 한다(test_flow가 검사한다).
    ("013_cases",
     "CREATE TABLE IF NOT EXISTS cases (\n"
     "    id uuid PRIMARY KEY,\n"
     "    subclass text NOT NULL CHECK (subclass ~ '^[0-9]{8}$'),\n"
     "    year smallint NOT NULL CHECK (year BETWEEN 2000 AND 2100),\n"
     "    name text NOT NULL DEFAULT '',\n"
     "    improvement text NOT NULL CHECK (improvement IN ('기존개선', '최소개선', '양식편집')),\n"
     "    created_by text NOT NULL,\n"
     "    created_at timestamptz NOT NULL DEFAULT now(),\n"
     "    UNIQUE (subclass, year)\n"
     ");\n"
     "CREATE TABLE IF NOT EXISTS case_volumes (\n"
     "    id uuid PRIMARY KEY,\n"
     "    case_id uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,\n"
     "    module_code text NOT NULL,\n"
     "    title text NOT NULL DEFAULT '',\n"
     "    author_id uuid REFERENCES accounts(id) ON DELETE SET NULL,\n"
     "    created_at timestamptz NOT NULL DEFAULT now(),\n"
     "    UNIQUE (case_id, module_code)\n"
     ");\n"
     "CREATE INDEX IF NOT EXISTS case_volumes_module_idx ON case_volumes (module_code);\n"
     "CREATE INDEX IF NOT EXISTS case_volumes_author_idx ON case_volumes (author_id);\n"
     "CREATE TABLE IF NOT EXISTS volume_versions (\n"
     "    id uuid PRIMARY KEY,\n"
     "    volume_id uuid NOT NULL REFERENCES case_volumes(id) ON DELETE CASCADE,\n"
     "    stage text NOT NULL,\n"
     "    number integer NOT NULL CHECK (number >= 1),\n"
     "    sha256 text NOT NULL,\n"
     "    filename text NOT NULL,\n"
     "    byte_size bigint NOT NULL,\n"
     "    content bytea NOT NULL,\n"
     "    submitted_by uuid REFERENCES accounts(id) ON DELETE SET NULL,\n"
     "    submitted_name text NOT NULL,\n"
     "    submitted_at timestamptz NOT NULL DEFAULT now(),\n"
     "    UNIQUE (volume_id, stage, number)\n"
     ");\n"
     "CREATE TABLE IF NOT EXISTS case_events (\n"
     "    id uuid PRIMARY KEY,\n"
     "    seq bigint GENERATED ALWAYS AS IDENTITY,\n"
     "    case_id uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,\n"
     "    volume_id uuid REFERENCES case_volumes(id) ON DELETE CASCADE,\n"
     "    stage text NOT NULL DEFAULT '',\n"
     "    action text NOT NULL,\n"
     "    actor_id uuid REFERENCES accounts(id) ON DELETE SET NULL,\n"
     "    actor text NOT NULL,\n"
     "    proxy boolean NOT NULL DEFAULT false,\n"
     "    at timestamptz NOT NULL DEFAULT now(),\n"
     "    note text NOT NULL DEFAULT '',\n"
     "    version_id uuid REFERENCES volume_versions(id) ON DELETE SET NULL,\n"
     "    evidence jsonb NOT NULL DEFAULT '{}'::jsonb\n"
     ");\n"
     "CREATE INDEX IF NOT EXISTS case_events_case_idx ON case_events (case_id, seq)"),
    # 014: 원고 검수 실행이 어느 판본의 것인지(review_runs.version_id) — 세분류 건의 권 화면에서 판본마다 검수 결과를 보이고,
    # 보완 요청·완료의 근거로 가리킨다. 건 밖에서 돌린 검수(단독 실행)는 NULL.
    ("014_review_version",
     "ALTER TABLE review_runs ADD COLUMN IF NOT EXISTS version_id uuid REFERENCES volume_versions(id) ON DELETE SET NULL;\n"
     "CREATE INDEX IF NOT EXISTS review_runs_version_idx ON review_runs (version_id)"),
    # 015: 기록마다 돌린 계정(account_id)과, 세분류 건의 어느 권·어느 단계 것인지(case_volume_id, case_stage)를 적는다(ncs_service.auth.access).
    # 돌린 계정은 볼 수 있는 범위를 거르는 데 쓴다(집필진은 담당 권의 기록과 자기가 돌린 기록만). 원고 검수는 판본(version_id)으로 권에 붙으므로 권·단계 열이 없다.
    ("015_record_owner_and_stage",
     "ALTER TABLE review_runs ADD COLUMN IF NOT EXISTS account_id uuid REFERENCES accounts(id) ON DELETE SET NULL;\n"
     "ALTER TABLE volume_runs ADD COLUMN IF NOT EXISTS account_id uuid REFERENCES accounts(id) ON DELETE SET NULL;\n"
     "ALTER TABLE volume_runs ADD COLUMN IF NOT EXISTS case_volume_id uuid REFERENCES case_volumes(id) ON DELETE SET NULL;\n"
     "ALTER TABLE volume_runs ADD COLUMN IF NOT EXISTS case_stage text;\n"
     "ALTER TABLE work_records ADD COLUMN IF NOT EXISTS account_id uuid REFERENCES accounts(id) ON DELETE SET NULL;\n"
     "ALTER TABLE work_records ADD COLUMN IF NOT EXISTS case_volume_id uuid REFERENCES case_volumes(id) ON DELETE SET NULL;\n"
     "ALTER TABLE work_records ADD COLUMN IF NOT EXISTS case_stage text;\n"
     "CREATE INDEX IF NOT EXISTS volume_runs_case_volume_idx ON volume_runs (case_volume_id);\n"
     "CREATE INDEX IF NOT EXISTS work_records_case_volume_idx ON work_records (case_volume_id)"),
    # 016: 건 단위 단계에 올리는 문서(case_files — 개발계획서). 권의 판본과 같은 짜임이고 지우는 기한 없이 보관한다.
    # 개발계획서 점검 실행은 review_runs.case_file_id로 그 문서에, 분량 산정과 개수 기록은 version_id로 쓴 판본에 붙는다.
    ("016_case_files",
     "CREATE TABLE IF NOT EXISTS case_files (\n"
     "    id uuid PRIMARY KEY,\n"
     "    case_id uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,\n"
     "    stage text NOT NULL,\n"
     "    number integer NOT NULL CHECK (number >= 1),\n"
     "    sha256 text NOT NULL,\n"
     "    filename text NOT NULL,\n"
     "    byte_size bigint NOT NULL,\n"
     "    content bytea NOT NULL,\n"
     "    submitted_by uuid REFERENCES accounts(id) ON DELETE SET NULL,\n"
     "    submitted_name text NOT NULL,\n"
     "    submitted_at timestamptz NOT NULL DEFAULT now(),\n"
     "    UNIQUE (case_id, stage, number)\n"
     ");\n"
     "ALTER TABLE review_runs ADD COLUMN IF NOT EXISTS case_file_id uuid REFERENCES case_files(id) ON DELETE SET NULL;\n"
     "ALTER TABLE case_events ADD COLUMN IF NOT EXISTS case_file_id uuid REFERENCES case_files(id) ON DELETE SET NULL;\n"
     "ALTER TABLE volume_runs ADD COLUMN IF NOT EXISTS version_id uuid REFERENCES volume_versions(id) ON DELETE SET NULL;\n"
     "ALTER TABLE work_records ADD COLUMN IF NOT EXISTS version_id uuid REFERENCES volume_versions(id) ON DELETE SET NULL;\n"
     "CREATE INDEX IF NOT EXISTS review_runs_case_file_idx ON review_runs (case_file_id)"),
    # 017: 그림 설명(REQ-02-011 설명 색인 0단계) — 그림을 보는 모델이 그림을 글로 풀어 둔 것. 그림마다 엔진(제공자:모델)별 한 벌이라
    # 두 엔진의 설명을 나란히 견줄 수 있다(image_embeddings가 모델마다 한 벌인 것과 같다). 사람이 단 image_assets.keywords는 건드리지 않고,
    # 추천할 때 둘을 따로 읽어 점수도 따로 낸다. 사람이 읽고 고친 설명(checked_by)은 다시 채울 때 덮어쓰지 않는다.
    ("017_image_descriptions",
     "CREATE TABLE IF NOT EXISTS image_descriptions (\n"
     "    image_id uuid NOT NULL REFERENCES image_assets(id) ON DELETE CASCADE,\n"
     "    engine text NOT NULL,\n"
     "    kind text CHECK (kind IN ('photo', 'illustration', 'diagram', 'flowchart', 'table', 'graph', 'screenshot', 'other')),\n"
     "    scene text NOT NULL,\n"
     "    objects jsonb NOT NULL DEFAULT '[]',\n"
     "    visible_text text[] NOT NULL DEFAULT '{}',\n"
     "    keywords text[] NOT NULL DEFAULT '{}',\n"
     "    checked_by text,\n"
     "    checked_at timestamptz,\n"
     "    created_at timestamptz NOT NULL DEFAULT now(),\n"
     "    PRIMARY KEY (image_id, engine)\n"
     ")"),
    # 018: 추천 선택 기록(REQ-02-011) — 집필자가 추천된 그림을 '쓸 그림'으로 골랐는지 '맞지 않음'으로 보았는지. 추천을 재는 정답 세트의
    # 재료다(ncs_recommend.evaluate). 문단 글(query_text)을 함께 남긴다 — 같은 문단으로 방식을 다시 견주려면 글이 있어야 한다.
    # 그림이 지워지면 기록도 지워진다. 같은 사람이 같은 문단·같은 그림을 다시 고르면 앞의 기록을 바꾼다(한 줄만 남는다).
    ("018_recommend_choices",
     "CREATE TABLE IF NOT EXISTS recommend_choices (\n"
     "    id uuid PRIMARY KEY,\n"
     "    created_at timestamptz NOT NULL DEFAULT now(),\n"
     "    chosen_by text NOT NULL,\n"
     "    query_key text NOT NULL,\n"
     "    query_text text NOT NULL DEFAULT '',\n"
     "    unit_code text NOT NULL DEFAULT '',\n"
     "    criterion_no text NOT NULL DEFAULT '',\n"
     "    image_id uuid NOT NULL REFERENCES image_assets(id) ON DELETE CASCADE,\n"
     "    choice text NOT NULL CHECK (choice IN ('used', 'rejected')),\n"
     "    rank integer CHECK (rank >= 1),\n"
     "    score real,\n"
     "    detail jsonb NOT NULL DEFAULT '{}',\n"
     "    UNIQUE (chosen_by, query_key, image_id)\n"
     ");\n"
     "CREATE INDEX IF NOT EXISTS recommend_choices_query_idx ON recommend_choices (query_key);\n"
     "CREATE INDEX IF NOT EXISTS recommend_choices_image_idx ON recommend_choices (image_id)"),
    # 019: 원고 검수의 담당자 판정 확정(REQ-02-002 사람 작업 5번)을 서버에 둔다 — 전에는 확정한 브라우저에만 남아 다른 컴퓨터나 다른 담당자가 볼 수 없었다.
    # 검수 묶음(전체 실행)마다 항목(구성요소-번호) 하나에 확정 하나. 누가 언제 정했는지 함께 남긴다. 판정 허용값은 화면의 선택지와 같다.
    ("019_review_decisions",
     "CREATE TABLE IF NOT EXISTS review_decisions (\n"
     "    group_id uuid NOT NULL,\n"
     "    item_key text NOT NULL,\n"
     "    verdict text NOT NULL DEFAULT '' CHECK (verdict IN ('', '적합', '부적합')),\n"
     "    reason text NOT NULL DEFAULT '',\n"
     "    decided_by uuid REFERENCES accounts(id) ON DELETE SET NULL,\n"
     "    decided_name text NOT NULL DEFAULT '',\n"
     "    decided_at timestamptz NOT NULL DEFAULT now(),\n"
     "    PRIMARY KEY (group_id, item_key)\n"
     ")"),
    # 020: 그림 검수의 담당자 최종 판단(REQ-02-005 사람 작업 4번)과 태깅의 사람 확인(REQ-02-009 사람 작업 4번) — 그림마다 하나.
    # 그림 검수 결과는 서버에 두지 않으므로(업로드와 함께 사라진다) 원고 파일의 sha256과 그림 자리(item_id, 없으면 image_id)로 찾는다:
    # 같은 파일을 다시 올리면 앞의 판단이 그대로 보인다. fixes는 태깅에서 고친 값({필드: 값}, 필드 이름은 overrides.tsv와 같다).
    # 세분류 건의 판본으로 돌린 것이면 version_id를 적어 권 화면이 확정 개수를 센다.
    ("020_figure_decisions",
     "CREATE TABLE IF NOT EXISTS figure_decisions (\n"
     "    manuscript_sha text NOT NULL,\n"
     "    figure_key text NOT NULL,\n"
     "    image_id text NOT NULL DEFAULT '',\n"
     "    verdict text NOT NULL DEFAULT '' CHECK (verdict IN ('', '사용 가능', '정정 필요')),\n"
     "    reason text NOT NULL DEFAULT '',\n"
     "    fixes jsonb NOT NULL DEFAULT '{}',\n"
     "    module_code text NOT NULL DEFAULT '',\n"
     "    version_id uuid REFERENCES volume_versions(id) ON DELETE SET NULL,\n"
     "    decided_by uuid REFERENCES accounts(id) ON DELETE SET NULL,\n"
     "    decided_name text NOT NULL DEFAULT '',\n"
     "    decided_at timestamptz NOT NULL DEFAULT now(),\n"
     "    PRIMARY KEY (manuscript_sha, figure_key)\n"
     ");\n"
     "CREATE INDEX IF NOT EXISTS figure_decisions_version_idx ON figure_decisions (version_id)"),
    # 021: 의견 반영 검토의 보관(REQ-02-003 사람 작업 4번) — 세분류 건의 권에서 돌린 검토만. 의견별 결과(의견 글, 판정 후보, 근거 문단)와
    # 담당자 확정, 올린 의견서 파일을 둔다. 따로 연 검토는 전처럼 개수만 남는다. 개수 기록을 지우면 같이 지워진다.
    ("021_opinion_archives",
     "CREATE TABLE IF NOT EXISTS opinion_archives (\n"
     "    record_id uuid PRIMARY KEY REFERENCES work_records(id) ON DELETE CASCADE,\n"
     "    created_at timestamptz NOT NULL DEFAULT now(),\n"
     "    kept_name text NOT NULL DEFAULT '',\n"
     "    result jsonb NOT NULL,\n"
     "    decisions jsonb NOT NULL DEFAULT '{}',\n"
     "    decided_name text NOT NULL DEFAULT '',\n"
     "    decided_at timestamptz\n"
     ");\n"
     "CREATE TABLE IF NOT EXISTS opinion_archive_files (\n"
     "    id uuid PRIMARY KEY,\n"
     "    record_id uuid NOT NULL REFERENCES opinion_archives(record_id) ON DELETE CASCADE,\n"
     "    round text NOT NULL DEFAULT '',\n"
     "    filename text NOT NULL,\n"
     "    sha256 text NOT NULL,\n"
     "    byte_size bigint NOT NULL,\n"
     "    content bytea NOT NULL\n"
     ");\n"
     "CREATE INDEX IF NOT EXISTS opinion_archive_files_record_idx ON opinion_archive_files (record_id)"),
    # 022: 편집 검수 진행도의 쪽 수(REQ-02-007 사람 작업 1번 '진행완료 페이지 / 총 페이지') — 검수 실행마다 원고의 총 쪽과 부적합이 놓인 쪽.
    # {'총 쪽', '지적 쪽': [쪽 번호], '못 찾은 항목'}(ncs_service.annotate.page_progress). 쪽을 알 수 없는 원고(hwp, 배치 정보 없는 hwpx)는 비어 있다.
    ("022_review_pages",
     "ALTER TABLE review_runs ADD COLUMN IF NOT EXISTS pages jsonb"),
    # 023: 그림의 지각 해시(pHash 64비트, 16진 16자) — 만든 도표·그래프를 DB의 그림과 견줄 때 쓴다(REQ-02-006 ①, image_generate.similar).
    # 적재할 때가 아니라 대조할 때 없는 것만 채운다. 읽을 수 없는 그림은 빈 값이다. 그림을 지우면 같이 지워진다.
    ("023_image_phashes",
     "CREATE TABLE IF NOT EXISTS image_phashes (\n"
     "    image_id uuid PRIMARY KEY REFERENCES image_assets(id) ON DELETE CASCADE,\n"
     "    phash text NOT NULL CHECK (phash ~ '^([0-9a-f]{16})?$'),\n"
     "    created_at timestamptz NOT NULL DEFAULT now()\n"
     ")"),
)

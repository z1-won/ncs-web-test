"""PostgreSQL 스키마와 번호 마이그레이션 목록. SQL 텍스트만 두고 psycopg를 import하지 않는다.

규칙: 적용된 항목은 수정하지 않고 다음 번호를 뒤에 추가한다. 모든 문장은 IF (NOT) EXISTS로 보호한다.
check_name의 허용값은 registry.ENGINES가 검증하므로 SQL에 엔진 이름을 적지 않는다 (tests/test_migrations.py).
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
)

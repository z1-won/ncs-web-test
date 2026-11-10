#!/bin/sh
# 앱 계정(ncs_app)을 만든다. 데이터베이스 소유권은 넘기지 않고(DB 삭제·설정 변경 불가), 접속과 public 스키마에
# 표를 만들 권한만 준다 — 마이그레이션(migrations.py)은 앱 계정이 서버 시작 때 돌리므로 CREATE는 필요하다.
# 이 스크립트는 빈 볼륨에서 처음 뜰 때만 실행된다. 이미 있는 DB에는 아래 SQL을 ncs_admin으로 직접 적용한다.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_password="$NCS_DB_PASSWORD" <<'SQL'
CREATE ROLE ncs_app LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
REVOKE ALL ON DATABASE ncs_review FROM PUBLIC;
GRANT CONNECT ON DATABASE ncs_review TO ncs_app;
GRANT USAGE, CREATE ON SCHEMA public TO ncs_app;
SQL

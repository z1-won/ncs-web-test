"""기능별 API 경로. 모듈마다 register(app, services)가 그 기능의 경로를 앱에 붙인다 — server.create_app이 차례로 부른다.

  review   검수 실행(/api/review) · 업로드 토큰(/api/uploads) · 상태(/api/health)
  history  검수 이력(/api/reviews, /api/groups) — 이력을 지원하는 저장소일 때만
  export   확인서·수정 메모 원고 내려받기(/api/export/…)
  plan     개발계획서 작성(/api/plan/…)
  upscale  그림 업스케일(/api/uploads/{token}/pictures…, /proposal)
  rights   권리 증빙 제출 현황 점검(/api/rights/…)
  images   이미지 저작권 DB 조회·수정·확정(/api/images…) — PostgreSQL 저장소일 때만
  volume   원고 분량 산정(/api/volume) · 산정 이력(/api/volumes) — 이력은 이력을 지원하는 저장소일 때만
  opinion  검토의견서 반영 여부 검토(/api/opinion)
  suggest  원고 문장 추천(/api/suggest, /api/suggest/sentence, /api/suggest/kinds)
"""

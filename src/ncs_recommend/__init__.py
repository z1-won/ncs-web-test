"""수행준거 문맥 기반 이미지 추천 — REQ-02-011. 집필 중인 문단·수행준거에 맞는 그림을 이미지 저작권 DB에서 고른다.

검수 엔진(F02 확인서 항목)이 아니라 ncs_plan·ncs_upscale·ncs_rights처럼 ncs_core 위에 서는 기능 패키지다.
  context  문단 → 요약·핵심어. 생성형 AI(ncs_core.llm)가 읽고, 키·전송 승인이 없으면 규칙으로 핵심어만 뽑는다
  context  … 그림이 필요한 지점(Point: 짧은 묘사·그림 종류·문단 속 낱말·다른 이름)도 함께 받는다
  rank     후보 그림에 점수를 매겨 순서를 정하고, 이용조건·출처 문구·화질 안내를 붙인다
  describe 그림 설명(그림을 글로 풀어 둔 것)의 지시문·형식·응답 검사 — 설명의 낱말을 순위에 쓴다
  evaluate 정답 세트(문단마다 맞는 그림과 등급)로 추천 결과를 잰다(hit@k, recall@5, nDCG@10, 권하지 말아야 할 문단의 오탐)
DB에서 후보를 꺼내는 일은 ncs_service.images.image_recommend가 한다(이 패키지는 DB를 모른다).
권리가 확인되지 않은 그림을 거르는 것은 DB의 v_image_recommendable 뷰이며 여기서는 그 결과만 받는다.
"""

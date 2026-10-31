# 검수 패키지 공통 규약

두 검수 패키지(`ncs_toc`, `ncs_position`)와 앞으로 추가될 F02 항목 패키지는 이 규약을 따른다.

## 구조
- 공통 코어 `ncs_core`: 문서 읽기, 문자 정규화·판정, 입력 역할 판별, 모듈 코드, 규칙 실행기, 저장. **판정 정책을 두지 않는다.**
- 검수 패키지의 파일 구성은 고정이다.
  `config.py`(양식 가정, frozen dataclass) · `patterns.py`(정규식·라벨) · `text.py`(`norm, same = make_normalizer(접두 패턴)`) ·
  `compare.py`(목록 비교 도우미) · `parsers.py`(추출, I/O 없음) · `models.py`(`ReviewContext`) ·
  `rules/<규칙>.py`(판정, I/O 없음) · `registry.py`(`DEFAULT_RULES`, `ALL_ITEM_IDS`) · `pipeline.py` · `reporting.py` · `__main__.py`.
- 규칙은 `Rule(key, item_prefix, run)`으로 등록한다. `run`은 `ReviewContext` 하나를 받아 체크리스트 행 목록을 돌려주고, 행의 `item_id`는 `item_prefix`로 시작해야 한다.

## 공개 API (두 패키지 동일)
```python
run_review(paths, *, roles=None, module_code="", config=DEFAULT_CONFIG, rules=DEFAULT_RULES) -> ReviewResult
prepare_review(manuscript: Document, plan: Document | None, *, module_code="", config=...) -> ReviewContext
evaluate_review(context, *, rules=DEFAULT_RULES) -> ReviewResult
save_results(result, out_dir="결과", *, per_run_dir=True) -> SavedReport
python -m <패키지> 경로... [--manuscript 경로] [--plan 경로] [--module-code LM...] [--front-section N] [--out 결과]
```

## 체크리스트 행 (JSON 키는 한국어, 기존 호환)
`item_id`, `region_path`, `원고`, `체크`({이름: O|X|△|-}), `판정`(적합|부적합|판단불가, `ncs_core.PASS/FAIL/UNDECIDED`), `비고`(dict 또는 list), `수정 제안`.
추가 키(`개발계획서`, `기준`, `자리`, `해당 행 근거` 등)는 패키지가 정한다. 판정은 반드시 `ncs_core.verdict`로 계산한다.

## 저장 파일
`<out>/<코드>_xxxx/` 아래 `<코드>_<항목 꼬리말>.json`, `<코드>_<이름>_00_요약.json`, `_지적사항.json`, `_전체.json`, `_진단.json`, `<코드>_<이름>_검수결과.zip`.
항목 꼬리말은 각 패키지 `reporting.ITEM_FILES`에 둔다.

## 코드 스타일
- 검수 엔진·실행 조정 계층은 Python 3.10+, 표준 라이브러리만. 웹 계층은 FastAPI·Uvicorn을 사용하며 의존성은 `webapp/requirements.txt`에서 관리한다. 타입 힌트는 공개 함수와 dataclass에 붙인다.
- black 스타일, 줄 길이 120. 한 줄에 여러 문장(`if …: a; b`) 금지. 한 글자 변수는 짧은 comprehension 안에서만.
- 모듈 첫 줄은 한국어 docstring 한 문단. 사용자에게 보이는 문자열(비고·오류)은 한국어.
- 오류는 `ValueError`로 올리고, 웹 서버·CLI가 잡아서 메시지를 보여준다. 규칙·파서는 `print`하지 않는다.

## 실행과 수정
검수 엔진의 수정 원본은 `src/`이다. 웹 서버와 네 CLI는 모두 `ncs_service.execute_review()` 및 `persist_review()`를 통해 검수·저장을 실행한다.
`ncs_service`는 파일 경로를 받아 문서 선택·엔진 실행·저장을 조정하며 HTTP 요청이나 업로드 객체를 받지 않는다.
`ReviewRequest.config`에는 선택한 엔진의 `CheckConfig`, `rules`에는 사용자 지정 `Rule` 목록을 전달할 수 있다. 둘 다 `None`이면 엔진 기본값을 사용하며 `rules=()`는 규칙을 실행하지 않는다. 다른 엔진의 설정 객체는 `ValueError`로 거절한다.
각 엔진의 기존 `run_review()` 공개 API는 Python 호출자와의 호환성을 위해 유지한다.
FastAPI 요청·응답 모델 및 오류 상태 코드는 `webapp/server.py`에서 관리한다. 기존 `/api/review`의 입력 오류는 400, 저장 I/O 오류 등은 500을 유지한다.
웹 화면은 `webapp/frontend/src/`에서 수정하고, 프런트엔드 폴더에서 `npm run build`로 `webapp/frontend/dist/`를 생성한다.

## 변경 검증
정책을 바꾸지 않는 리팩토링은 `tests/compare_with_original.py`(또는 같은 방식의 전후 비교)로 체크리스트 JSON이 동일함을 보인다.
정책을 바꾸면 `docs/CONSISTENCY_REVIEW.md`의 "의도적으로 바꾼 동작" 표에 적는다.

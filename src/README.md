# `src/` 패키지 지도

패키지 24개가 이름만으로는 종류가 구분되지 않아, 층별로 정리한 지도입니다. 패키지마다 하는 일의 자세한 설명은 저장소 `README.md`의 '`src/` 패키지별 역할'과 `docs/ARCHITECTURE.md`에 있습니다.

## 층

아래 층은 위 층을 가져다 쓰지 않습니다. 이 규칙은 `tests/contract/test_layering.py`가 검사합니다.

```
4층  ncs_web                                   웹 서버(FastAPI). 화면이 부르는 API
3층  ncs_service                               검수 실행, 저장, 내보내기, 이미지 DB, 세분류 건, 계정
     ncs_llmreview  ncs_sources  ncs_opinion  ncs_suggest     엔진이나 Claude 호출을 쓰는 기능
2층  검수 엔진 10개                              F02 검수 확인서의 구성요소 하나씩
     기능 패키지 7개                             검수 확인서 밖의 기능(계획서, 분량, 그림 등)
1층  ncs_core                                  한글 파일 읽기, 공통 파서, 판정, 기준 데이터
```

2층의 패키지는 서로 가져다 쓰지 않습니다. 함께 쓰는 코드는 `ncs_core`에 둡니다.

## 1층: 공통

| 패키지 | 하는 일 |
|---|---|
| `ncs_core` | hwp/hwpx/PDF 읽기, 원고와 개발계획서 파서(`manuscript/`), 판정과 비고, NCS 목록과 법령 목록, 출처 줄 읽기, 공용 생성형 AI 호출(`llm`), 기준 데이터(`data/`) |

## 2층: 검수 엔진 (F02 검수 확인서)

엔진마다 모양이 같습니다: `rules/`(항목별 규칙), `pipeline.py`(실행), `sheet.py`(확인서 행), `registry.py`(규칙 목록), `config.py`.

| 패키지 | 확인서 구성요소 |
|---|---|
| `ncs_position` | NCS-학습모듈의 위치 ①~⑤ |
| `ncs_toc` | 차례 ①~⑦ |
| `ncs_overview` | 학습모듈의 개요 ①~⑧ |
| `ncs_knowledge` | 필요 지식 ①~⑧ |
| `ncs_perform` | 수행 내용 ①~④ |
| `ncs_teaching` | 교수·학습 방법 ①~④ |
| `ncs_evaluation` | 평가 ①~⑤ |
| `ncs_references` | 참고 자료 ①~④ |
| `ncs_colophon` | 개발 이력 및 판권 ① |
| `ncs_misc` | 기타 ①~⑧, 편집 체계, 법령 |

## 2층: 기능 패키지 (검수 확인서 밖)

| 패키지 | 요구사항 | 하는 일 |
|---|---|---|
| `ncs_plan` | REQ-02-001 | 개발계획서 초안 채우기, 점검, 판본 비교, 개선 유형 판단 자료 |
| `ncs_figures` | REQ-02-005, 009 | 원고 그림 검수와 태깅, 그림 판독 |
| `ncs_aiimage` | REQ-02-006 | 생성형 AI를 쓴 그림의 활용 표기와 결과물 현황 |
| `ncs_upscale` | REQ-02-006 | 해상도가 낮은 그림의 화질 높이기 |
| `ncs_recommend` | REQ-02-011 | 문단과 수행준거에 맞는 그림 고르기 |
| `ncs_volume` | REQ-02-013 | 원고 분량과 집필료 산정 |
| `ncs_rights` | REQ-02-014 | 그림의 권리 증빙 제출 현황 점검 |

## 3층: 서비스와 그 옆의 기능

| 패키지 | 요구사항 | 하는 일 | 2층에서 쓰는 것 |
|---|---|---|---|
| `ncs_service` | REQ-02-002, 007, 010, 012 | 검수 실행과 저장(파일, PostgreSQL), 확인서와 메모 원고 내보내기, 이미지 저작권 DB, 세분류 건과 진행 현황, 계정과 권한 | 엔진 전부, `ncs_recommend`, `ncs_upscale` |
| `ncs_llmreview` | REQ-02-003 | 누를 때만 도는 LLM 검토, Claude 호출(`claude.py`) | `ncs_perform`, `ncs_evaluation` |
| `ncs_sources` | REQ-02-008 | 출처 줄과 참고 자료 점검 | `ncs_references` |
| `ncs_opinion` | REQ-02-003 | 검토의견서와 심의의견서의 반영 여부 검토 | `ncs_llmreview`의 Claude 호출 |
| `ncs_suggest` | REQ-02-004 | 문장 추천 | `ncs_llmreview`의 Claude 호출 |

## 4층: 웹

| 패키지 | 하는 일 |
|---|---|
| `ncs_web` | FastAPI 서버. `routes/`에 기능마다 파일 하나, 로그인(`auth.py`), 빌드된 화면 제공 |

## 알아 둘 예외

- `ncs_plan/__main__.py`와 `ncs_figures/__main__.py`는 명령줄 실행 때만 `ncs_service`를 씁니다(공용 CLI, 메모 원고). 패키지 본체는 `ncs_core`만 씁니다.
- `ncs_service` 맨 위에는 검수 실행과 저장(`service`, `registry`, `store`, `postgres`, `migrations`, `cli`)과 내보내기(`export`, `annotate`, `f03`)만 있고, 나머지는 하위 폴더 셋입니다.

  | 폴더 | 든 것 |
  |---|---|
  | `ncs_service/images/` | 이미지 저작권 DB: `image_records`, `image_store`, `image_db`, `image_audit`, `image_recommend`, `image_terms`, `image_embed`, `kogl_import`, `ai_register`, `rights_link` |
  | `ncs_service/workflow/` | 세분류 건과 진행 현황: `cases`, `flow`, `progress` |
  | `ncs_service/auth/` | 계정과 볼 수 있는 범위: `accounts`, `access` |

  명령도 경로가 바뀌었습니다: `python -m ncs_service.images.image_db`, `python -m ncs_service.images.image_embed`, `python -m ncs_service.auth.accounts`(설치했다면 `ncs-accounts`. 경로가 바뀌었으니 `pip install -e ".[web]"`을 한 번 다시 해야 합니다).
- AI 활용 줄('○○를 활용하여 생성함. 2026. 7. 20.')을 읽는 규칙은 `ncs_core/ai_mark.py` 한 곳에 있습니다. `figures.parse_ai_mark`(필요 지식 ⑧, 권리 증빙 점검, AI 표기 넣기)와 `source_line.parse_ai_marker`(그림 검수, 출처 검토)는 그 결과를 각자의 자료형으로 바꾸기만 합니다.

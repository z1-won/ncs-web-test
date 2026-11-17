# 이미지 레코드 형식 (`ncs-image-record/0.3`)

이미지 저작권 DB(REQ-02-010)에 넣는 자료의 형식입니다. 이미지 추출(REQ-02-009)과 공공누리 수집(REQ-02-012)이 이 형식으로 내보내면 그대로 적재됩니다.
기준은 「NCS PoC 과업 안내」(요구사항정의서 V0.23) REQ-02-010의 데이터셋 예시 `학습모듈명 > [그림 N] > {그림명, 출처, 페이지, 그림 크기, jpeg, 공공누리 유형, 그림 사용 문장, 주요 키워드}`입니다.
코드는 `ncs_service/image_records.py`(검사), `ncs_service/image_db.py`(적재), 표는 `migrations.py`의 `006_image_db`, 예시는 `docs/examples/image_records/`.

## 쓰는 법

```bash
python -m ncs_service.image_db docs/examples/image_records/records.example.json --check     # DB 없이 형식만 검사
set -a; source .env; set +a
python -m ncs_service.image_db 레코드.json --by 담당자이름                                    # 적재(DATABASE_URL 필요)
```

파이썬에서는 `ncs_service.image_db.load_records(dsn, records, changed_by=…)`. 이때는 `file` 대신 `content`에 바이트를 바로 줄 수 있습니다.
결과는 전체·적재·거부 건수와 거부 사유, 필수 항목 충족률(적재 ÷ 전체)입니다. 거부가 있으면 종료 코드가 1입니다.

## 파일 모양

```json
{"schema": "ncs-image-record/0.3", "records": [ {레코드}, {레코드} ]}
```

레코드 1건은 **그림 파일 1개**입니다. 같은 그림이 여러 곳에 실렸으면 레코드는 하나, `placements`가 여러 개입니다.
표에 없는 키를 적으면 거부됩니다(오타를 조용히 버리지 않기 위해).

## 레코드

| 키 | 필수 | 내용 |
|---|---|---|
| `file` | `sha256`과 둘 중 하나 | 그림 파일 경로. JSON 파일이 있는 폴더 기준 상대 경로이고 그 폴더 밖은 가리킬 수 없음 |
| `sha256` | `file`과 둘 중 하나 | 그림 파일의 SHA-256(16진 64자). `file`이 있으면 계산하므로 적지 않아도 되고, 적었는데 다르면 거부 |
| `filename`, `title` | | 파일 이름(없으면 `file`에서), 자료 제목 |
| `source_id` | | 수집할 때 붙인 고유 번호(예: `KOGL-0001`). 화면에 ‘수집 번호’로 보이고 검색됨. 같은 그림인지는 여전히 `sha256`으로 가림 |
| `format`, `width_px`, `height_px`, `byte_size` | | `file`이 있으면 파일에서 읽어 채움(png·jpeg·bmp) |
| `kind` | | `photo` 사진 / `illustration` 삽화 / `table` 도표 / `graph` 그래프 / `screenshot` 화면 캡처 / `other` |
| `keywords` | | 주요 키워드 목록 |
| `upscaled` | | 업스케일본 `{file, format, width_px, height_px, engine}`. `file` 필수 |
| `placements` | | 수록 위치 목록(아래) |
| `links` | | 수행준거 연결 목록(아래) |
| `rights` | | 권리 정보(아래). 모르면 생략 |

### placements — 수록 위치

| 키 | 필수 | 내용 |
|---|---|---|
| `module_code` | ○ | 학습모듈 코드 `LM1203020201_24v3` |
| `module_name` | | 학습모듈명 |
| `label` | | 그림 번호 `그림 1-1`. 캡션 없는 그림은 생략 |
| `para_index` | | 문서 안 문단 순번(0부터). 캡션 없는 그림 여러 개를 구분하려면 필요 |
| `page` | | 쪽. hwpx만으로는 알 수 없어 출력본 PDF가 있을 때 채움 |
| `caption` | | 그림명 |
| `source_line`, `source_template` | | 원고에 적힌 출처 줄 그대로, 맞은 F14 출처 골격 이름 |
| `context_text` | | 그림 사용 문장(그림을 가리키는 본문 문장) |
| `lesson_no` | | 학습 번호 |
| `width_mm`, `height_mm` | | 쪽 위 출력 크기 |

같은 그림의 같은 자리는 (`module_code`, `label`, `para_index`)로 구분합니다.

### links — 수행준거 연결

| 키 | 필수 | 내용 |
|---|---|---|
| `unit_code` | ○ | 능력단위 코드 `1203020201_24v3` |
| `element_code` | | 능력단위요소 코드 `1203020201_24v3.1` |
| `criterion_no` | | 수행준거 번호 `1.1` |
| `placement` | | 이 연결이 나온 수록 위치의 순번(`placements`에서 0부터) |

### rights — 권리 정보

| 키 | 내용 |
|---|---|
| `category` | 분류 체계: `author_made` 집필자 직접제작 / `commissioned` 외부 제작의뢰 / `public_license` 공공누리·공유마당 / `blanket_license` 포괄적 이용허락 / `prior_module` 기개발 학습모듈 |
| `ownership` | 권리 귀속: `government` 정부(교육부) 귀속 / `licensed` 이용허락 한정 / `kogl` 공공누리 조건 |
| `reuse_scope` | 재사용 범위: `all` 전체 / `module_only` 해당 학습모듈 한정 / `unknown` 미확인(기본). 미확인은 추천에 나오지 않음 |
| `release_class` | 산출물 분류(REQ-04-006): `open` 공개 가능 / `inherit` 원 조건 승계 / `private` 비공개 |
| `license` | `{scheme, kogl_type, kogl_ai, cc, note}` (아래) |
| `conditions` | `{attribution, non_commercial, no_derivatives, share_alike}`. 공공누리·CC는 유형에서 정해지므로 **적지 않습니다**. 적었는데 유형과 다르면 거부 |
| `author`, `source_org`, `source_url`, `retrieved_on`, `credit_line` | 저작자, 원 출처 기관, URL, 확인 일자(`YYYY-MM-DD`), 출처 문구 |
| `ai` | `{used, usage, mode, tool, date, original_source, pledge_submitted, tos_scope}` (아래) |

**license**

| 키 | 내용 |
|---|---|
| `kogl_type` | 공공누리 유형 0~4. 적으면 `scheme`은 `kogl`, 이용조건은 자동 |
| `kogl_ai` | AI유형 병행 표시. 제1~4유형과만 가능. 이용조건은 함께 표시된 유형 그대로 |
| `cc` | CC 유형 `by` / `by-sa` / `by-nd` / `by-nc` / `by-nc-sa` / `by-nc-nd` / `cc0`. 적으면 `scheme`은 `cc`, 이용조건은 자동 |
| `scheme` | 유형이 없는 경우에만 적음: `expired` 보호기간 만료 / `donated` 기증 / `other` 기타 |
| `note` | 설명(만료·기증·기타일 때) |

| 공공누리 | 출처표시 | 상업적 이용금지 | 변경금지 |
|---|---|---|---|
| 제0유형 | | | |
| 제1유형 | ○ | | |
| 제2유형 | ○ | ○ | |
| 제3유형 | ○ | | ○ |
| 제4유형 | ○ | ○ | ○ |

**ai**

| 키 | 내용 |
|---|---|
| `usage` | AI 도구 사용 표기 예 번호: 1 집필진 작성 내용 기반 AI 생성 / 2 집필진 삽화 AI 수정 보완 / 3 기존 이미지 보정 / 4 AI 창작 / 5 원본 사진 AI 수정 |
| `mode` | `generated` 생성함 / `modified` 수정 보완함. `usage`를 적으면 자동(1·4는 생성함, 2·3·5는 수정 보완함) |
| `tool`, `date` | 활용 도구, 활용 일자 |
| `original_source` | 수정 보완한 원본의 출처 |
| `pledge_submitted` | 서약서 제출 여부 |
| `tos_scope` | 사용 AI 서비스 약관상 이용 범위 |
| `used` | 다른 AI 키가 있으면 true로 봄. AI를 쓰지 않았음을 명시하려면 `{"used": false}` |

`status`, `confirmed_by`, `confirmed_at`, `version`은 적을 수 없습니다. 적재되는 값은 모두 '자동 태깅'이고 기관 확정은 확정 화면에서 합니다.

## 다시 넣으면

같은 파일을 몇 번 넣어도 결과가 같습니다.

| 대상 | 이미 있을 때 |
|---|---|
| 그림 파일 | sha256이 같으면 같은 그림. 비어 있는 값만 채우고 있는 값은 덮지 않음. 키워드는 합침. 업스케일본은 없을 때만 넣음 |
| 수록 위치 | 새 자리는 추가. 있는 자리는 레코드가 적은 값으로 고침(추출기를 고쳐 다시 돌리면 캡션·출처 줄이 바로잡힘) |
| 권리 정보 | 자동 태깅 상태면 레코드가 적은 묶음만 고치고 버전을 올리며 변경 이력에 남김. **기관이 확정한 권리 정보는 건드리지 않고** 결과의 '확정 유지'에 표시 |
| 수행준거 연결 | 같은 연결은 한 번만 |

`license`와 `ai`는 묶음 단위로 바뀝니다. 예를 들어 `license`를 적으면 유형·조건 9개 열이 그 내용으로 통째로 바뀌고, 적지 않으면 그대로 둡니다.

## 거부되는 예

| 입력 | 사유 |
|---|---|
| `sha256`도 `file`도 없음 | sha256 또는 file이 필요합니다 |
| `"kind": "사진"` | 허용값이 아닙니다(코드로 적음) |
| `"license": {"kogl_type": 1}, "conditions": {"non_commercial": true}` | 상업적 이용금지가 라이선스 유형과 다릅니다 |
| `"license": {"kogl_type": 0, "kogl_ai": true}` | AI유형은 제1~4유형과만 함께 표시됩니다 |
| `"ownership": "kogl"`인데 `kogl_type` 없음 | 귀속이 공공누리 조건이면 kogl_type이 필요합니다 |
| `"ai": {"usage": 1, "mode": "modified"}` | usage 1은 '생성함'인데 mode가 '수정 보완함'입니다 |
| `"rights": {"status": "confirmed"}` | 기관 확정은 적재로 할 수 없습니다 |

## 화면

메뉴의 **이미지 저작권 DB**(`/images`)에서 같은 일을 합니다. 서버가 `DATABASE_URL` 없이 떠 있으면 안내만 나옵니다.

1. **변경한 사람**에 이름을 적습니다(적재·수정·확정의 변경 이력에 남음).
2. **자료 적재**: 레코드 JSON 1개와 그림 파일들을 함께 고르고 [형식만 검사] 또는 [적재]. 예시는 `docs/examples/image_records/`의 JSON 1개 + `images/`의 그림 3장.
3. **이미지 목록·확정**: 확정 상태·분류 체계·검색어로 거르고, [열기]로 그림·수록 위치·권리 정보·증빙·변경 이력을 봅니다. 권리 정보를 고쳐 [저장], 분류 체계와 권리 귀속이 있으면 [기관 확정].
   **증빙**은 같은 화면에서 직접 등록·삭제합니다(종류, 서류의 파일 이름이나 보관 위치, 제출일, 비고). 기관 확정 여부와 상관없이 됩니다.
   서류 파일 자체는 올리지 않습니다 — 서명된 동의서의 개인정보를 DB에 두지 않기 위해서입니다.
4. **추천용 조회**: 추천과 생성형 AI가 받게 될 목록. 확정 + 재사용 범위 확인 + 비공개 아님만 나옵니다.

## 조회·확정 API

서버를 `DATABASE_URL`과 함께 띄우면 붙습니다(`/api/health`의 `image_db`가 true). 자세한 입력은 서버의 `/docs`.

| API | 내용 |
|---|---|
| `GET /api/images/terms` | 허용값 코드 → 이름 |
| `POST /api/images/load` | 레코드 JSON 1개 + 그림 파일들을 올려 적재(`files`, `by`). `check_only=true`면 형식만 검사. 그림은 파일 이름으로 짝지음(합계 50MB까지) |
| `GET /api/images` | 관리용 목록 `{total, items}`. 거르기: `status`(`auto` / `confirmed` / `none` 권리 정보 없음), `category`, `license_scheme`, `kogl_type`, `reuse_scope`, `module_code`, `unit_code`, `keyword`, `kind`, `q`(제목·파일 이름·키워드·그림명·그림 사용 문장), `limit`·`offset` |
| `GET /api/images/{id}` | 그림 1건: 수록 위치, 권리 정보, 증빙, 수행준거 연결, 변경 이력 |
| `GET /api/images/{id}/file` | 그림 파일. `?upscaled=true`는 업스케일본 |
| `POST /api/images/{id}/rights` | 권리 정보 수정. `{"by": "이름", "version": 3, "rights": {…}}` — `rights`는 위 형식과 같고, 값을 `null`로 적으면 그 칸을 비움(`"license": null`은 라이선스 묶음 전체) |
| `POST /api/images/{id}/confirm` | 기관 확정 `{"by": "이름"}`. 분류 체계와 권리 귀속이 있어야 함 |
| `POST /api/images/{id}/unconfirm` | 확정 취소(값은 그대로, 자동 태깅 상태로) |
| `POST /api/images/{id}/evidence` | 증빙 1건 등록 `{"by": "이름", "kind": "license_consent", "file_ref": "붙임3.hwp", "submitted_on": "2026-10-20", "note": "…"}`. `kind`는 `transfer_consent` 양도 동의서 / `license_consent` 이용허락 동의서 / `portrait_consent` 초상권 동의서 / `ai_pledge` AI 서약서. 같은 종류·같은 파일이 이미 있으면 409 |
| `POST /api/images/{id}/evidence/{증빙 id}/delete` | 증빙 1건 삭제 `{"by": "이름"}`. 변경 이력에 남음 |
| `GET /api/images/recommendable` | 추천·생성형 AI용 목록. 기관 확정 + 재사용 범위 확인 + 비공개가 아닌 그림만. 항목마다 출처·라이선스 유형·이용조건이 함께 나가고, 이용허락 한정 자산은 `scope_check_needed`가 true |
| `GET /api/images/recommendable/{id}/file` | 추천 목록에 나오는 그림의 파일만 |

- `by`는 변경 이력에 남는 이름입니다(로그인이 없어 요청이 적어 보냅니다).
- `version`을 보내면 그 버전일 때만 바뀝니다. 그사이 다른 사람이 바꿨으면 409.
- 확정된 권리 정보는 수정할 수 없습니다(409). 확정을 푼 뒤 고치고 다시 확정합니다.
- 응답 코드: 없는 그림·증빙 404, 형식·필수 항목 오류 400(사유를 모두 담음), 확정된 것 수정·이미 확정·버전 불일치·같은 증빙 중복 409.

## DB 점검 (검증 기준)

정의서 REQ-02-010의 검증 기준 두 가지를 지금 DB에 든 것으로 셉니다.

```bash
set -a; source .env; set +a
python -m ncs_service.image_audit            # 글로. --json은 JSON으로. 추천 노출이 1건이라도 있으면 종료 코드 1
```

| 기준 | 세는 법 |
|---|---|
| 권리 정보 필수 항목 충족(99.5%) | 그림마다 그 그림에 해당하는 항목만 따져 채워진 항목 ÷ 따진 항목. 항목: 그림 파일, 권리 정보, 분류 체계, 권리 귀속, 재사용 범위, 라이선스 유형(공공누리·공유마당 자료), 이용조건, 원 출처 기관·URL·검색일과 출처 문구(공공누리), AI 활용 방식·도구·일자와 서약서(AI 활용 그림), 양도 동의서(직접제작·제작의뢰), 이용허락 동의서(포괄적 이용허락). **전체**와 **기관 확정분**을 따로 냅니다 — 자동 태깅 상태는 덜 채워진 것이 정상이고, 기준과 견줄 값은 기관 확정분입니다 |
| 재사용 범위 미확인 이미지의 추천 노출 0건 | 추천이 실제로 쓰는 세 길(뷰 `v_image_recommendable`, 추천용 목록, 추천 후보)에서 나온 그림을 원래 표와 다시 맞춰, 확정이 아니거나 재사용 범위가 미확인이거나 비공개인 것을 셉니다 |

적재할 때의 충족률(거부되지 않은 레코드 ÷ 전체)은 적재 보고서의 ‘필수 항목 충족률’이 따로 냅니다.

2026-11-17 측정(빈 PostgreSQL 16에 보유 자료를 넣음: 공공누리 수집 8건 + 원고 3권의 그림, 서류는 평가용으로 만든 것):

| 항목 | 결과 |
|---|---|
| 적재 | 공공누리 8건 중 8건, 원고 그림 레코드 88건 중 88건 — 거부 0건(적재 충족률 100%). 같은 파일은 합쳐져 그림 52개·수록 위치 88곳 |
| 추천 노출 | 52개를 모두 확정하되 16개는 재사용 범위를 미확인으로 둔 상태에서, 세 길 모두 36개만 나오고 나오면 안 되는 그림 0건 |
| 필수 항목(기관 확정분) | **아직 값이 없습니다.** 위 확정은 측정용으로 흉내 낸 것이라, 기관이 실제로 확정한 DB에서 이 명령을 돌려야 합니다 |

원고에서 그림 파일을 찾지 못해 건너뛴 그림이 7개 있었습니다(캡션 위 8문단 안에 그림 개체가 없는 경우).

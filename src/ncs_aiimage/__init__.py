"""이미지·도식 AI 생성 및 수정 보완(REQ-02-006) 가운데 표기와 현황 — AI를 쓴 그림에 표기 문구를 넣고, 생성형 AI 결과물 현황을 만든다.

검수 엔진이 아닌 기능 패키지다(ncs_plan·ncs_upscale과 같은 층, ncs_core만 import). 판정(O/X)을 내지 않는다.
  notice.py   ⑤ 프롬프트 유의 안내(화면에 그대로 보이는 글과 근거)
  marking.py  ③ 표기 문구 자동 삽입 — 원고(hwpx)의 그림 캡션 위에 'OO를 활용하여 생성함/수정 보완함. 일자' 줄을 넣은 사본.
              출처 줄이 없는 그림에 출처 줄을 넣는 일(REQ-02-011 출처 표기 자동 삽입)도 같은 방법이라 여기 둔다
  results.py  ④ 생성형 AI 결과물 현황(서약서 붙임 양식의 칸: 순번, 결과물 명, 학습모듈 해당 쪽수, 활용 AI, 비고)
  service.py  화면·명령행이 부르는 묶음(그림 읽기, 미리 보기, 표기 넣기, 현황 만들기)
AI로 그림을 만드는 일(①)과 내용을 고치는 일(②의 일부)은 여기 없다. 화질 보정은 ncs_upscale이 하고, 그 결과에 표기를 넣는 길만 잇는다.
"""

from .marking import Mark, insert_marks, insert_source_line, mark_pictures
from .notice import NOTICE
from .results import HEAD, build_xlsx, result_rows
from .service import inspect, marked_copy, preview, source_copy

__all__ = ["HEAD", "Mark", "NOTICE", "build_xlsx", "insert_marks", "insert_source_line", "inspect", "mark_pictures", "marked_copy", "preview", "result_rows",
           "source_copy"]

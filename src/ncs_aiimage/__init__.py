"""이미지·도식 AI 생성 및 수정 보완(REQ-02-006) 가운데 표기와 현황 — AI를 쓴 그림에 표기 문구를 넣고, 생성형 AI 결과물 현황을 만든다.

검수 엔진이 아닌 기능 패키지다(ncs_plan·ncs_upscale과 같은 층, ncs_core만 import). 판정(O/X)을 내지 않는다.
  notice.py   ⑤ 프롬프트 유의 안내(화면에 그대로 보이는 글과 근거)
  marking.py  ③ 표기 문구 자동 삽입 — 원고(hwpx)의 그림 캡션 위에 'OO를 활용하여 생성함/수정 보완함. 일자' 줄을 넣은 사본.
              출처 줄이 없는 그림에 출처 줄을 넣는 일(REQ-02-011 출처 표기 자동 삽입)도 같은 방법이라 여기 둔다
  results.py  ④ 생성형 AI 결과물 현황(서약서 붙임 양식의 칸: 순번, 결과물 명, 학습모듈 해당 쪽수, 활용 AI, 비고)
  service.py  화면·명령행이 부르는 묶음(그림 읽기, 미리 보기, 표기 넣기, 현황 만들기)
  diagram.py  ① AI 생성 가운데 도표·표·그래프의 명세 — 모양 검사(read_spec)와 근거 검사(grounding: 명세의 글이 집필자가 쓴 글에 있는 말인가)
  draw.py     명세를 PNG로 그린다(Pillow, 놓을 폭 기준 300 DPI, 회색 단계). 그리는 것은 코드다
  generate.py 집필자가 쓴 문단 → 생성형 AI(글)가 낸 명세 후보 → 검사를 통과한 것만 그릴 후보
사진·삽화를 만드는 일(①의 나머지)과 내용을 고치는 일(②의 일부)은 아직 없다. 화질 보정은 ncs_upscale이 하고, 그 결과에 표기를 넣는 길만 잇는다.
"""

from .diagram import Spec, SpecError, grounding, omissions, read_spec, table_html, table_tsv
from .draw import FontError, render
from .generate import propose
from .marking import Mark, insert_marks, insert_source_line, mark_pictures
from .notice import NOTICE
from .results import HEAD, build_xlsx, result_rows
from .service import inspect, marked_copy, preview, source_copy

__all__ = ["FontError", "HEAD", "Mark", "NOTICE", "Spec", "SpecError", "build_xlsx", "grounding", "insert_marks", "insert_source_line", "inspect",
           "mark_pictures", "marked_copy", "omissions", "preview", "propose", "read_spec", "render", "result_rows", "source_copy", "table_html", "table_tsv"]

"""F02 차례 ①: 학습명."""
import re
from ..common import O, X, TRI, NA, PUA, norm, same, visible, _verdict

def check_toc1(plan, toc):
    C = []
    n_plan = len(plan['학습명']) if plan else None
    if plan and n_plan != len(toc['학습']):
        C.append({'item_id': 'F02-차례-①', 'region_path': 'section0 > 차례', '원고': f"학습 {len(toc['학습'])}개", '개발계획서': f'학습 {n_plan}개',
                  '체크': {'학습 개수 일치': X}, '판정': '미반영', '비고': {'학습 개수 일치': '학습 누락 또는 추가'}, '수정 제안': None})
    for idx, L in enumerate(toc['학습']):
        txt, rp = L['text'], f"section0 > 차례 > 학습 {L['no']}"
        exp_name = plan['학습명'][idx] if plan and idx < n_plan else None
        exp_elem = plan['요소명'][idx] if plan and idx < len(plan['요소명']) else None
        ok_name = same(exp_name, txt) if exp_name else None
        ok_elem = same(exp_elem, txt) if exp_elem else None
        ws_only = ok_elem is False and re.sub(r'\s', '', norm(exp_elem)) == re.sub(r'\s', '', norm(txt))
        if ws_only: ok_elem = True
        checks = {"'~하기' 종결": O if re.search(r'하기$', txt) else X,
                  '개발계획서 학습명 일치': NA if ok_name is None else (O if ok_name else X),
                  '능력단위요소명 준용': NA if ok_elem is None else (O if ok_elem else TRI),
                  '기호 글꼴 문자 없음': X if PUA.search(txt) else O}
        notes = {}
        if checks["'~하기' 종결"] == X: notes["'~하기' 종결"] = "'~하기'로 종결되지 않음"
        if ok_name is False: notes['개발계획서 학습명 일치'] = f'개발계획서 학습명과 다름: "{exp_name}"'
        if ok_elem is False: notes['능력단위요소명 준용'] = f'능력단위요소명 "{exp_elem}" 과 글자가 다름 — 요소를 합치거나 이름을 바꿨는지 확인'
        if ws_only: notes['능력단위요소명 준용(참고)'] = f'능력단위요소명 "{exp_elem}" 과 공백만 다름 — 통과 처리'
        if PUA.search(txt): notes['기호 글꼴 문자 없음'] = '가운뎃점 등이 기호 글꼴(사용자 정의 영역) 문자 — ·(U+00B7)로 교체'
        if not plan: notes['개발계획서'] = '개발계획서를 읽지 못해 학습명·요소명 대조는 생략'
        v = _verdict(checks)
        C.append({'item_id': 'F02-차례-①', 'region_path': rp, '원고': visible(txt), '개발계획서': norm(exp_name) if exp_name else None,
                  '능력단위요소명': exp_elem, '체크': checks, '판정': v, '비고': notes,
                  '수정 제안': norm(exp_name) if (v != '반영' and exp_name) else None})
    return C


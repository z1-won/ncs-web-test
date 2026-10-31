"""F02 차례 ③: 개발계획서와 다섯 위치의 명칭 비교."""
from ..common import O, X, TRI, PUA, norm, same, visible, _diff_list, _pua_note, _verdict

def check_toc3(plan, toc, ov, body, eval_tbls=None):
    """자리(차례·개요·내비게이터·필요지식·평가)당 1건. 기준 = 개발계획서, 못 읽으면 차례(△)"""
    C = []
    use_plan_names = bool(plan and plan['학습명'])
    use_plan_subs = bool(plan and plan['내용명'])
    ref_names = [norm(x) for x in plan['학습명']] if use_plan_names else [L['text'] for L in toc['학습']]
    ref_subs = plan['내용명'] if use_plan_subs else toc['내용']
    ref_sub_texts = [s['text'] for s in ref_subs]
    toc_pua = {PUA.sub('·', t) for t in [L['text'] for L in toc['학습']] + [s['text'] for s in toc['내용']] if PUA.search(t)}
    base_note = {}
    if not use_plan_names: base_note['기준'] = '개발계획서 학습명을 읽지 못해 차례를 기준으로 비교 (△)'
    if not use_plan_subs: base_note['기준(내용명)'] = '개발계획서 학습 내용명을 읽지 못해 차례를 기준으로 비교 (△)'
    def item(place, act_names, act_subs, extra_checks=None, extra_notes=None, rp=None):
        checks, notes = {}, dict(base_note)
        if act_names is not None:
            v, n = _diff_list('학습명', ref_names, act_names); checks['학습명 일치'] = v
            if n: notes['학습명 일치'] = ' / '.join(n)
            if not use_plan_names and v == O and place != '차례': checks['학습명 일치'] = TRI; notes['학습명 일치'] = '차례와 일치 (개발계획서 미확인)'
        if act_subs is not None:
            v, n = _diff_list('학습 내용명', ref_sub_texts, act_subs); checks['학습 내용명 일치'] = v
            if n: notes['학습 내용명 일치'] = ' / '.join(n)
            if not use_plan_subs and v == O and place != '차례': checks['학습 내용명 일치'] = TRI; notes['학습 내용명 일치'] = '차례와 일치 (개발계획서 미확인)'
        pv, pn = _pua_note((act_names or []) + (act_subs or []), toc_pua)
        checks['기호 글꼴 문자 없음'] = pv
        if pn: notes['기호 글꼴 문자 없음'] = ' / '.join(pn)
        if extra_checks: checks.update(extra_checks)
        if extra_notes: notes.update(extra_notes)
        v = _verdict(checks)
        C.append({'item_id': 'F02-차례-③', 'region_path': rp or f'{place}', '자리': place,
                  '원고': {'학습명': [visible(x) for x in act_names] if act_names is not None else None,
                           '학습 내용명': [visible(x) for x in act_subs] if act_subs is not None else None},
                  '기준': {'학습명': ref_names, '학습 내용명': ref_sub_texts, '출처': ('개발계획서' if use_plan_names and use_plan_subs else '차례' if not use_plan_names and not use_plan_subs else '혼합'),
                           '학습명 출처': '개발계획서' if use_plan_names else '차례',
                           '학습 내용명 출처': '개발계획서' if use_plan_subs else '차례'},
                  '체크': checks, '판정': v, '비고': notes, '수정 제안': None if v == '반영' else '기준 값으로 통일'})
    # 1 차례 (개발계획서 기준일 때만 의미 있음; 차례 기준이면 자기 자신 → 차례는 PUA 만)
    if use_plan_names or use_plan_subs:
        item('차례', [L['text'] for L in toc['학습']] if use_plan_names else None, [s['text'] for s in toc['내용']] if use_plan_subs else None,
             rp='section0 > 차례')
    # 2 개요 내용체계
    if ov: item('학습모듈의 개요 > 내용체계', [L['text'] for L in ov['학습']], [s['text'] for s in ov['내용']], rp='section0 > 학습모듈의 개요 > 내용체계 표')
    else: C.append({'item_id': 'F02-차례-③', 'region_path': 'section0 > 학습모듈의 개요', '자리': '내용체계', '원고': None, '기준': None,
                    '체크': {'표 찾기': TRI}, '판정': '판단불가', '비고': {'표 찾기': "'학습모듈의 내용체계' 표를 찾지 못함"}, '수정 제안': None})
    # 3 내비게이터 (run 마다)
    if body['nav_runs']:
        ex_c, ex_n = {}, {}
        for r_i, run in enumerate(body['nav_runs'][1:], 2):
            v, n = _diff_list('학습명', ref_names, [x['text'] for x in run])
            if v == X: ex_c[f'내비게이터 {r_i}번째(학습 {r_i}) 일치'] = X; ex_n[f'내비게이터 {r_i}번째(학습 {r_i}) 일치'] = ' / '.join(n)
        if len(body['nav_runs']) != len(toc['학습']):
            ex_c['내비게이터 반복 횟수'] = TRI; ex_n['내비게이터 반복 횟수'] = f"내비게이터 묶음 {len(body['nav_runs'])}개 / 차례 학습 {len(toc['학습'])}개 — 학습 구간이 어긋났을 수 있음"
        item('내비게이터', [x['text'] for x in body['nav_runs'][0]], None, ex_c, ex_n,
             rp=f"section1 > 내비게이터 (학습마다 반복 {len(body['nav_runs'])}회)")
    else: C.append({'item_id': 'F02-차례-③', 'region_path': 'section1 > 내비게이터', '자리': '내비게이터', '원고': None, '기준': None,
                    '체크': {'내비게이터 찾기': TRI}, '판정': '판단불가', '비고': {'내비게이터 찾기': "'학습 1'…'학습 N' 제목 묶음을 찾지 못함"}, '수정 제안': None})
    # 4 필요지식 N-M. 제목 — 학습 구간 안의 것만, (no, sub) 순서로
    body_subs = sorted({(s['no'], s['sub']): s['text'] for L in body['lessons'] for s in L['subs']}.items())
    item('필요지식(본문) 학습 내용명', None, [t for _, t in body_subs], rp='section1 > 본문 N-M. 제목')
    # 5 평가 — 학습마다. 1순위: hwpx 표의 '학습 내용' 열(확정). 2순위: 블록 안 짧은 줄 휴리스틱(△)
    ex_c, ex_n, all_c = {}, {}, []
    by_table = bool(eval_tbls)
    for L in body['lessons']:
        exp = [s['text'] for s in ref_subs if s['no'] == L['no']]
        key = f"학습 {L['no']} 평가"
        if by_table:
            ra, rb = L['raw_span']
            tbls = [(k, vals) for pi, k, vals in eval_tbls if ra <= pi < rb]
            if not tbls:
                ex_c[key] = X; ex_n[key] = "학습 구간 안에 평가 준거·평가 방법 표('학습 내용' 열)를 찾지 못함"; continue
            probs = []
            for kind, vals in tbls:
                all_c += vals
                v, n = _diff_list(f'{kind} 학습 내용', exp, vals)
                if v == X: probs += n
            ex_c[key] = O if not probs else X
            if probs: ex_n[key] = ' / '.join(probs)
            kinds = {k for k, _ in tbls}
            missing_kind = [k for k in ('평가 준거', '평가 방법') if k not in kinds]
            if missing_kind:
                ex_c[key] = TRI if ex_c[key] == O else ex_c[key]
                ex_n[key] = (ex_n.get(key, '') + f" / {', '.join(missing_kind)} 표('학습 내용' 열)를 찾지 못함").strip(' /')
        else:
            if not L['eval']:
                ex_c[key] = X; ex_n[key] = "'평 가' 제목을 찾지 못함"; continue
            cands = L['eval_cands']; all_c += cands
            miss = [e for e in exp if not any(same(e, c) for c in cands)]
            strange = sorted({c for c in cands if not any(same(e, c) for e in exp)})
            if miss: ex_c[key] = X; ex_n[key] = '평가 표에 없는 학습 내용명: ' + ', '.join(f'"{m}"' for m in miss)
            elif strange: ex_c[key] = TRI; ex_n[key] = '기준에 없는 짧은 줄(학습 내용명일 수 있음): ' + ', '.join(f'"{visible(x)}"' for x in strange[:5])
            else: ex_c[key] = TRI; ex_n[key] = '표를 못 읽어 문단 휴리스틱으로 확인 (hwpx 권장)'
    if not body['lessons']:
        ex_c['평가 구간 찾기'] = TRI
        ex_n['평가 구간 찾기'] = '학습 구간을 읽지 못해 평가 표 대조를 수행하지 못함'
    if not use_plan_subs:
        ex_c['개발계획서 기준 확인'] = TRI
        ex_n['개발계획서 기준 확인'] = '개발계획서 학습 내용명을 읽지 못해 차례를 기준으로 비교'
    pv, pn = _pua_note(all_c, toc_pua)
    checks = dict(ex_c); checks['기호 글꼴 문자 없음'] = pv
    notes = dict(base_note); notes.update(ex_n)
    if pn: notes['기호 글꼴 문자 없음'] = ' / '.join(pn)
    v = _verdict(checks)
    C.append({'item_id': 'F02-차례-③', 'region_path': 'section1 > 평가 (평가 준거·평가 방법 표)', '자리': '평가',
              '원고': {'평가 표 학습 내용' if by_table else '학습 내용명 후보': sorted(set(all_c)), '읽기': '표 셀' if by_table else '문단 휴리스틱'}, '기준': {'학습 내용명': ref_sub_texts, '출처': '개발계획서' if use_plan_subs else '차례'},
              '체크': checks, '판정': v, '비고': notes, '수정 제안': None if v == '반영' else '평가 준거·평가 방법 표의 학습 내용명을 기준 값으로 통일'})
    return C


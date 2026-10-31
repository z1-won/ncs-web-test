"""F02 차례 ⑤·⑥: 참고 자료와 활용 서식·부록."""
from ..common import O, X, TRI, _verdict

def check_toc5(presence, toc):
    p = presence['참고 자료']
    in_toc = '참고 자료' in toc['꼬리']
    checks = {'⑤ 참고 자료 본문 존재': O if p['있음'] else X, '차례에 참고 자료 줄': O if in_toc else X}
    notes = {'근거': p['근거']}
    if not in_toc: notes['차례에 참고 자료 줄'] = '차례에 "참고 자료" 줄이 없음'
    if not p['있음']: notes['⑤ 참고 자료 본문 존재'] = '본문에서 참고 자료를 찾지 못함 (필수 작성)'
    v = _verdict(checks)
    return [{'item_id': 'F02-차례-⑤', 'region_path': 'section1 > 참고 자료', '원고': p['근거'], '차례': toc['꼬리'].get('참고 자료'),
             '체크': checks, '판정': v, '비고': notes, '수정 제안': None if v == '반영' else '참고 자료를 작성하고 차례에 쪽수와 함께 제시'}]


def check_toc6(presence, toc):
    C = []
    for name in ('활용 서식', '부록'):
        p, in_toc = presence[name], name in toc['꼬리']
        if p['있음'] is None: val, note = TRI, f'본문: {p["근거"]}' + (f' / 차례에는 {name} {toc["꼬리"][name] or ""}' if in_toc else ' / 차례에는 없음')
        elif in_toc and p['있음']: val, note = O, f'차례·본문 모두 있음 — {p["근거"]}'
        elif in_toc and not p['있음']: val, note = X, f'차례에는 "{name} {toc["꼬리"][name] or ""}" 이 있는데 본문에 없음 — 미작성이면 차례에서 삭제'
        elif not in_toc and p['있음']: val, note = X, f'본문에 {name} 이 있는데({p["근거"]}) 차례에 없음 — 차례에 추가'
        else: val, note = O, '차례·본문 모두 없음 (해당 없음)'
        checks = {f'⑥ {name} 차례↔본문 일치': val}
        v = _verdict(checks)
        C.append({'item_id': 'F02-차례-⑥', 'region_path': f'section0 > 차례 > {name}', '원고': {'차례': toc['꼬리'].get(name) if in_toc else None, '본문': p['있음']},
                  '체크': checks, '판정': v, '비고': {f'⑥ {name} 차례↔본문 일치': note} if val != O or '해당 없음' in note else {},
                  '수정 제안': None if val == O else ('차례에서 삭제' if in_toc and p['있음'] is False else '차례에 추가' if p['있음'] and not in_toc else '본문 확인 후 차례와 맞출 것')})
    return C


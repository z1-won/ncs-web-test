"""참고 자료·활용 서식·부록의 존재 근거 추출."""
import re
from .patterns import REF_LINE
from .config import DEFAULT_CONFIG

def section_presence(sections, banners, config=DEFAULT_CONFIG):
    """참고 자료 / 활용 서식 / 부록 이 본문에 있는가 → {이름: {'있음': bool|None, '근거': str, 'k': 위치}}"""
    raw = sections[1] if len(sections) > 1 else []
    ne = [(i, l) for i, l in enumerate(raw) if l]
    KEYS = {'참고 자료': r'참\s*고\s*자\s*료', '활용 서식': r'활\s*용\s*서\s*식', '부록': r'부\s*록'}
    out = {}
    for name, pat in KEYS.items():
        res = {'있음': False, '근거': '제목 텍스트·배너 이미지·내용 패턴 어느 것도 없음', 'k': None}
        # 1) 제목 텍스트
        hit = next(((i, l) for i, l in ne if re.fullmatch(pat, l)), None)
        if hit: res = {'있음': True, '근거': f'제목 텍스트 "{hit[1]}" (section1 p{hit[0]})', 'k': hit[0]}
        else:
            # 2) 배너 이미지 (section1)
            b = next(((pi, nm) for si, pi, nm in banners if si == 1 and re.search(pat.replace(r'\s*', ''), nm.replace(' ', ''))), None)
            if b: res = {'있음': True, '근거': f'배너 이미지 "{b[1]}" (section1 p{b[0]})', 'k': b[0]}
        out[name] = res
    # 제목·배너 뒤에 내용이 없으면(개발이력 전까지 문단 3개 미만) '배너만' → △
    for name in ('활용 서식', '부록'):
        r = out[name]
        if r['있음']:
            stop = next((i for i, l in ne if i > r['k'] and (re.search(r'개발\s*이력', l) or any(re.fullmatch(KEYS[o], l) for o in KEYS if o != name))), len(raw))
            body_n = len([l for i, l in ne if r['k'] < i < stop and not re.match(r'^※', l)])
            if body_n < config.tail_min_paragraphs:
                out[name] = {'있음': None, '근거': f'{r["근거"]} 뒤에 내용이 없음(문단 {body_n}개) — 양식 배너만 남은 것인지 확인', 'k': r['k']}
    # 3) 내용 패턴 — 참고 자료: 참고문헌 꼴 줄 3개 이상 연속
    if not out['참고 자료']['있음']:
        run, best = [], []
        for i, l in ne:
            if REF_LINE.match(l): run.append(i)
            else:
                if len(run) > len(best): best = run
                run = []
        if len(run) > len(best): best = run
        if len(best) >= config.reference_min_lines:
            out['참고 자료'] = {'있음': True, '근거': f'참고문헌 꼴 줄 {len(best)}개 연속 (section1 p{best[0]}~p{best[-1]}) — 제목은 텍스트가 아님(이미지일 가능성)', 'k': best[0]}
            out['참고 자료']['end'] = best[-1]
    # 활용 서식: 참고 자료 뒤 ~ 개발이력 앞에 내용이 있으면 '있을 가능성'
    if not out['활용 서식']['있음'] and out['참고 자료']['있음']:
        start = out['참고 자료'].get('end', out['참고 자료']['k'])
        stop = next((i for i, l in ne if i > start and re.search(r'개발\s*이력', l)), len(raw))
        mid = [l for i, l in ne if start < i < stop and not REF_LINE.match(l) and not re.match(r'^※', l)]
        if len(mid) >= config.ambiguous_tail_min_paragraphs:
            out['활용 서식'] = {'있음': None, '근거': f'제목은 없지만 참고 자료 뒤~개발이력 앞에 문단 {len(mid)}개 있음 (예: "{mid[0][:30]}") — 활용 서식 또는 부록 내용으로 보임(제목이 이미지라 둘을 구분 못 함), 확인 필요', 'k': start + 1}
    return out


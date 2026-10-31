"""문단에서 차례, 개요, 내비게이터, 개발계획서를 추출한다."""
import re
from .patterns import (TOC_LESSON, TOC_SUB, TOC_LINE, TOC_TAIL, OV_LESSON, OV_SUB, NAV_HEAD, BODY_SUB, HEAD_TEACH, HEAD_EVAL, EVAL_LABELS, EVAL_ITEM_END)
from .config import DEFAULT_CONFIG

def parse_toc(sections):
    """section0 의 차례 블록 → {'학습': [{'no','text'}], '내용': [{'no','sub','text','page'}], '줄': [...], '꼬리': {참고 자료: 쪽, ...}, 'span': (s,e)}"""
    lines = [l for l in sections[0] if l] if sections else []
    s = next((i for i, l in enumerate(lines) if re.fullmatch(r'차\s*례', l)), None)
    if s is None: return None
    e = next((i for i in range(s + 1, len(lines)) if re.search(r'학습모듈의\s*개요$', lines[i]) and not re.search(r'\d+$', lines[i])), len(lines))
    toc = {'학습': [], '내용': [], '줄': [], '꼬리': {}, 'span': (s, e)}
    for i in range(s + 1, e):
        l = lines[i]
        if (m := TOC_LESSON.match(l)) and int(m.group(1)) == len(toc['학습']) + 1:
            toc['학습'].append({'no': int(m.group(1)), 'text': m.group(2).strip()}); continue
        if (m := TOC_SUB.match(l)):
            toc['내용'].append({'no': int(m.group(1)), 'sub': int(m.group(2)), 'text': m.group(3).strip(), 'page': m.group(4)}); continue
        if (m := TOC_LINE.match(l)):
            toc['줄'].append({'lesson': len(toc['학습']), 'kind': '교수·학습 방법' if '교수' in m.group(1) else '평가', 'page': m.group(2)}); continue
        if (m := TOC_TAIL.match(l)):
            toc['꼬리'][{'참고자료': '참고 자료', '활용서식': '활용 서식', '부록': '부록'}[re.sub(r'\s+', '', m.group(1))]] = m.group(2)
    return toc


def parse_overview(sections):
    lines = [l for l in sections[0] if l] if sections else []
    s = next((i for i, l in enumerate(lines) if re.fullmatch(r'학습모듈의\s*내용\s*체계', l)), None)
    if s is None: return None
    e = next((i for i in range(s + 1, len(lines)) if re.fullmatch(r'핵심\s*용어', lines[i])), len(lines))
    ov = {'학습': [], '내용': []}
    for l in lines[s + 1:e]:
        if (m := OV_SUB.match(l)): ov['내용'].append({'no': int(m.group(1)), 'sub': int(m.group(2)), 'text': m.group(3).strip()})
        elif (m := OV_LESSON.match(l)) and int(m.group(1)) == len(ov['학습']) + 1: ov['학습'].append({'no': int(m.group(1)), 'text': m.group(2).strip()})
    return ov


def parse_body(sections, n_lessons, cutoff=None, config=DEFAULT_CONFIG):
    """cutoff: 참고 자료 시작 인덱스(raw) — 마지막 학습 구간을 여기서 끊음"""
    """내비게이터 run / 학습 구간 / 필요지식 N-M. 제목 / 각 학습의 평가 블록 후보 줄 / 교수·평가 제목 위치"""
    raw = sections[1] if len(sections) > 1 else []
    lines = [(i, l) for i, l in enumerate(raw) if l]              # (원래 인덱스, 텍스트)
    # 내비게이터: '학습 1' 다음 줄이 이름, 이어서 '학습 2' … 가 run
    nav_runs = []
    k = 0
    while k < len(lines):
        if NAV_HEAD.match(lines[k][1]) and int(NAV_HEAD.match(lines[k][1]).group(1)) == 1:
            run, no, j = [], 1, k
            while j + 1 < len(lines) and NAV_HEAD.match(lines[j][1]) and int(NAV_HEAD.match(lines[j][1]).group(1)) == no:
                run.append({'no': no, 'text': lines[j + 1][1], 'k': j}); no += 1; j += 2
            if len(run) >= (1 if n_lessons == 1 else 2):                                   # 개수 차이는 ③ 내비게이터 항목의 비고로
                nav_runs.append(run); k = j; continue
        k += 1
    # 학습 구간: run 시작 ~ 다음 run 시작
    starts = [r[0]['k'] for r in nav_runs]
    last = next((k for k, (i, l) in enumerate(lines) if cutoff is not None and i >= cutoff), len(lines))
    spans = [(i + 1, starts[i], starts[i + 1] if i + 1 < len(starts) else last) for i in range(len(starts))]
    # 필요지식 N-M. 제목 (같은 줄 또는 다음 줄)
    subs = []
    for k, (i, l) in enumerate(lines):
        if (m := BODY_SUB.match(l)) and len(l) < config.body_heading_max_length:
            text = m.group(3).strip() or (lines[k + 1][1] if k + 1 < len(lines) else '')
            if not re.search(r'\s\d+$', l):                       # 차례 줄(끝 쪽수) 제외
                subs.append({'no': int(m.group(1)), 'sub': int(m.group(2)), 'text': text, 'k': k})
    # 학습별 교수·학습 방법 / 평가 제목 위치, 평가 블록의 '학습 내용' 후보 줄
    lessons = []
    for no, a, b in spans:
        seg = lines[a:b]
        teach = [a + j for j, (i, l) in enumerate(seg) if HEAD_TEACH.match(l)]
        evals = [a + j for j, (i, l) in enumerate(seg) if HEAD_EVAL.match(l)]
        cand = []
        if evals:
            for i, l in lines[evals[0]:b]:
                if (len(l) <= config.eval_candidate_max_length and not re.match(r'^[-•·※\d(\[]', l) and l not in EVAL_LABELS
                        and not NAV_HEAD.match(l) and not HEAD_EVAL.match(l) and not re.search(r'[.?!]$', l)
                        and not EVAL_ITEM_END.search(l)):
                    cand.append(l)
        own_subs = [s for s in subs if a <= s['k'] < b and s['no'] == no]
        raw_span = (lines[a][0], lines[b][0] if b < len(lines) else (lines[-1][0] + 1 if lines else 0))
        lessons.append({'no': no, 'span': (a, b), 'raw_span': raw_span, 'teach': teach, 'eval': evals, 'eval_cands': cand, 'subs': own_subs})
    return {'lines': lines, 'nav_runs': nav_runs, 'spans': spans, 'subs': subs, 'lessons': lessons}


def parse_plan_toc(sections, module_code):
    """개발계획서 → {'학습명': [...], '요소명': [...], '내용명': [{'no','sub','text'}]} (블록을 못 찾으면 None)"""
    lines = [l for sec in sections for l in sec]
    code = module_code.replace('LM', '')
    start = next((i for i, l in enumerate(lines) if l == code and i > 0 and lines[i-1].startswith('능력단위 코드번호')), None)
    if start is None: return None
    end = next((i for i in range(start, len(lines)) if lines[i].startswith('NCS (수정 금지)')), len(lines))
    block = lines[start:end]
    plan = {'학습명': [], '요소명': [], '내용명': []}
    for i, l in enumerate(block):
        if re.fullmatch(rf'{re.escape(code)}\.\d+', l) and i + 1 < len(block): plan['요소명'].append(block[i + 1])
        if (m := OV_SUB.match(l)): plan['내용명'].append({'no': int(m.group(1)), 'sub': int(m.group(2)), 'text': m.group(3).strip()})
        elif re.fullmatch(r'\d+\.\s+\S.*', l): plan['학습명'].append(l)
    return plan


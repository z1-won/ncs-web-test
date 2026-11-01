"""F02 필요지식-⑦ 그림·표 번호 연속성 검사 .

check_figtab(sections, lesson_spans) -> 체크리스트 행 목록(행 = 그림/표 × 학습 묶음, 본문 참조, 괄호 없는 번호).
기준
  - 학습 N 안의 그림은 [그림 N-1], [그림 N-2] … 순서대로, 표는 〈표 N-1〉, 〈표 N-2〉 … 순서대로
  - 괄호: 그림은 [ ], 표는 〈 〉
  - 본문에서 참조한 번호([그림 2-3]과 같이 …)는 실제 캡션이 있어야 함
"""
import re

from ncs_core import NA, O, PUA, TRI as UNDECIDED_MARK, X, visible

ITEM = 'F02-필요지식-⑦'

_FW = str.maketrans('０１２３４５６７８９－', '0123456789-')          # 전각 숫자·대시 → 반각
_DASH = r'[-–—－‐]'
LABEL = re.compile(rf'([\[〔\(（〈〈<＜《])\s*(그림|표)\s*(\d+)\s*{_DASH}\s*(\d+)\s*([\]〕\)）〉〉>＞》])')
BARE  = re.compile(rf'(그림|표)\s*(\d+)\s*{_DASH}\s*(\d+)')                # 괄호 없이 나온 번호(기호글꼴 괄호 의심)
CORRECT = {'그림': ('[', ']'), '표': ('〈', '〉')}
_OK_BRACKETS = {'그림': {('[', ']')}, '표': {('〈', '〉'), ('〈', '〉')}}  # U+3008/3009, U+2329/232A 둘 다 허용

# 학습 제목줄: "학습 1" / "학습 1. 제목" / "학습 1. 제목 12"(차례) / "학습 1 ○○하기"
HEAD = re.compile(r'^학습\s*(\d+)(?:\s*\.\s*(.*?)|\s*(\S.*?하기))?(?:\s+\d+)?$')
# 마지막 학습의 끝(참고자료 등)으로 볼 줄
TAIL = re.compile(r'^(교수\s*[·ㆍ]?\s*학습\s*)?참고\s*(자료|문헌)$|^활용\s*서식$|^부록$')

SENTENCE_END = re.compile(r'(다|요|라|오|죠|까)\s*[.。?]\s*$')
# 라벨 바로 뒤(띄어쓰기 없이) 조사가 붙으면 참조: "[그림 2-9]를", "〈표 1-1〉과 같이"
JOSA_AFTER = re.compile(r'^(은|는|이|가|을|를|과|와|의|에|로|처럼|같이|에서|부터|까지|도|만)(\s|$)')


def _flatten(sections, exclude=None):
    """(섹션, 문단, 텍스트) 평탄화. exclude: 뺄 (섹션, 문단) 집합 — 메모·머리말 등 본문 밖 문단."""
    exclude = exclude or set()
    return [(s, i, t) for s, sec in enumerate(sections) for i, t in enumerate(sec) if t and (s, i) not in exclude]


def split_lessons(flat, caps=None):
    """학습 제목줄로 본문을 학습별 구간으로 나눔. 반환 ([(학습번호, start, end)], 일치율)
    차례(section0)에도 '학습 1. …' 줄이 있으므로 1부터 연속하는 제목줄 묶음(run)이 여럿 나온다.
    caps가 있으면 '캡션의 앞 번호 == 그 캡션이 속한 학습 번호'인 비율이 가장 높은 run을 고르고(동률이면 넓은 것),
    없으면 가장 넓게 펼쳐진 run을 고른다. 일치율은 호출자가 경계 신뢰도 판단에 쓴다."""
    runs, cur = [], []
    for k, (s, i, t) in enumerate(flat):
        m = HEAD.match(t)
        if not m: continue
        no = int(m.group(1))
        if cur and no == cur[-1][1]: continue             # 같은 번호 반복(표지 '학습 1' + '학습 1. 제목') 무시
        if no == 1:
            if cur: runs.append(cur)
            cur = [(k, no)]
        elif cur and no == cur[-1][1] + 1:
            cur.append((k, no))
    if cur: runs.append(cur)
    if not runs: return [], 0.0

    def spans_of(run):
        out = []
        for j, (k, no) in enumerate(run):
            end = run[j + 1][0] if j + 1 < len(run) else \
                  next((kk for kk in range(k + 1, len(flat)) if TAIL.match(flat[kk][2])), len(flat))
            out.append((no, k, end))
        return out

    def agreement(spans):
        if not caps: return None
        hit = sum(1 for c in caps if any(a <= c['k'] < b and c['major'] == no for no, a, b in spans))
        return hit / len(caps)

    cands = [(spans_of(r), r) for r in runs]
    if caps:
        best = max(cands, key=lambda sr: (agreement(sr[0]), sr[1][-1][0] - sr[1][0][0], sr[1][0][0]))
    else:
        best = max(cands, key=lambda sr: (sr[1][-1][0] - sr[1][0][0], sr[1][0][0]))
    spans = best[0]
    return spans, (agreement(spans) if caps else 1.0)


def _fmt(kind, major, minor):
    o, c = CORRECT[kind]
    return f'{o}{kind} {major}-{minor}{c}'


def collect_labels(flat):
    """캡션(문단 첫머리의 라벨)과 참조(문장 중간의 라벨)를 나눠 모음."""
    caps, refs, bare = [], [], []
    for k, (s, i, t) in enumerate(flat):
        tt = t.translate(_FW)
        covered = []
        for j, m in enumerate(LABEL.finditer(tt)):
            covered.append(m.span())
            tail = tt[m.end():]
            rest = tail.strip()
            d = dict(kind=m.group(2), major=int(m.group(3)), minor=int(m.group(4)),
                     open=m.group(1), close=m.group(5), label=m.group(0), k=k, sec=s, para=i, text=t)
            # 캡션 판정: 문단이 라벨로 시작 + 라벨에 조사가 붙지 않음 + 뒤가 짧은 제목(문장으로 끝나지 않음)
            is_cap = (j == 0 and m.start() == 0 and len(rest) <= 80
                      and not JOSA_AFTER.match(tail) and not SENTENCE_END.search(rest))
            (caps if is_cap else refs).append(d)
        for m in BARE.finditer(tt):
            if not any(a <= m.start() < b for a, b in covered):
                bare.append(dict(kind=m.group(1), major=int(m.group(2)), minor=int(m.group(3)),
                                 label=m.group(0), k=k, sec=s, para=i, text=t))
    return caps, refs, bare


MIN_AGREEMENT = 0.5     # 캡션 앞 번호와 학습 경계가 이 비율 미만으로 맞으면 '놓인 학습' 검사를 하지 않음
SHOW = 3                # 비고에 적는 대표 라벨 수


def _title(c):
    """라벨을 뺀 캡션 글(그림명). 공백은 로더가 이미 한 칸으로 줄였으므로 그대로 비교"""
    t = c['text'].translate(_FW)
    return t[len(c['label']):].strip() if t.startswith(c['label']) else t.strip()


def _row(no_suffix, region, where, source, checks, notes, suggestion, details):
    from ncs_core import PASS, verdict
    result = verdict(checks)
    return {'item_id': ITEM, 'region_path': region, '위치': where, '원고': source, '체크': checks, '판정': result,
            '비고': notes, '수정 제안': None if result == PASS else suggestion, '상세': details}


def _few(labels):
    return ', '.join(labels[:SHOW]) + (' …' if len(labels) > SHOW else '')


def sequence_problems(group):
    """한 학습·한 종류의 캡션 묶음(문서 순서) → {'재사용': [...], '중복 삽입': [...], '누락': [...], '역행': [...]} (라벨 목록).

    번호 재사용: 같은 번호가 다른 그림명으로 다시 나옴. 중복 삽입: 같은 번호·같은 그림명(같은 그림을 두 번 넣음).
    누락: 1..최대 사이에 없는 번호. 역행: 앞서 나온 가장 큰 번호보다 작은 번호가 뒤에 나옴(재사용·중복 제외).
    """
    out = {'재사용': [], '중복 삽입': [], '누락': [], '역행': []}
    seen, high = {}, 0
    for c in group:
        m = c['minor']
        if m in seen:
            (out['중복 삽입'] if _title(seen[m]) == _title(c) else out['재사용']).append(c['label'])
            continue
        seen[m] = c
        if m < high:
            out['역행'].append(c['label'])
        high = max(high, m)
    kind, major = group[0]['kind'], group[0]['major']
    out['누락'] = [_fmt(kind, major, m) for m in range(1, high + 1) if m not in seen]
    return out


def check_figtab(sections, lesson_spans=None, *, min_agreement=MIN_AGREEMENT, labels=None):
    """⑦ 행 목록. 행 = (그림/표) × 학습 묶음 + 본문 참조 1~2행 + 괄호 없는 번호 1행.

    학습 묶음은 캡션이 '놓인 학습'(lesson_spans)으로 나누고, 학습 경계를 믿을 수 없으면 캡션의 앞 번호로 나눈다.
    앞 번호(학습 번호)는 연속일 필요가 없다 — 표가 없는 학습은 건너뛴다(〈표 1-1〉 다음 〈표 4-1〉 정상).
    """
    if labels is None:
        flat = _flatten(sections)
        caps, refs, bare = collect_labels(flat)
    else:
        flat, caps, refs, bare = labels["flat"], labels["caps"], labels["refs"], labels["bare"]
    rows = []
    if not caps and not refs and not bare:
        # 그림·표가 전혀 없는 원고: 검사할 것이 없음을 적합(해당 없음)으로 남긴다 — '규칙 미구현'과 구분
        return [_row('', 'section1', '', {'개수': 0}, {'그림·표 캡션': NA}, {'그림·표 캡션': '원고에 그림·표 캡션이 없어 검사할 것이 없음'}, None, [])]
    spans, agree = (lesson_spans, 1.0) if lesson_spans else split_lessons(flat, caps)
    reliable = bool(spans) and agree >= min_agreement
    lesson_of = (lambda k: next((no for no, a, b in spans if a <= k < b), None)) if reliable else (lambda k: None)

    for kind in ('그림', '표'):
        cs = [c for c in caps if c['kind'] == kind]
        if not cs:
            continue
        groups = {}
        for c in cs:
            groups.setdefault(lesson_of(c['k']) or c['major'], []).append(c)
        for lesson, group in sorted(groups.items()):
            checks, notes, details = {}, {}, []
            own = [c for c in group if c['major'] == lesson]
            misplaced = [c for c in group if c['major'] != lesson]
            if reliable:
                checks['놓인 학습 일치'] = X if misplaced else O
                if misplaced:
                    notes['놓인 학습 일치'] = f'{len(misplaced)}개가 학습 {lesson} 본문에 있는데 앞 번호가 다름: {_few([c["label"] for c in misplaced])}'
                    details += [{'문단': c['para'], '라벨': c['label'], '캡션': visible(c['text']), '문제': f'학습 {lesson}에 놓였는데 앞 번호 {c["major"]}'} for c in misplaced]
            problems = sequence_problems(own) if own else {}
            bad = {k: v for k, v in problems.items() if v}
            checks['번호 연속'] = X if bad else O
            if bad:
                notes['번호 연속'] = f'{kind} {lesson}-x {len(own)}개 중 ' + ' · '.join(f'{k} {len(v)}({_few(v)})' for k, v in bad.items())
                for k, v in bad.items():
                    for label in v:
                        c = next((c for c in own if c['label'] == label), None)
                        details.append({'문단': c['para'] if c else None, '라벨': label, '캡션': visible(c['text']) if c else None, '문제': k})
            wrong = [c for c in group if (c['open'], c['close']) not in _OK_BRACKETS[kind]]
            checks['괄호 표기'] = X if wrong else O
            if wrong:
                notes['괄호 표기'] = f'{len(wrong)}개가 {CORRECT[kind][0]} {CORRECT[kind][1]} 가 아님: {_few([c["label"] for c in wrong])}'
                details += [{'문단': c['para'], '라벨': c['label'], '캡션': visible(c['text']), '문제': f'괄호 {c["open"]} {c["close"]}'} for c in wrong]
            pua = [c for c in group if PUA.search(c['text'] or '')]
            if pua:
                checks['기호 글꼴 문자'] = X
                notes['기호 글꼴 문자'] = f'{len(pua)}개 캡션에 사용자 정의 영역 문자(다른 환경에서 깨짐): {_few([c["label"] for c in pua])}'
                details += [{'문단': c['para'], '라벨': c['label'], '캡션': visible(c['text']), '문제': '기호 글꼴 문자'} for c in pua]
            advice = []
            if misplaced or bad:
                advice.append(f'{kind} 번호는 놓인 학습 번호-1 부터 나오는 순서대로 다시 매김' + (' (같은 그림은 하나만 남김)' if problems.get('중복 삽입') else ''))
            if wrong:
                advice.append(f'{kind} 번호는 {CORRECT[kind][0]} {CORRECT[kind][1]} 로 묶음')
            if pua:
                advice.append('캡션의 기호 글꼴 문자를 일반 문자(가운뎃점 등)로 바꿈')
            rows.append(_row('', f'section1 > 학습 {lesson} > {kind}', f'학습 {lesson}',
                             {'개수': len(group), '번호': [c['label'] for c in group]}, checks, notes, ' / '.join(advice) or None, details))
    if caps and not reliable:
        rows.append(_row('', 'section1', '', None, {'놓인 학습 일치': UNDECIDED_MARK}, {
            '놓인 학습 일치': f'학습 경계를 믿을 만하게 잡지 못해(캡션-경계 일치율 {agree:.0%}) 캡션이 놓인 학습과 앞 번호를 대조하지 못함'}, None, []))

    # 본문 참조: 가리키는 캡션이 있는가, 괄호가 맞는가 — 종류별 1행
    cap_keys = {(c['kind'], c['major'], c['minor']) for c in caps}
    for kind in ('그림', '표'):
        rs = [r for r in refs if r['kind'] == kind]
        if not rs:
            continue
        missing = [r for r in rs if (r['kind'], r['major'], r['minor']) not in cap_keys]
        wrong = [r for r in rs if (r['open'], r['close']) not in _OK_BRACKETS[kind]]
        checks = {'참조 대상 캡션 존재': X if missing else O, '참조 괄호 표기': X if wrong else O}
        notes = {}
        if missing:
            notes['참조 대상 캡션 존재'] = f'본문 참조 {len(rs)}개 중 {len(missing)}개는 캡션이 없음: {_few([r["label"] for r in missing])}'
        if wrong:
            notes['참조 괄호 표기'] = f'{len(wrong)}개가 {CORRECT[kind][0]} {CORRECT[kind][1]} 가 아님: {_few([r["label"] for r in wrong])}'
        details = [{'문단': r['para'], '라벨': r['label'], '문장': visible(r['text']), '문제': '캡션 없음'} for r in missing] + \
                  [{'문단': r['para'], '라벨': r['label'], '문장': visible(r['text']), '문제': f'괄호 {r["open"]} {r["close"]}'} for r in wrong]
        rows.append(_row('', f'section1 > 본문 {kind} 참조', '', {'참조 수': len(rs)}, checks, notes,
                         f'{kind} 번호를 바꾼 뒤 본문 참조도 함께 고치고 {CORRECT[kind][0]} {CORRECT[kind][1]} 로 묶음', details))
    if bare:
        rows.append(_row('', 'section1 > 본문', '', {'개수': len(bare)}, {'괄호 없는 번호': UNDECIDED_MARK},
                         {'괄호 없는 번호': f'{len(bare)}개가 괄호 없이 나옴(기호 글꼴 괄호이거나 빠진 것, 원고 확인): {_few([x["label"] for x in bare])}'},
                         '그림은 [ ], 표는 〈 〉 로 묶음', [{'문단': x['para'], '라벨': x['label'], '문장': visible(x['text'])} for x in bare]))
    return rows

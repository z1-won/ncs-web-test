"""F02 필요지식-⑦ 그림·표 번호 연속성 검사 (figtab v1.4 논리 그대로, ncs_core 어휘로 옮김).

check_figtab(sections, lesson_spans) -> findings: item_id / region_path / verdict / evidence_quote / reason / suggestion
기준
  - 학습 N 안의 그림은 [그림 N-1], [그림 N-2] … 순서대로, 표는 〈표 N-1〉, 〈표 N-2〉 … 순서대로
  - 괄호: 그림은 [ ], 표는 〈 〉
  - 본문에서 참조한 번호([그림 2-3]과 같이 …)는 실제 캡션이 있어야 함
"""
import re

from ncs_core import FAIL, PASS, PUA, UNDECIDED, visible

ITEM = 'F02-필요지식-⑦'

def pua_finding(item_id, rp, txt):
    if not PUA.search(txt or ''): return None
    return {'item_id': item_id + '-문자', 'region_path': rp, 'verdict': FAIL, 'evidence_quote': visible(txt),
            'reason': '기호 글꼴(사용자 정의 영역) 문자가 들어 있음 — 한글 화면에서는 가운뎃점 등으로 보이지만 다른 환경에서는 빈칸·네모로 깨짐',
            'suggestion': PUA.sub('·', txt)}

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


def _flatten(sections):
    return [(s, i, t) for s, sec in enumerate(sections) for i, t in enumerate(sec) if t]


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


def _f(item, rp, verdict, quote, reason, suggestion=None):
    return {'item_id': item, 'region_path': rp, 'verdict': verdict,
            'evidence_quote': visible(quote) if quote else quote, 'reason': reason, 'suggestion': suggestion}


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


MIN_AGREEMENT = 0.5     # 캡션 앞 번호와 학습 경계가 이 비율 미만으로 맞으면 '-위치' 검사를 하지 않음


def _title(c):
    """라벨을 뺀 캡션 글(그림명). 공백은 로더가 이미 한 칸으로 줄였으므로 그대로 비교"""
    t = c['text'].translate(_FW)
    return t[len(c['label']):].strip() if t.startswith(c['label']) else t.strip()


def toc_lesson_count(sections):
    """차례(section0)의 '학습 N. …' 줄 개수 — toc_check의 parse_manuscript 와 같은 규칙"""
    n = 0
    for s in sections[0] if sections else []:
        m = re.match(r'학습\s*(\d+)\.\s*(.+)', s)
        if m and int(m.group(1)) == n + 1: n += 1
    return n


def check_figtab(sections, lesson_spans=None, *, min_agreement=MIN_AGREEMENT, labels=None):
    """lesson_spans: [(학습번호, flat_start, flat_end)] 를 밖(내비게이터 기반 학습 구간)에서 주면 그것을 씀.
    1차: 캡션 번호 자체로 연속성 검사(확정적). 2차: 앞 번호 열이 차례 학습 개수와 맞는가.
    3차: 학습 제목줄이 믿을 만하게 잡힐 때만, 캡션이 놓인 학습과 앞 번호가 같은가(-위치)."""
    if labels is None:
        flat = _flatten(sections)
        caps, refs, bare = collect_labels(flat)
    else:
        flat, caps, refs, bare = labels["flat"], labels["caps"], labels["refs"], labels["bare"]
    F = []
    n_toc = toc_lesson_count(sections)

    # ---------- 1차·2차: 종류별로 문서 순서대로 ----------
    for kind in ('그림', '표'):
        cs = [c for c in caps if c['kind'] == kind]
        if not cs: continue
        groups, g = [], []
        for c in cs:
            if g and c['major'] != g[-1]['major']: groups.append(g); g = []
            g.append(c)
        if g: groups.append(g)

        # 앞 번호 열: 1,2,3… 한 번씩 순서대로여야 함
        majors = [g[0]['major'] for g in groups]
        seen = []
        for g in groups:
            major = g[0]['major']; first = g[0]
            rp0 = f"section{first['sec']} > {kind} {major}-x 묶음"
            if major in seen:
                F.append(_f(ITEM + '-번호', rp0, FAIL, ' / '.join(c['label'] for c in g[:4]),
                            f'{kind} {major}-x 가 다른 번호 묶음 뒤에 다시 나옴(앞서 {kind} {max(seen)}-x 까지 나온 뒤). '
                            f'학습 {major}의 {kind}은 한 곳에 이어져야 함 — 뒤에 나온 {first["label"]} 부터는 놓인 학습에 맞춰 번호를 바꿀 것'))
            elif seen and major != seen[-1] + 1:
                F.append(_f(ITEM + '-번호', rp0, FAIL, ' / '.join(c['label'] for c in g[:4]),
                            f'{kind} 앞 번호가 {seen[-1]} 다음에 {major} 로 감 — 학습 순서대로 {seen[-1] + 1} 이어야 함'
                            + ('' if major > seen[-1] else '(되돌아감)')))
            elif not seen and major != 1:
                F.append(_f(ITEM + '-번호', rp0, FAIL, ' / '.join(c['label'] for c in g[:4]),
                            f'원고에서 처음 나오는 {kind}의 앞 번호가 {major} — 학습 1의 {kind}이면 {_fmt(kind, 1, 1)} 부터여야 함'))
            seen.append(major)

            # 뒷 번호: 묶음 안에서 1부터 연속
            bad, expect = 0, 1
            for nth, c in enumerate(g, 1):
                rp = f"section{c['sec']} > {c['label']}"
                if (pf := pua_finding(ITEM, rp, c['text'])): F.append(pf)
                same = None
                if c['minor'] == expect:
                    expect += 1
                else:
                    bad += 1
                    if c['minor'] < expect:
                        prev = next((p for p in g[:nth - 1] if p['minor'] == c['minor']), None)
                        if prev and _title(prev) == _title(c):
                            same = prev
                            F.append(_f(ITEM + '-번호', rp, FAIL, c['text'],
                                        f'{c["label"]} 이(가) 두 번 나오고 그림명도 "{_title(c)}" 로 똑같음 — 같은 {kind}을 두 번 넣은 것. '
                                        f'하나를 빼면 뒤 번호는 그대로 맞음', '(중복이면 삭제)'))
                        elif prev:
                            F.append(_f(ITEM + '-번호', rp, FAIL, c['text'],
                                        f'{c["label"]} 이(가) 두 번 나오는데 그림명이 다름 — 앞: "{_title(prev)}", 뒤: "{_title(c)}". '
                                        f'다른 {kind}이므로 뒤의 것은 {_fmt(kind, major, expect)} 이어야 함', _fmt(kind, major, expect)))
                        else:
                            F.append(_f(ITEM + '-번호', rp, FAIL, c['text'],
                                        f'{c["label"]} 이(가) {_fmt(kind, major, expect - 1)} 뒤에 나옴 — 순서가 뒤바뀜. '
                                        f'자리를 옮기거나, 이 자리라면 {_fmt(kind, major, expect)} 이어야 함', _fmt(kind, major, expect)))
                    else:
                        skipped = ', '.join(_fmt(kind, major, m) for m in range(expect, c['minor']))
                        F.append(_f(ITEM + '-번호', rp, FAIL, c['text'],
                                    f'{kind} {major}-x 묶음의 {nth}번째인데 {c["label"]} 로 매겨짐 — {skipped} 를 건너뜀. {_fmt(kind, major, expect)} 이어야 함',
                                    _fmt(kind, major, expect)))
                    if not same: expect = max(expect, c['minor']) + 1   # 한 번 어긋난 뒤 연쇄 보고 방지
                if (c['open'], c['close']) not in _OK_BRACKETS[kind]:
                    F.append(_f(ITEM + '-표기', rp, FAIL, c['text'],
                                f"{kind} 번호는 {CORRECT[kind][0]} {CORRECT[kind][1]} 로 묶어야 하는데 {c['open']} {c['close']} 로 묶음",
                                _fmt(kind, c['major'], c['minor'])))
            if bad == 0:
                seq = ', '.join(c['label'] for c in g) if len(g) <= 4 else f"{g[0]['label']} … {g[-1]['label']}"
                F.append(_f(ITEM, f'{kind} {major}-x', PASS, ' / '.join(c['label'] for c in g),
                            f'{kind} {major}-x {len(g)}개가 {seq} 순서로 빠짐없이 이어짐'))

        # 차례의 학습 개수와 대조
        if n_toc and majors and max(majors) > n_toc:
            F.append(_f(ITEM + '-번호', f'{kind} 앞 번호', FAIL, ', '.join(f'{kind} {m}-x' for m in majors),
                        f'{kind} 앞 번호가 {max(majors)} 까지 나오는데 차례의 학습은 {n_toc}개 — 학습 번호를 넘는 번호가 있음'))

    # ---------- 3차: 학습 제목줄이 믿을 만할 때만 '놓인 학습' 과 대조 ----------
    spans, agree = (lesson_spans, 1.0) if lesson_spans else split_lessons(flat, caps)
    if spans and caps and agree >= min_agreement:
        lesson_of = lambda k: next((no for no, a, b in spans if a <= k < b), None)
        for c in caps:
            no = lesson_of(c['k'])
            if no is not None and c['major'] != no:
                F.append(_f(ITEM + '-위치', f"section{c['sec']} > 학습 {no} > {c['label']}", FAIL, c['text'],
                            f'{c["label"]} 이(가) 학습 {no} 본문(제목줄 "{flat[[a for n,a,b in spans if n==no][0]][2][:20]}" 아래)에 놓여 있음 — '
                            f'앞 번호 {c["major"]} 와 다름. 학습 {no}에 두려면 {c["kind"]} {no}-x 로',
                            None))
    elif caps:
        F.append(_f(ITEM + '-위치', '본문', UNDECIDED, None,
                    '학습 제목줄을 믿을 만하게 잡지 못해(캡션-경계 일치율 '
                    f'{agree:.0%}) "캡션이 놓인 학습 = 앞 번호" 검사는 못 함. 번호 연속성 검사(위)는 영향 없음'))

    # ---------- 참조 · 괄호 없음 ----------
    cap_keys = {(c['kind'], c['major'], c['minor']) for c in caps}
    for r in refs:
        rp = f"section{r['sec']} > 본문"
        if (r['kind'], r['major'], r['minor']) not in cap_keys:
            F.append(_f(ITEM + '-참조', rp, FAIL, r['text'],
                        f'본문 문장이 {r["label"]} 을(를) 가리키지만 원고 어디에도 {r["label"]} 캡션이 없음 — 그림·표를 빼거나 번호를 바꾼 뒤 본문을 안 고쳤을 가능성'))
        if (r['open'], r['close']) not in _OK_BRACKETS[r['kind']]:
            F.append(_f(ITEM + '-표기', rp, FAIL, r['text'],
                        f"본문에서 {r['kind']} 번호를 {r['open']} {r['close']} 로 묶음 — {CORRECT[r['kind']][0]} {CORRECT[r['kind']][1]} 로 묶어야 함",
                        _fmt(r['kind'], r['major'], r['minor'])))
    for x in bare:
        F.append(_f(ITEM + '-표기', f"section{x['sec']} > 본문", UNDECIDED, x['text'],
                    f'"{x["label"]}" 이 괄호 없이 나옴 — 괄호가 기호 글꼴(사용자 정의 문자)로 찍혔거나 빠진 것. 어느 쪽인지 원고에서 확인',
                    _fmt(x['kind'], x['major'], x['minor'])))
    return F

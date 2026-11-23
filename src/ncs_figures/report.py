"""이미지별 검수표(HTML) — 정의서 '검수표(화면·PDF)'. 한 파일로 열리고(그림 썸네일 포함), 브라우저 인쇄로 PDF가 된다.

그림 한 장 = 카드 하나: 위치·캡션 / 썸네일 / 출처 줄과 해석 / 문맥(본문 참조·앞뒤 문단·표 맥락) / 점검 결과 / 위험도·근거 /
미실행 점검 / 수정 제안. 위험도 순(고위험 → 확인 필요 → 문제없음). 판정 문구는 후보·근거 중심(법적 단정 없음).
"""

from __future__ import annotations

import base64
import html
import io
from pathlib import Path

from PIL import Image

THUMB = 260
COLOR = {"고위험": "#b42318", "확인 필요": "#b54708", "문제없음": "#027a48", "판정 안 함": "#475467"}
CHECK_COLOR = {"X": "#b42318", "△": "#b54708", "O": "#027a48", "-": "#667085"}
# 표시용 — 점검 이름은 '무엇을 묻는가'로, 결과 기호는 말로(웹 FiguresPanel.CHECK_LABEL과 같음). "①출처 있음 △"가 "출처 있음"으로 읽히지 않게.
CHECK_LABEL = {"①출처 있음": "① 출처 줄이 있나", "①출처 형식": "① 출처가 양식대로 적혔나",
               "①출처 요건": "① 출처에 필수 요소가 다 있나(계약서 제4조)", "③캡션 일치": "③ 캡션이 그림과 맞나",
               "④DB 대조": "④ DB에 같은 그림이 있나(권리 정보)", "③출처-DB 일치": "③ 출처가 DB의 원래 출처와 맞나",
               "⑦AI 표기": "⑦ AI 활용 표기가 양식대로인가", "⑨제3자 원본": "⑨ 남의 원본을 AI로 고쳤다면 이용허락 확인"}
VALUE_LABEL = {"O": "문제없음", "X": "문제", "△": "확인 필요", "-": "해당 없음"}

CSS = """
:root{--fg:#101828;--muted:#475467;--line:#d0d5dd;--bg:#fff;--card:#f9fafb}
*{box-sizing:border-box}body{font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;color:var(--fg);background:var(--bg);margin:0;padding:24px;line-height:1.5}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:0}.muted{color:var(--muted);font-size:12px}
.summary{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0 24px}.stat{border:1px solid var(--line);border-radius:8px;padding:8px 14px;min-width:110px}
.stat b{display:block;font-size:20px}.card{border:1px solid var(--line);border-radius:10px;margin:0 0 16px;page-break-inside:avoid;overflow:hidden}
.head{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:10px 14px;background:var(--card);border-bottom:1px solid var(--line)}
.badge{color:#fff;border-radius:999px;padding:2px 10px;font-size:12px;white-space:nowrap}.body{display:grid;grid-template-columns:280px 1fr;gap:14px;padding:14px}
.thumb img{max-width:260px;max-height:260px;border:1px solid var(--line);background:#fff}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{border:1px solid var(--line);padding:4px 6px;vertical-align:top;text-align:left}
th{background:var(--card);width:120px;font-weight:600}.ctx{font-size:12px;color:var(--muted);margin:0;padding-left:16px}
.v{font-weight:700}@media (max-width:760px){.body{grid-template-columns:1fr}}
@media print{body{padding:0}.card{break-inside:avoid}}
"""


def _e(value) -> str:
    return html.escape(str(value or ""))


def _thumb(data: bytes) -> str:
    if not data:
        return '<span class="muted">그림 파일 없음</span>'
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        image = image.convert("RGB")
        image.thumbnail((THUMB, THUMB))
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
    except Exception:  # noqa: BLE001
        return '<span class="muted">그림을 읽지 못함</span>'
    return f'<img alt="그림" src="data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}">'


def _list(items) -> str:
    items = [i for i in items if i]
    return "<ul class=\"ctx\">" + "".join(f"<li>{_e(i)}</li>" for i in items) + "</ul>" if items else '<span class="muted">없음</span>'


def _reading(reading: dict | None) -> str:
    """그림 판독(모델) — 켜지 않았으면 줄 없음. 모델 결과는 후보임을 표시."""
    if reading is None:
        return ""
    if reading.get("status") != "완료":
        return f'<tr><th>그림 판독</th><td><span class="muted">{_e(reading.get("status"))} — {_e(reading.get("reason"))}</span></td></tr>'
    words = ", ".join(reading.get("그림 속 글자") or []) or "없음"
    problems = f'<br><span class="muted">확인: {_e(", ".join(reading["problems"]))}</span>' if reading.get("problems") else ""
    return (f'<tr><th>그림 판독<br><span class="muted">(모델 후보)</span></th><td><b>{_e(reading.get("유형"))}</b> — {_e(reading.get("설명"))}'
            f'<br><span class="muted">그림 속 글자: {_e(words)} · 키워드: {_e(", ".join(reading.get("키워드") or []))}'
            f' · 맥락 요약: {_e(reading.get("맥락 요약") or "근거 없음")} · {_e(reading.get("model"))}</span>{problems}</td></tr>')


def _card(review, row: dict) -> str:
    ctx, item = review.item.ctx, review.item
    risk = row["위험도"]
    checks = "".join(
        f'<tr><td>{_e(CHECK_LABEL.get(name, name))}</td><td class="v" style="color:{CHECK_COLOR.get(value, "#101828")}">{_e(VALUE_LABEL.get(value, value))}</td>'
        f'<td>{_e(row["비고"].get(name, ""))}</td></tr>' for name, value in row["체크"].items())
    source = row["출처 해석"]
    source_html = (f"{_e(source['text'])}<br><span class=\"muted\">종류: {_e(source['source_kind'])}"
                   + (f" · 인용 모듈 {_e(source['cited_module'])} p.{_e(source['page'])}" if source.get("cited_module") else "")
                   + (f" · 공공누리 {_e(source['kogl_type'])}유형" if source.get("kogl_type") else "") + "</span>") if source else '<span class="muted">출처 줄 없음</span>'
    ai = row["AI 표기"]
    return f"""
<section class="card">
 <div class="head"><div><h2>{_e(row['원고'])}</h2><div class="muted">{_e(row['region_path'])} · {_e(row['그림 종류'])} · {_e(row['item_id'])}</div></div>
  <span class="badge" style="background:{COLOR.get(risk, '#475467')}">{_e(risk)}</span></div>
 <div class="body"><div class="thumb">{_thumb(ctx.data)}<div class="muted">{ctx.px[0]}×{ctx.px[1]}px · {ctx.mm[0]}×{ctx.mm[1]}mm · {_e(ctx.dpi)} DPI{' · 표 안' if ctx.in_table else ''}</div></div>
 <div><table>
  <tr><th>출처</th><td>{source_html}</td></tr>
  <tr><th>AI 활용 표기</th><td>{_e(ai['raw']) if ai else '<span class="muted">없음</span>'}</td></tr>
  <tr><th>본문 참조</th><td>{_list(ctx.references)}</td></tr>
  <tr><th>앞 문맥</th><td>{_list(ctx.before)}</td></tr>
  <tr><th>뒤 문맥</th><td>{_list(ctx.after)}</td></tr>
  {f'<tr><th>표 맥락</th><td>{_list(ctx.table_context)}</td></tr>' if ctx.in_table else ''}
  {_reading(review.reading)}
  <tr><th>위험 근거</th><td>{_list(row['위험 근거'])}</td></tr>
  <tr><th>수정 제안</th><td>{_e(row['수정 제안']) or '<span class="muted">없음</span>'}</td></tr>
  <tr><th>대체 후보<br><span class="muted">(그림 DB 같은 주제)</span></th><td>{_list(f"{c['module']} {c['figure_label']} {c['figure_title']} — 권리 {c['rights_status']}" for c in row.get('대체 후보') or [])}</td></tr>
  <tr><th>미실행 점검</th><td>{_list(row['미실행'])}</td></tr>
  <tr><th>외부 전송</th><td>{_e(item.transfer)} <span class="muted">{_e(item.transfer_reason)}</span></td></tr>
 </table>
 <table style="margin-top:8px"><tr><th>점검</th><th style="width:72px">결과</th><th>근거</th></tr>{checks}</table>
 </div></div>
</section>"""


def write_html(result, path: Path, *, title: str = "") -> Path:
    by_id = {r["item_id"]: r for r in result.rows}
    from .rows import item_id
    cards = [_card(review, by_id[item_id(review)]) for review in result.reviews if review.risk is not None]
    order = {"고위험": 0, "확인 필요": 1, "문제없음": 2, "판정 안 함": 3}
    cards_sorted = [c for _, c in sorted(zip([order[by_id[item_id(r)]["위험도"]] for r in result.reviews if r.risk is not None], cards),
                                         key=lambda pair: pair[0])]
    s = result.summary
    stats = "".join(f'<div class="stat"><span class="muted">{_e(k)}</span><b>{_e(v)}</b></div>' for k, v in (
        ("그림", s["그림"]), ("검수 대상", s["검수 대상"]), ("양식 제외", s["양식 제외"]),
        ("고위험", s["위험도"]["고위험"]), ("확인 필요", s["위험도"]["확인 필요"]), ("문제없음", s["위험도"]["문제없음"]),
        ("판정 안 함", s["위험도"]["판정 안 함"])))
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>이미지 검수표 {_e(title)}</title><style>{CSS}</style></head><body>
<h1>이미지 검수표 — {_e(title)}</h1>
<div class="muted">REQ-02-005 · AI·규칙은 후보와 근거만 제시합니다. 최종 판단은 에디팅 기관이 합니다. 인쇄(Ctrl+P)하면 PDF로 저장할 수 있습니다.</div>
<div class="summary">{stats}</div>
<div class="muted" style="margin-bottom:12px">미실행 점검: {_e(', '.join(f'{k} {v}건' for k, v in s['미실행'].items())) or '없음'}</div>
{''.join(cards_sorted)}
</body></html>"""
    path.write_text(page, encoding="utf-8")
    return path

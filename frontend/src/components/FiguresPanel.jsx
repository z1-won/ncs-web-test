import React, { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api.js";
import { useCanManage } from "../lib/auth.jsx";
import { formatDate } from "../lib/format.jsx";
import { Spinner } from "./Badge.jsx";
import { PageAlert } from "./PageAlert.jsx";
import { FigureReadBar, FigureReadResults } from "./FigureReadPanel.jsx";

// 그림 검수(005)와 그림 태깅(009)을 한 표로. 그림 판독(Claude)은 버튼을 눌렀을 때만.

export const RISK_BADGE = { 고위험: "bg-light-danger", "확인 필요": "bg-light-warning", 문제없음: "bg-light-success", "판정 안 함": "bg-light-gray" };

export function RiskBadge({ value }) {
  return <span className={`krds-badge ${RISK_BADGE[value] || "bg-light-gray"}`}>{value}</span>;
}

export function Thumb({ token, id, alt }) {
  const [broken, setBroken] = useState(false);
  if (!id || broken) return <span className="fig-thumb empty">그림 없음</span>;
  const src = api.figures.imageUrl(token, id);
  return (
    <a className="fig-thumb" href={src} target="_blank" rel="noreferrer" title="원본 크기로 보기">
      <img src={src} alt={alt || "그림"} loading="lazy" onError={() => setBroken(true)} />
    </a>
  );
}

export function FiguresPanel({ uploadToken, moduleCode, refresh = 0 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("review");
  const [onlyIssues, setOnlyIssues] = useState(false);   // 기본은 그림 전부(문제없음 포함)
  const [readResult, setReadResult] = useState(null);
  const canRead = useCanManage();     // 그림 판독(그림을 밖으로 보내고 비용이 듦)은 에디터와 직능연 계정만 — 그 밖의 계정에는 버튼과 결과 탭을 그리지 않는다
  const [reload, setReload] = useState(0);   // 그림 판독이 끝나면 늘려 규칙 결과(③이 든 위험도)를 다시 불러온다
  // 담당자 최종 판단과 태깅에서 고친 값 — 서버가 보관한다(이력을 두는 서버에서만, 아니면 null이라 판단 칸을 그리지 않는다)
  const [decisions, setDecisions] = useState(null);
  const [decideError, setDecideError] = useState(null);
  async function decide(key, imageId, next) {
    setDecideError(null);
    const { ok, data: body, error: message } = await api.figures.decide(uploadToken, { key, image_id: imageId || "", ...next });
    if (!ok) { setDecideError(`판단을 저장하지 못했습니다. ${message}`); return false; }
    setDecisions((have) => {
      const out = { ...(have || {}) };
      if (body.decision) out[key] = body.decision; else delete out[key];
      return out;
    });
    return true;
  }

  useEffect(() => {
    setData(null);
    setError(null);
    if (!uploadToken) return;
    const controller = new AbortController();
    setLoading(true);
    api.figures.rules(uploadToken, { moduleCode, signal: controller.signal }).then(({ ok, data: body, error: message, aborted }) => {
      if (aborted) return;
      if (ok) { setData(body); setDecisions(body.decisions ?? null); }
      else setError(message);
      setLoading(false);
    });
    return () => controller.abort();
  }, [uploadToken, moduleCode, reload, refresh]);

  const merged = useMemo(() => (data ? mergeFigures(data.review.rows || [], data.tags.records || []) : []), [data]);
  const issues = merged.filter(needsLook);
  const fallback = onlyIssues && !issues.length && merged.length > 0;
  const shown = onlyIssues && !fallback ? issues : merged;
  const s = data?.review.summary;
  const decided = Object.values(decisions || {}).filter((item) => item.verdict);
  const fixedTags = Object.values(decisions || {}).some((item) => Object.keys(item.fixes || {}).length > 0);
  const onlyListed = Object.entries(data?.submissions?.["목록에만 있음"] || {});

  return (
    <section id="figures" className="figures-panel nav-anchor">
      <div className="section-head">
        <h2 className="section-title">그림 검수</h2>
      </div>

      {loading && <Spinner label="그림 검수 중" />}
      {error && <PageAlert kind="danger">{error}</PageAlert>}

      {data && (
        <>
          {canRead && <FigureReadBar uploadToken={uploadToken} onResult={setReadResult} onDone={() => setReload((n) => n + 1)} />}

          <div className="fig-toolbar">
            <div className="fig-tabs" role="tablist" aria-label="그림 결과 보기">
              <button type="button" role="tab" aria-selected={tab === "review"} className={tab === "review" ? "on" : ""} onClick={() => setTab("review")}>그림 검수 · 태깅</button>
              {canRead && <button type="button" role="tab" aria-selected={tab === "read"} className={tab === "read" ? "on" : ""} onClick={() => setTab("read")}>그림 판독 결과</button>}
            </div>
            <span className="fig-counts">
              <span className="count fail">고위험 {s.위험도.고위험}</span>
              <span className="count undecided">확인 필요 {s.위험도["확인 필요"]}</span>
              <span className="count pass">문제없음 {s.위험도.문제없음}</span>
              {s.위험도["판정 안 함"] > 0 && <span className="count">판정 안 함(판독 전) {s.위험도["판정 안 함"]}</span>}
            </span>
            <div className="krds-form-check">
              <input type="checkbox" id="fig-only-issues" checked={onlyIssues} onChange={(e) => setOnlyIssues(e.target.checked)} />
              <label htmlFor="fig-only-issues">확인할 것만 보기</label>
            </div>
            <div className="fig-downloads">
              <a className="krds-btn small tertiary" href={api.figures.reportUrl(uploadToken)} target="_blank" rel="noreferrer">검수표(인쇄→PDF)</a>
              <a className="krds-btn small tertiary" href={api.figures.memoUrl(uploadToken)}>메모 단 원고(hwpx)</a>
              <a className="krds-btn small tertiary" href={api.figures.csvUrl(uploadToken)}>태깅 표(CSV)</a>
              {fixedTags && <a className="krds-btn small tertiary" href={api.figures.overridesUrl(uploadToken)}>고친 태깅 값(TSV)</a>}
              <a className="krds-btn small tertiary" href={api.figures.jsonUrl(uploadToken)}>원본 데이터(JSON)</a>
            </div>
          </div>
          {onlyListed.map(([name, items]) => (
            <PageAlert key={name} kind="warning">{name}에만 있고 원고에 없는 그림: {items.join(", ")}</PageAlert>
          ))}

          {tab === "review" && decisions && (
            <p className="form-hint fig-decide-guide">
              {canRead
                ? "그림마다 ‘판정과 근거’ 칸 아래에서 최종 판단을 고르고 까닭을 적습니다. 서버에 저장되어 같은 원고 파일을 다시 올려도 보입니다."
                : "담당자가 내린 최종 판단이 ‘판정과 근거’ 칸 아래에 보입니다."}
              {decided.length > 0 && ` 지금까지 ${decided.length}개를 판단했고 그중 정정 필요는 ${decided.filter((item) => item.verdict === "정정 필요").length}개입니다.`}
            </p>
          )}
          {decideError && <PageAlert kind="danger">{decideError}</PageAlert>}
          {tab === "review" && fallback && <PageAlert kind="success">확인할 그림 없음 — {merged.length}개 모두 문제없음</PageAlert>}
          {tab === "review" && <FigureTable items={shown} token={uploadToken} hasDb={Boolean(data.db)} decisions={decisions} canDecide={canRead} onDecide={decide} />}
          {tab === "read" && <FigureReadResults uploadToken={uploadToken} result={readResult} />}
        </>
      )}
    </section>
  );
}

// 005 검수 행과 009 태깅 레코드를 그림(image_id)으로 묶는다. 태깅에만 있는 그림은 뒤에 붙인다.
function mergeFigures(rows, records) {
  const byImage = new Map(records.filter((r) => r.image_id).map((r) => [r.image_id, r]));
  const used = new Set();
  const out = rows.map((row) => {
    const rec = row.image_id ? byImage.get(row.image_id) : null;
    if (rec) used.add(rec);
    return { row, rec };
  });
  records.forEach((rec) => { if (!used.has(rec)) out.push({ row: null, rec }); });
  return out;
}

// 태깅의 사람 확인 사유 중 검수 줄(출처·수록 현황·AI 현황)과 겹치는 것은 뺀다
const SHOWN_IN_REVIEW = ["출처 줄 없음", "출처 형식 문제", "캡션 없는 그림", "수록 현황 목록과 다름", "제작 목록에 없음", "AI 결과물 현황과 다름"];
const tagReasons = (rec, hasRow) => (rec?.review_reasons || []).filter((x) => !hasRow || !SHOWN_IN_REVIEW.some((k) => x.startsWith(k)));
const needsLook = ({ row, rec }) => (row && row.위험도 !== "문제없음") || tagReasons(rec, Boolean(row)).length > 0;

// 출처 줄을 읽은 결과: 종류 · 저작자(연도) · 인용 모듈·쪽 / URL / 공공누리 유형
export function SourceCell({ source, ai, quote = true }) {
  if (!source) {
    return <><b className="fig-nosrc">출처 없음</b><div className="sub">캡션 위에 '출처:' 줄이 없음</div>
      {ai && <div className="sub">AI 표기: {ai.raw}</div>}</>;
  }
  const kind = source.kind || source.source_kind;
  const page = source.cited_page ?? source.page;
  return (
    <>
      <b>{kind}</b>{source.author && source.author !== kind ? ` · ${source.author}` : ""}{source.year ? ` (${source.year})` : ""}
      {source.cited_module && <div>인용 모듈 {source.cited_module}{page != null ? ` p.${page}` : ""}</div>}
      {source.url && <div className="fig-url"><a href={source.url} target="_blank" rel="noreferrer">{source.url}</a>{source.checked_date ? ` (${source.checked_date} 확인)` : ""}</div>}
      {source.kogl_type && <div>공공누리 {source.kogl_type}유형</div>}
      {quote && <div className="sub">원문: {source.text}</div>}
      {ai && <div className="sub">AI 표기: {ai.raw}</div>}
    </>
  );
}

// 그림이 무엇에 대한 것인지 — 모델이 아니라 원고에서 코드가 모은 글: 본문 참조 문장 → 표 안이면 같은 표 → 앞·뒤 문단.
// 펼치기 없이 모두 보인다(표가 길어져도 한눈에). '/'처럼 글자가 거의 없는 표 칸은 뺀다.
const CLIP = 140;
const clip = (t) => (t && t.length > CLIP ? `${t.slice(0, CLIP)}…` : t);
const squash = (t) => (t || "").replace(/\s+/g, "");
const sameText = (a, b) => Boolean(b) && squash(a).includes(squash(b)) && squash(a).length - squash(b).length < 15;
const meaningful = (t) => (t || "").replace(/[^\p{L}\p{N}]/gu, "").length >= 2;

export function ContextCell({ ctx }) {
  if (!ctx) return <span className="sub">—</span>;
  const groups = [
    ["본문에서 이 그림을 가리키는 문장", ctx["본문 참조"] || []],
    ["같은 표의 글", (ctx.표 || []).slice(0, 3)],
    // 앞 문단은 문서 순서(먼 것 → 가까운 것)로 저장돼 있다 — 그림 바로 위 두 문단을 문서 순서대로
    ["앞 문단(그림 바로 위)", (ctx.앞 || []).filter(meaningful).slice(-2)],
    ["뒤 문단(그림 바로 아래)", (ctx.뒤 || []).filter((t) => !sameText(t, ctx.캡션)).filter(meaningful).slice(0, 2)],
  ].map(([label, lines]) => [label, lines.filter(meaningful)]).filter(([, lines]) => lines.length);
  if (!groups.length) return <span className="sub">주변 글 없음</span>;
  return (
    <div className="fig-ctx">
      {groups.map(([label, lines]) => (
        <div key={label} className="ctx-group">
          <div className="ctx-label">{label}</div>
          {lines.map((t, i) => <div key={i}>{clip(t)}</div>)}
        </div>
      ))}
    </div>
  );
}

// 위치를 쉬운 말로: "section1 > 학습 1 > 1-1. 제목 > [그림 1-1]" → "학습 1 > 1-1. 제목"
// section은 한글 파일의 '구역'(0 = 앞부분, 1 = 본문), p숫자는 문단 번호. 그림 번호는 그림 칸에 이미 있어 뺀다.
export function placeText(regionPath) {
  const parts = (regionPath || "").split(" > ").map((p) => p.trim()).filter(Boolean);
  const out = [];
  parts.forEach((p) => {
    const section = p.match(/^section(\d+)$/);
    if (section) { if (section[1] === "0") out.push("앞부분(위치·차례·개요)"); return; }
    const para = p.match(/^p(\d+)$/);
    if (para) { out.push(`${Number(para[1]).toLocaleString()}번째 문단 근처`); return; }
    if (p.startsWith("[그림")) return;
    out.push(p);
  });
  return out.join(" > ") || "본문";
}

// 위치(학습 > 소제목). 문단 사이의 그림 / 표 안의 그림은 표의 묶음 머리 줄이 이미 말하므로 여기엔 쓰지 않는다.
function PlaceCell({ regionPath }) {
  return <div>{placeText(regionPath)}</div>;
}

// 그림 칸: 썸네일 + 그 아래 그림 번호·제목(캡션)
function FigureCell({ token, id, caption }) {
  return (
    <>
      <Thumb token={token} id={id} alt={caption || "캡션 없는 그림"} />
      <div className="fig-caption">{caption || <b className="fig-nosrc">캡션 없음</b>}</div>
    </>
  );
}

// 문단 사이의 그림을 먼저, 표 안의 그림을 그다음에 — 묶음마다 머리 줄
function grouped(list, inTable) {
  const between = list.filter((x) => !inTable(x));
  const tables = list.filter((x) => inTable(x));
  return [["문단 사이의 그림", between], ["표 안의 그림", tables]].filter(([, items]) => items.length);
}

// 판정과 근거 — 기호·꼬리표 없이 문장으로. 출처는 원문 그대로, 양식·요건은 O / X(X면 어디가 틀렸는지).
// 해당 없는 점검(AI 표기 없음 등)은 줄을 만들지 않는다. 문제(X)·확인 필요(△)는 굵게.
const OX = { O: "O", X: "X", "△": "확인 필요" };

function VerdictLine({ label, value, note }) {
  const bad = value === "X" || value === "△";
  return (
    <div className={`v-line${bad ? " bad" : ""}`}>
      {bad ? <b>{label}: {OX[value]}</b> : <>{label}: {OX[value] || value}</>}
      {bad && note && <div className="v-note">{note}</div>}
    </div>
  );
}

// 위험 근거 중 아래 점검 줄(X·확인 필요의 설명)과 같은 말은 뺀다 — 같은 문장이 두 번 보이지 않게.
// 점검 줄에 없는 근거(고위험 규칙의 설명, 미실행 등)만 남는다.
function riskReasons(row) {
  const c = row.체크 || {};
  const n = row.비고 || {};
  const shown = Object.keys(c).filter((k) => (c[k] === "X" || c[k] === "△") && n[k]).map((k) => n[k]);
  const body = (why) => why.replace(/^\[[^\]]+\]\s*/, "").replace(/^(고위험|확인 필요):\s*/, "").replace(/^\[[^\]]+\]\s*/, "");
  return (row["위험 근거"] || []).filter((why) => {
    const text = body(why);
    if (!row["출처 해석"] && text.startsWith("출처 표기 없음")) return false;     // '출처: 없음' 줄과 같음
    return !shown.some((note) => note.length > 8 && (text.includes(note) || note.includes(text)));
  });
}

function VerdictCell({ row }) {
  const c = row.체크 || {};
  const n = row.비고 || {};
  const source = row["출처 해석"];
  return (
    <div className="fig-verdict">
      <div className="v-risk">위험도: <b>{row.위험도}</b></div>
      {row.위험도 !== "문제없음" && riskReasons(row).map((why) => <div key={why} className="v-why">{why}</div>)}
      {source
        ? <div className="v-line">출처: 「{source.text}」</div>
        : <div className="v-line bad"><b>출처: 없음</b><div className="v-note">{n["①출처 있음"] || "캡션 위에 '출처:' 줄이 없음"}</div></div>}
      {source && c["①출처 형식"] && <VerdictLine label="출처 양식(F14 템플릿)" value={c["①출처 형식"]} note={n["①출처 형식"]} />}
      {c["①출처 요건"] && c["①출처 요건"] !== "-" && <VerdictLine label="필수 요소(계약서 제4조)" value={c["①출처 요건"]} note={n["①출처 요건"]} />}
      {c["①기관 명칭"] && <VerdictLine label="옛 기관 명칭" value={c["①기관 명칭"]} note={n["①기관 명칭"]} />}
      {c["⑦AI 표기"] && c["⑦AI 표기"] !== "-" && <VerdictLine label="AI 활용 표기" value={c["⑦AI 표기"]} note={n["⑦AI 표기"]} />}
      {c["⑦생성·수정 구분"] && c["⑦생성·수정 구분"] !== "-" && <VerdictLine label="AI 생성·수정 구분" value={c["⑦생성·수정 구분"]} note={n["⑦생성·수정 구분"]} />}
      {c["⑨제3자 원본"] && c["⑨제3자 원본"] !== "-" && <VerdictLine label="남의 원본을 AI로 고침(이용허락)" value={c["⑨제3자 원본"]} note={n["⑨제3자 원본"]} />}
      {c["④DB 대조"] && <VerdictLine label="그림 DB에 같은 그림(권리·원래 출처)" value={c["④DB 대조"]} note={n["④DB 대조"]} />}
      {c["②마크·워터마크"] && <VerdictLine label="그림 속 공공누리 마크·저작권 문구·워터마크" value={c["②마크·워터마크"]} note={n["②마크·워터마크"]} />}
      {c["③캡션 일치"] && <VerdictLine label="캡션과 그림 내용" value={c["③캡션 일치"]} note={n["③캡션 일치"]} />}
      {c["⑥수록 현황"] && <VerdictLine label="수록 현황 목록" value={c["⑥수록 현황"]} note={n["⑥수록 현황"]} />}
      {c["⑥증빙"] && c["⑥증빙"] !== "-" && <VerdictLine label="제작 방식별 증빙" value={c["⑥증빙"]} note={n["⑥증빙"]} />}
      {c["⑦AI 현황 대조"] && c["⑦AI 현황 대조"] !== "-" && <VerdictLine label="서약서 AI 결과물 현황" value={c["⑦AI 현황 대조"]} note={n["⑦AI 현황 대조"]} />}
      {c["⑧AI 결과물 유사"] && c["⑧AI 결과물 유사"] !== "-" && <VerdictLine label="기존 그림과 비슷한가(AI·외부 제작)" value={c["⑧AI 결과물 유사"]} note={n["⑧AI 결과물 유사"]} />}
      {row["수정 제안"] && <div className="v-fix"><b>고칠 것:</b> {row["수정 제안"]}</div>}
    </div>
  );
}

// 비슷한 그림 추천 — 저작권이 문제이거나 오래된 그림이면 바꿔 쓸 수 있는, 같은 주제(캡션·키워드)의 그림 DB 그림
function ReplaceCell({ candidates, db, hasCaption }) {
  if (!db) return <span className="sub">이미지 저작권 DB에 연결되지 않음</span>;
  if (!hasCaption && !candidates?.length) return <span className="sub">캡션이 없어 비슷한 그림을 찾지 못함</span>;
  if (!candidates?.length) return <span className="sub">비슷한 그림 없음</span>;
  return (
    <div className="fig-db">
      {candidates.map((m) => (
        <div key={`${m.image_id}-${m.module}-${m.figure_label}`} className="fig-cand">
          <a className="fig-thumb small" href={api.figures.dbImageUrl(m.image_id)} target="_blank" rel="noreferrer" title="DB 그림 원본 보기">
            <img src={api.figures.dbImageUrl(m.image_id)} alt={m.figure_title || "DB 그림"} loading="lazy" />
          </a>
          <div><b>{m.figure_label} {m.figure_title}</b></div>
          <div className="sub">{m.module}</div>
          <div className="sub">겹치는 말: {m.common.join(", ") || "—"}</div>
          <div className="sub">{m.source_text ? `「${m.source_text}」` : "출처 줄 없음"}</div>
          <div className="sub">권리: {m.rights_status || "미확인"}</div>
        </div>
      ))}
    </div>
  );
}

// AI 활용 유형 1~5 — 정해졌으면 유형과 근거, 아니면 후보
function AiTypeLine({ ai }) {
  const t = ai.ai_type;
  if (!t) return <div className="sub">AI 활용 유형 후보: {(ai.ai_type_candidates || []).join(", ") || "없음"}</div>;
  return (
    <div className="sub">
      AI 활용 유형: {t.type ? <b>{t.type}. {t.name}</b> : `${t.candidates.join(", ")} 중 하나`}
      {t.type && t.basis?.length > 1 && <div>{t.basis.slice(1).join(" · ")}</div>}
    </div>
  );
}

function pageText(u) {
  if (!u?.page) return "쪽 없음(출력본 PDF 없음)";
  return `p.${u.page}${u.page_from === "PDF(추정)" ? " (추정)" : u.page_from === "PDF 장 순서" ? " (PDF 장 순서)" : ""}`;
}

// 그림 검수(005)와 태깅(009)을 한 표로: 그림 · 위치 · 출처 · 주변 글 · 학습·수행준거 · 유형·해상도 · 비슷한 그림 추천 · 판정과 근거
// 담당자 최종 판단(REQ-02-005 사람 작업 4번) — 사용 가능 / 정정 필요와 까닭. 판정은 고르는 즉시, 까닭은 칸을 벗어날 때 저장한다.
// 태깅이 '사람 확인'으로 남긴 그림(REQ-02-009 사람 작업 4번)은 출처 종류·저작자·연도·그림 유형을 고쳐 적을 수 있다 — 고친 값이 태깅 표에 들어간다.
const FIGURE_CHOICES = ["", "사용 가능", "정정 필요"];
const SOURCE_KINDS = ["집필진 제작", "기존 학습모듈", "공공누리", "웹·검색", "스크린숏", "문헌", "법령", "AI 표기", "알 수 없음"];
const FIX_FIELDS = [["source.kind", "출처 종류"], ["source.author", "저작자"], ["source.year", "연도"], ["image_type.value", "그림 유형"]];

function DecideCell({ figureKey, imageId, name, mine, canDecide, onDecide, canFix }) {
  const [reason, setReason] = useState(mine?.reason || "");
  const [fixes, setFixes] = useState(mine?.fixes || {});
  useEffect(() => { setReason(mine?.reason || ""); setFixes(mine?.fixes || {}); }, [mine]);
  const fixed = Object.entries(mine?.fixes || {});
  if (!canDecide) {
    if (!mine?.verdict && !mine?.reason && !fixed.length) return null;
    return (
      <div className="fig-decide">
        {(mine.verdict || mine.reason) && <div><b>담당자 판단: {mine.verdict || "판단 전"}</b>{mine.reason ? `, ${mine.reason}` : ""}</div>}
        {fixed.length > 0 && <div className="sub">고친 태깅 값: {fixed.map(([field, value]) => `${FIX_FIELDS.find(([f]) => f === field)?.[1] || field} ${value}`).join(", ")}</div>}
        <span className="meta">{mine.by}, {formatDate(mine.at)}</span>
      </div>
    );
  }
  const save = (next) => onDecide(figureKey, imageId, { verdict: mine?.verdict || "", reason, fixes, ...next });
  const saveFix = (field, value) => {
    const next = { ...fixes, [field]: value };
    setFixes(next);
    if ((mine?.fixes?.[field] || "") !== value.trim()) save({ fixes: next });
  };
  return (
    <div className="fig-decide">
      <div className="fig-decide-main">
        <select className="krds-form-select small" aria-label={`${name} 최종 판단`} value={mine?.verdict || ""} onChange={(e) => save({ verdict: e.target.value })}>
          {FIGURE_CHOICES.map((c) => <option key={c} value={c}>{c || "판단 전"}</option>)}
        </select>
        <input type="text" className="krds-input small" maxLength={500} aria-label={`${name} 판단한 까닭`} placeholder="판단한 까닭"
               value={reason} onChange={(e) => setReason(e.target.value)} onBlur={() => { if (reason.trim() !== (mine?.reason || "")) save({ reason }); }} />
      </div>
      {mine?.by && <span className="meta">{mine.by}, {formatDate(mine.at)}</span>}
      {canFix && (
        <details className="fig-fix" open={fixed.length > 0}>
          <summary>태깅 값 고치기{fixed.length > 0 ? ` (${fixed.length}칸 고침)` : ""}</summary>
          <div className="fig-fix-fields">
            {FIX_FIELDS.map(([field, label]) => (
              <label key={field}>
                <span>{label}</span>
                {field === "source.kind" ? (
                  <select className="krds-form-select small" value={fixes[field] || ""} onChange={(e) => saveFix(field, e.target.value)}>
                    <option value="">고치지 않음</option>
                    {SOURCE_KINDS.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
                  </select>
                ) : (
                  <input type="text" className="krds-input small" maxLength={100} value={fixes[field] || ""}
                         onChange={(e) => setFixes({ ...fixes, [field]: e.target.value })} onBlur={(e) => saveFix(field, e.target.value)} />
                )}
              </label>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function FigureTable({ items, token, hasDb, decisions, canDecide, onDecide }) {
  if (!items.length) return <p className="empty">확인할 그림 없음</p>;
  return (
    <div className="krds-table-wrap">
      <table className="tbl col data fig-table fig-review">
        <caption className="sr-only">그림 검수 — 그림별 출처·내용·태깅·판정</caption>
        <thead>
          <tr><th scope="col">그림</th><th scope="col">위치</th><th scope="col">출처</th><th scope="col">주변 글</th><th scope="col">학습 · 수행준거</th><th scope="col">유형 · 해상도</th><th scope="col">비슷한 그림 추천</th><th scope="col">판정과 근거</th></tr>
        </thead>
        {grouped(items, ({ row, rec }) => (row ? row.그림?.["표 안"] : rec.uses[0]?.in_table)).map(([title, group]) => (
          <tbody key={title}>
            <tr className="fig-group"><th colSpan={8} scope="rowgroup">{title} · {group.length}개</th></tr>
            {group.map(({ row, rec }, i) => {
              const u = rec?.uses[0];
              const caption = row?.문맥?.캡션 || (u?.figure_label ? `${u.figure_label}${u.figure_title ? ` ${u.figure_title}` : ""}` : "");
              const extra = tagReasons(rec, Boolean(row));
              return (
                <tr key={row?.item_id || rec?.image_id || i}>
                  <td className="thumb-cell"><FigureCell token={token} id={row?.image_id || rec?.image_id} caption={caption} /></td>
                  <td><PlaceCell regionPath={row?.region_path || u?.region_path} /><div className="sub">{pageText(u)}</div></td>
                  <td><SourceCell source={row ? row["출처 해석"] : rec.source} ai={row ? row["AI 표기"] : rec.ai_marker} quote={false} />
                    {rec?.ai_marker && <AiTypeLine ai={rec.ai_marker} />}</td>
                  <td><ContextCell ctx={row?.문맥 || u?.context} /></td>
                  <td>{u ? (
                    <>
                      {u.lesson ? `학습 ${u.lesson}` : "—"}{u.content_no ? ` · ${u.content_no}` : ""}
                      {u.element_code && <div className="sub">{u.element_code} {u.element_name}
                        {u.element_check && u.element_check !== "일치" ? ` (${u.element_check})` : ""}</div>}
                      <div className="sub">수행준거: {u.performance_criteria?.length ? u.performance_criteria.join(", ") : "없음"}</div>
                    </>
                  ) : <span className="sub">—</span>}</td>
                  <td>{rec ? (
                    <>
                      {rec.image_type?.value || rec.llm?.image_type || rec.rule_type || <span className="sub">모름</span>}
                      <div className="sub">{rec.px?.join("×")}px · {u?.dpi} DPI{u?.min_px_300dpi ? ` · 300dpi엔 ${u.min_px_300dpi.join("×")}px` : ""}</div>
                    </>
                  ) : <span className="sub">—</span>}</td>
                  <td>{row ? <ReplaceCell candidates={row["대체 후보"]} db={hasDb} hasCaption={Boolean(caption)} /> : <span className="sub">—</span>}</td>
                  <td className="verdict">
                    {row && <VerdictCell row={row} />}
                    {extra.map((x) => <div key={x} className="v-line bad"><b>{x}</b></div>)}
                    {rec?.overridden?.length > 0 && <div className="sub">사람이 고친 칸이 있어 태깅의 사람 확인에서 빠졌습니다.</div>}
                    {decisions && (row || rec?.image_id) && (
                      <DecideCell figureKey={row?.item_id || rec.image_id} imageId={row?.image_id || rec?.image_id} name={caption || "캡션 없는 그림"}
                                  mine={decisions[row?.item_id || rec.image_id]} canDecide={canDecide} onDecide={onDecide}
                                  canFix={Boolean(rec?.image_id) && ((rec.review_reasons || []).length > 0 || Object.keys(decisions[row?.item_id || rec.image_id]?.fixes || {}).length > 0)} />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        ))}
      </table>
    </div>
  );
}

// 이미지 추천(REQ-02-011) — 집필 중인 문단·수행준거를 넣으면 이미지 저작권 DB에서 실을 수 있는 그림을 권한다.
// 추천되는 것은 기관이 확정했고 재사용 범위가 확인된 그림뿐이다(서버의 v_image_recommendable). 서버가 PostgreSQL일 때만 쓸 수 있다.
import React, { useEffect, useState } from "react";

import { api } from "../lib/api.js";
import { Spinner } from "../components/Badge.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { usePageTitle } from "../lib/hooks.js";
import { copyText } from "../lib/clipboard.js";
import { licenseLabel } from "../lib/imageTerms.js";

const ANCHORS = [{ id: "recommend-input", label: "문단·수행준거" }, { id: "recommend-result", label: "추천 결과" }];
const LINK_LABEL = { criterion: "같은 수행준거", element: "같은 능력단위요소", unit: "같은 능력단위" };

function Card({ item, rank, terms }) {
  const [copied, setCopied] = useState(false);
  const name = item.title || item.captions?.[0] || item.filename || "이름 없는 그림";
  return (
    <li className="recommend-card">
      <a className="recommend-thumb" href={api.images.recommendableFileUrl(item.id)} target="_blank" rel="noreferrer" title="새 창에서 원본 보기">
        <img src={api.images.recommendableFileUrl(item.id)} alt={name} loading="lazy" />
      </a>
      <div className="recommend-body">
        <h3><span className="recommend-rank">{rank}</span>{name}</h3>
        <p className="krds-badge-wrap recommend-badges">
          {item.priority && <span className="krds-badge bg-light-success">정부 귀속 · 전체 재사용</span>}
          {item.scope_check_needed && <span className="krds-badge bg-light-warning">범위 확인 필요</span>}
          {item.link_level && <span className="krds-badge bg-light-information">{LINK_LABEL[item.link_level]}</span>}
          {item.low_quality && <span className="krds-badge bg-light-danger">화질 낮음</span>}
          {item.ai_used && <span className="krds-badge bg-light-gray">AI 활용 그림</span>}
        </p>
        <dl className="recommend-facts">
          {item.similarity != null && (
            <div><dt>그림 유사도</dt><dd>{item.similarity.toFixed(3)}<span className="meta"> · 바탕보다 {item.visual_z >= 0 ? "+" : ""}{item.visual_z.toFixed(1)}σ · 유사도 점수 {Math.round(item.visual * 100)}%</span></dd></div>
          )}
          <div><dt>맞은 핵심어</dt><dd>{item.matched.length ? item.matched.map((word) => (item.common?.includes(word) ? `${word}(후보 대부분에 있음)` : word)).join(", ") : "—"}<span className="meta"> · 점수 {item.score}</span></dd></div>
          <div><dt>라이선스</dt><dd>{licenseLabel(item, terms)}{item.license_scheme ? <span className="meta"> · {item.conditions.length ? item.conditions.join(" · ") : "조건 없음"}</span> : null}</dd></div>
          <div><dt>권리 귀속</dt><dd>{terms?.ownership?.[item.ownership] || item.ownership} · 재사용 범위 {terms?.reuse_scope?.[item.reuse_scope] || item.reuse_scope}</dd></div>
          <div><dt>출처</dt><dd>{item.source_org || item.author || "—"}{item.source_url && <> · <a href={item.source_url} target="_blank" rel="noreferrer">원 출처 열기</a></>}</dd></div>
          <div><dt>크기</dt><dd>{item.width_px ? `${item.width_px}×${item.height_px}px` : "—"}{item.has_upscaled ? " (업스케일본 있음)" : ""}
            {item.max_width_mm != null && <span className="meta"> · 300dpi로 가로 {item.max_width_mm}mm까지</span>}</dd></div>
        </dl>
        {item.notes.length > 0 && <ul className="krds-info-list recommend-notes">{item.notes.map((note, i) => <li key={i}>{note}</li>)}</ul>}
        {item.credit ? (
          <div className="recommend-credit">
            <code>{item.credit}</code>
            <button type="button" className="krds-btn small secondary" onClick={async () => { setCopied(await copyText(item.credit)); }}>
              {copied ? "복사했습니다" : "출처 문구 복사"}
            </button>
          </div>
        ) : <p className="form-hint">{item.credit_note}</p>}
      </div>
    </li>
  );
}

export default function RecommendPage() {
  usePageTitle("이미지 추천");
  const [ready, setReady] = useState(null);       // null 확인 중 | true | false(DB 없음) | "error"
  const [terms, setTerms] = useState(null);
  const [form, setForm] = useState({ text: "", unitCode: "", criterionNo: "", useLlm: true });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const set = (key) => (value) => setForm((prev) => ({ ...prev, [key]: value }));

  useEffect(() => {
    api.health().then(({ ok, data }) => {
      if (!ok) { setReady("error"); return; }
      setReady(!!data.image_db);
      if (data.image_db) api.images.terms().then((found) => { if (found.ok) setTerms(found.data); });
    });
  }, []);

  async function run(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const { ok, data, error: message } = await api.recommend.images(form);
    setBusy(false);
    if (!ok) { setError(message); return; }
    setResult(data);
    requestAnimationFrame(() => document.getElementById("recommend-result")?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }));
  }

  const unitError = form.unitCode.trim() && !/\d{10}/.test(form.unitCode) ? "숫자 10자리가 들어 있어야 합니다(예: 1203020201)." : "";
  const criterionError = form.criterionNo && !/^\d+\.\d+$/.test(form.criterionNo) ? "1.1처럼 숫자.숫자로 적습니다."
    : form.criterionNo && !form.unitCode.trim() ? "능력단위 코드를 함께 적어야 수행준거를 찾습니다." : "";
  const canRun = (form.text.trim() || form.unitCode.trim()) && !unitError && !criterionError;
  const context = result?.context;
  return (
    <>
    <Header anchors={ready === true ? (result ? ANCHORS : ANCHORS.slice(0, 1)) : []} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page image-db-page recommend-page">
      <h1 className="page-title">이미지 추천</h1>
      <p className="page-desc">
        집필 중인 문단과 수행준거를 넣으면 이미지 저작권 DB에서 실을 수 있는 그림을 권합니다.
        기관이 확정했고 재사용 범위가 확인된 그림만 나오며, 그림마다 출처·라이선스·이용조건과 원고에 넣을 출처 문구를 함께 보여 줍니다.
        그림 유사도 기능이 켜져 있으면 그림에 달린 키워드뿐 아니라 그림 자체를 문단과 견주어 찾습니다. 이 계산은 서버 안에서만 하며 외부로 보내지 않습니다.
      </p>

      {ready === null && <Spinner label="서버 상태를 확인하는 중" />}
      {ready === "error" && <PageAlert kind="danger">서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요. 계속되면 관리자에게 문의해 주세요.</PageAlert>}
      {ready === false && (
        <PageAlert kind="info">
          지금은 이미지 추천을 쓸 수 없습니다. 데이터베이스가 연결되어 있지 않습니다.{"\n"}
          관리자에게 문의해 주세요.
        </PageAlert>
      )}

      {ready === true && <>
        <section id="recommend-input" className="nav-anchor image-section">
          <h2 className="section-title">문단·수행준거</h2>
          <form className="fieldset review-form" onSubmit={run}>
            <div className="form-group form-group-wide">
              <div className="form-tit"><label htmlFor="recommend-text">집필 중인 문단</label></div>
              <div className="form-conts">
                <div className="textarea-wrap">
                  <textarea id="recommend-text" className="krds-input recommend-text" rows={6} maxLength={4000} value={form.text} aria-describedby="recommend-text-hint"
                            placeholder="그림을 넣으려는 곳의 문단을 붙여 넣으세요." onChange={(e) => set("text")(e.target.value)} />
                  <p className="textarea-count"><span className="sr-only">적은 글자 수 </span><span className="count-now">{form.text.length}</span><span className="count-total">/4000</span></p>
                </div>
              </div>
              <p className="form-hint" id="recommend-text-hint">문단 없이 능력단위 코드만 넣어도 그 능력단위에 이어진 그림을 찾습니다.</p>
            </div>
            <div className="form-group">
              <div className="form-tit"><label htmlFor="recommend-unit">능력단위 코드 <span className="meta">(선택)</span></label></div>
              <div className="form-conts">
                <input id="recommend-unit" type="text" className={`krds-input${unitError ? " is-error" : ""}`} maxLength={30} value={form.unitCode} placeholder="예: LM1203020201"
                       aria-invalid={unitError ? "true" : undefined} aria-describedby="recommend-unit-hint" onChange={(e) => set("unitCode")(e.target.value)} />
              </div>
              {unitError ? <p className="form-hint-invalid" id="recommend-unit-hint" role="alert">{unitError}</p>
                         : <p className="form-hint" id="recommend-unit-hint">LM을 붙여도, 숫자 10자리만 적어도 됩니다.</p>}
            </div>
            <div className="form-group">
              <div className="form-tit"><label htmlFor="recommend-criterion">수행준거 번호 <span className="meta">(선택)</span></label></div>
              <div className="form-conts">
                <input id="recommend-criterion" type="text" inputMode="decimal" className={`krds-input${criterionError ? " is-error" : ""}`} maxLength={10} value={form.criterionNo} placeholder="예: 1.1"
                       aria-invalid={criterionError ? "true" : undefined} aria-describedby="recommend-criterion-hint" onChange={(e) => set("criterionNo")(e.target.value.trim())} />
              </div>
              {criterionError ? <p className="form-hint-invalid" id="recommend-criterion-hint" role="alert">{criterionError}</p>
                              : <p className="form-hint" id="recommend-criterion-hint">능력단위 코드와 함께 적습니다.</p>}
            </div>
            <div className="form-group form-group-wide">
              <div className="form-conts krds-check-area">
              <div className="krds-form-check">
                <input type="checkbox" id="recommend-llm" checked={form.useLlm} onChange={(e) => set("useLlm")(e.target.checked)} />
                <label htmlFor="recommend-llm"><span className="check-text">생성형 AI로 문단을 요약해 핵심어 뽑기
                  <span className="check-hint">켜면 위 문단과 수행준거 글이 외부 생성형 AI 서비스로 전송됩니다(관리자가 외부 전송을 허용해 둔 경우에만). 끄면 규칙으로 핵심어를 뽑습니다.</span></span></label>
              </div>
              </div>
            </div>
            <div className="form-group form-group-wide form-actions">
              {error && <PageAlert kind="danger">{error}</PageAlert>}
              <div className="run-buttons image-actions">
                <button type="submit" className="krds-btn large primary" disabled={busy || !canRun}>{busy ? "찾는 중" : "그림 추천"}</button>
              </div>
            </div>
          </form>
        </section>

        {/* 추천을 한 번 돌린 뒤에만 보인다 */}
        {result && (
        <section id="recommend-result" className="nav-anchor image-section" aria-live="polite">
          <h2 className="section-title">추천 결과<span className="meta"> {result.items.length}건 (후보 {result.total_candidates}건 가운데)</span></h2>
          <>
            <div className="recommend-context">
              <p className="recommend-method">
                <span className={`krds-badge ${context.method === "llm" ? "bg-light-information" : "bg-light-gray"}`}>
                  {context.method === "llm" ? `생성형 AI 요약${context.model ? ` · ${context.model}` : ""}` : "규칙으로 뽑은 핵심어"}</span>
                {context.note && <span className="meta"> {context.note}</span>}
              </p>
              {context.summary && <p><strong>요약</strong> {context.summary}</p>}
              <div className="recommend-keywords"><strong>핵심어</strong>
                {context.keywords.length ? <span className="krds-tag-wrap small">{context.keywords.map((word) => <span key={word} className="krds-btn-tag">{word}</span>)}</span> : " —"}</div>
              <p className="recommend-method">
                <span className={`krds-badge ${result.embedding.used ? "bg-light-information" : "bg-light-gray"}`}>
                  {result.embedding.used ? `그림 유사도 사용 · ${result.embedding.model}` : "그림 유사도 사용 안 함"}</span>
                <span className="meta"> {result.embedding.used
                  ? `견준 글: “${result.embedding.query}”${result.embedding.note ? ` · ${result.embedding.note}` : ""}`
                  : `핵심어와 수행준거 연결로만 찾았습니다. ${result.embedding.note}`}</span>
              </p>
              {context.dropped.length > 0 && <p className="form-hint">생성형 AI가 제시했지만 문단에 없어 쓰지 않은 낱말: {context.dropped.join(", ")}</p>}
              {result.criterion.criterion_no && (result.criterion.found
                ? <p><strong>수행준거 {result.criterion.criterion_no}</strong> {result.criterion.text}<span className="meta"> ({result.criterion.unit_name})</span></p>
                : <p className="form-hint">수행준거 {result.criterion.criterion_no}의 글을 NCS 목록에서 찾지 못했습니다. 번호가 같은 연결만 봅니다.</p>)}
            </div>
            {result.guidance.length > 0 && <PageAlert kind="info">{result.guidance.join("\n")}</PageAlert>}
            {result.truncated && <p className="form-hint">후보가 많아 최근 확정된 {result.total_candidates}건만 보았습니다.</p>}
            {result.items.length > 0 && (
              <ol className="recommend-list">
                {result.items.map((item, index) => <Card key={item.id} item={item} rank={index + 1} terms={terms} />)}
              </ol>
            )}
            {result.items.length > 0 && (
              <p className="form-hint">출처 문구는 ‘복사’해서 원고의 그림 아래 출처 줄에 붙여 넣습니다. 그림을 실은 뒤에는 사진·삽화 수록 현황 목록에도 올려야 합니다.</p>
            )}
          </>
        </section>
        )}
      </>}
      <TopButton />
    </main>
    <Footer />
    </>
  );
}

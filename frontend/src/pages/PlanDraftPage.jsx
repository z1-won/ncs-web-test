// 개발계획서 작성(REQ-02-001) — 세분류를 고르고 능력단위를 체크하면 T01 양식에 NCS 정보를 채운 초안 hwpx를 내려받는다.
// 초안은 서버가 바로 ①~⑩ 점검(ncs_plan)을 돌려 요약을 함께 준다(응답 본문의 check). 요소·수행준거 표(ncs_elements.tsv)에 있는 세분류만 고를 수 있다.
// 이어서 작성한 개발계획서 파일의 점검(①~⑩, 최종본/1차본)도 이 페이지에서만 한다 — 원고 검수 페이지의 선택 목록에는 없다.
import React, { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../lib/api.js";
import { ComponentResult } from "../components/AllResults.jsx";
import { FileSlot } from "../components/FileSlot.jsx";
import { Badge, Spinner } from "../components/Badge.jsx";
import { KrdsSelect } from "../components/KrdsSelect.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { ResultHead } from "../components/ResultHead.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { RawJson } from "../components/RawJson.jsx";
import { SheetTable } from "../components/Tables.jsx";
import { usePageTitle } from "../lib/hooks.js";
import { PLAN_CHECK, overallVerdict } from "../lib/checks.js";
import { formatDate } from "../lib/format.jsx";

const ANCHORS = [
  { id: "plan-form", label: "초안 만들기" },
  { id: "plan-check", label: "초안 점검" },
  { id: "plan-review", label: "개발계획서 점검" },
];

const STAGES = [["final", "최종본 (개발기관)"], ["draft", "1차본 (직능연)"]];
const MAX_OPTIONS = 100;   // 세분류 목록에 한 번에 펴는 수 — 넘으면 검색어를 더 적게 한다

export default function PlanDraftPage() {
  usePageTitle("개발계획서 작성");
  const [catalog, setCatalog] = useState(null);     // /api/plan/subclasses 응답
  const [loadError, setLoadError] = useState(null);
  const [duty, setDuty] = useState("");
  const [picked, setPicked] = useState({});          // 능력단위 코드 → true
  const [agency, setAgency] = useState("");
  const [english, setEnglish] = useState("");
  const [people, setPeople] = useState({});          // 코드 → { writer, reviewer }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [check, setCheck] = useState(null);          // 초안 점검 요약 [{번호, 검수결과, 비고}]
  const [made, setMade] = useState(null);            // 마지막으로 만든 세분류·개수
  const [query, setQuery] = useState("");            // 세분류 검색어
  const [detail, setDetail] = useState(null);        // 고른 세분류의 상세(/api/plan/subclasses/{duty}) — 능력단위·요소 수·받아 온 날
  const [fetching, setFetching] = useState(false);   // NCS에서 기준정보를 받아 오는 중
  const [fetchError, setFetchError] = useState(null);
  const [fetchNote, setFetchNote] = useState(null);  // 받아 온 결과 안내(처음 받음 / 달라진 능력단위)
  const loadSeq = useRef(0);                         // 세분류 상세 요청의 순번
  // 개발계획서 점검 — 작성한(또는 받은) 개발계획서 파일 하나를 올려 ①~⑩을 점검한다
  const [reviewFile, setReviewFile] = useState(null);
  const [stage, setStage] = useState("final");       // 점검 단계: final 최종본 / draft 1차본
  const [reviewing, setReviewing] = useState(false);
  const [reviewError, setReviewError] = useState(null);
  const [review, setReview] = useState(null);        // { data: /api/review 응답(check=plan), stage: 그때 고른 단계 }
  const aborter = useRef(null);                      // 진행 중 점검의 AbortController — 취소 버튼

  useEffect(() => {
    api.plan.subclasses().then(({ ok, data, error: message }) => {
      if (!ok) { setLoadError(message); return; }
      setCatalog(data);
      // 처음에는 바로 초안을 만들 수 있는(기준정보를 받아 둔) 세분류를 고른다. 없으면 비워 두고 검색해서 고르게 한다
      const first = data.subclasses?.find((s) => s.ready);
      if (first) setDuty(first.duty);
    });
  }, []);

  // 고른 세분류의 능력단위(요소·수행준거 수)를 읽는다. 아직 받아 두지 않은 세분류면 서버가 NCS에서 받아 온다(받을 수 있는 서버일 때).
  async function loadDetail(code, { refresh = false } = {}) {
    const mine = ++loadSeq.current;   // 받아 오는 사이에 다른 세분류를 고르면 늦게 온 응답은 버린다
    const stale = () => mine !== loadSeq.current;
    setFetchError(null); setFetchNote(null); setFetching(false);
    if (!refresh) {
      const found = await api.plan.subclass(code);
      if (stale()) return;
      if (!found.ok) { setDetail(null); setFetchError(found.error); return; }
      if (found.data.ready || !catalog?.can_fetch) { setDetail(found.data); return; }
      setDetail(found.data);   // 받아 오는 동안 분류 이름은 보이게
    }
    setFetching(true);
    const { ok, data, error: message } = await api.plan.fetchSubclass(code, refresh);
    if (stale()) return;
    setFetching(false);
    if (!ok) { setFetchError(message); return; }
    setDetail(data);
    setCatalog((prev) => prev && { ...prev, subclasses: prev.subclasses.map((s) => (s.duty === code ? { ...s, ready: true, units: data.units.length } : s)) });
    const change = data.변화;
    if (data.처음) setFetchNote(`NCS에서 능력단위 ${data.units.length}개의 요소와 수행준거를 받아 왔습니다.`);
    else if (change) {
      const parts = [["추가", change.추가], ["삭제", change.삭제], ["변경", change.변경]].filter(([, list]) => list.length)
        .map(([name, list]) => `${name} ${list.length}개(${list.join(", ")})`);
      setFetchNote(parts.length ? `NCS에서 다시 받아 왔습니다. 달라진 능력단위: ${parts.join(", ")}` : "NCS에서 다시 받아 왔습니다. 달라진 내용이 없습니다.");
    }
  }
  useEffect(() => {
    if (!duty || !catalog) return;
    setDetail(null);
    loadDetail(duty);
    // 세분류를 바꿀 때만 다시 읽는다(catalog는 목록이 처음 올 때와 받아 온 뒤 표시만 바뀐다)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [duty, !!catalog]);

  const subclass = detail?.ready && detail.duty === duty ? detail : null;   // 초안을 만들 수 있는 상태의 세분류
  useEffect(() => {   // 세분류를 바꾸면 능력단위는 전부 선택
    if (!subclass) return;
    setPicked(Object.fromEntries(subclass.units.map((u) => [u.code, true])));
    setCheck(null);
  }, [subclass]);

  // 세분류는 천 개가 넘어 검색해서 고른다: 이름·코드·분류 이름에 검색어가 든 것만, 받아 둔 세분류를 먼저. 목록은 MAX_OPTIONS개까지만 편다
  const matches = useMemo(() => {
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const all = catalog?.subclasses || [];
    const hit = words.length
      ? all.filter((s) => { const text = `${s.name} ${s.duty} ${Object.values(s.classes || {}).join(" ")}`.toLowerCase(); return words.every((w) => text.includes(w)); })
      : all;
    return [...hit].sort((a, b) => (a.ready === b.ready ? 0 : a.ready ? -1 : 1));
  }, [catalog, query]);
  const shown = matches.slice(0, MAX_OPTIONS);
  const current = catalog?.subclasses?.find((s) => s.duty === duty);
  const options = [...(current && !shown.some((s) => s.duty === duty) ? [current] : []), ...shown]
    .map((s) => ({ value: s.duty, label: `${s.name} (${s.duty}), 능력단위 ${s.units}개${s.ready ? "" : ", NCS에서 받아 와야 함"}` }));
  const chosen = subclass ? subclass.units.filter((u) => picked[u.code]) : [];

  async function submit(e) {
    e.preventDefault();
    if (!subclass || !chosen.length) return;
    setBusy(true); setError(null); setCheck(null);
    const writers = {}, reviewers = {};
    chosen.forEach((u) => {
      if (people[u.code]?.writer) writers[u.code] = people[u.code].writer;
      if (people[u.code]?.reviewer) reviewers[u.code] = people[u.code].reviewer;
    });
    const { ok, error: message, check: summary } = await api.plan.draft({
      duty: subclass.duty, units: chosen.map((u) => u.code), agency, english, writers, reviewers,
    });
    setBusy(false);
    if (!ok) { setError(message); return; }
    setCheck(summary);
    setMade({ name: subclass.name, duty: subclass.duty, units: chosen.length, elements: chosen.reduce((n, u) => n + u.elements, 0) });
    setTimeout(() => document.getElementById("plan-check")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  async function runReview(e) {
    e.preventDefault();
    if (!reviewFile) { setReviewError("점검할 개발계획서 파일(hwp, hwpx)을 선택해 주세요."); return; }
    setReviewing(true); setReviewError(null); setReview(null);
    const controller = new AbortController();
    aborter.current = controller;
    const { ok, data, error: message, aborted } = await api.review({ check: PLAN_CHECK, files: [reviewFile], roles: [PLAN_CHECK], stage, signal: controller.signal });
    aborter.current = null;
    setReviewing(false);
    if (aborted) return;
    if (!ok) { setReviewError(message); return; }
    setReview({ data, stage });
    setTimeout(() => document.getElementById("plan-review-result")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  const allPicked = !!subclass && chosen.length === subclass.units.length;
  const somePicked = chosen.length > 0 && !allPicked;
  function pickAll(on) {
    if (subclass) setPicked(Object.fromEntries(subclass.units.map((u) => [u.code, on])));
  }
  const verdict = check ? overallVerdict(check.map((row) => row.검수결과)) : null;
  const missing = [
    ...(!agency.trim() ? ["개발기관명"] : []),
    ...(!english.trim() ? ["영문 세분류명"] : []),
    ...(chosen.some((u) => !(people[u.code]?.writer || "").trim()) ? ["담당 집필진"] : []),
    ...(chosen.some((u) => !(people[u.code]?.reviewer || "").trim()) ? ["담당 검토진"] : []),
  ];

  function setPerson(code, key, value) {
    setPeople((prev) => ({ ...prev, [code]: { ...(prev[code] || {}), [key]: value } }));
  }

  return (
    <>
    <Header anchors={ANCHORS} hasHistory={false} hasResult={!!check} />
    <main id="container" className="inner page">
      <h1 className="page-title">NCS 학습모듈 개발계획서 작성 지원</h1>
      <p className="page-desc">
        세분류를 고르면 NCS 능력단위, 요소, 수행준거를 개발계획서 양식(T01)에 자동으로 채운 초안(hwpx)을 내려받습니다.
        학습 내용명, 선수학습 등 집필자가 정할 칸은 비워 두며, 초안은 바로 개발계획서 점검 ①~⑩을 거칩니다.
        이어서 작성한 개발계획서는 아래 ‘개발계획서 점검’에 올려 다시 점검합니다.
      </p>

      <PageAlert kind="danger">{loadError}</PageAlert>
      {catalog && !catalog.subclasses?.length && (
        <p className="empty">NCS 세분류 목록을 읽지 못했습니다. 관리자에게 문의해 주세요.</p>
      )}

      {/* 입력 묶음은 구획 셋: 세분류 선택 → 개발계획서에 적을 내용 → 실행(다른 화면과 같은 구조). 구획 안에서만 3열 격자(.form-section-grid)를 쓴다 */}
      <form id="plan-form" className="fieldset review-form is-sectioned nav-anchor" onSubmit={submit}>
        <div className="form-section" role="group" aria-labelledby="plan-duty-title">
        <h2 className="form-section-title" id="plan-duty-title">세분류 선택</h2>
        <div className="form-section-grid">
        <div className="form-group">
          <div className="form-tit"><label htmlFor="duty-query">세분류 검색</label></div>
          <div className="form-conts">
            <input id="duty-query" type="search" className="krds-input" value={query} onChange={(e) => setQuery(e.target.value)}
                   placeholder="예: 숙박, 12030202" aria-describedby="duty-query-hint" />
          </div>
          <p className="form-hint" id="duty-query-hint">
            세분류 이름, 코드, 분류 이름으로 찾습니다. {query.trim() ? `찾은 세분류 ${matches.length}개` : `전체 ${matches.length}개`}
            {matches.length > MAX_OPTIONS ? ` 가운데 ${MAX_OPTIONS}개만 목록에 보입니다. 검색어를 더 적어 주세요.` : "."}
          </p>
        </div>

        {/* 세분류 이름이 길어 두 열을 쓰고 셀렉트는 칸 폭 전체 */}
        <div className="form-group form-group-span2 is-full">
          <div className="form-tit"><label htmlFor="duty">세분류</label></div>
          <div className="form-conts">
            <KrdsSelect id="duty" value={duty} options={options} onChange={setDuty} title="세분류 선택" describedBy="duty-hint" />
          </div>
          <p className="form-hint" id="duty-hint">
            {detail ? `${detail.classes?.대분류 || ""} › ${detail.classes?.중분류 || ""} › ${detail.classes?.소분류 || ""} › ${detail.name}` : "세분류를 선택해 주세요."}
          </p>
        </div>

        {/* NCS 기준정보 — 이 세분류의 요소와 수행준거를 언제 받았는지, 다시 받기. 아직 없는 세분류는 고르는 즉시 받아 온다 */}
        <div className="form-group form-group-wide plan-refdata" id="plan-refdata">
          <div className="form-tit"><span>NCS 기준정보</span></div>
          <div className="form-conts">
            {fetching ? <Spinner label="NCS에서 요소와 수행준거를 받아 오는 중" />
              : subclass ? (
                <p className="plan-refdata-line">
                  <span>{subclass.fetched ? `${subclass.fetched}에 NCS에서 받아 온 자료입니다.` : "프로그램에 들어 있는 기본 자료입니다(받아 온 날 기록 없음)."}</span>
                  {catalog?.can_fetch && (
                    <button type="button" className="krds-btn small tertiary" disabled={busy} onClick={() => loadDetail(duty, { refresh: true })}>NCS에서 다시 받아 오기</button>
                  )}
                </p>
              ) : detail && !detail.ready && !fetchError ? (
                <p className="plan-refdata-line"><span>이 세분류는 요소와 수행준거를 아직 받아 두지 않았습니다. {catalog?.can_fetch ? "" : "이 서버는 NCS에서 받아 오도록 설정되어 있지 않습니다. 관리자에게 문의해 주세요."}</span></p>
              ) : null}
            <PageAlert kind="danger">{fetchError && (
              <>
                <p>{fetchError}</p>
                {catalog?.can_fetch && duty && <button type="button" className="krds-btn small tertiary" onClick={() => loadDetail(duty, { refresh: !!subclass })}>다시 시도</button>}
              </>
            )}</PageAlert>
            <PageAlert kind="success">{fetchNote}</PageAlert>
          </div>
          <p className="form-hint">NCS가 개정되면 [NCS에서 다시 받아 오기]로 최신 내용을 받습니다. 달라진 능력단위를 알려 줍니다.</p>
        </div>
        </div>
        </div>

        <div className="form-section" role="group" aria-labelledby="plan-content-title" aria-describedby="plan-content-desc">
        <h2 className="form-section-title" id="plan-content-title">개발계획서에 적을 내용</h2>
        <p className="form-section-desc" id="plan-content-desc">개발기관명과 영문 세분류명은 최종본에 꼭 적어야 하는 항목입니다(점검 ⑧). 초안 점검은 1차본(직능연) 기준이라 비워 두어도 됩니다.</p>
        <div className="form-section-grid">
        <div className="form-group">
          <div className="form-tit"><label htmlFor="agency">개발기관명 <span className="required"><i aria-hidden="true">*</i><span className="sr-only">필수</span></span></label></div>
          <div className="form-conts">
            <input id="agency" type="text" className="krds-input" placeholder="예: (사)한국호텔전문경영인협회" value={agency} onChange={(e) => setAgency(e.target.value)} aria-describedby="agency-hint" aria-required="true" />
          </div>
          <p className="form-hint" id="agency-hint">초안에서는 비워 두어도 됩니다.</p>
        </div>

        <div className="form-group">
          <div className="form-tit"><label htmlFor="english">영문 세분류명 <span className="required"><i aria-hidden="true">*</i><span className="sr-only">필수</span></span></label></div>
          <div className="form-conts">
            <input id="english" type="text" className="krds-input" placeholder="예: Rooms Operation" value={english} onChange={(e) => setEnglish(e.target.value)} aria-describedby="english-hint" aria-required="true" />
          </div>
          <p className="form-hint" id="english-hint">NCS 누리집 ‘환경 분석’의 영문명을 적습니다.</p>
        </div>

        {subclass && (
          <div className="form-group form-group-wide">
            <div className="form-tit"><span id="units-title">능력단위 ({chosen.length}/{subclass.units.length})와 담당 집필진, 검토진 <span className="required"><i aria-hidden="true">*</i><span className="sr-only">필수</span></span></span></div>
            <div className="form-conts">
              <div className="krds-table-wrap">
                <table className="tbl col data plan-units" aria-labelledby="units-title">
                  <caption>초안에 넣을 능력단위 선택과 담당자</caption>
                  <colgroup>
                    <col className="col-check" /><col /><col className="col-level" /><col className="col-count" /><col className="col-person" /><col className="col-person" />
                  </colgroup>
                  <thead>
                    <tr>
                      <th scope="col">
                        <div className="krds-check-area">
                          <div className="krds-form-check">
                            <input type="checkbox" id="unit-all" checked={allPicked} ref={(el) => { if (el) el.indeterminate = somePicked; }} onChange={(e) => pickAll(e.target.checked)} />
                            <label htmlFor="unit-all"><span className="sr-only">능력단위 전체 선택</span></label>
                          </div>
                        </div>
                      </th>
                      <th scope="col">능력단위</th><th scope="col">수준</th><th scope="col">요소 / 수행준거</th><th scope="col">담당 집필진 <span className="required"><i aria-hidden="true">*</i><span className="sr-only">필수</span></span></th><th scope="col">담당 검토진 <span className="required"><i aria-hidden="true">*</i><span className="sr-only">필수</span></span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {subclass.units.map((u) => (
                      <tr key={u.code}>
                        <td>
                          <div className="krds-check-area">
                            <div className="krds-form-check">
                              <input type="checkbox" id={`unit-${u.code}`} checked={!!picked[u.code]} onChange={(e) => setPicked({ ...picked, [u.code]: e.target.checked })} />
                              <label htmlFor={`unit-${u.code}`}><span className="sr-only">{u.name} 선택</span></label>
                            </div>
                          </div>
                        </td>
                        <td><strong>{u.name}</strong><br /><span className="code">{u.code}</span></td>
                        <td>{u.level ?? "-"}</td>
                        <td>{u.elements} / {u.criteria}</td>
                        <td><input type="text" className="krds-input small" aria-label={`${u.name} 담당 집필진`} value={people[u.code]?.writer || ""} onChange={(e) => setPerson(u.code, "writer", e.target.value)} /></td>
                        <td><input type="text" className="krds-input small" aria-label={`${u.name} 담당 검토진`} value={people[u.code]?.reviewer || ""} onChange={(e) => setPerson(u.code, "reviewer", e.target.value)} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        </div>
        </div>

        {/* form-group: 버튼 아래 안내(form-hint)가 KRDS 도움말 모양을 쓰도록 */}
        <div className="form-group form-actions">
          <div className="run-buttons">
            <button className="krds-btn primary large" type="submit" disabled={busy || !chosen.length}>
              {busy ? "만드는 중" : "초안 만들어 내려받기"}
            </button>
          </div>
          {missing.length > 0 && !busy && (
            <p className="form-hint" id="missing-hint">비어 있는 필수 항목: {missing.join(", ")}. 초안(1차본)에서는 비워 둘 수 있고, 최종본 점검 ⑧에서 확인합니다.</p>
          )}
          <PageAlert kind="danger">{error}</PageAlert>
        </div>
      </form>

      <div id="plan-check" className="results-anchor nav-anchor" />
      {busy && <ResultHead status={<Spinner label="초안을 만들고 점검하는 중" />} />}
      {check && made && (
        <section>
          <ResultHead
            status={verdict ? <Badge value={verdict} large /> : <span className="krds-badge large bg-light-gray">결과 없음</span>}
            meta={`${made.name} (${made.duty}), 능력단위 ${made.units}개, 요소 ${made.elements}개, 초안 점검 ①~⑩`}
            downloads={
              <>
                <span className="meta">초안 파일은 내려받기 폴더에 저장됐습니다</span>
                <button type="button" className="krds-btn small tertiary" disabled={busy} onClick={submit} title="같은 설정으로 초안을 다시 만들어 내려받기">다시 내려받기</button>
              </>
            }
          />
          <h2 className="section-title">초안 점검 확인서</h2>
          <p className="meta section-desc">1차본(직능연) 기준 점검입니다. 학습 내용명, 영문명, 집필진 등 기관이 적는 칸은 해당 없음으로 둡니다. 내려받은 hwpx를 한글에서 열어 이어서 작성하고, 완성본은 아래 ‘개발계획서 점검’에서 ‘최종본’으로 다시 점검하세요.</p>
          <SheetTable sheet={check} findings={[]} />
        </section>
      )}
      {/* ── 개발계획서 점검 ── 작성한 파일을 올려 ①~⑩ 점검. 예전에는 원고 검수 페이지의 선택 목록에 있었다 */}
      <section id="plan-review" className="nav-anchor plan-review">
        <h2 className="section-title">개발계획서 점검</h2>
        <p className="meta section-desc">작성한 개발계획서(hwp, hwpx)를 올리면 점검 ①~⑩을 실행합니다. 원고는 필요하지 않습니다. 1차본은 학습모듈명, 영문명, 기관명, 집필진, 학습 내용명이 비어 있어도 부적합으로 보지 않습니다. 이 칸들은 최종 단계에서 기관이 적습니다.</p>
        <form className="fieldset review-form is-sectioned" onSubmit={runReview}>
          <div className="form-section-grid">
          {/* 다른 페이지의 업로드 칸과 같은 부품 — 파일 선택, 끌어다 놓기, 고른 파일 표시와 삭제 */}
          <FileSlot id="plan-file" label="개발계획서 파일" required accept=".hwp,.hwpx" file={reviewFile} disabled={reviewing}
                    onChange={(picked) => { setReviewFile(picked); setReviewError(null); }} />

          <div className="form-group">
            <div className="form-tit"><span id="plan-stage-label">점검 단계</span></div>
            <div className="form-conts plan-stage" role="radiogroup" aria-labelledby="plan-stage-label">
              {STAGES.map(([value, label]) => (
                <div className="krds-form-check" key={value}>
                  <input type="radio" id={`plan-stage-${value}`} name="plan-stage" value={value} checked={stage === value} onChange={() => setStage(value)} />
                  <label htmlFor={`plan-stage-${value}`}>{label}</label>
                </div>
              ))}
            </div>
            <p className="form-hint">1차본은 기관이 적는 칸이 비어 있어도 됩니다.</p>
          </div>
          </div>

          <div className="form-actions">
            <div className="run-buttons">
              <button className="krds-btn primary large" type="submit" disabled={reviewing || !reviewFile}>
                {reviewing ? "점검하는 중" : "점검 실행"}
              </button>
              {reviewing && <button className="krds-btn tertiary large" type="button" onClick={() => aborter.current?.abort()}>취소</button>}
            </div>
            <PageAlert kind="danger">{reviewError}</PageAlert>
          </div>
        </form>

        <div id="plan-review-result" className="results-anchor nav-anchor" />
        {reviewing && <ResultHead status={<Spinner label="개발계획서를 점검하는 중" />} />}
        {review && (
          <section aria-live="polite">
            <ResultHead
              status={<Badge value={review.data.요약.검수결과} large />}
              meta={[review.data.module_code, "개발계획서 점검 ①~⑩", STAGES.find(([value]) => value === review.stage)?.[1],
                     review.data.created_at && formatDate(review.data.created_at)].filter(Boolean).join(", ")}
              downloads={review.data.id
                ? <a href={api.reviews.zipUrl(review.data.id)} className="krds-btn small tertiary" title="결과 파일 내려받기(ZIP)">결과 파일 내려받기(ZIP)</a>
                : review.data.저장?.zip ? <span className="meta">저장: {review.data.저장.zip}</span> : null}
            />
            <h3 className="section-title">개발계획서 점검 확인서</h3>
            <ComponentResult result={review.data} showSave={false} />
            <RawJson data={review.data} title="원본 데이터 보기(개발자용)" />
          </section>
        )}
      </section>

      <TopButton />
    </main>
    <Footer />
    </>
  );
}

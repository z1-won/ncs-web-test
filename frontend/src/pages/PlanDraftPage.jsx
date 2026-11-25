// 개발계획서 작성(REQ-02-001) — 세분류를 고르고(NCS 누리집과 같은 분야별·키워드·코드 검색, components/NcsPicker) 능력단위를 체크하면 T01 양식에 NCS 정보를 채운 초안 hwpx를 내려받는다.
// 초안은 서버가 바로 ①~⑩ 점검(ncs_plan)을 돌려 요약을 함께 준다(응답 본문의 check). 요소·수행준거 표(ncs_elements.tsv)에 있는 세분류만 고를 수 있다.
// 이어서 작성한 개발계획서 파일의 점검(①~⑩, 최종본/1차본)도 이 페이지에서만 한다 — 원고 검수 페이지의 선택 목록에는 없다.
// 개선 계획서면 능력단위마다 개선 유형과 개선 전 능력단위번호를 적어 개선 양식(변경 전·후 대조표 + 개선 유형 열)에 채운다. 끝의 '계획서 비교'는 계획서 둘을 칸별로 견준다(/api/plan/compare).
import React, { useEffect, useRef, useState } from "react";

import { api } from "../lib/api.js";
import { ComponentResult } from "../components/AllResults.jsx";
import { FileSlot } from "../components/FileSlot.jsx";
import { Badge, Spinner } from "../components/Badge.jsx";
import { NcsPicker } from "../components/NcsPicker.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { ResultHead } from "../components/ResultHead.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { RawJson } from "../components/RawJson.jsx";
import { SheetTable } from "../components/Tables.jsx";
import { usePageTitle } from "../lib/hooks.js";
import { PLAN_CHECK, overallVerdict } from "../lib/checks.js";
import { formatDate } from "../lib/format.jsx";

// 이 화면의 도구 넷 — 한 번에 하나만 보인다(탭). 전에는 넷이 세로로 쌓여 화면이 다른 도구 화면의 두세 배 길었다.
// 탭을 바꿔도 다른 탭에 넣어 둔 파일과 결과는 그대로 남는다(감추기만 한다). 주소 끝의 #plan-review 등으로 그 탭을 바로 열 수 있다
const TOOLS = [["draft", "초안 만들기", "plan-form"], ["review", "개발계획서 점검", "plan-review"], ["type", "개선 유형 판단 자료", "plan-type"], ["compare", "계획서 비교", "plan-compare"]];

const KINDS = [["신규", "신규 개발"], ["개선", "개선"]];
// 개선 유형(F05 최소개선 유형 세부 지침, F21 작성 매뉴얼). 정하는 것은 사람(직능연 협의)이고 화면은 적어 둘 뿐이다
// 기본값은 없다 — 유형은 직능연이 대상 학습모듈을 검토해 분류하고(F21), 바꿀 때는 직능연과 협의한다(F05 2항). 화면이 대신 정하지 않는다
const TYPES = ["기존 개선", "최소개선", "양식 편집", "신규 개발"].map((name) => ({ value: name, label: name }));
const DIFF_BADGE = { "다름": "bg-light-danger", "띄어쓰기만 다름": "bg-light-warning", "기준에만 있음": "bg-light-gray", "대상에만 있음": "bg-light-gray" };
const AREAS = ["기본 정보", "변경 전·후 대조표", "총괄표", "위치", "모듈 표"];

const STAGES = [["final", "최종본 (개발기관)"], ["draft", "1차본 (직능연)"]];

export default function PlanDraftPage() {
  usePageTitle("개발계획서 작성");
  const [catalog, setCatalog] = useState(null);     // /api/plan/subclasses 응답
  const [loadError, setLoadError] = useState(null);
  const [tool, setTool] = useState(() => (TOOLS.find(([, , id]) => `#${id}` === window.location.hash) || TOOLS[0])[0]);
  const [duty, setDuty] = useState("");
  const [picked, setPicked] = useState({});          // 능력단위 코드 → true
  const [agency, setAgency] = useState("");
  const [english, setEnglish] = useState("");
  const [people, setPeople] = useState({});          // 코드 → { writer, reviewer, type(개선 유형), previous(개선 전 능력단위번호) }
  const [kind, setKind] = useState("신규");          // 신규 / 개선 — 개선이면 개선 양식에 채운다
  // 계획서 비교 — 기준(최종결과 예시나 앞 판본)과 대상(지금 계획서)
  const [baseFile, setBaseFile] = useState(null);
  const [targetFile, setTargetFile] = useState(null);
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState(null);
  const [compared, setCompared] = useState(null);
  const [onlyKind, setOnlyKind] = useState("");      // 비교 결과에서 볼 차이 종류("" 전부)
  const [applyPick, setApplyPick] = useState({});    // 비교 결과 행 번호 → 반영할지
  const [applying, setApplying] = useState(false);
  const [applyNote, setApplyNote] = useState(null);  // { report } | { error }
  // 개선 유형 판단 자료 — 기존 학습모듈 원고의 내용 수정 신호
  const [signalFile, setSignalFile] = useState(null);
  const [signalCode, setSignalCode] = useState("");
  const [signalBusy, setSignalBusy] = useState(false);
  const [signalError, setSignalError] = useState(null);
  const [signals, setSignals] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [check, setCheck] = useState(null);          // 초안 점검 요약 [{번호, 검수결과, 비고}]
  const [made, setMade] = useState(null);            // 마지막으로 만든 세분류·개수
  const wantUnit = useRef("");                       // 코드 검색에서 능력단위 번호까지 적어 고른 경우 그 두 자리 — 세분류가 열리면 그 능력단위만 체크한다
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
      setCatalog(data);      // 세분류는 미리 골라 두지 않는다 — 분야별 검색이 대분류 고르기부터 시작한다
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
    if (data.처음) setFetchNote(`NCS에서 능력단위 ${data.units.length}개의 요소와 수행준거를 불러왔습니다.`);
    else if (change) {
      const parts = [["추가", change.추가], ["삭제", change.삭제], ["변경", change.변경]].filter(([, list]) => list.length)
        .map(([name, list]) => `${name} ${list.length}개(${list.join(", ")})`);
      setFetchNote(parts.length ? `NCS에서 다시 불러왔습니다. 달라진 능력단위: ${parts.join(", ")}` : "NCS에서 다시 불러왔습니다. 달라진 내용이 없습니다.");
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
  useEffect(() => {   // 세분류를 바꾸면 능력단위는 전부 선택(코드 검색에서 능력단위 번호를 적었으면 그것만)
    if (!subclass) return;
    applyPicked(subclass);
    setCheck(null);
  }, [subclass]);

  function pickDuty(code, unitNo = "") {
    wantUnit.current = unitNo;
    if (code === duty && subclass) applyPicked(subclass);     // 같은 세분류를 능력단위 번호만 바꿔 다시 고른 경우
    setDuty(code);
  }
  // 세분류가 열리면 능력단위는 전부 선택. 코드 검색에서 능력단위 번호까지 적었으면 그 능력단위만
  function applyPicked(found) {
    const only = wantUnit.current && found.units.some((u) => u.code.slice(8, 10) === wantUnit.current) ? wantUnit.current : "";
    setPicked(Object.fromEntries(found.units.map((u) => [u.code, only ? u.code.slice(8, 10) === only : true])));
  }
  const chosen = subclass ? subclass.units.filter((u) => picked[u.code]) : [];

  async function submit(e) {
    e.preventDefault();
    if (!subclass || !chosen.length) return;
    setBusy(true); setError(null); setCheck(null);
    const writers = {}, reviewers = {}, types = {}, previous = {};
    chosen.forEach((u) => {
      if (people[u.code]?.writer) writers[u.code] = people[u.code].writer;
      if (people[u.code]?.reviewer) reviewers[u.code] = people[u.code].reviewer;
      if (improve) {
        if (people[u.code]?.type) types[u.code] = people[u.code].type;
        if ((people[u.code]?.previous || "").trim()) previous[u.code] = people[u.code].previous.trim();
      }
    });
    const { ok, error: message, check: summary } = await api.plan.draft({
      duty: subclass.duty, units: chosen.map((u) => u.code), agency, english, writers, reviewers, kind, types, previous,
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

  async function runCompare(e) {
    e.preventDefault();
    if (!baseFile || !targetFile) { setCompareError("기준 계획서와 대상 계획서를 모두 선택해 주세요."); return; }
    setComparing(true); setCompareError(null); setCompared(null); setOnlyKind("");
    const { ok, data, error: message } = await api.plan.compare(baseFile, targetFile);
    setComparing(false);
    if (!ok) { setCompareError(message); return; }
    setCompared(data);
    // 기본으로 고르는 것: NCS 쪽 칸 가운데 글자가 다른 것만. 띄어쓰기만 다른 칸은 고르지 않는다 — NCS 원문(F22)과 기준정보의 띄어쓰기 중 어느 쪽이 맞는지 확인이 먼저다
    setApplyPick(Object.fromEntries(data.차이.map((row, i) => [i, canApply(row) && row["수정 금지 칸"] && row.차이 === "다름"])));
    setApplyNote(null);
    setTimeout(() => document.getElementById("plan-compare-result")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  const canApply = (row) => !!row.기준 && !!row.대상;       // 한쪽이 빈 칸은 한글에서 직접 적는다
  const targetIsHwpx = /\.hwpx$/i.test(targetFile?.name || "");
  const picks = compared ? compared.차이.filter((row, i) => applyPick[i] && canApply(row)) : [];
  async function runApply() {
    if (!picks.length || !baseFile || !targetFile) return;
    setApplying(true); setApplyNote(null);
    const { ok, report, error: message } = await api.plan.apply(baseFile, targetFile, picks);
    setApplying(false);
    setApplyNote(ok ? { report } : { error: message });
  }
  async function runSignals(e) {
    e.preventDefault();
    if (!signalFile) { setSignalError("기존 학습모듈 원고 파일(hwp, hwpx)을 선택해 주세요."); return; }
    setSignalBusy(true); setSignalError(null); setSignals(null);
    const { ok, data, error: message } = await api.plan.typeSignals(signalFile, signalCode.trim());
    setSignalBusy(false);
    if (!ok) { setSignalError(message); return; }
    setSignals(data);
  }

  const improve = kind === "개선";
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
    // 최소개선은 담당 검토진을 비워도 된다(점검 ⑧)
    ...(chosen.some((u) => !(people[u.code]?.reviewer || "").trim() && !(improve && people[u.code]?.type === "최소개선")) ? ["담당 검토진"] : []),
    ...(improve && chosen.some((u) => !people[u.code]?.type) ? ["개선 유형"] : []),
    ...(improve && chosen.some((u) => !(people[u.code]?.previous || "").trim()) ? ["개선 전 능력단위번호"] : []),
  ];

  // 체크한 능력단위 전부에 한 칸을 한꺼번에 적는다. pick(능력단위, 지금 값) → 새 값
  function setBulk(key, pick) {
    setPeople((prev) => ({ ...prev, ...Object.fromEntries(chosen.map((u) => [u.code, { ...(prev[u.code] || {}), [key]: pick(u, prev[u.code]?.[key] || "") }])) }));
  }
  function setPerson(code, key, value) {
    setPeople((prev) => ({ ...prev, [code]: { ...(prev[code] || {}), [key]: value } }));
  }

  return (
    <>
    <Header anchors={[]} hasHistory={false} hasResult={!!check} />
    <main id="container" className="inner page">
      <h1 className="page-title">개발계획서 작성</h1>
      <p className="page-desc">
        세분류를 선택하면 NCS 능력단위, 요소, 수행준거를 개발계획서 양식(T01)에 채운 초안(hwpx)을 내려받을 수 있습니다.
        학습 내용명, 선수학습처럼 집필자가 정하는 칸은 비워 둡니다. 초안을 만들 때 점검 ①~⑩을 함께 실행합니다.
        이어서 작성한 개발계획서는 ‘개발계획서 점검’ 탭에서 다시 점검해 주세요.
      </p>

      <div className="krds-tab-area page-tools">
        <div className="tab line">
          <ul role="tablist" aria-label="개발계획서 도구">
            {TOOLS.map(([key, label]) => (
              <li key={key} role="none" className={tool === key ? "active" : undefined}>
                <button type="button" role="tab" id={`plan-tab-${key}`} className="btn-tab" aria-selected={tool === key} onClick={() => setTool(key)}>
                  {label}{tool === key && <span className="sr-only"> 선택됨</span>}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div role="tabpanel" aria-labelledby="plan-tab-draft" hidden={tool !== "draft"}>
      <PageAlert kind="danger">{loadError}</PageAlert>
      {catalog && !catalog.subclasses?.length && (
        <p className="empty">NCS 세분류 목록을 읽지 못했습니다. 관리자에게 문의해 주세요.</p>
      )}

      {/* 입력 묶음은 구획 셋: 세분류 선택 → 개발계획서에 적을 내용 → 실행(다른 화면과 같은 구조). 구획 안에서만 3열 격자(.form-section-grid)를 쓴다 */}
      <form id="plan-form" className="fieldset review-form is-sectioned nav-anchor" onSubmit={submit}>
        <div className="form-section" role="group" aria-labelledby="plan-duty-title">
        <h2 className="form-section-title" id="plan-duty-title">세분류 선택</h2>
        <div className="form-section-grid">
        {/* NCS 누리집 'NCS 및 학습모듈검색'과 같은 차례: 분야별(대 › 중 › 소 › 세분류 › 능력단위), 키워드, 코드 */}
        <div className="form-group form-group-wide">
          <div className="form-tit"><span id="duty-title">세분류</span></div>
          <div className="form-conts">
            <NcsPicker subclasses={catalog?.subclasses || []} duty={duty} onPick={pickDuty} detail={detail} loading={fetching || (!!duty && !detail)} />
          </div>
          <p className="form-hint" id="duty-hint" role="status">
            {detail && detail.duty === duty
              ? `선택한 세분류: ${detail.classes?.대분류 || ""} › ${detail.classes?.중분류 || ""} › ${detail.classes?.소분류 || ""} › ${detail.name} (${duty})`
              : duty ? "세분류 정보를 불러오는 중입니다." : "세분류를 선택해 주세요."}
          </p>
        </div>

        {/* NCS 기준정보 — 세분류를 고른 뒤에만 보인다(고르기 전에는 보일 내용이 없다). 이 세분류의 요소와 수행준거를 언제 받았는지, 다시 받기. 아직 없는 세분류는 고르는 즉시 받아 온다 */}
        {duty && (
        <div className="form-group form-group-wide plan-refdata" id="plan-refdata">
          <div className="form-tit"><span>NCS 기준정보</span></div>
          <div className="form-conts">
            {fetching ? <Spinner label="NCS에서 요소와 수행준거를 불러오는 중" />
              : subclass ? (
                <p className="plan-refdata-line">
                  <span>{subclass.fetched ? `${subclass.fetched}에 NCS에서 불러온 자료입니다.` : "기본으로 제공하는 자료입니다. 불러온 날짜는 기록되어 있지 않습니다."}</span>
                  {catalog?.can_fetch && (
                    <button type="button" className="krds-btn small tertiary" disabled={busy} onClick={() => loadDetail(duty, { refresh: true })}>NCS에서 다시 불러오기</button>
                  )}
                </p>
              ) : detail && !detail.ready && !fetchError ? (
                <p className="plan-refdata-line"><span>이 세분류의 요소와 수행준거 자료가 아직 없습니다. {catalog?.can_fetch ? "" : "지금은 NCS에서 자료를 불러올 수 없습니다. 관리자에게 문의해 주세요."}</span></p>
              ) : null}
            <PageAlert kind="danger">{fetchError && (
              <>
                <p>{fetchError}</p>
                {catalog?.can_fetch && duty && <button type="button" className="krds-btn small tertiary" onClick={() => loadDetail(duty, { refresh: !!subclass })}>다시 시도</button>}
              </>
            )}</PageAlert>
            <PageAlert kind="success">{fetchNote}</PageAlert>
          </div>
          <p className="form-hint">NCS가 개정되면 [NCS에서 다시 불러오기]를 눌러 최신 내용으로 바꿔 주세요. 달라진 능력단위를 알려 드립니다.</p>
        </div>
        )}
        </div>
        </div>

        <div className="form-section" role="group" aria-labelledby="plan-content-title" aria-describedby="plan-content-desc">
        <h2 className="form-section-title" id="plan-content-title">개발계획서 입력 항목</h2>
        <p className="form-section-desc" id="plan-content-desc">개발기관명과 영문 세분류명은 최종본의 필수 항목입니다(점검 ⑧). 초안 단계에서는 입력하지 않아도 됩니다.</p>
        <div className="form-section-grid">
        <div className="form-group form-group-wide">
          <div className="form-tit"><span id="plan-kind-label">개발 구분</span></div>
          <div className="form-conts plan-stage" role="radiogroup" aria-labelledby="plan-kind-label">
            {KINDS.map(([value, label]) => (
              <div className="krds-form-check" key={value}>
                <input type="radio" id={`plan-kind-${value}`} name="plan-kind" value={value} checked={kind === value} onChange={() => { setKind(value); setCheck(null); }} />
                <label htmlFor={`plan-kind-${value}`}>{label}</label>
              </div>
            ))}
          </div>
          <p className="form-hint">개선을 선택하면 개선 양식(NCS 변경 전·후 대조표, 총괄표의 개선 유형)으로 초안을 만듭니다. 능력단위별로 개선 유형과 개선 전 능력단위번호를 입력해 주세요.</p>
        </div>

        <div className="form-group">
          <div className="form-tit"><label htmlFor="agency">개발기관명 <span className="required"><i aria-hidden="true">*</i><span className="sr-only">필수</span></span></label></div>
          <div className="form-conts">
            <input id="agency" type="text" className="krds-input" placeholder="예: (사)한국호텔전문경영인협회" value={agency} onChange={(e) => setAgency(e.target.value)} aria-describedby="agency-hint" aria-required="true" />
          </div>
          <p className="form-hint" id="agency-hint">초안 단계에서는 입력하지 않아도 됩니다.</p>
        </div>

        <div className="form-group">
          <div className="form-tit"><label htmlFor="english">영문 세분류명 <span className="required"><i aria-hidden="true">*</i><span className="sr-only">필수</span></span></label></div>
          <div className="form-conts">
            <input id="english" type="text" className="krds-input" placeholder="예: Rooms Operation" value={english} onChange={(e) => setEnglish(e.target.value)} aria-describedby="english-hint" aria-required="true" />
          </div>
          <p className="form-hint" id="english-hint">NCS 누리집 ‘환경 분석’에 있는 영문명을 입력해 주세요.</p>
        </div>

        {subclass && (
          <div className="form-group form-group-wide">
            <div className="form-tit"><span id="units-title">능력단위 ({chosen.length}/{subclass.units.length})와 담당 집필진, 검토진 <span className="required"><i aria-hidden="true">*</i><span className="sr-only">필수</span></span></span></div>
            <div className="form-conts">
              {improve && (
                <div className="plan-bulk" role="group" aria-label="선택한 능력단위에 일괄 적용">
                  <span className="plan-bulk-label">선택한 능력단위 {chosen.length}개의 개선 유형</span>
                  <div className="plan-bulk-buttons">
                    {TYPES.map((type) => {
                      const all = chosen.length > 0 && chosen.every((u) => people[u.code]?.type === type.value);
                      return (
                        <button type="button" key={type.value} className={`krds-btn small ${all ? "secondary" : "tertiary"}`} aria-pressed={all} disabled={!chosen.length} onClick={() => setBulk("type", () => type.value)}>{type.label}</button>
                      );
                    })}
                  </div>
                  <button type="button" className="krds-btn small tertiary plan-bulk-fill" disabled={!chosen.some((u) => people[u.code]?.type)} onClick={() => setBulk("type", () => "")}>유형 삭제</button>
                </div>
              )}
              <div className="krds-table-wrap">
                <table className="tbl col data plan-units" aria-labelledby="units-title">
                  <caption>초안에 넣을 능력단위 선택과 담당자</caption>
                  <colgroup>
                    <col className="col-check" /><col /><col className="col-level" /><col className="col-count" />{improve && <><col className="col-type" /><col className="col-person" /></>}<col className="col-person" /><col className="col-person" />
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
                      <th scope="col">능력단위</th><th scope="col">수준</th><th scope="col">요소 / 수행준거</th>{improve && <><th scope="col">개선 유형</th><th scope="col">개선 전 능력단위번호</th></>}<th scope="col">담당 집필진 <span className="required"><i aria-hidden="true">*</i><span className="sr-only">필수</span></span></th><th scope="col">담당 검토진 <span className="required"><i aria-hidden="true">*</i><span className="sr-only">필수</span></span></th>
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
                        {improve && (
                          <>
                            <td>
                              <select className={`krds-form-select small${people[u.code]?.type ? " completed" : ""}`} aria-label={`${u.name} 개선 유형`} value={people[u.code]?.type || ""} onChange={(e) => setPerson(u.code, "type", e.target.value)}>
                                <option value="">선택</option>
                                {TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
                              </select>
                            </td>
                            <td><input type="text" className="krds-input small" aria-label={`${u.name} 개선 전 능력단위번호`} placeholder="없으면 ‘없음’ 입력" value={people[u.code]?.previous || ""} onChange={(e) => setPerson(u.code, "previous", e.target.value)} /></td>
                          </>
                        )}
                        <td><input type="text" className="krds-input small" aria-label={`${u.name} 담당 집필진`} value={people[u.code]?.writer || ""} onChange={(e) => setPerson(u.code, "writer", e.target.value)} /></td>
                        <td><input type="text" className="krds-input small" aria-label={`${u.name} 담당 검토진`} value={people[u.code]?.reviewer || ""} onChange={(e) => setPerson(u.code, "reviewer", e.target.value)} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {improve && (
                <p className="form-hint">
                  개선 유형은 직능연이 대상 학습모듈을 검토해 분류한 결과대로 선택해 주세요. 정해지지 않았으면 ‘선택’으로 두세요. 초안에는 빈칸으로 들어갑니다. 유형을 바꿀 때는 직능연과 협의해야 합니다.
                  개선 전 능력단위번호는 NCS 변경전후대조표 파일에서 확인해 입력해 주세요. 현재 번호나 기존 학습모듈 번호와 다를 수 있으니 두 파일을 모두 확인해 주세요.
                  입력한 번호가 현재 번호와 같으면 ‘변경 없음’, 다르면 ‘능력단위 코드 변경’, ‘없음’이면 ‘능력단위 신설’로 채웁니다. 비워 두면 대조표의 개선 전 칸도 비워 둡니다.
                  개선 전 능력단위명은 해당 판의 NCS 파일을 확인해 한글 프로그램에서 직접 입력해 주세요.
                </p>
              )}
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
            <p className="form-hint" id="missing-hint">입력하지 않은 필수 항목: {missing.join(", ")}. 초안(1차본) 단계에서는 입력하지 않아도 됩니다. 최종본 점검 ⑧에서 확인합니다.</p>
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
                <span className="meta">초안 파일을 내려받기 폴더에 저장했습니다.</span>
                <button type="button" className="krds-btn small tertiary" disabled={busy} onClick={submit} title="같은 설정으로 초안을 다시 만들어 내려받기">다시 내려받기</button>
              </>
            }
          />
          <h2 className="section-title">초안 점검 확인서</h2>
          <p className="meta section-desc">1차본(직능연) 기준으로 점검한 결과입니다. 학습 내용명, 영문명, 집필진처럼 개발기관이 입력하는 칸은 ‘해당 없음’으로 표시합니다. 내려받은 hwpx 파일을 한글 프로그램에서 열어 이어서 작성해 주세요. 완성본은 ‘개발계획서 점검’ 탭에서 ‘최종본’으로 다시 점검해 주세요.</p>
          <SheetTable sheet={check} findings={[]} />
        </section>
      )}
      {/* ── 개발계획서 점검 ── 작성한 파일을 올려 ①~⑩ 점검. 예전에는 원고 검수 페이지의 선택 목록에 있었다 */}
      </div>

      <section id="plan-review" className="nav-anchor plan-review" role="tabpanel" aria-labelledby="plan-tab-review" hidden={tool !== "review"}>
        <h2 className="section-title sr-only">개발계획서 점검</h2>{/* 탭 이름과 같아 화면에는 감춘다(화면낭독기용 제목은 남긴다) */}
        <p className="meta section-desc">작성한 개발계획서(hwp, hwpx)를 올리면 점검 ①~⑩을 실행합니다. 원고는 필요하지 않습니다. 1차본은 학습모듈명, 영문명, 기관명, 집필진, 학습 내용명이 비어 있어도 부적합으로 판정하지 않습니다. 이 칸은 최종 단계에서 개발기관이 입력합니다.</p>
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
            <p className="form-hint">1차본은 개발기관이 입력하는 칸이 비어 있어도 됩니다.</p>
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

      {/* ── 개선 유형 판단 자료 ── 기존 학습모듈 원고에서 지침(F05 1항, F21 운영 기준 예시표)이 든 내용 수정 신호를 찾는다. 유형은 정하지 않는다 */}
      <section id="plan-type" className="nav-anchor plan-review" role="tabpanel" aria-labelledby="plan-tab-type" hidden={tool !== "type"}>
        <h2 className="section-title sr-only">개선 유형 판단 자료</h2>{/* 탭 이름과 같아 화면에는 감춘다(화면낭독기용 제목은 남긴다) */}
        <p className="meta section-desc">
          기존 학습모듈 원고를 올리면 내용 수정이 필요한지 판단할 때 참고할 신호를 찾아 보여 줍니다. 찾는 신호는 법령 기재, URL 기재, 안전·유의 사항의 ‘해당 사항 없음’, 학습 목표와 NCS 수행준거의 불일치입니다.
          개선 유형은 직능연이 대상 학습모듈을 검토해 분류합니다. 유형을 바꿀 때는 직능연과 협의해야 합니다. 이 화면에서는 유형을 정하지 않습니다.
        </p>
        <form className="fieldset review-form is-sectioned" onSubmit={runSignals}>
          <div className="form-section-grid">
            <FileSlot id="plan-signal-file" label="기존 학습모듈 원고" required accept=".hwp,.hwpx" file={signalFile} disabled={signalBusy} onChange={(picked) => { setSignalFile(picked); setSignalError(null); }} />
            <div className="form-group">
              <div className="form-tit"><label htmlFor="plan-signal-code">학습모듈 코드</label></div>
              <div className="form-conts"><input id="plan-signal-code" type="text" className="krds-input" placeholder="예: LM1203020201_24v3" value={signalCode} onChange={(e) => setSignalCode(e.target.value)} aria-describedby="plan-signal-code-hint" /></div>
              <p className="form-hint" id="plan-signal-code-hint">비워 두면 파일 이름에서 찾습니다. 수행준거를 대조할 때 사용합니다.</p>
            </div>
          </div>
          <div className="form-actions">
            <div className="run-buttons">
              <button className="krds-btn primary large" type="submit" disabled={signalBusy || !signalFile}>{signalBusy ? "찾는 중" : "신호 찾기"}</button>
            </div>
            <PageAlert kind="danger">{signalError}</PageAlert>
          </div>
        </form>
        {signalBusy && <ResultHead status={<Spinner label="원고를 읽는 중" />} />}
        {signals && (
          <section aria-live="polite">
            <ResultHead
              status={<span className={`krds-badge large ${signals.신호.length ? "bg-light-warning" : "bg-light-gray"}`}>{signals.신호.length ? `신호 ${signals.신호.length}종` : "찾은 신호 없음"}</span>}
              meta={[signals.파일, signals["모듈 코드"]].filter(Boolean).join(", ")}
            />
            <PageAlert kind="info">{signals.안내}</PageAlert>
            {signals["확인 못 한 것"].map((text) => <PageAlert kind="warning" key={text}>{text}</PageAlert>)}
            {signals.신호.length > 0 && (
              <div className="krds-table-wrap">
                <table className="tbl col data plan-signal-table">
                  <caption>기존 학습모듈 원고에서 찾은 내용 수정 신호</caption>
                  <thead><tr><th scope="col">신호</th><th scope="col">건수</th><th scope="col">지침상 유형</th><th scope="col">찾은 내용</th><th scope="col">근거</th></tr></thead>
                  <tbody>
                    {signals.신호.map((item) => (
                      <tr key={item.신호}>
                        <td><strong>{item.신호}</strong></td>
                        <td>{item.건수}</td>
                        <td>{item.유형}</td>
                        <td>{item.예.length ? <ul className="plan-signal-list">{item.예.map((text) => <li key={text}>{text}</li>)}{item.건수 > item.예.length && <li>외 {item.건수 - item.예.length}건</li>}</ul> : "-"}</td>
                        <td className="meta">{item.근거}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </section>

      {/* ── 계획서 비교 ── 사람 작업의 '결과 비교': 최종결과 예시나 앞 판본과 칸별로 견준다. 판정은 하지 않는다 */}
      <section id="plan-compare" className="nav-anchor plan-review" role="tabpanel" aria-labelledby="plan-tab-compare" hidden={tool !== "compare"}>
        <h2 className="section-title sr-only">계획서 비교</h2>{/* 탭 이름과 같아 화면에는 감춘다(화면낭독기용 제목은 남긴다) */}
        <p className="meta section-desc">개발계획서 두 개를 칸별로 비교합니다. 기준에는 최종결과 예시나 이전 판본을, 대상에는 현재 계획서를 올려 주세요. 내용이 같은 칸은 개수만 세고, 다른 칸만 보여 줍니다. 판정은 하지 않습니다.</p>
        <form className="fieldset review-form is-sectioned" onSubmit={runCompare}>
          <div className="form-section-grid">
            <FileSlot id="plan-base" label="기준 계획서" required accept=".hwp,.hwpx" file={baseFile} disabled={comparing} onChange={(picked) => { setBaseFile(picked); setCompareError(null); }} />
            <FileSlot id="plan-target" label="대상 계획서" required accept=".hwp,.hwpx" file={targetFile} disabled={comparing} onChange={(picked) => { setTargetFile(picked); setCompareError(null); }} />
          </div>
          <div className="form-actions">
            <div className="run-buttons">
              <button className="krds-btn primary large" type="submit" disabled={comparing || !baseFile || !targetFile}>{comparing ? "비교하는 중" : "비교 실행"}</button>
            </div>
            <PageAlert kind="danger">{compareError}</PageAlert>
          </div>
        </form>

        <div id="plan-compare-result" className="results-anchor nav-anchor" />
        {comparing && <ResultHead status={<Spinner label="계획서를 비교하는 중" />} />}
        {compared && (
          <section aria-live="polite">
            <ResultHead
              status={<span className={`krds-badge large ${compared.차이.length ? "bg-light-warning" : "bg-light-success"}`}>{compared.차이.length ? `다른 칸 ${compared.차이.length}개` : "다른 칸 없음"}</span>}
              meta={`기준 ${compared["기준 파일"]} (능력단위 ${compared.요약.능력단위.기준}개), 대상 ${compared["대상 파일"]} (능력단위 ${compared.요약.능력단위.대상}개), 비교한 칸 ${compared.요약["견준 칸"]}개 중 같은 칸 ${compared.요약.같음}개`}
            />
            {compared.요약["수정 금지 칸 변경"] > 0 && (
              <PageAlert kind="danger">NCS 쪽 칸(능력단위명, 정의, 요소명, 수행준거, 분류)이 {compared.요약["수정 금지 칸 변경"]}개 다릅니다. 이 칸은 수정하면 안 되는 칸입니다. 어느 쪽이 NCS와 같은지 확인해 주세요.</PageAlert>
            )}
            {compared["개선 유형 변경"].length > 0 && (
              <>
                <h3 className="section-title">개선 유형이 달라진 능력단위 ({compared["개선 유형 변경"].length})</h3>
                <p className="meta section-desc">개선 유형이 바뀌면 최종 개발계획서와 결과물 목록에 동일하게 반영해야 합니다(최소개선 유형 세부 지침).</p>
                <div className="krds-table-wrap">
                  <table className="tbl col data">
                    <caption>개선 유형이 달라진 능력단위</caption>
                    <thead><tr><th scope="col">능력단위</th><th scope="col">기준</th><th scope="col">대상</th></tr></thead>
                    <tbody>
                      {compared["개선 유형 변경"].map((row) => (
                        <tr key={row.코드}><td><strong>{row.명칭}</strong><br /><span className="code">{row.코드}</span></td><td>{row.기준 || "(없음)"}</td><td>{row.대상 || "(없음)"}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            {compared.차이.length > 0 && (
              <>
                <h3 className="section-title">다른 칸</h3>
                <div className="plan-bulk" role="group" aria-label="선택한 칸 반영">
                  <span className="plan-bulk-label">반영할 칸 {picks.length}개</span>
                  <span className="meta">선택한 칸을 대상 계획서 사본에 기준 계획서의 내용으로 바꿔 넣습니다. 처음에는 NCS 쪽 칸 가운데 글자가 다른 칸만 선택되어 있습니다. 띄어쓰기만 다른 칸은 NCS 원문을 확인한 뒤 선택해 주세요. 한쪽이 빈칸이면 한글 프로그램에서 직접 입력해 주세요.</span>
                  <button type="button" className="krds-btn small secondary plan-bulk-fill" disabled={applying || !picks.length || !targetIsHwpx} onClick={runApply}>{applying ? "반영하는 중" : "선택한 칸을 반영한 사본 내려받기"}</button>
                </div>
                {!targetIsHwpx && <PageAlert kind="warning">hwpx 형식의 대상 계획서에만 반영할 수 있습니다. hwp 파일은 한글 프로그램에서 hwpx로 저장한 뒤 다시 비교해 주세요.</PageAlert>}
                <PageAlert kind="danger">{applyNote?.error}</PageAlert>
                {applyNote?.report && (
                  <PageAlert kind={applyNote.report["반영 못 함"].length ? "warning" : "success"}>
                    <p>{applyNote.report.반영}개 칸을 반영한 사본을 내려받았습니다. 원본은 바뀌지 않습니다. 한글 프로그램에서 열어 확인해 주세요.</p>
                    {applyNote.report["반영 못 함"].length > 0 && (
                      <ul className="plan-signal-list">{applyNote.report["반영 못 함"].map((row, i) => <li key={i}>{row.자리 || row.구역} {row.칸}: {row.사유}</li>)}</ul>
                    )}
                  </PageAlert>
                )}
                <div className="plan-compare-filter" role="group" aria-label="차이 종류별로 보기">
                  {["", ...Object.keys(DIFF_BADGE)].map((name) => {
                    const count = name ? compared.요약[name] : compared.차이.length;
                    return (name === "" || count > 0) && (
                      <button type="button" key={name || "all"} className={`krds-btn small ${onlyKind === name ? "secondary" : "tertiary"}`} aria-pressed={onlyKind === name} onClick={() => setOnlyKind(name)}>{name || "전체"} {count}</button>
                    );
                  })}
                </div>
                {AREAS.map((area) => {
                  const rows = compared.차이.map((row, index) => ({ ...row, index })).filter((row) => row.구역 === area && (!onlyKind || row.차이 === onlyKind));
                  return rows.length > 0 && (
                    <details className="plan-compare-area" key={area} open={rows.length <= 40}>
                      <summary>{area} ({rows.length})</summary>
                      <div className="krds-table-wrap">
                        <table className="tbl col data plan-compare-table">
                          <caption>{area}에서 다른 칸</caption>
                          <thead><tr><th scope="col">반영</th><th scope="col">자리</th><th scope="col">칸</th><th scope="col">차이</th><th scope="col">기준</th><th scope="col">대상</th></tr></thead>
                          <tbody>
                            {rows.map((row) => (
                              <tr key={row.index}>
                                <td>
                                  {canApply(row) ? (
                                    <div className="krds-form-check">
                                      <input type="checkbox" id={`apply-${row.index}`} checked={!!applyPick[row.index]} onChange={(e) => setApplyPick((prev) => ({ ...prev, [row.index]: e.target.checked }))} />
                                      <label htmlFor={`apply-${row.index}`}><span className="sr-only">{row.자리} {row.칸} 반영</span></label>
                                    </div>
                                  ) : <span className="meta" title="한쪽이 빈칸이면 한글 프로그램에서 직접 입력해 주세요">-</span>}
                                </td>
                                <td><span className="code">{row.자리 || "-"}</span></td>
                                <td>{row.칸}{row["수정 금지 칸"] && <><br /><span className="krds-badge small bg-light-danger">NCS 쪽</span></>}</td>
                                <td><span className={`krds-badge small ${DIFF_BADGE[row.차이]}`}>{row.차이}</span></td>
                                <td>{row.기준 || <span className="meta">(없음)</span>}</td>
                                <td>{row.대상 || <span className="meta">(없음)</span>}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  );
                })}
              </>
            )}
            <RawJson data={compared} title="원본 데이터 보기(개발자용)" />
          </section>
        )}
      </section>

      <TopButton />
    </main>
    <Footer />
    </>
  );
}

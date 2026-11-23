// 원고 검수 — 원고·개발계획서·출력본 PDF를 올려 구성요소 하나 또는 전체(10개)를 검사하고, 결과·확인서 내려받기·검수 이력을 한 화면에서 본다.
import React, { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../lib/api.js";
import { ALL_CHECK, ALL_OPTION, CHECKS, checksFromEngines, manuscriptChecks } from "../lib/checks.js";
import { formatDate, formatDateLines } from "../lib/format.jsx";
import { AllResults, ComponentResult } from "../components/AllResults.jsx";
import { Badge, Spinner } from "../components/Badge.jsx";
import { ConfirmDialog } from "../components/ConfirmDialog.jsx";
import { ExportButtons } from "../components/ExportButtons.jsx";
import { FileSlot } from "../components/FileSlot.jsx";
import { KrdsSelect } from "../components/KrdsSelect.jsx";
import { RawJson } from "../components/RawJson.jsx";
import { ResultHead } from "../components/ResultHead.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { Pagination } from "../components/Pagination.jsx";
import { IMAGE_DPI_DEFAULT, IMAGE_DPI_OPTIONS } from "../lib/dpi.js";
import { usePageTitle } from "../lib/hooks.js";

const HISTORY_PAGE = 10;   // 이력 표 한 쪽 행 수(KRDS 페이지네이션)

// 업로드 칸 셋(#13) — 칸이 곧 역할이다. 올릴 때 칸 이름을 역할(roles)로 함께 보내 서버가 내용 판별 대신 그대로 쓴다
const SLOTS = [
  { role: "manuscript", label: "원고", accept: ".hwp,.hwpx", required: true },
  { role: "plan", label: "개발계획서", accept: ".hwp,.hwpx" },
  { role: "print", label: "출력본 PDF", accept: ".pdf" },
];

// 원고 단계 선택지 — 서버 ncs_service.progress.REVIEW_STAGES와 같아야 한다
const WORK_STAGE_OPTIONS = [
  { value: "", label: "고르지 않음" }, { value: "2", label: "초고본" }, { value: "3", label: "수정본" }, { value: "6", label: "최종본" },
];

export default function ReviewPage() {
  usePageTitle("원고 검수");
  const [check, setCheck] = useState(ALL_CHECK); // 기본은 전체 검수
  const [checks, setChecks] = useState(CHECKS);
  // 원고·개발계획서·출력본 PDF를 칸마다 따로 고른다(#13). 서버에는 고른 것만 모아 한 번에 올린다(files).
  const [slots, setSlots] = useState({ manuscript: null, plan: null, print: null });
  const filled = useMemo(() => SLOTS.filter((slot) => slots[slot.role]), [slots]);
  const files = useMemo(() => filled.map((slot) => slots[slot.role]), [filled, slots]);
  const fileRoles = useMemo(() => filled.map((slot) => slot.role), [filled]);   // files와 같은 순서의 역할
  const [tried, setTried] = useState(false);   // 실행을 한 번 눌렀는가 — 그 뒤부터 빈 필수 칸에 오류 문구를 보인다
  const [moduleCode, setModuleCode] = useState("");
  const [workStage, setWorkStage] = useState("");   // 원고 진행 현황의 단계(초고본 2·수정본 3·최종본 6). 비우면 단계 없이 남는다
  const [imageDpi, setImageDpi] = useState(String(IMAGE_DPI_DEFAULT));   // 이미지 해상도 기준 — 기타 ⑤·⑧에 쓰인다
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);   // 성공 안내(메모 원고 요약 등)
  const [result, setResult] = useState(null);
  const [allRun, setAllRun] = useState(null);   // 전체 실행 진행·결과: { group, roles, items: {check: {status, data, error}}, running, created_at }
  const [history, setHistory] = useState(null);
  const resultsRef = useRef(null);
  // 파일을 고르면 바로 /api/uploads에 올려 토큰·역할을 받아 둔다. 실행은 이 토큰으로(파일을 다시 보내지 않음), 만료되면 다시 올린다.
  const [upload, setUpload] = useState({ status: "idle" });   // { status, token, group, roles, error }
  const uploadRef = useRef(upload);
  uploadRef.current = upload;
  const aborter = useRef(null);      // 진행 중 요청의 AbortController — 취소 버튼
  const [pendingDelete, setPendingDelete] = useState(null); // 삭제 확인 창에 올라간 이력 행
  const [historyPage, setHistoryPage] = useState(1);   // 이력 표 현재 쪽
  useEffect(() => {
    const pages = Math.max(1, Math.ceil((history?.length || 0) / HISTORY_PAGE));
    if (historyPage > pages) setHistoryPage(pages);
  }, [history, historyPage]);
  const [deleting, setDeleting] = useState(false);

  async function refreshHistory() {
    // 단독 실행(standalone)과 전체 실행 묶음(/api/groups)을 따로 받아 시각순으로 한 표에 섞는다. 묶음은 한 줄.
    const [runs, groups] = await Promise.all([api.reviews.list(), api.groups.list()]);
    if (!runs.ok) return;
    const rows = runs.data.map((row) => ({ ...row, kind: "run" }));
    if (groups.ok) groups.data.forEach((g) => rows.push({ ...g, id: g.group_id, kind: "group", check_name: ALL_CHECK }));
    rows.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    setHistory(rows);
  }

  useEffect(() => {
    const previous = uploadRef.current.token;
    if (previous) api.uploads.remove(previous);
    if (!files.length) { setUpload({ status: "idle" }); return undefined; }
    const controller = new AbortController();
    setUpload({ status: "uploading" });
    api.uploads.create(files, controller.signal, fileRoles).then(({ ok, data, error: message, aborted }) => {
      if (aborted) return;
      setUpload(ok ? { status: "ready", token: data.upload, group: data.group, roles: data.roles } : { status: "error", error: message });
    });
    return () => controller.abort();
  }, [files, fileRoles]);

  // 실행에 쓸 토큰. 미리 올린 것이 없거나(오류) 만료됐으면 지금 다시 올린다. 실패하면 null(오류는 setError).
  async function ensureUpload(signal) {
    const current = uploadRef.current;
    if (current.status === "ready") return current;
    const { ok, data, error: message, aborted } = await api.uploads.create(files, signal, fileRoles);
    if (aborted) return null;
    if (!ok) { setError(message); return null; }
    const fresh = { status: "ready", token: data.upload, group: data.group, roles: data.roles };
    setUpload(fresh);
    return fresh;
  }

  function cancel() {
    aborter.current?.abort();
  }

  // 단독 결과가 오거나 전체 실행이 시작(묶음 id가 바뀜)되면 결과 영역으로 스크롤. 전체 실행 중 구성요소가 채워질 때는 다시 움직이지 않는다.
  const resultKey = result?.id ?? (result ? "result" : null) ?? allRun?.group ?? null;
  useEffect(() => {
    if (resultKey) resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [resultKey]);

  // 서버가 이력 저장(DB 모드)을 지원할 때만 이력을 가져온다. 파일 모드에서는 /api/reviews가 없다.
  useEffect(() => {
    api.health().then(({ ok, data }) => {
      if (!ok) return undefined;
      if (data?.engines) setChecks(checksFromEngines(data.engines));
      if (data?.history) return refreshHistory();
      return undefined;
    });
  }, []);

  // "전체"는 개별 구성요소와 성격이 다른 실행 모드라 맨 위에 두고(가장 많이 쓰는 선택), 그 아래 구분선 뒤에 확인서 순서대로 10개
  // 개발계획서 점검(plan)은 여기서 고를 수 없다 — '개발계획서 작성' 페이지에서만 실행한다. checks(전체 목록)는 이력의 이름 표시에만 쓴다.
  const reviewChecks = manuscriptChecks(checks);
  const options = [ALL_OPTION, ...reviewChecks];
  const selected = options.find((c) => c.value === check) || options[0];

  const needsPlan = (selected.required || []).includes("plan");
  const usesPrint = (selected.optional || []).includes("print");
  const usesImageDpi = check === ALL_CHECK || check === "misc";

  // 실행 전 확인: 원고가 없거나, 개발계획서가 필요한 구성요소인데 없으면 실행하지 않고 오류 문구를 보인다(#13). 통과하면 null.
  function missingInput() {
    if (!slots.manuscript) return "원고 파일이 없습니다. ‘원고’ 칸에 원고(hwp, hwpx)를 올려 주세요.";
    if (needsPlan && !slots.plan) return `${selected.label} 검수는 개발계획서가 필요합니다. ‘개발계획서’ 칸에 파일을 올리세요.`;
    return null;
  }

  async function submit(event) {
    event.preventDefault();
    setTried(true);
    const missing = missingInput();
    if (missing) { setError(missing); setNotice(null); return undefined; }
    if (check === ALL_CHECK) return runAll();
    setBusy(true);
    setError(null);
    setNotice(null);
    setResult(null);
    setAllRun(null);
    const controller = new AbortController();
    aborter.current = controller;
    let kept = await ensureUpload(controller.signal);
    let answer = kept ? await api.review({ check, moduleCode, upload: kept.token, imageDpi, workStage, signal: controller.signal }) : null;
    if (answer && !answer.ok && answer.status === 400 && /만료/.test(answer.error)) {
      setUpload({ status: "idle" });
      uploadRef.current = { status: "idle" };
      kept = await ensureUpload(controller.signal);
      answer = kept ? await api.review({ check, moduleCode, upload: kept.token, imageDpi, workStage, signal: controller.signal }) : null;
    }
    if (answer && !answer.aborted) {
      if (!answer.ok) setError(answer.error);
      else {
        setResult(answer.data);
        if (answer.data.id) refreshHistory();
      }
    }
    aborter.current = null;
    setBusy(false);
  }

  // 전체 실행: 업로드 1회(토큰) → 엔진 순서대로 /api/review → 끝나면 토큰 반납. 한 구성요소의 오류는 그 칸에만 남기고 다음으로 간다.
  async function runAll() {
    setBusy(true);
    setError(null);
    setResult(null);
    const order = reviewChecks.map((c) => c.value);
    const controller = new AbortController();
    aborter.current = controller;
    // 미리 올린 토큰은 단독 실행용. 전체 실행은 이력 묶음 id가 실행마다 달라야 해서 새 토큰(새 묶음)을 만든다.
    const created = await api.uploads.create(files, controller.signal, fileRoles);
    if (!created.ok) {
      if (!created.aborted) setError(created.error);
      aborter.current = null;
      setBusy(false);
      return;
    }
    const upload = created.data;
    const hasPlan = Boolean(upload.roles?.plan);
    const items = {};
    order.forEach((value) => {
      const needsPlan = (reviewChecks.find((c) => c.value === value)?.required || []).includes("plan");
      items[value] = { status: needsPlan && !hasPlan ? "skipped" : "pending" };
    });
    setAllRun({ group: upload.group, roles: upload.roles, items, running: true, created_at: new Date().toISOString() });
    const update = (value, patch) => setAllRun((prev) => (prev ? { ...prev, items: { ...prev.items, [value]: { ...prev.items[value], ...patch } } } : prev));
    let cancelled = false;
    for (const value of order) {
      if (items[value].status === "skipped") continue;
      if (cancelled) { update(value, { status: "cancelled" }); continue; }
      update(value, { status: "running" });
      const { ok, data, error: message, aborted } = await api.review({ check: value, moduleCode, upload: upload.upload, group: upload.group, imageDpi, workStage, signal: controller.signal });
      if (aborted) { cancelled = true; update(value, { status: "cancelled" }); continue; }
      update(value, ok ? { status: "done", data } : { status: "error", error: message });
    }
    api.uploads.remove(upload.upload);  // 끝났으니 바로 반납(안 해도 만료 시 정리)
    setAllRun((prev) => (prev ? { ...prev, running: false, cancelled } : prev));
    aborter.current = null;
    setBusy(false);
    if (history) refreshHistory();
  }

  // 이력의 전체 실행 묶음을 열어 아코디언으로 되살린다. 저장되지 않은 구성요소(위치: 개발계획서 없음)는 건너뜀으로 표시.
  async function openGroup(id) {
    setError(null);
    const { ok, data, error: message } = await api.groups.get(id);
    if (!ok) return setError(message);
    const items = {};
    reviewChecks.forEach((c) => { items[c.value] = { status: "skipped" }; });
    data.runs.forEach((run) => { items[run.check] = { status: "done", data: run }; });
    const hasPlan = data.runs.some((run) => run.진단?.inputs?.plan);
    setResult(null);
    setAllRun({ group: id, roles: { manuscript: true, plan: hasPlan }, items, running: false, created_at: data.created_at, module_code: data.module_code });
  }

  // 세분류 건의 판본 검수 결과에서 넘어오면(?group=) 그 묶음을 바로 연다. 검수 목록(reviewChecks)이 준비된 뒤 한 번만
  // 실행 하나(?run=)도 같다 — 건의 개발계획서 점검 결과가 이 길로 온다
  const linked = useRef({ group: new URLSearchParams(window.location.search).get("group"), run: new URLSearchParams(window.location.search).get("run") });
  useEffect(() => {
    const { group, run } = linked.current;
    if ((!group && !run) || !history || !reviewChecks.length) return;
    linked.current = {};
    if (group) openGroup(group); else openHistory(run);
  }, [history, reviewChecks]);   // eslint-disable-line react-hooks/exhaustive-deps

  async function openHistory(id) {
    setError(null);
    const { ok, data, error: message } = await api.reviews.get(id);
    if (!ok) return setError(message);
    setAllRun(null);
    setResult(data);
  }

  async function deleteHistory(row) {
    setError(null);
    setDeleting(true);
    const { ok, error: message } = await (row.kind === "group" ? api.groups.remove(row.id) : api.reviews.remove(row.id));
    if (!ok) setError(message);
    else {
      if (result?.id === row.id) setResult(null); // 지운 이력의 결과가 화면에 열려 있으면 함께 내린다
      if (allRun?.group === row.id) setAllRun(null);
      await refreshHistory();
    }
    setDeleting(false);
    setPendingDelete(null);
  }

  return (
    <>
    <Header hasHistory={!!history} hasResult={!!(allRun || result)} />
    <main id="container" className="inner page">
      <h1 className="page-title">NCS 학습모듈 원고 검수</h1>
      <p className="page-desc">
        원고(hwp, hwpx)를 올리면 검수 확인서 양식에 맞춰 항목별 검수 결과를 보여 줍니다. 개발계획서와 출력본 PDF는 선택 사항이며 각자의 칸에 따로 올립니다. 개발계획서를 올리면 ‘위치’와 대조 항목을, 원고를 한글에서 PDF로 저장한 출력본을 올리면 차례 ⑦(쪽수)을 함께 검수합니다.
        원고 여러 권을 한 번에 검수하려면 <a href="/review/batch">원고 폴더 일괄 검수</a>를 씁니다.
      </p>

      {/* 입력 묶음은 구획 셋: 파일 올리기 → 검수 조건 → 실행(권리 증빙 점검과 같은 구조). 구획 안에서만 3열 격자(.form-section-grid)를 쓴다 */}
      <form id="review-run" className="fieldset review-form is-sectioned nav-anchor" onSubmit={submit}>
        <div className="form-section" role="group" aria-labelledby="review-files-title">
        <h2 className="form-section-title" id="review-files-title">파일 올리기</h2>
        <div className="form-section-grid">
        {/* 업로드 칸 셋(#13): 원고(필수) / 개발계획서 / 출력본 PDF. 칸마다 따로 고르고 지울 수 있어, 개발계획서는 두고 원고만 바꿔 올릴 수 있다.
            역할은 칸이 정한다 — 서버는 내용으로 판별하지 않고 칸 이름을 그대로 쓴다. 고른 즉시 올려 읽을 수 있는 파일인지 확인한다 */}
        {SLOTS.map((slot) => (
          <FileSlot key={slot.role} id={`file-${slot.role}`} label={slot.label} required={slot.required} accept={slot.accept}
                    file={slots[slot.role]} disabled={busy}
                    onChange={(file) => { setSlots((prev) => ({ ...prev, [slot.role]: file })); setError(null); }}
                    uploading={upload.status === "uploading"}
                    invalid={
                      (slot.role === "manuscript" && upload.status === "error" ? upload.error : null)
                      || (slot.role === "manuscript" && tried && !slots.manuscript ? "원고 파일이 없습니다. 원고(hwp, hwpx)를 올려 주세요." : null)
                      || (slot.role === "plan" && !slots.plan && needsPlan ? "이 구성요소는 개발계획서가 필요합니다. 개발계획서를 올리세요." : null)
                    }
                    hint={
                      slot.role === "plan" && !slots.plan && !needsPlan
                        ? "hwp, hwpx. 없으면 대조 항목은 ‘판단불가’로 남습니다."
                      : slot.role === "print" && !slots.print
                        ? (usesPrint ? "pdf. 없으면 차례 ⑦(쪽수)은 ‘판단불가’로 남습니다." : "pdf. 이 구성요소는 출력본 PDF를 쓰지 않습니다.")
                      : null
                    } />
        ))}
        </div>
        </div>

        <div className="form-section" role="group" aria-labelledby="review-options-title">
        <h2 className="form-section-title" id="review-options-title">검수 조건</h2>
        <div className="form-section-grid">
        <div className="form-group">
          <div className="form-tit"><label htmlFor="check">검수 구성요소</label></div>
          <div className="form-conts">
            {/* KRDS 셀렉트: 레이블(form-tit) + 선택완료 상태(completed) + 도움말(form-hint). 값이 바뀌어도 폼은 제출하지 않는다 */}
            <KrdsSelect id="check" value={check} options={options} onChange={setCheck} title="검수 구성요소 선택" describedBy="check-hint" />
          </div>
          <p className="form-hint" id="check-hint">
            필요한 파일: {selected.files}
            {selected.items && selected.total ? `, 확인서 항목 ${selected.total}개 중 ${selected.items.length}개 검수` : ""}
          </p>
        </div>

        <div className="form-group">
          <div className="form-tit"><label htmlFor="module-code">모듈 코드 (선택)</label></div>
          <div className="form-conts">
            <input id="module-code" type="text" className="krds-input" placeholder="예: LM1203020201_24v3" value={moduleCode} onChange={(e) => setModuleCode(e.target.value)} />
          </div>
          <p className="form-hint">비워 두면 원고 파일 이름에서 찾습니다.</p>
        </div>

        {/* 원고 단계 — 진행 현황(/progress)에서 이 검수가 초고본·수정본·최종본 중 어느 것의 기록인지 가르는 데 쓴다. 고르지 않아도 검수는 같다 */}
        <div className="form-group">
          <div className="form-tit"><label htmlFor="work-stage">원고 단계</label></div>
          <div className="form-conts">
            <KrdsSelect id="work-stage" value={workStage} options={WORK_STAGE_OPTIONS} onChange={setWorkStage} title="원고 단계 선택" describedBy="work-stage-hint" />
          </div>
          <p className="form-hint" id="work-stage-hint">고르면 진행 현황에서 그 단계의 기록으로 보입니다.</p>
        </div>

        {/* 이미지 해상도 기준 — 지침에 숫자 기준이 없어 고르게 한다. 기타 ⑤·⑧만 쓰므로 전체·기타를 고를 때만 보인다 */}
        {usesImageDpi && (
          <div className="form-group">
            <div className="form-tit"><label htmlFor="image-dpi">이미지 해상도 기준</label></div>
            <div className="form-conts">
              <KrdsSelect id="image-dpi" value={imageDpi} options={IMAGE_DPI_OPTIONS} onChange={setImageDpi} title="이미지 해상도 기준 선택" describedBy="image-dpi-hint" />
            </div>
            <p className="form-hint" id="image-dpi-hint">기타 ⑤, ⑧에 적용합니다. 이보다 낮은 그림은 ‘판단불가’입니다.</p>
          </div>
        )}

        </div>
        </div>

        <div className="form-actions">
          <div className="run-buttons">
            <button className="krds-btn primary large" type="submit" disabled={busy || upload.status === "uploading"}>
              {busy ? "검수하는 중" : check === ALL_CHECK ? "전체 검수 실행" : "검수 실행"}
            </button>
            {busy && <button className="krds-btn tertiary large" type="button" onClick={cancel}>취소</button>}
          </div>
          {/* 실행·이력 열기 오류는 버튼 바로 아래에 — 검수 이력 표보다 먼저 보이도록 */}
          {error && <PageAlert kind="danger">{error}</PageAlert>}
          {notice && !error && <PageAlert kind="success">{notice}</PageAlert>}
        </div>
      </form>

      <div id="review-result" ref={resultsRef} className="results-anchor nav-anchor" />

      {busy && !allRun && (
        <ResultHead status={<Spinner label={`${selected.label} 검수하는 중`} />} />
      )}
      {allRun && <AllResults run={allRun} checks={reviewChecks} onError={setError} onNotice={setNotice}
                             uploadToken={upload.status === "ready" ? upload.token : null} />}

      {result && (
        <section aria-live="polite">
          <ResultHead
            status={<Badge value={result.요약.검수결과} large />}
            meta={`${result.module_code}, ${checks.find((item) => item.value === result.check)?.label || result.check}${result.created_at ? `, ${formatDate(result.created_at)}` : ""}`}
            downloads={
              <>
                {/* 단독 결과도 확인서 파일로 — 이 구성요소만 채워지고 나머지는 '미검사' */}
                <ExportButtons moduleCode={result.module_code} createdAt={result.created_at} rows={result.검수확인서 || []} onError={setError} onNotice={setNotice}
                               annotate={{ upload: upload.status === "ready" ? upload.token : null, runId: result.id,
                                           rows: (result.전체 || []).filter((r) => r.판정 !== "적합") }} />
                {result.id
                  ? <a href={api.reviews.zipUrl(result.id)} className="krds-btn small tertiary" title="결과 파일 내려받기(ZIP)">결과 파일 내려받기(ZIP)</a>
                  : result.저장?.zip ? <span className="meta">저장: {result.저장.zip}</span> : null}
              </>
            }
          />

          <h2 className="section-title">검수 확인서</h2>
          {/* 전체 실행의 아코디언 몸통과 같은 구성: 확인서(행마다 지적사항 펼치기) + 진단 경고 + 접힌 지적사항·전체 체크리스트 */}
          <ComponentResult result={result} showSave={false} />

          <RawJson data={result} title="원본 데이터 보기(개발자용)" />
        </section>
      )}

      {history && (
        <section id="review-history" className="nav-anchor history">
          <div className="section-head">
            <h2 className="section-title">검수 이력</h2>
          </div>
          {history.length === 0 ? <p className="empty">저장된 검수 이력이 없습니다.</p> : (
            <div className="krds-table-wrap" id="history-table">
              <table className="tbl col data history-table">
                <caption>최근 검수 실행</caption>
                {/* 열 너비 고정: '더 보기'로 행이 늘어도 칸 너비가 다시 계산되어 흔들리지 않게 */}
                {/* 실행 시각·모듈·판정·열기·삭제는 내용 폭이 정해져 있어 rem으로 고정(%면 창이 좁아질 때 모듈 코드·배지·버튼이 줄바꿈됨). 남는 폭은 모두 모듈 칸 */}
                <colgroup>
                  <col className="col-when" />
                  <col />
                  <col className="col-check" />
                  <col className="col-verdict" />
                  <col className="col-action" />
                  <col className="col-action" />
                </colgroup>
                <thead><tr><th scope="col">실행 시각</th><th scope="col">모듈</th><th scope="col">검수</th><th scope="col">판정</th><th scope="col">열기</th><th scope="col">삭제</th></tr></thead>
                <tbody>{history.slice((historyPage - 1) * HISTORY_PAGE, historyPage * HISTORY_PAGE).map((row) => (
                  <tr key={row.id} className={row.id === result?.id || row.id === allRun?.group ? "is-open" : undefined}>
                    <td className="when">{formatDateLines(row.created_at).map((line, i) => <span key={i}>{line}</span>)}</td>
                    <td className="module" title={row.module_code}>{row.module_code}</td>
                    <td>{row.kind === "group"
                      ? `전체 실행(구성요소 ${row.checks.filter((c) => reviewChecks.some((item) => item.value === c)).length}/${reviewChecks.length})`
                      : checks.find((item) => item.value === row.check_name)?.label || row.check_name}</td>
                    <td><Badge value={row.verdict} /></td>
                    <td><button className="krds-btn small tertiary" type="button" onClick={() => (row.kind === "group" ? openGroup(row.id) : openHistory(row.id))}>결과 보기</button></td>
                    <td>
                      <button className="krds-btn small tertiary btn-delete-history" type="button" onClick={() => setPendingDelete(row)}>
                        <i className="svg-icon ico-del" aria-hidden="true"></i>삭제
                      </button>
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <Pagination page={historyPage} total={Math.ceil(history.length / HISTORY_PAGE)} onChange={setHistoryPage} label="검수 이력 페이지" />
        </section>
      )}

      <TopButton />

      {pendingDelete && (
        <ConfirmDialog title="검수 이력 삭제" confirmLabel="삭제" busy={deleting}
                       onConfirm={() => deleteHistory(pendingDelete)} onCancel={() => setPendingDelete(null)}>
          <p>정말 삭제하시겠습니까?</p>
          <p className="meta">
            {formatDate(pendingDelete.created_at)}, {pendingDelete.module_code},{" "}
            {pendingDelete.kind === "group" ? `전체 실행(구성요소 ${pendingDelete.checks.length}개)` : checks.find((item) => item.value === pendingDelete.check_name)?.label || pendingDelete.check_name}
          </p>
          <p className="meta">삭제한 이력은 되돌릴 수 없습니다.</p>
        </ConfirmDialog>
      )}
    </main>
    <Footer />
    </>
  );
}

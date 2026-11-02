import React, { useEffect, useRef, useState } from "react";

import { api } from "./lib/api.js";
import { ALL_CHECK, ALL_OPTION, CHECKS, checksFromEngines } from "./lib/checks.js";
import { formatDate } from "./lib/format.jsx";
import { AllResults, ComponentResult } from "./components/AllResults.jsx";
import { Badge, Spinner } from "./components/Badge.jsx";
import { ConfirmDialog } from "./components/ConfirmDialog.jsx";
import { ExportButtons } from "./components/ExportButtons.jsx";
import { KrdsSelect } from "./components/KrdsSelect.jsx";
import { Footer, Header, TopButton } from "./components/Layout.jsx";

const HISTORY_PREVIEW = 5;

export default function App() {
  const [check, setCheck] = useState("position");
  const [checks, setChecks] = useState(CHECKS);
  const [files, setFiles] = useState([]);
  const [moduleCode, setModuleCode] = useState("");
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
  const fileInput = useRef(null);    // 숨긴 <input type=file> — 진짜 <button>이 대신 열어 키보드(Enter/Space)로도 동작
  const [pendingDelete, setPendingDelete] = useState(null); // 삭제 확인 창에 올라간 이력 행
  const [historyExpanded, setHistoryExpanded] = useState(false); // 이력은 기본 최근 5건만, '더 보기'로 전체
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
    api.uploads.create(files, controller.signal).then(({ ok, data, error: message, aborted }) => {
      if (aborted) return;
      setUpload(ok ? { status: "ready", token: data.upload, group: data.group, roles: data.roles } : { status: "error", error: message });
    });
    return () => controller.abort();
  }, [files]);

  // 실행에 쓸 토큰. 미리 올린 것이 없거나(오류) 만료됐으면 지금 다시 올린다. 실패하면 null(오류는 setError).
  async function ensureUpload(signal) {
    const current = uploadRef.current;
    if (current.status === "ready") return current;
    const { ok, data, error: message, aborted } = await api.uploads.create(files, signal);
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

  const options = [...checks, ALL_OPTION];
  const selected = options.find((c) => c.value === check) || options[0];

  async function submit(event) {
    event.preventDefault();
    if (check === ALL_CHECK) return runAll();
    setBusy(true);
    setError(null);
    setNotice(null);
    setResult(null);
    setAllRun(null);
    const controller = new AbortController();
    aborter.current = controller;
    let kept = await ensureUpload(controller.signal);
    let answer = kept ? await api.review({ check, moduleCode, upload: kept.token, signal: controller.signal }) : null;
    if (answer && !answer.ok && answer.status === 400 && /만료/.test(answer.error)) {
      setUpload({ status: "idle" });
      uploadRef.current = { status: "idle" };
      kept = await ensureUpload(controller.signal);
      answer = kept ? await api.review({ check, moduleCode, upload: kept.token, signal: controller.signal }) : null;
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
    const order = checks.map((c) => c.value);
    const controller = new AbortController();
    aborter.current = controller;
    // 미리 올린 토큰은 단독 실행용. 전체 실행은 이력 묶음 id가 실행마다 달라야 해서 새 토큰(새 묶음)을 만든다.
    const created = await api.uploads.create(files, controller.signal);
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
      const needsPlan = (checks.find((c) => c.value === value)?.required || []).includes("plan");
      items[value] = { status: needsPlan && !hasPlan ? "skipped" : "pending" };
    });
    setAllRun({ group: upload.group, roles: upload.roles, items, running: true, created_at: new Date().toISOString() });
    const update = (value, patch) => setAllRun((prev) => (prev ? { ...prev, items: { ...prev.items, [value]: { ...prev.items[value], ...patch } } } : prev));
    let cancelled = false;
    for (const value of order) {
      if (items[value].status === "skipped") continue;
      if (cancelled) { update(value, { status: "cancelled" }); continue; }
      update(value, { status: "running" });
      const { ok, data, error: message, aborted } = await api.review({ check: value, moduleCode, upload: upload.upload, group: upload.group, signal: controller.signal });
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
    checks.forEach((c) => { items[c.value] = { status: "skipped" }; });
    data.runs.forEach((run) => { items[run.check] = { status: "done", data: run }; });
    const hasPlan = data.runs.some((run) => run.진단?.inputs?.plan);
    setResult(null);
    setAllRun({ group: id, roles: { manuscript: true, plan: hasPlan }, items, running: false, created_at: data.created_at, module_code: data.module_code });
  }

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
      <h1 className="page-title">NCS 학습모듈 검수 확인 (로컬 테스트)</h1>
      <p className="page-desc">
        원고와 개발계획서(.hwp/.hwpx)를 올리면 검수 패키지를 그대로 실행해 검수 확인서 형식과 결과 JSON을 보여줍니다. 파일 역할은 내용으로 자동 판별합니다.
      </p>

      <form id="review-run" className="fieldset review-form nav-anchor" onSubmit={submit}>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="check">검수 구성요소</label></div>
          <div className="form-conts">
            {/* KRDS 셀렉트: 레이블(form-tit) + 선택완료 상태(completed) + 도움말(form-hint). 값이 바뀌어도 폼은 제출하지 않는다 */}
            <KrdsSelect id="check" value={check} options={options} onChange={setCheck} title="검수 구성요소 선택" describedBy="check-hint" />
          </div>
          <p className="form-hint" id="check-hint">
            필요한 파일: {selected.files}
            {selected.items && selected.total ? ` · 확인서 항목 ${selected.total}개 중 ${selected.items.length}개 검사` : ""}
          </p>
        </div>

        <div className="form-group">
          <div className="form-tit"><label htmlFor="files">파일</label></div>
          <div className="form-conts">
            <input ref={fileInput} id="files" type="file" multiple accept=".hwp,.hwpx" className="sr-only" tabIndex={-1} aria-describedby="files-hint"
                   onChange={(e) => setFiles(Array.from(e.target.files || []))} />
            {/* 셀렉트·입력칸과 같은 large 높이(--krds-size-height large)로 세 칸의 규격을 맞춘다 */}
            <button type="button" className="krds-btn large tertiary" disabled={busy} onClick={() => fileInput.current?.click()}>파일 선택</button>
          </div>
          {/* 고른 즉시 서버가 내용으로 역할을 판별해 파일명 뒤에 적어 준다(원고/개발계획서). 실행 전에 '개발계획서 없음'을 알 수 있다 */}
          <p className="form-hint" id="files-hint">
            {!files.length ? "선택된 파일 없음"
              : upload.status === "uploading" ? `${files.map((f) => f.name).join(", ")} — 역할 확인 중…`
              : files.map((f) => {
                const role = upload.status !== "ready" ? null
                  : upload.roles?.manuscript === f.name ? "원고" : upload.roles?.plan === f.name ? "개발계획서" : "역할 미판별";
                return role ? `${f.name} (${role})` : f.name;
              }).join(", ")}
          </p>
          {upload.status === "error" && <p className="form-hint-invalid" role="alert" style={{ whiteSpace: "pre-wrap" }}>{upload.error}</p>}
          {upload.status === "ready" && !upload.roles?.plan && (selected.required || []).includes("plan") && (
            <p className="form-hint-invalid">이 구성요소는 개발계획서가 필요합니다. 개발계획서를 함께 올리세요.</p>
          )}
          {upload.status === "ready" && !upload.roles?.manuscript && (
            <p className="form-hint-invalid">원고를 찾지 못했습니다. 원고 파일을 올리세요.</p>
          )}
        </div>

        <div className="form-group">
          <div className="form-tit"><label htmlFor="module-code">모듈 코드 (선택)</label></div>
          <div className="form-conts">
            <input id="module-code" type="text" className="krds-input" placeholder="예: LM1203020201_24v3" value={moduleCode} onChange={(e) => setModuleCode(e.target.value)} />
          </div>
          <p className="form-hint">비우면 원고 파일명에서 추출</p>
        </div>

        <div className="form-group form-actions">
          <div className="run-buttons">
            <button className="krds-btn primary large" type="submit" disabled={busy || files.length === 0 || upload.status === "uploading"}>
              {busy ? "검사 중…" : check === ALL_CHECK ? "전체 검사 실행" : "검사 실행"}
            </button>
            {busy && <button className="krds-btn tertiary large" type="button" onClick={cancel}>취소</button>}
          </div>
          {/* 실행·이력 열기 오류는 버튼 바로 아래에 — 검수 이력 표보다 먼저 보이도록 */}
          {error && (
            <p className="form-hint-invalid" role="alert" style={{ whiteSpace: "pre-wrap" }}>{error}</p>
          )}
          {notice && !error && <p className="form-hint-success" role="status">{notice}</p>}
        </div>
      </form>

      <div id="review-result" ref={resultsRef} className="results-anchor nav-anchor" />

      {busy && !allRun && (
        <div className="result-head"><Spinner label={`검사 중 — ${selected.label}`} /></div>
      )}
      {!allRun && !result && !busy && (
        <p className="empty result-placeholder">검사를 실행하면 결과가 여기에 표시됩니다{history?.length ? " — 아래 검수 이력에서 이전 결과를 열 수도 있습니다" : ""}.</p>
      )}
      {allRun && <AllResults run={allRun} checks={checks} onError={setError} onNotice={setNotice}
                             uploadToken={upload.status === "ready" ? upload.token : null} />}

      {result && (
        <section>
          <div className="result-head">
            <Badge value={result.요약.검수결과} large />
            <span className="meta">{result.module_code} · {checks.find((item) => item.value === result.check)?.label || result.check}</span>
            {result.id ? <a href={api.reviews.zipUrl(result.id)}>ZIP 다운로드</a> : <span className="meta">저장: {result.저장?.zip}</span>}
            {/* 단독 결과도 확인서 파일로 — 이 구성요소만 채워지고 나머지는 '미검사' */}
            <ExportButtons moduleCode={result.module_code} createdAt={result.created_at} rows={result.검수확인서 || []} onError={setError} onNotice={setNotice}
                           annotate={{ upload: upload.status === "ready" ? upload.token : null, rows: (result.전체 || []).filter((r) => r.판정 !== "적합") }} />
          </div>

          <h2 className="section-title">검수 확인서</h2>
          {/* 전체 실행의 아코디언 몸통과 같은 구성: 확인서(행마다 지적사항 펼치기) + 진단 경고 + 접힌 지적사항·전체 체크리스트 */}
          <ComponentResult result={result} showSave={false} />

          <details className="raw">
            <summary>원본 JSON (요약·진단·검수확인서·지적사항·전체)</summary>
            <pre>{JSON.stringify(result, null, 1)}</pre>
          </details>
        </section>
      )}

      {history && (
        <section id="review-history" className="nav-anchor history">
          <div className="section-head">
            <h2 className="section-title">검수 이력 <span className="meta">({history.length}건)</span></h2>
            {history.length > HISTORY_PREVIEW && (
              <button type="button" className="krds-btn small text" aria-expanded={historyExpanded} aria-controls="history-table"
                      onClick={() => setHistoryExpanded((v) => !v)}>
                {historyExpanded ? "최근 5건만 보기" : `더 보기 (${history.length - HISTORY_PREVIEW}건 더)`}
              </button>
            )}
          </div>
          {history.length === 0 ? <p className="empty">저장된 검수 이력이 없습니다.</p> : (
            <div className="krds-table-wrap" id="history-table">
              <table className="tbl col data history-table">
                <caption>최근 검수 실행</caption>
                {/* 열 너비 고정: '더 보기'로 행이 늘어도 칸 너비가 다시 계산되어 흔들리지 않게 */}
                {/* 판정·열기·삭제는 내용 폭이 정해져 있어 rem으로 고정(%면 창이 좁아질 때 '부적합' 배지·버튼이 줄바꿈됨). 나머지는 비율 */}
                <colgroup>
                  <col style={{ width: "18%" }} />
                  <col style={{ width: "18%" }} />
                  <col />
                  <col className="col-verdict" />
                  <col className="col-action" />
                  <col className="col-action" />
                </colgroup>
                <thead><tr><th scope="col">실행 시각</th><th scope="col">모듈</th><th scope="col">검수</th><th scope="col">판정</th><th scope="col">열기</th><th scope="col">삭제</th></tr></thead>
                <tbody>{(historyExpanded ? history : history.slice(0, HISTORY_PREVIEW)).map((row) => (
                  <tr key={row.id} className={row.id === result?.id || row.id === allRun?.group ? "is-open" : undefined}>
                    <td>{formatDate(row.created_at)}</td>
                    <td>{row.module_code}</td>
                    <td>{row.kind === "group"
                      ? `전체 실행 — 구성요소 ${row.checks.length}/${checks.length}`
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
        </section>
      )}

      <TopButton />

      {pendingDelete && (
        <ConfirmDialog title="검수 이력 삭제" confirmLabel="삭제" busy={deleting}
                       onConfirm={() => deleteHistory(pendingDelete)} onCancel={() => setPendingDelete(null)}>
          <p>정말 삭제하시겠습니까?</p>
          <p className="meta">
            {formatDate(pendingDelete.created_at)} · {pendingDelete.module_code} ·{" "}
            {pendingDelete.kind === "group" ? `전체 실행 — 구성요소 ${pendingDelete.checks.length}개` : checks.find((item) => item.value === pendingDelete.check_name)?.label || pendingDelete.check_name}
          </p>
          <p className="meta">삭제한 이력은 되돌릴 수 없습니다.</p>
        </ConfirmDialog>
      )}
    </main>
    <Footer />
    </>
  );
}

// 원고 폴더 일괄 검수(REQ-02-002 사람 작업 1 '입력 원고(또는 원고 폴더) 준비') — 원고 여러 권을 한 번에 올려 권마다 구성요소 전체를 차례로 검수한다.
// 서버 경로는 원고 검수와 같다: 권마다 /api/uploads로 올려 묶음을 만들고 구성요소마다 /api/review를 부른다. 결과는 권별 요약 표로 보이고,
// 권을 누르면 원고 검수 화면에서 그 묶음을 연다(/review?group=). 모듈 코드는 원고 파일명에서 읽으므로 파일명에 LM 코드가 있어야 한다.
import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api.js";
import { FileSlot, MultiFileSlot } from "../components/FileSlot.jsx";
import { Badge, Spinner } from "../components/Badge.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { usePageTitle } from "../lib/hooks.js";
import { checksFromEngines, manuscriptChecks, overallVerdict } from "../lib/checks.js";

const ANCHORS = [{ id: "batch-form", label: "원고 올리기" }, { id: "batch-result", label: "권별 결과" }];
const CODE = /LM\d{10}_\d+v\d+/;

export default function BatchReviewPage() {
  usePageTitle("원고 폴더 일괄 검수");
  const [checks, setChecks] = useState(null);       // 원고 검수 구성요소(서버가 알려 준 엔진 목록)
  const [manuscripts, setManuscripts] = useState([]);
  const [plan, setPlan] = useState(null);
  const [rows, setRows] = useState([]);             // 권별 진행·결과: { name, status, done, total, verdicts: {check: 판정}, group, error }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const aborter = useRef(null);

  useEffect(() => {
    api.health().then(({ ok, data }) => setChecks(manuscriptChecks(checksFromEngines(ok ? data.engines : null))));
  }, []);

  const noCode = manuscripts.filter((file) => !CODE.test(file.name));

  async function run(e) {
    e.preventDefault();
    if (!manuscripts.length || !checks) return;
    setBusy(true); setError(null);
    const controller = new AbortController();
    aborter.current = controller;
    const start = manuscripts.map((file) => ({ name: file.name, status: "pending", done: 0, total: 0, verdicts: {} }));
    setRows(start);
    const patch = (index, change) => setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...(typeof change === "function" ? change(row) : change) } : row)));
    let cancelled = false;
    for (let index = 0; index < manuscripts.length; index += 1) {
      if (cancelled) { patch(index, { status: "cancelled" }); continue; }
      const files = plan ? [manuscripts[index], plan] : [manuscripts[index]];
      const roles = plan ? ["manuscript", "plan"] : ["manuscript"];
      patch(index, { status: "running" });
      const created = await api.uploads.create(files, controller.signal, roles);
      if (!created.ok) {
        if (created.aborted) { cancelled = true; patch(index, { status: "cancelled" }); } else patch(index, { status: "error", error: created.error });
        continue;
      }
      const upload = created.data;
      const order = checks.filter((c) => !(c.required || []).includes("plan") || plan).map((c) => c.value);
      patch(index, { total: order.length, group: upload.group });
      const failed = [];
      for (const value of order) {
        const { ok, data, error: message, aborted } = await api.review({ check: value, upload: upload.upload, group: upload.group, signal: controller.signal });
        if (aborted) { cancelled = true; break; }
        if (!ok) failed.push(`${value}: ${message}`);
        patch(index, (row) => ({ done: row.done + 1, verdicts: ok ? { ...row.verdicts, [value]: data.요약?.검수결과 } : row.verdicts, module_code: data?.module_code || row.module_code }));
      }
      api.uploads.remove(upload.upload);
      patch(index, { status: cancelled ? "cancelled" : failed.length ? "error" : "done", error: failed.join(" / ") || undefined });
    }
    aborter.current = null;
    setBusy(false);
    setTimeout(() => document.getElementById("batch-result")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  const count = (row, verdict) => Object.values(row.verdicts).filter((value) => value === verdict).length;
  const finished = rows.filter((row) => row.status === "done").length;

  return (
    <>
    <Header anchors={ANCHORS} hasHistory={false} hasResult={rows.length > 0} />
    <main id="container" className="inner page">
      <h1 className="page-title">원고 폴더 일괄 검수</h1>
      <p className="page-desc">
        원고 여러 권을 한 번에 올려 권마다 구성요소 전체를 차례로 검수합니다. 결과는 권별로 요약해 보여 주고, 권을 누르면 원고 검수 화면에서 자세히 봅니다.
        한 권씩 볼 때는 <Link to="/review">원고 검수</Link>를 씁니다.
      </p>

      <form id="batch-form" className="fieldset review-form is-sectioned nav-anchor" onSubmit={run}>
        <div className="form-section-grid">
          <MultiFileSlot id="batch-manuscripts" label="원고" required accept=".hwp,.hwpx" files={manuscripts} disabled={busy} wide
                         onChange={setManuscripts} hint="폴더의 원고 파일을 모두 골라 올립니다. 파일명에 학습모듈 코드(LM…)가 있어야 합니다." />
          <FileSlot id="batch-plan" label="개발계획서" accept=".hwp,.hwpx" file={plan} disabled={busy} onChange={setPlan}
                    hint="같은 세분류의 개발계획서 하나. 없으면 ‘위치’는 건너뛰고, 학습 목표는 받아 둔 NCS 기준정보와 대조합니다." />
        </div>
        <div className="form-group form-actions">
          <div className="run-buttons">
            <button className="krds-btn primary large" type="submit" disabled={busy || !manuscripts.length || !checks}>{busy ? "검수하는 중" : `원고 ${manuscripts.length}권 검수 실행`}</button>
            {busy && <button className="krds-btn tertiary large" type="button" onClick={() => aborter.current?.abort()}>취소</button>}
          </div>
          {noCode.length > 0 && <PageAlert kind="warning">파일명에 학습모듈 코드가 없는 원고 {noCode.length}권은 검수하지 못합니다: {noCode.map((file) => file.name).join(", ")}</PageAlert>}
          <PageAlert kind="danger">{error}</PageAlert>
        </div>
      </form>

      <div id="batch-result" className="results-anchor nav-anchor" />
      {rows.length > 0 && (
        <section aria-live="polite">
          <h2 className="section-title">권별 결과 ({finished}/{rows.length})</h2>
          <div className="krds-table-wrap">
            <table className="tbl col data batch-table">
              <caption>원고별 검수 결과 요약</caption>
              <thead><tr><th scope="col">원고</th><th scope="col">상태</th><th scope="col">결과</th><th scope="col">부적합</th><th scope="col">판단불가</th><th scope="col">적합</th><th scope="col">자세히</th></tr></thead>
              <tbody>
                {rows.map((row) => {
                  const verdict = overallVerdict(Object.values(row.verdicts));
                  return (
                    <tr key={row.name}>
                      <td><strong>{row.name}</strong>{row.module_code && <><br /><span className="code">{row.module_code}</span></>}{row.error && <p className="form-hint-invalid">{row.error}</p>}</td>
                      <td>{row.status === "running" ? <Spinner label={`검수하는 중 ${row.done}/${row.total || "?"}`} />
                        : { pending: "기다리는 중", done: "끝남", error: "오류", cancelled: "취소됨" }[row.status]}</td>
                      <td>{verdict && row.status !== "running" ? <Badge value={verdict} /> : "-"}</td>
                      <td>{count(row, "부적합")}</td><td>{count(row, "판단불가")}</td><td>{count(row, "적합")}</td>
                      <td>{row.group && row.status === "done" ? <Link className="krds-btn small tertiary" to={`/review?group=${row.group}`}>결과 열기</Link> : "-"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="meta">부적합·판단불가·적합은 구성요소 수입니다(구성요소 하나에 부적합 항목이 있으면 그 구성요소가 부적합). 결과는 검수 이력에 권별 묶음으로 남습니다.</p>
        </section>
      )}
      <TopButton />
    </main>
    <Footer />
    </>
  );
}

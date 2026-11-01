// 전체 실행 결과 — 구성요소별 KRDS 아코디언. 실행 자체(업로드 토큰·순차 호출)는 App.runAll이 하고 여기는 run 상태를 그린다.
import React, { useState } from "react";
import { Badge, Spinner } from "./Badge.jsx";
import { ExportButtons } from "./ExportButtons.jsx";
import { ChecklistTable, FindingsTable, SheetTable } from "./Tables.jsx";
import { api } from "../lib/api.js";
import { countVerdicts, overallVerdict } from "../lib/checks.js";
import { formatDate } from "../lib/format.jsx";

// 아코디언 머리의 상태 표시: 대기 / 검사 중 / 건너뜀 / 오류 / 판정 + 항목 수
export function ItemStatus({ item }) {
  if (item.status === "pending") return <span className="krds-badge bg-light-gray">대기</span>;
  if (item.status === "running") return <Spinner label="검사 중…" />;
  if (item.status === "skipped") return <span className="krds-badge bg-light-gray">미실행 — 개발계획서 없음</span>;
  if (item.status === "cancelled") return <span className="krds-badge bg-light-gray">취소됨</span>;
  if (item.status === "error") return <span className="krds-badge bg-light-danger">오류</span>;
  const counts = countVerdicts(item.data?.검수확인서);
  return (
    <span className="item-status">
      <Badge value={item.data?.요약?.검수결과} />
      <span className="counts">
        <span className="count pass">적합 {counts.적합}</span>
        <span className="count fail">부적합 {counts.부적합}</span>
        <span className="count undecided">판단불가 {counts.판단불가}</span>
      </span>
    </span>
  );
}

export function AllResults({ run, checks, onError }) {
  const [expanded, setExpanded] = useState(() => new Set());
  const [view, setView] = useState("accordion");   // "accordion"(구성요소별) | "sheet"(확인서 한 표)
  const order = checks.filter((c) => !c.all).map((c) => c.value);
  const items = order.map((check) => ({ check, option: checks.find((c) => c.value === check), ...(run.items[check] || { status: "pending" }) }));
  const finished = items.filter((i) => i.status === "done");
  const verdict = overallVerdict(finished.map((i) => i.data?.요약?.검수결과));
  const total = finished.reduce((acc, i) => {
    const c = countVerdicts(i.data?.검수확인서);
    return { 적합: acc.적합 + c.적합, 부적합: acc.부적합 + c.부적합, 판단불가: acc.판단불가 + c.판단불가 };
  }, { 적합: 0, 부적합: 0, 판단불가: 0 });
  const moduleCode = finished[0]?.data?.module_code || run.module_code || "";
  const openable = items.filter((i) => i.status !== "pending" && i.status !== "running").map((i) => i.check);

  function toggle(check) {
    setExpanded((prev) => { const next = new Set(prev); next.has(check) ? next.delete(check) : next.add(check); return next; });
  }

  return (
    <section className="all-results" aria-live="polite">
      <div className="result-head">
        {run.running
          ? <Spinner label={`검사 중 — ${items.filter((i) => i.status === "done" || i.status === "error" || i.status === "skipped").length}/${items.length} 구성요소 완료`} />
          : verdict ? <Badge value={verdict} large /> : <span className="krds-badge large bg-light-gray">결과 없음</span>}
        <span className="meta">{moduleCode}{moduleCode ? " · " : ""}전체 실행{run.created_at ? ` · ${formatDate(run.created_at)}` : ""}</span>
        <span className="meta">적합 {total.적합} · 부적합 {total.부적합} · 판단불가 {total.판단불가} 항목</span>
        {run.roles && !run.roles.plan && <span className="krds-badge bg-light-warning">개발계획서 없음 — 위치 미실행</span>}
        {run.cancelled && <span className="krds-badge bg-light-gray">중간에 취소됨</span>}
        {!run.running && finished.length > 0 && (
          <ExportButtons moduleCode={moduleCode} createdAt={run.created_at} onError={onError}
                         rows={finished.flatMap((i) => i.data.검수확인서 || [])} />
        )}
        <span className="toolbar">
          {view === "accordion" && (
            <>
              <button type="button" className="krds-btn xsmall text" onClick={() => setExpanded(new Set(openable))} disabled={!openable.length}>모두 펼치기</button>
              <button type="button" className="krds-btn xsmall text" onClick={() => setExpanded(new Set())} disabled={!expanded.size}>모두 접기</button>
            </>
          )}
        </span>
      </div>

      {/* 보기 전환 — KRDS 탭(krds-tab-area.layer › .tab.line › ul[role=tablist] › li[role=tab].active › button.btn-tab) 마크업 그대로.
          아코디언은 구성요소별로 파고들 때, 한 표는 확인서 전체(F02 양식 한 장)를 훑을 때 */}
      <div className="krds-tab-area layer view-switch">
        <div className="tab line">
          <ul role="tablist" aria-label="결과 보기 방식">
            {[["accordion", "구성요소별 보기"], ["sheet", "확인서 한 표로 보기"]].map(([key, label]) => (
              <li key={key} id={`view-tab-${key}`} role="tab" aria-selected={view === key} aria-controls={`view-panel-${key}`} className={view === key ? "active" : ""}>
                <button type="button" className="btn-tab" onClick={() => setView(key)}>
                  {label}{view === key && <i className="sr-only created"> 선택됨</i>}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {view === "sheet" && (
        <section id="view-panel-sheet" role="tabpanel" aria-labelledby="view-tab-sheet" className="tab-conts active">
          <FullSheet items={items} />
        </section>
      )}

      {view === "accordion" && <section id="view-panel-accordion" role="tabpanel" aria-labelledby="view-tab-accordion" className="tab-conts active">
      <h2 className="section-title">구성요소별 검수 결과</h2>
      {/* KRDS 아코디언: accordion-item(.active) › h5.accordion-header › button.btn-accordion(.active, aria-controls) + .accordion-collapse(aria-labelledby) › .accordion-body */}
      <div className="krds-accordion">
        {items.map((item) => {
          const open = expanded.has(item.check);
          const canOpen = openable.includes(item.check);
          const headerId = `all-head-${item.check}`;
          const bodyId = `all-body-${item.check}`;
          return (
            <div key={item.check} className={`accordion-item${open ? " active" : ""} status-${item.status}`}>
              <h5 className="accordion-header">
                <button type="button" id={headerId} className={`btn-accordion${open ? " active" : ""}`} aria-controls={bodyId} aria-expanded={open}
                        disabled={!canOpen} onClick={() => toggle(item.check)}>
                  <span className="acc-title">
                    <span className="acc-name">{item.option?.label || item.check}</span>
                    <ItemStatus item={item} />
                  </span>
                </button>
              </h5>
              <div id={bodyId} className="accordion-collapse collapse" aria-labelledby={headerId}>
                <div className="accordion-body">
                  {open && item.status === "cancelled" && <p className="empty">취소되어 실행하지 않았습니다.</p>}
                  {open && item.status === "skipped" && (
                    <p className="empty">개발계획서가 없어 실행하지 않았습니다. 위치 ①~⑤는 원고와 개발계획서를 함께 올렸을 때만 검사합니다.</p>
                  )}
                  {open && item.status === "error" && (
                    <p className="form-hint-invalid" role="alert" style={{ whiteSpace: "pre-wrap" }}>{item.error}</p>
                  )}
                  {open && item.status === "done" && <ComponentResult result={item.data} />}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      </section>}
    </section>
  );
}

// 확인서 한 표: 끝난 구성요소의 확인서 행을 순서대로 이어 붙인다(F02 양식 한 장). 실행되지 않은 구성요소는 표 위에 적는다.
function FullSheet({ items }) {
  const done = items.filter((i) => i.status === "done");
  const sheet = done.flatMap((i) => (i.data.검수확인서 || []).map((row) => ({ ...row, _check: i.check })));
  const findings = done.flatMap((i) => (i.data.지적사항 || []).map((f) => ({ ...f, _check: i.check })));
  const missing = items.filter((i) => i.status !== "done");
  const label = { skipped: "미실행(개발계획서 없음)", error: "오류", pending: "대기", running: "검사 중", cancelled: "취소됨" };
  return (
    <>
      <h2 className="section-title">검수 확인서 (구성요소 {done.length}/{items.length})</h2>
      {missing.length > 0 && (
        <p className="meta full-sheet-missing">
          표에 없는 구성요소: {missing.map((i) => `${i.option?.label || i.check} — ${label[i.status] || i.status}`).join(" / ")}
        </p>
      )}
      {sheet.length ? <SheetTable sheet={sheet} findings={findings} /> : <p className="empty">아직 끝난 구성요소가 없습니다.</p>}
    </>
  );
}

// 아코디언 몸통: 그 구성요소의 확인서(행마다 지적사항 펼치기) + 진단 경고 + ZIP. 지적사항·전체 체크리스트는 접힌 상세로.
// showSave: ZIP 링크·저장 경로를 표시할지(단독 결과 화면은 머리에 따로 있어 끈다)
export function ComponentResult({ result, showSave = true }) {
  return (
    <div className="component-result">
      <SheetTable sheet={result.검수확인서 || []} findings={result.지적사항 || []} />
      {result.진단?.warnings?.length > 0 && (
        <ul className="krds-info-list dash">
          {result.진단.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
      <div className="component-foot">
        {showSave && (result.id ? <a href={api.reviews.zipUrl(result.id)}>ZIP 다운로드</a> : result.저장?.zip ? <span className="meta">저장: {result.저장.zip}</span> : null)}
        <details>
          <summary>지적사항 {result.지적사항?.length || 0}건 · 전체 체크리스트 {result.전체?.length || 0}행</summary>
          <FindingsTable findings={result.지적사항 || []} />
          <ChecklistTable rows={result.전체 || []} />
        </details>
      </div>
    </div>
  );
}

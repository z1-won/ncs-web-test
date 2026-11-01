import React, { useEffect, useRef, useState } from "react";

// 순서 = F02 검수 확인서의 구성요소 순서(위치 → 차례 → 개요 → 필요 지식 → 수행 내용 → 교수·학습 방법 → 평가 → …)
// 선택 목록의 기본값. 글(구성요소·항목 번호)은 서버 /api/health의 engines(실제 등록된 엔진·구현 항목)로 덮어쓴다.
// 순서 = F02 검수 확인서의 구성요소 순서(위치 → 차례 → 개요 → 필요 지식 → 수행 내용 → 교수·학습 방법 → 평가 → 참고 자료 → 판권 → 기타)
const FILE_HINTS = {
  position: "원고 + 개발계획서 (2개 필수)",
  toc: "원고 (+ 개발계획서 선택)",
  overview: "원고 (+ 개발계획서 선택)",
  knowledge: "원고 (+ 개발계획서: ⑤에만 필요)",
  perform: "원고 (hwpx 권장)",
  teaching: "원고 (hwpx 권장)",
  evaluation: "원고 + 개발계획서 (없으면 ② 판단불가)",
  references: "원고",
  colophon: "원고 (hwpx 권장)",
  misc: "원고 (hwpx 권장)",
};
const CHECKS = [
  { value: "position", label: "NCS-학습모듈의 위치 ①~⑤" },
  { value: "toc", label: "차례 ①~⑥" },
  { value: "overview", label: "학습모듈의 개요 ①·②·⑤~⑧" },
  { value: "knowledge", label: "필요 지식 ①~⑧" },
  { value: "perform", label: "수행 내용 ①·④" },
  { value: "teaching", label: "교수·학습 방법 ①~④" },
  { value: "evaluation", label: "평가 ①~③·⑤" },
  { value: "references", label: "참고 자료 ①~③" },
  { value: "colophon", label: "개발 이력 및 판권 ①" },
  { value: "misc", label: "기타 ①·②·⑥·⑦" },
].map((c) => ({ ...c, files: FILE_HINTS[c.value] || "원고", required: c.value === "position" ? ["manuscript", "plan"] : ["manuscript"] }));

const CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫";

// 구현된 항목 번호 목록 → "①~③·⑤" (연속 3개 이상은 범위로)
function formatItems(items) {
  const idx = items.map((n) => CIRCLED.indexOf(n)).filter((i) => i >= 0).sort((a, b) => a - b);
  const parts = [];
  for (let i = 0; i < idx.length;) {
    let j = i;
    while (j + 1 < idx.length && idx[j + 1] === idx[j] + 1) j += 1;
    parts.push(j - i >= 2 ? `${CIRCLED[idx[i]]}~${CIRCLED[idx[j]]}` : idx.slice(i, j + 1).map((k) => CIRCLED[k]).join("·"));
    i = j + 1;
  }
  return parts.join("·");
}

// 서버가 알려 준 엔진 목록으로 선택 목록을 만든다. 구성요소 이름의 띄어쓰기는 확인서 원문(예: "개발 이력 및판권")을 읽기 좋게 고른다.
function checksFromEngines(engines) {
  if (!Array.isArray(engines) || !engines.length) return CHECKS;
  return engines.map((e) => ({
    value: e.check,
    label: `${String(e.component).replace("및판권", "및 판권")} ${formatItems(e.items || [])}`,
    files: FILE_HINTS[e.check] || (e.required?.includes("plan") ? "원고 + 개발계획서" : "원고"),
    items: e.items,
    total: e.total,
    required: e.required || ["manuscript"],
  }));
}

// 검수결과 → KRDS 배지 변형
const BADGE = { 적합: "bg-light-success", 부적합: "bg-light-danger", 판단불가: "bg-light-warning", 미검사: "bg-light-gray" };
const MARK = { 적합: "pass", 부적합: "fail", 판단불가: "undecided" };

function Badge({ value, large }) {
  return <span className={`krds-badge ${large ? "large " : ""}${BADGE[value] || "bg-light-gray"}`}>{value}</span>;
}

// 결과 텍스트의 네모 번호 표기 [1]~[20]을 한컴 원고처럼 네모 안 숫자로 그린다(유니코드에 대응 글자가 없어 CSS로 그림).
function withBoxNumbers(text) {
  if (typeof text !== "string" || !/\[\d{1,2}\]/.test(text)) return text;
  const parts = text.split(/(\[\d{1,2}\])/);
  return parts.map((part, i) => (/^\[\d{1,2}\]$/.test(part)
    ? <span key={i} className="box-number" aria-label={`네모 번호 ${part.slice(1, -1)}`}>{part.slice(1, -1)}</span>
    : part));
}

// 결과 값(문자열·목록·딕셔너리)을 표 칸에 읽기 좋게 편다. 데이터 자체(JSON·ZIP)는 구조를 그대로 유지한다.
//   목록      → 한 줄에 하나
//   딕셔너리  → "이름: 값" 한 줄에 하나 (값이 목록이면 그 아래에 한 줄씩)
function asText(value, depth = 0) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    if (value.every((item) => item == null || typeof item !== "object")) return value.map((item) => asText(item)).join("\n");
    return value.map((item) => asText(item, depth + 1)).join("\n");
  }
  if (depth > 1) return JSON.stringify(value);
  return Object.entries(value)
    .map(([key, item]) => (Array.isArray(item) && item.length > 1 ? `${key}:\n${asText(item, depth + 1)}` : `${key}: ${asText(item, depth + 1)}`))
    .join(depth === 0 ? "\n" : ", ");
}

/* F02 검수 확인서 모양: 구성요소 | 체크 항목 | 검수 결과(적합/부적합/판단불가) | 비고 */
// 확인서 행에 속한 지적사항: item_id가 그 번호로 끝나거나(F02-필요지식-⑤), 체크 이름이 그 번호로 시작(위치 ②③④처럼 한 item_id를 나눠 쓰는 엔진)
function findingsOfRow(findings, row) {
  return (findings || []).filter((f) => f.item_id.endsWith(row.번호) || String(f.check).startsWith(row.번호));
}

function SheetTable({ sheet, findings }) {
  const [expanded, setExpanded] = useState(() => new Set());
  if (!sheet.length) return null;
  function toggle(no) {
    setExpanded((prev) => { const next = new Set(prev); next.has(no) ? next.delete(no) : next.add(no); return next; });
  }
  return (
    <div className="krds-table-wrap">
      <table className="tbl col data sheet">
        <caption>F02 검수 확인서 형식의 항목별 검수 결과</caption>
        <colgroup>
          <col style={{ width: "12%" }} />
          <col />
          <col style={{ width: "7%" }} />
          <col style={{ width: "7%" }} />
          <col style={{ width: "8%" }} />
          <col style={{ width: "28%" }} />
        </colgroup>
        <thead>
          <tr>
            <th scope="col" rowSpan={2}>학습모듈<br />구성요소</th>
            <th scope="col" rowSpan={2}>체크 항목</th>
            <th scope="colgroup" colSpan={3}>검수 결과</th>
            <th scope="col" rowSpan={2}>비고</th>
          </tr>
          <tr>
            <th scope="col">적합</th>
            <th scope="col">부적합</th>
            <th scope="col">판단불가</th>
          </tr>
        </thead>
        <tbody>
          {sheet.map((row, i) => {
            const own = findingsOfRow(findings, row);
            const open = expanded.has(row.번호);
            return (
              <React.Fragment key={row.번호}>
                <tr>
                  {i === 0 && <th scope="rowgroup" className="component" rowSpan={sheet.length + expanded.size}>{row.구성요소}</th>}
                  <td style={{ whiteSpace: "pre-wrap" }}>{row.번호} {withBoxNumbers(row["체크 항목"])}</td>
                  <td className={`mark ${MARK[row.검수결과] || ""}`}>{row.검수결과 === "적합" ? "✓" : ""}</td>
                  <td className={`mark ${MARK[row.검수결과] || ""}`}>{row.검수결과 === "부적합" ? "✓" : ""}</td>
                  <td className={`mark ${MARK[row.검수결과] || ""}`}>{row.검수결과 === "판단불가" ? "△" : ""}</td>
                  <td style={{ whiteSpace: "pre-line" }}>
                    {withBoxNumbers(row.비고)}
                    {own.length > 0 && (
                      <div className="sheet-more">
                        {/* 확인서 비고는 요약이므로, 어디가 어떻게 틀렸는지는 이 행의 지적사항을 펼쳐서 본다 */}
                        <button type="button" className="krds-btn xsmall text" aria-expanded={open} aria-controls={`sheet-detail-${row.번호}`}
                                onClick={() => toggle(row.번호)}>
                          {open ? "지적사항 접기" : `지적사항 ${own.length}건 보기`}
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
                {open && (
                  <tr className="sheet-detail" id={`sheet-detail-${row.번호}`}>
                    <td colSpan={5}><FindingsTable findings={own} compact /></td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FindingsTable({ findings, compact = false }) {
  if (!findings.length) return <p className="empty">지적사항이 없습니다.</p>;
  return (
    <div className="krds-table-wrap">
      <table className="tbl col data findings">
        <caption>검수에서 부적합 또는 판단불가로 나온 체크 목록</caption>
        {/* 열 너비를 고정해 긴 사유·수정 제안이 다른 열을 한 글자씩 세로로 쪼개지 않게 한다 */}
        <colgroup>
          {!compact && <col style={{ width: "11%" }} />}
          <col style={{ width: "17%" }} />
          <col style={{ width: "8%" }} />
          <col style={{ width: "16%" }} />
          <col />
          <col style={{ width: "20%" }} />
        </colgroup>
        <thead>
          <tr>
            {!compact && <th scope="col">항목</th>}
            <th scope="col">체크</th>
            <th scope="col">검수결과</th>
            <th scope="col">위치</th>
            <th scope="col">사유</th>
            <th scope="col">수정 제안</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f, i) => (
            <tr key={i}>
              {!compact && <td>{f.item_id}</td>}
              <td>{f.check}</td>
              <td><Badge value={f.verdict} /></td>
              <td className="path">{f.region_path}</td>
              <td className="long"><div className="clamp">{withBoxNumbers(f.reason)}</div></td>
              <td className="long"><div className="clamp">{asText(f.suggestion)}</div></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChecklistTable({ rows }) {
  return (
    <div className="krds-table-wrap">
      <table className="tbl col data">
        <caption>검수 규칙이 낸 모든 체크리스트 행</caption>
        <thead>
          <tr>
            <th scope="col">항목</th>
            <th scope="col">위치</th>
            <th scope="col">검수결과</th>
            <th scope="col">체크</th>
            <th scope="col">원고</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{r.item_id}</td>
              <td className="mono">{r.region_path}</td>
              <td><Badge value={r.판정} /></td>
              <td className="mono">{Object.entries(r.체크).map(([k, v]) => `${v} ${k}`).join("\n")}</td>
              <td className="mono">{withBoxNumbers(asText(r.원고))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// KRDS 셀렉트 + 드롭다운 메뉴. 브라우저 기본 <select>는 펼친 목록의 모양을 바꿀 수 없어서, 닫힌 모양은 KRDS 셀렉트(krds-form-select),
// 펼친 목록은 KRDS 드롭다운(krds-drop-wrap › drop-menu › drop-list › item-link)으로 그린다.
// 동작은 KRDS 셀렉트 가이드대로: 클릭·Enter·Space로 열고 닫기, Esc로 닫고 초점은 컨테이너로, 닫힌 상태에서 ↑↓로 바로 이전·다음 값,
// 열린 상태에서 ↑↓·Home·End로 이동 후 Enter로 선택, Tab·바깥 클릭이면 닫힘. 값이 바뀌어도 폼은 제출하지 않는다.
function KrdsSelect({ id, value, options, onChange, title, describedBy }) {
  const [open, setOpen] = useState(false);
  const [focusIndex, setFocusIndex] = useState(0);
  const wrap = useRef(null);
  const button = useRef(null);
  const selectedIndex = Math.max(0, options.findIndex((o) => o.value === value));
  const selected = options[selectedIndex];

  useEffect(() => {
    if (!open) return undefined;
    setFocusIndex(selectedIndex);
    function onDocumentClick(event) { if (!wrap.current?.contains(event.target)) setOpen(false); }
    document.addEventListener("mousedown", onDocumentClick);
    return () => document.removeEventListener("mousedown", onDocumentClick);
  }, [open, selectedIndex]);

  useEffect(() => {
    if (open) wrap.current?.querySelector(`#${id}-opt-${focusIndex}`)?.focus();
  }, [open, focusIndex, id]);

  function choose(index) {
    onChange(options[index].value);
    setOpen(false);
    button.current?.focus();
  }

  function onButtonKey(event) {
    const last = options.length - 1;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (open) setFocusIndex((i) => Math.min(last, Math.max(0, i + (event.key === "ArrowDown" ? 1 : -1))));
      else onChange(options[Math.min(last, Math.max(0, selectedIndex + (event.key === "ArrowDown" ? 1 : -1)))].value);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setOpen((o) => !o);
    } else if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
    }
  }

  function onOptionKey(event, index) {
    const last = options.length - 1;
    const moves = { ArrowDown: Math.min(last, index + 1), ArrowUp: Math.max(0, index - 1), Home: 0, End: last };
    if (event.key in moves) {
      event.preventDefault();
      setFocusIndex(moves[event.key]);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      choose(index);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      button.current?.focus();
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  }

  return (
    <div ref={wrap} className={`krds-drop-wrap drop-left check-select${open ? " is-open" : ""}`}>
      <button ref={button} type="button" id={id} className={`krds-form-select${value ? " completed" : ""}${open ? " is-active" : ""}`}
              title={title} aria-haspopup="listbox" aria-expanded={open} aria-controls={`${id}-list`} aria-describedby={describedBy}
              onClick={() => setOpen((o) => !o)} onKeyDown={onButtonKey}>
        {selected?.label}
      </button>
      <div className="drop-menu" id={`${id}-list`} hidden={!open}>
        <div className="drop-in">
          <ul className="drop-list" role="listbox" aria-labelledby={id}>
            {options.map((option, index) => (
              <li key={option.value} role="none">
                <button type="button" role="option" id={`${id}-opt-${index}`} tabIndex={index === focusIndex ? 0 : -1}
                        className={`item-link${option.value === value ? " active" : ""}`} aria-selected={option.value === value}
                        onClick={() => choose(index)} onKeyDown={(event) => onOptionKey(event, index)}>
                  {option.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

// KRDS 모달(krds-modal) 마크업을 그대로 쓰되, 열기/닫기는 ui-script.js 대신 React 상태로 제어한다.
// 열리면 첫 버튼에 초점을 두고, ESC로 닫는다(KRDS 모달 스크립트와 같은 동작).
function ConfirmDialog({ title, children, confirmLabel = "확인", busy = false, onConfirm, onCancel }) {
  const firstButton = useRef(null);
  useEffect(() => {
    firstButton.current?.focus();
    function onKey(event) { if (event.key === "Escape" && !busy) onCancel(); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  return (
    <section className="krds-modal shown in" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="modal-dialog modal-sm">
        <div className="modal-content">
          <div className="modal-header">
            <h2 id="confirm-title" className="modal-title">{title}</h2>
          </div>
          <div className="modal-conts">
            <div className="conts-area">{children}</div>
          </div>
          <div className="modal-btn btn-wrap">
            <button ref={firstButton} type="button" className="krds-btn medium tertiary" onClick={onCancel} disabled={busy}>취소</button>
            <button type="button" className="krds-btn medium primary" onClick={onConfirm} disabled={busy}>{busy ? "삭제 중…" : confirmLabel}</button>
          </div>
          <button type="button" className="krds-btn medium icon btn-close" onClick={onCancel} disabled={busy}>
            <span className="sr-only">닫기</span>
            <i className="svg-icon ico-popup-close" aria-hidden="true"></i>
          </button>
        </div>
      </div>
      <div className="modal-back in" onClick={busy ? undefined : onCancel}></div>
    </section>
  );
}

// ───────────────────────── 전체 실행(구성요소 10개를 차례로) ─────────────────────────
// 선택 목록의 마지막 항목. 서버의 check 값이 아니라 화면이 처리한다: 파일을 /api/uploads에 한 번 올려 토큰을 받고,
// 엔진 순서대로 /api/review를 upload=토큰으로 부른다. 결과는 구성요소별 아코디언(KRDS krds-accordion)에 하나씩 채워진다.
const ALL_CHECK = "all";
const ALL_OPTION = {
  value: ALL_CHECK,
  label: "전체 — 구성요소 10개를 차례로 검수",
  files: "원고 + 개발계획서 (개발계획서가 없으면 '위치'만 건너뛰고 나머지를 실행)",
  all: true,
};

// 확인서 행의 검수결과 집계 → { 적합, 부적합, 판단불가, 미검사 }
function countVerdicts(sheet) {
  const counts = { 적합: 0, 부적합: 0, 판단불가: 0, 미검사: 0 };
  (sheet || []).forEach((row) => { if (row.검수결과 in counts) counts[row.검수결과] += 1; });
  return counts;
}

// 묶음 판정: 부적합 하나라도 있으면 부적합 → 판단불가 → 적합 (서버 group_verdict와 같은 규칙)
function overallVerdict(verdicts) {
  for (const candidate of ["부적합", "판단불가", "적합"]) if (verdicts.includes(candidate)) return candidate;
  return null;
}

function Spinner({ label }) {
  // KRDS 스피너: role=status + sr-only 글. 글을 눈에 보이게도 둔다(진행 중인 구성요소 이름)
  return <span className="krds-spinner" role="status"><span className="sr-only">{label}</span><span aria-hidden="true">{label}</span></span>;
}

// 아코디언 머리의 상태 표시: 대기 / 검사 중 / 건너뜀 / 오류 / 판정 + 항목 수
function ItemStatus({ item }) {
  if (item.status === "pending") return <span className="krds-badge bg-light-gray">대기</span>;
  if (item.status === "running") return <Spinner label="검사 중…" />;
  if (item.status === "skipped") return <span className="krds-badge bg-light-gray">미실행 — 개발계획서 없음</span>;
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

function AllResults({ run, checks }) {
  const [expanded, setExpanded] = useState(() => new Set());
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
        <span className="meta">{moduleCode}{moduleCode ? " · " : ""}전체 실행{run.created_at ? ` · ${new Date(run.created_at).toLocaleString("ko-KR")}` : ""}</span>
        <span className="meta">적합 {total.적합} · 부적합 {total.부적합} · 판단불가 {total.판단불가} 항목</span>
        {run.roles && !run.roles.plan && <span className="krds-badge bg-light-warning">개발계획서 없음 — 위치 미실행</span>}
        <span className="toolbar">
          <button type="button" className="krds-btn xsmall text" onClick={() => setExpanded(new Set(openable))} disabled={!openable.length}>모두 펼치기</button>
          <button type="button" className="krds-btn xsmall text" onClick={() => setExpanded(new Set())} disabled={!expanded.size}>모두 접기</button>
        </span>
      </div>

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
    </section>
  );
}

// 아코디언 몸통: 그 구성요소의 확인서(행마다 지적사항 펼치기) + 진단 경고 + ZIP. 지적사항·전체 체크리스트는 접힌 상세로.
function ComponentResult({ result }) {
  return (
    <div className="component-result">
      <SheetTable sheet={result.검수확인서 || []} findings={result.지적사항 || []} />
      {result.진단?.warnings?.length > 0 && (
        <ul className="krds-info-list dash">
          {result.진단.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
      <div className="component-foot">
        {result.id ? <a href={`/api/reviews/${result.id}/zip`}>ZIP 다운로드</a> : result.저장?.zip ? <span className="meta">저장: {result.저장.zip}</span> : null}
        <details>
          <summary>지적사항 {result.지적사항?.length || 0}건 · 전체 체크리스트 {result.전체?.length || 0}행</summary>
          <FindingsTable findings={result.지적사항 || []} />
          <ChecklistTable rows={result.전체 || []} />
        </details>
      </div>
    </div>
  );
}

/* 맨 위로(TOP) 버튼 — KRDS 아이콘 버튼 규격(app.css .krds-btn-top). 300px 넘게 내려가면 나타나고, 누르면 맨 위로 올린 뒤 포커스를 본문(#container)으로 옮긴다. */
function TopButton({ showAfter = 300, target = "#container" }) {
  const [active, setActive] = useState(false);
  useEffect(() => {
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => { setActive(window.scrollY > showAfter); ticking = false; });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, [showAfter]);
  function goTop() {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    const el = document.querySelector(target);
    if (el) {
      if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
      el.focus({ preventScroll: true });
    }
  }
  return (
    <button type="button" className={`krds-btn-top${active ? " active" : ""}`} aria-label="맨 위로 이동" onClick={goTop}>
      <i className="svg-icon" aria-hidden="true"></i>
      <span className="sr-only">맨 위로</span>
    </button>
  );
}

/* 헤더 — KRDS 헤더(#krds-header) 최소 구성: 건너뛰기 링크 + 로고(서비스 식별)만. 통합검색·로그인·메인메뉴·유틸리티 메뉴는 이 서비스에 없어 두지 않는다. */
function Header() {
  return (
    <>
      <div id="krds-skip-link">
        <a href="#container">본문 바로가기</a>
      </div>
      {/* 공식 배너(#krds-masthead) 변주 — 정부 누리집 식별 배너 자리에 '공식 서비스가 아닌 테스트 페이지'임을 알린다. 태극기 아이콘은 쓰지 않는다. */}
      <div id="krds-masthead" className="masthead-test">
        <div className="toggle-wrap">
          <div className="toggle-head">
            <div className="inner">
              <span className="nuri-txt">이 누리집은 공식 서비스가 아닌 테스트 페이지입니다. (동국대학교 종합설계1 프로토콜 팀)</span>
            </div>
          </div>
        </div>
      </div>
      <header id="krds-header">
        <div className="header-in">
          <div className="header-container">
            <div className="inner">
              <div className="header-branding">
                <h2 className="logo logo-text">
                  <a href="/">NCS 학습모듈 검수</a>
                </h2>
              </div>
            </div>
          </div>
        </div>
      </header>
    </>
  );
}

/* 푸터 — KRDS 푸터(#krds-footer) 구조: 서비스 로고 → 연락처 → 유틸리티 링크 → 정책 링크 → 저작권. 관련 사이트·SNS·운영기관 식별자는 쓰지 않는다. */
function Footer() {
  return (
    <footer id="krds-footer">
      <div className="inner">
        <div className="f-logo f-logo-text">
          <div className="f-logo-imgs">
            <a href="https://ai.dongguk.edu/main" target="_blank" rel="noopener noreferrer" title="새 창 열기"><img src="/img/logo_dongguk.png" alt="동국대학교" /></a>
            <a href="https://www.krivet.re.kr/kor/index.do" target="_blank" rel="noopener noreferrer" title="새 창 열기"><img src="/img/logo_krivet.png" alt="한국직업능력연구원" /></a>
          </div>
          <strong>동국대학교 종합설계1(김동우) · 프로토콜</strong>
          <span>생성형 AI를 활용한 NCS 학습모듈 활용 및 사업운영 지원체계 구축</span>
        </div>
        <div className="f-cnt">
          <div className="f-info">
            <ul className="info-cs">
              <li><strong className="strong">이메일</strong><span className="span"><a href="mailto:dgu2026protocol@gmail.com">dgu2026protocol@gmail.com</a></span></li>
            </ul>
          </div>
          <div className="f-link">
            <div className="link-go">
              <a href="https://www.krivet.re.kr/kor/index.do" className="krds-btn medium text" target="_blank" rel="noopener noreferrer" title="새 창 열기">한국직업능력연구원 <i className="svg-icon ico-angle right"></i></a>
              <a href="https://ai.dongguk.edu/main" className="krds-btn medium text" target="_blank" rel="noopener noreferrer" title="새 창 열기">동국대학교 첨단융합대학 <i className="svg-icon ico-angle right"></i></a>
            </div>
          </div>
        </div>
        <div className="f-btm">
          <div className="f-btm-text">
            <div className="f-menu">
              {/* TODO: 개인정보처리방침 페이지가 생기면 <a href="..." className="point">로 교체 */}
              <span className="point">개인정보처리방침</span>
            </div>
            <p className="f-copy">© 2026 동국대학교 종합설계1 프로토콜 팀. All rights reserved.</p>
          </div>
        </div>
      </div>
    </footer>
  );
}

export default function App() {
  const [check, setCheck] = useState("position");
  const [checks, setChecks] = useState(CHECKS);
  const [files, setFiles] = useState([]);
  const [moduleCode, setModuleCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [allRun, setAllRun] = useState(null);   // 전체 실행 진행·결과: { group, roles, items: {check: {status, data, error}}, running, created_at }
  const [history, setHistory] = useState(null);
  const resultsRef = useRef(null);   // 결과 영역 — 검사 실행·이력 열기 뒤 여기로 화면을 내린다(이력 표가 길면 결과가 화면 밖에 있다)
  const [pendingDelete, setPendingDelete] = useState(null); // 삭제 확인 창에 올라간 이력 행
  const [deleting, setDeleting] = useState(false);

  async function refreshHistory() {
    // 단독 실행(standalone)과 전체 실행 묶음(/api/groups)을 따로 받아 시각순으로 한 표에 섞는다. 묶음은 한 줄.
    const [runs, groups] = await Promise.all([fetch("/api/reviews?standalone=true"), fetch("/api/groups")]);
    if (!runs.ok) return;
    const rows = (await runs.json()).map((row) => ({ ...row, kind: "run" }));
    if (groups.ok) (await groups.json()).forEach((g) => rows.push({ ...g, id: g.group_id, kind: "group", check_name: ALL_CHECK }));
    rows.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    setHistory(rows);
  }

  // 단독 결과가 오거나 전체 실행이 시작(묶음 id가 바뀜)되면 결과 영역으로 스크롤. 전체 실행 중 구성요소가 채워질 때는 다시 움직이지 않는다.
  const resultKey = result?.id ?? (result ? "result" : null) ?? allRun?.group ?? null;
  useEffect(() => {
    if (resultKey) resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [resultKey]);

  // 서버가 이력 저장(DB 모드)을 지원할 때만 이력을 가져온다. 파일 모드에서는 /api/reviews가 없다.
  useEffect(() => {
    fetch("/api/health")
      .then((response) => (response.ok ? response.json() : null))
      .then((health) => {
        if (health?.engines) setChecks(checksFromEngines(health.engines));
        if (health?.history) return refreshHistory();
      })
      .catch(() => {});
  }, []);

  const options = [...checks, ALL_OPTION];
  const selected = options.find((c) => c.value === check) || options[0];

  async function submit(event) {
    event.preventDefault();
    if (check === ALL_CHECK) return runAll();
    setBusy(true);
    setError(null);
    setResult(null);
    setAllRun(null);
    const form = new FormData();
    form.append("check", check);
    form.append("module_code", moduleCode);
    files.forEach((file) => form.append("files", file, file.name));
    try {
      const response = await fetch("/api/review", { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) setError(data.error + (data.traceback ? "\n\n" + data.traceback : ""));
      else {
        setResult(data);
        if (data.id) refreshHistory().catch(() => {});
      }
    } catch (e) {
      setError(`서버에 연결하지 못했습니다: ${e.message}\n(가상환경의 ncs-web 서버가 실행 중인지 확인)`);
    } finally {
      setBusy(false);
    }
  }

  // 전체 실행: 업로드 1회(토큰) → 엔진 순서대로 /api/review → 끝나면 토큰 반납. 한 구성요소의 오류는 그 칸에만 남기고 다음으로 간다.
  async function runAll() {
    setBusy(true);
    setError(null);
    setResult(null);
    const order = checks.map((c) => c.value);
    let upload;
    try {
      const form = new FormData();
      files.forEach((file) => form.append("files", file, file.name));
      const response = await fetch("/api/uploads", { method: "POST", body: form });
      upload = await response.json();
      if (!response.ok) {
        setError(upload.error || "업로드 실패");
        setBusy(false);
        return;
      }
    } catch (e) {
      setError(`서버에 연결하지 못했습니다: ${e.message}\n(가상환경의 ncs-web 서버가 실행 중인지 확인)`);
      setBusy(false);
      return;
    }
    const hasPlan = Boolean(upload.roles?.plan);
    const items = {};
    order.forEach((value) => {
      const needsPlan = (checks.find((c) => c.value === value)?.required || []).includes("plan");
      items[value] = { status: needsPlan && !hasPlan ? "skipped" : "pending" };
    });
    setAllRun({ group: upload.group, roles: upload.roles, items, running: true, created_at: new Date().toISOString() });
    const update = (value, patch) => setAllRun((prev) => (prev ? { ...prev, items: { ...prev.items, [value]: { ...prev.items[value], ...patch } } } : prev));
    for (const value of order) {
      if (items[value].status === "skipped") continue;
      update(value, { status: "running" });
      const form = new FormData();
      form.append("check", value);
      form.append("module_code", moduleCode);
      form.append("upload", upload.upload);
      form.append("group", upload.group);
      try {
        const response = await fetch("/api/review", { method: "POST", body: form });
        const data = await response.json();
        if (!response.ok) update(value, { status: "error", error: data.error + (data.traceback ? "\n\n" + data.traceback : "") });
        else update(value, { status: "done", data });
      } catch (e) {
        update(value, { status: "error", error: `서버에 연결하지 못했습니다: ${e.message}` });
      }
    }
    fetch(`/api/uploads/${upload.upload}`, { method: "DELETE" }).catch(() => {});
    setAllRun((prev) => (prev ? { ...prev, running: false } : prev));
    setBusy(false);
    if (history) refreshHistory().catch(() => {});
  }

  // 이력의 전체 실행 묶음을 열어 아코디언으로 되살린다. 저장되지 않은 구성요소(위치: 개발계획서 없음)는 건너뜀으로 표시.
  async function openGroup(id) {
    setError(null);
    try {
      const response = await fetch(`/api/groups/${id}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "이력을 열 수 없습니다");
      const items = {};
      checks.forEach((c) => { items[c.value] = { status: "skipped" }; });
      data.runs.forEach((run) => { items[run.check] = { status: "done", data: run }; });
      const hasPlan = data.runs.some((run) => run.진단?.inputs?.plan);
      setResult(null);
      setAllRun({ group: id, roles: { manuscript: true, plan: hasPlan }, items, running: false, created_at: data.created_at, module_code: data.module_code });
    } catch (e) {
      setError(e.message);
    }
  }

  async function openHistory(id) {
    setError(null);
    try {
      const response = await fetch(`/api/reviews/${id}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "이력을 열 수 없습니다");
      setAllRun(null);
      setResult(data);
    } catch (e) {
      setError(e.message);
    }
  }

  async function deleteHistory(row) {
    setError(null);
    setDeleting(true);
    try {
      const response = await fetch(row.kind === "group" ? `/api/groups/${row.id}` : `/api/reviews/${row.id}`, { method: "DELETE" });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || "이력을 삭제할 수 없습니다");
      }
      if (result?.id === row.id) setResult(null); // 지운 이력의 결과가 화면에 열려 있으면 함께 내린다
      if (allRun?.group === row.id) setAllRun(null);
      await refreshHistory();
    } catch (e) {
      setError(e.message);
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  }

  return (
    <>
    <Header />
    <main id="container" className="inner page">
      <h1 className="page-title">F02 검수 로컬 테스트</h1>
      <p className="page-desc">
        원고와 개발계획서(.hwp/.hwpx)를 올리면 검수 패키지를 그대로 실행해 검수 확인서 형식과 결과 JSON을 보여줍니다. 파일 역할은 내용으로 자동 판별합니다.
      </p>

      <form className="fieldset review-form" onSubmit={submit}>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="check">검수 항목</label></div>
          <div className="form-conts">
            {/* KRDS 셀렉트: 레이블(form-tit) + 선택완료 상태(completed) + 도움말(form-hint). 값이 바뀌어도 폼은 제출하지 않는다 */}
            <KrdsSelect id="check" value={check} options={options} onChange={setCheck} title="검수 항목 선택" describedBy="check-hint" />
          </div>
          <p className="form-hint" id="check-hint">
            필요한 파일: {selected.files}
            {selected.items && selected.total ? ` · 확인서 항목 ${selected.total}개 중 ${selected.items.length}개 검사` : ""}
          </p>
        </div>

        <div className="form-group">
          <div className="form-tit"><label htmlFor="files">파일</label></div>
          <div className="form-conts">
            <input id="files" type="file" multiple accept=".hwp,.hwpx" hidden onChange={(e) => setFiles(Array.from(e.target.files || []))} />
            <label htmlFor="files">
              <span className="krds-btn medium tertiary" role="button" tabIndex={0}>파일 선택</span>
            </label>
          </div>
          <p className="form-hint">{files.length ? files.map((f) => f.name).join(", ") : "선택된 파일 없음"}</p>
        </div>

        <div className="form-group">
          <div className="form-tit"><label htmlFor="module-code">모듈 코드 (선택)</label></div>
          <div className="form-conts">
            <input id="module-code" type="text" className="krds-input" placeholder="예: LM1203020201_24v3" value={moduleCode} onChange={(e) => setModuleCode(e.target.value)} />
          </div>
          <p className="form-hint">비우면 원고 파일명에서 추출</p>
        </div>

        <div className="form-group form-actions">
          <button className="krds-btn primary large" type="submit" disabled={busy || files.length === 0}>
            {busy ? "검사 중…" : check === ALL_CHECK ? "전체 검사 실행" : "검사 실행"}
          </button>
          {/* 실행·이력 열기 오류는 버튼 바로 아래에 — 검수 이력 표보다 먼저 보이도록 */}
          {error && (
            <p className="form-hint-invalid" role="alert" style={{ whiteSpace: "pre-wrap" }}>{error}</p>
          )}
        </div>
      </form>

      {history && (
        <section>
          <h2 className="section-title">검수 이력</h2>
          {history.length === 0 ? <p className="empty">저장된 검수 이력이 없습니다.</p> : (
            <div className="krds-table-wrap">
              <table className="tbl col data">
                <caption>최근 검수 실행</caption>
                <thead><tr><th scope="col">실행 시각</th><th scope="col">모듈</th><th scope="col">검수</th><th scope="col">판정</th><th scope="col">열기</th><th scope="col">삭제</th></tr></thead>
                <tbody>{history.map((row) => (
                  <tr key={row.id}>
                    <td>{new Date(row.created_at).toLocaleString("ko-KR")}</td>
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

      <div ref={resultsRef} className="results-anchor" />

      {allRun && <AllResults run={allRun} checks={checks} />}

      {result && (
        <section>
          <div className="result-head">
            <Badge value={result.요약.검수결과} large />
            <span className="meta">{result.module_code} · {checks.find((item) => item.value === result.check)?.label || result.check}</span>
            {result.id ? <a href={`/api/reviews/${result.id}/zip`}>ZIP 다운로드</a> : <span className="meta">저장: {result.저장?.zip}</span>}
          </div>

          <h2 className="section-title">검수 확인서</h2>
          <SheetTable sheet={result.검수확인서 || []} findings={result.지적사항 || []} />

          {result.진단.warnings?.length > 0 && (
            <>
              <h2 className="section-title">진단 경고</h2>
              <ul className="krds-info-list dash">
                {result.진단.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </>
          )}

          <h2 className="section-title">지적사항 ({result.지적사항.length}건)</h2>
          <FindingsTable findings={result.지적사항} />

          <h2 className="section-title">전체 체크리스트 ({result.전체.length}행)</h2>
          <ChecklistTable rows={result.전체} />

          <details className="raw">
            <summary>원본 JSON (요약·진단·검수확인서·지적사항·전체)</summary>
            <pre>{JSON.stringify(result, null, 1)}</pre>
          </details>
        </section>
      )}

      <TopButton />

      {pendingDelete && (
        <ConfirmDialog title="검수 이력 삭제" confirmLabel="삭제" busy={deleting}
                       onConfirm={() => deleteHistory(pendingDelete)} onCancel={() => setPendingDelete(null)}>
          <p>정말 삭제하시겠습니까?</p>
          <p className="meta">
            {new Date(pendingDelete.created_at).toLocaleString("ko-KR")} · {pendingDelete.module_code} ·{" "}
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

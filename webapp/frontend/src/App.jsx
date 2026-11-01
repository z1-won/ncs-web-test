import { useEffect, useRef, useState } from "react";

// 순서 = F02 검수 확인서의 구성요소 순서(위치 → 차례 → 개요 → 필요 지식 → 수행 내용 → 교수·학습 방법 → 평가 → …)
const CHECKS = [
  { value: "position", label: "NCS-학습모듈의 위치 ①~⑤", files: "원고 + 개발계획서 (2개 필수)" },
  { value: "toc", label: "차례 ①·③·④·⑤·⑥", files: "원고 (+ 개발계획서 선택)" },
  { value: "overview", label: "학습모듈의 개요 ①·②·⑤·⑥·⑧", files: "원고 (+ 개발계획서 선택)" },
  { value: "knowledge", label: "필요 지식 ①~⑧", files: "원고 (+ 개발계획서: ⑤에만 필요)" },
  { value: "perform", label: "수행 내용 ①·④", files: "원고 (hwpx 권장)" },
  { value: "teaching", label: "교수·학습 방법 ①~④", files: "원고 (hwpx 권장)" },
  { value: "evaluation", label: "평가 ① 학습 내용명 일치", files: "원고 + 개발계획서 (없으면 판단불가)" },
];

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

function asText(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 1);
}

/* F02 검수 확인서 모양: 구성요소 | 체크 항목 | 검수 결과(적합/부적합/판단불가) | 비고 */
function SheetTable({ sheet }) {
  if (!sheet.length) return null;
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
          {sheet.map((row, i) => (
            <tr key={row.번호}>
              {i === 0 && <th scope="rowgroup" className="component" rowSpan={sheet.length}>{row.구성요소}</th>}
              <td style={{ whiteSpace: "pre-wrap" }}>{row.번호} {withBoxNumbers(row["체크 항목"])}</td>
              <td className={`mark ${MARK[row.검수결과] || ""}`}>{row.검수결과 === "적합" ? "✓" : ""}</td>
              <td className={`mark ${MARK[row.검수결과] || ""}`}>{row.검수결과 === "부적합" ? "✓" : ""}</td>
              <td className={`mark ${MARK[row.검수결과] || ""}`}>{row.검수결과 === "판단불가" ? "△" : ""}</td>
              <td style={{ whiteSpace: "pre-line" }}>{withBoxNumbers(row.비고)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FindingsTable({ findings }) {
  if (!findings.length) return <p className="empty">지적사항이 없습니다.</p>;
  return (
    <div className="krds-table-wrap">
      <table className="tbl col data">
        <caption>검수에서 부적합 또는 판단불가로 나온 체크 목록</caption>
        <thead>
          <tr>
            <th scope="col">항목</th>
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
              <td>{f.item_id}</td>
              <td>{f.check}</td>
              <td><Badge value={f.verdict} /></td>
              <td className="mono">{f.region_path}</td>
              <td>{withBoxNumbers(f.reason)}</td>
              <td className="mono">{asText(f.suggestion)}</td>
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

export default function App() {
  const [check, setCheck] = useState("position");
  const [files, setFiles] = useState([]);
  const [moduleCode, setModuleCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null); // 삭제 확인 창에 올라간 이력 행
  const [deleting, setDeleting] = useState(false);

  async function refreshHistory() {
    const response = await fetch("/api/reviews");
    if (response.ok) setHistory(await response.json());
  }

  // 서버가 이력 저장(DB 모드)을 지원할 때만 이력을 가져온다. 파일 모드에서는 /api/reviews가 없다.
  useEffect(() => {
    fetch("/api/health")
      .then((response) => (response.ok ? response.json() : null))
      .then((health) => { if (health?.history) return refreshHistory(); })
      .catch(() => {});
  }, []);

  const selected = CHECKS.find((c) => c.value === check);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
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

  async function openHistory(id) {
    setError(null);
    try {
      const response = await fetch(`/api/reviews/${id}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "이력을 열 수 없습니다");
      setResult(data);
    } catch (e) {
      setError(e.message);
    }
  }

  async function deleteHistory(row) {
    setError(null);
    setDeleting(true);
    try {
      const response = await fetch(`/api/reviews/${row.id}`, { method: "DELETE" });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || "이력을 삭제할 수 없습니다");
      }
      if (result?.id === row.id) setResult(null); // 지운 이력의 결과가 화면에 열려 있으면 함께 내린다
      await refreshHistory();
    } catch (e) {
      setError(e.message);
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  }

  return (
    <main className="inner page">
      <h1 className="page-title">F02 검수 로컬 테스트</h1>
      <p className="page-desc">
        원고와 개발계획서(.hwp/.hwpx)를 올리면 검수 패키지를 그대로 실행해 검수 확인서 형식과 결과 JSON을 보여줍니다. 파일 역할은 내용으로 자동 판별합니다.
      </p>

      <form className="fieldset review-form" onSubmit={submit}>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="check">검수 항목</label></div>
          <div className="form-conts">
            <select id="check" className="krds-form-select" title="검수 항목 선택" value={check} onChange={(e) => setCheck(e.target.value)}>
              {CHECKS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </div>
          <p className="form-hint">{selected.files}</p>
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
            {busy ? "검사 중…" : "검사 실행"}
          </button>
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
                    <td>{CHECKS.find((item) => item.value === row.check_name)?.label || row.check_name}</td>
                    <td><Badge value={row.verdict} /></td>
                    <td><button className="krds-btn small tertiary" type="button" onClick={() => openHistory(row.id)}>결과 보기</button></td>
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

      {error && (
        <div className="form-group selected-files" role="alert">
          <p className="form-hint-invalid" style={{ whiteSpace: "pre-wrap" }}>{error}</p>
        </div>
      )}

      {result && (
        <section>
          <div className="result-head">
            <Badge value={result.요약.검수결과} large />
            <span className="meta">{result.module_code} · {CHECKS.find((item) => item.value === result.check)?.label || result.check}</span>
            {result.id ? <a href={`/api/reviews/${result.id}/zip`}>ZIP 다운로드</a> : <span className="meta">저장: {result.저장?.zip}</span>}
          </div>

          <h2 className="section-title">검수 확인서</h2>
          <SheetTable sheet={result.검수확인서 || []} />

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

      {pendingDelete && (
        <ConfirmDialog title="검수 이력 삭제" confirmLabel="삭제" busy={deleting}
                       onConfirm={() => deleteHistory(pendingDelete)} onCancel={() => setPendingDelete(null)}>
          <p>정말 삭제하시겠습니까?</p>
          <p className="meta">
            {new Date(pendingDelete.created_at).toLocaleString("ko-KR")} · {pendingDelete.module_code} ·{" "}
            {CHECKS.find((item) => item.value === pendingDelete.check_name)?.label || pendingDelete.check_name}
          </p>
          <p className="meta">삭제한 이력은 되돌릴 수 없습니다.</p>
        </ConfirmDialog>
      )}
    </main>
  );
}

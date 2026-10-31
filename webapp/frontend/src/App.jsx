import { useState } from "react";

const CHECKS = [
  { value: "position", label: "NCS-학습모듈의 위치 ①~⑤", files: "원고 + 개발계획서 (2개 필수)" },
  { value: "toc", label: "차례 ①·③·④·⑤·⑥", files: "원고 (+ 개발계획서 선택)" },
  { value: "overview", label: "학습모듈의 개요 ①·②·⑤·⑥·⑧", files: "원고 (+ 개발계획서 선택)" },
  { value: "knowledge", label: "필요 지식 ①~⑧", files: "원고 (+ 개발계획서: ⑤에만 필요)" },
];

// 검수결과 → KRDS 배지 변형
const BADGE = { 적합: "bg-light-success", 부적합: "bg-light-danger", 판단불가: "bg-light-warning", 미검사: "bg-light-gray" };
const MARK = { 적합: "pass", 부적합: "fail", 판단불가: "undecided" };

function Badge({ value, large }) {
  return <span className={`krds-badge ${large ? "large " : ""}${BADGE[value] || "bg-light-gray"}`}>{value}</span>;
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
              <td style={{ whiteSpace: "pre-wrap" }}>{row.번호} {row["체크 항목"]}</td>
              <td className={`mark ${MARK[row.검수결과] || ""}`}>{row.검수결과 === "적합" ? "✓" : ""}</td>
              <td className={`mark ${MARK[row.검수결과] || ""}`}>{row.검수결과 === "부적합" ? "✓" : ""}</td>
              <td className={`mark ${MARK[row.검수결과] || ""}`}>{row.검수결과 === "판단불가" ? "△" : ""}</td>
              <td>{row.비고}</td>
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
              <td>{f.reason}</td>
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
              <td className="mono">{asText(r.원고)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function App() {
  const [check, setCheck] = useState("position");
  const [files, setFiles] = useState([]);
  const [moduleCode, setModuleCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

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
      else setResult(data);
    } catch (e) {
      setError(`서버에 연결하지 못했습니다: ${e.message}\n(python3 webapp/server.py 가 실행 중인지 확인)`);
    } finally {
      setBusy(false);
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

      {error && (
        <div className="form-group selected-files" role="alert">
          <p className="form-hint-invalid" style={{ whiteSpace: "pre-wrap" }}>{error}</p>
        </div>
      )}

      {result && (
        <section>
          <div className="result-head">
            <Badge value={result.요약.검수결과} large />
            <span className="meta">{result.module_code} · {selected.label}</span>
            <span className="meta">저장: {result.저장.zip}</span>
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
    </main>
  );
}

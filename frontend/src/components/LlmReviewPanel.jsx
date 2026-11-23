import React, { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api.js";
import { plainReason } from "../lib/plain.js";
import { Spinner } from "./Badge.jsx";
import { PageAlert } from "./PageAlert.jsx";
import { Badge } from "./Badge.jsx";
import { llmRows } from "../lib/llm.js";

// LLM 검토 — 구성요소별 검수 결과 바로 아래의 버튼. 누를 때만 실행(토큰 사용).
// 결과는 여기 표(항목마다 LLM 검토 전 · LLM 판정 · 판정 사유 · 수정 내용)로 보이고, 확인서 판정에도 합쳐진다(lib/llm.js).
// 본문 전체를 보내 비용이 큰 항목은 기본으로 끔(고르면 실행)
const DEFAULT_OFF = new Set(["misc3_names", "src_unquoted"]);

export function LlmReviewPanel({ uploadToken, moduleCode, result, onResult, components }) {
  const [status, setStatus] = useState(null);       // { available, problem, model, tasks }
  const [picked, setPicked] = useState([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.llmReview.status().then(({ ok, data, error: message }) => {
      if (!ok) return setError(message);
      setStatus(data);
      setPicked(data.tasks.map((t) => t.value).filter((v) => !DEFAULT_OFF.has(v)));
    });
  }, []);

  useEffect(() => {   // 같은 업로드로 이미 돌린 결과가 있으면 불러온다(새로 과금하지 않음)
    onResult(null);
    if (!uploadToken) return;
    api.llmReview.previous(uploadToken).then(({ ok, data }) => { if (ok) onResult(data); });
  }, [uploadToken]); // eslint-disable-line react-hooks/exhaustive-deps

  async function run() {
    setRunning(true);
    setError(null);
    const { ok, data, error: message } = await api.llmReview.run(uploadToken, { tasks: picked, moduleCode });
    if (ok) onResult(data);
    else setError(message);
    setRunning(false);
  }

  const labels = useMemo(() => Object.fromEntries((status?.tasks || []).map((t) => [t.value, t.label])), [status]);
  const rows = useMemo(() => llmRows(result, components, labels), [result, components, labels]);

  const disabledWhy = !uploadToken ? "원고를 올리고 검수를 먼저 실행하세요"
    : status && !status.available ? plainReason(status.problem)
    : !picked.length ? "검토할 항목을 하나 이상 고르세요" : null;

  return (
    <section id="llm-review" className="llm-review nav-anchor">
      <div className="section-head">
        <h2 className="section-title">LLM 검토 <span className="meta">생성형 AI가 문장을 읽고 판정합니다. 누를 때만 실행하며 비용이 듭니다.</span></h2>
      </div>

      {status && (
        <fieldset className="llm-tasks" disabled={running}>
          <legend className="sr-only">검토할 항목</legend>
          <div className="krds-check-area">
            {status.tasks.map((t) => (
              <div className="krds-form-check" key={t.value}>
                <input type="checkbox" id={`llm-${t.value}`} checked={picked.includes(t.value)}
                       onChange={(e) => setPicked((prev) => e.target.checked ? [...prev, t.value] : prev.filter((v) => v !== t.value))} />
                <label htmlFor={`llm-${t.value}`}>{t.label}</label>
              </div>
            ))}
          </div>
        </fieldset>
      )}

      <div className="llm-actions">
        <button type="button" className="krds-btn primary medium" onClick={run} disabled={running || Boolean(disabledWhy)}>
          {running ? "LLM 검토하는 중" : result ? "LLM 검토 다시 실행" : "LLM 검토"}
        </button>
        {result && uploadToken && (
          <>
            <a className="krds-btn small tertiary" href={api.llmReview.jsonUrl(uploadToken)}>원본 데이터 내려받기(JSON)</a>
            <a className="krds-btn small tertiary" href={api.llmReview.memoUrl(uploadToken)}>메모 단 원고(hwpx)</a>
          </>
        )}
        {result && (
          <span className="meta">
            지적 {result.findings.length}건, 호출 {result.usage.calls}번
            {result.usage.new_calls ? `, 비용 약 $${result.usage.cost_usd}` : ", 새 비용 없음(앞 결과 다시 씀)"}
          </span>
        )}
      </div>
      {disabledWhy && !running && <p className="form-hint">{disabledWhy}</p>}
      {running && <Spinner label="LLM 검토하는 중" />}
      {error && <PageAlert kind="danger">{error}</PageAlert>}
      {result?.errors?.length > 0 && (
        <PageAlert kind="danger">검토하지 못한 항목: {result.errors.slice(0, 3).map((e) => `${e.항목}${e.위치 ? ` ${e.위치}` : ""} — ${e.오류}`).join(" / ")}</PageAlert>
      )}

      {rows.length > 0 && (
        <div className="krds-table-wrap">
          <table className="tbl col data llm llm-compare">
            <caption className="sr-only">LLM 검토 결과: 항목별 검토 전 판정, LLM 판정, 판정 사유, 수정 내용</caption>
            <colgroup><col style={{ width: "13%" }} /><col style={{ width: "22%" }} /><col style={{ width: "8%" }} /><col style={{ width: "33%" }} /><col /></colgroup>
            <thead>
              <tr><th scope="col">항목</th><th scope="col">LLM 검토 전</th><th scope="col">LLM 판정</th><th scope="col">판정 사유</th><th scope="col">수정 내용</th></tr>
            </thead>
            {rows.map((r) => {
              const span = Math.max(r.findings.length, 1);
              const before = (
                <>
                  <th scope="rowgroup" rowSpan={span} className="item">{r.label}</th>
                  <td rowSpan={span} className="before">
                    {r.before ? <><Badge value={r.before.verdict} /><div className="note" title={r.before.note}>{r.before.note.length > 160 ? `${r.before.note.slice(0, 160)}…` : r.before.note}</div></> : <span className="sub">확인서 항목 없음</span>}
                  </td>
                </>
              );
              if (!r.findings.length) {
                return (
                  <tbody key={r.task}>
                    <tr>{before}
                      <td>{r.chunks === 0 ? <span className="sub">검토 안 함</span> : <Badge value="적합" />}</td>
                      <td colSpan={2} className="sub">{r.chunks === 0 ? "검토할 문단을 원고에서 찾지 못함" : "지적 없음"}</td>
                    </tr>
                  </tbody>
                );
              }
              return (
                <tbody key={r.task}>
                  {r.findings.map((f, i) => (
                    <tr key={`${f.n}-${i}`}>
                      {i === 0 && before}
                      <td><Badge value="부적합" /></td>
                      <td>
                        <div className="sub">{f.위치}</div>
                        <div><Highlight text={f["수정해야 하는 부분"]} quote={f.인용} /></div>
                        <div className="why">{f.근거_종류 && <span className="kind">{f.근거_종류}</span>}{f.근거}</div>
                      </td>
                      <td className="fix">{f["수정 방안"]}</td>
                    </tr>
                  ))}
                </tbody>
              );
            })}
          </table>
        </div>
      )}
    </section>
  );
}

// 원문에서 모델이 인용한 부분을 굵게 — 어디를 고치라는지 바로 보이게
function Highlight({ text, quote }) {
  if (!quote || !text || !text.includes(quote)) return <>{text}</>;
  const at = text.indexOf(quote);
  return <>{text.slice(0, at)}<mark>{quote}</mark>{text.slice(at + quote.length)}</>;
}

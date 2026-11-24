// 검토의견서·심의의견서 반영 여부 검토(REQ-02-003) — 1·2차 검토의견서, 심의의견서와 최종 원고를 올리면 의견마다 반영 후보·미반영 후보·확인 필요를 근거 문단과 함께 보여 준다.
// 판정은 서버(ncs_opinion)가 Claude(ncs_llmreview.claude)로 내고 모두 후보다. Claude 설정(ANTHROPIC_API_KEY·반출 승인)이 없으면
// 서버가 모든 의견을 '확인 필요'와 이유로 돌려준다(체크박스 없음). 'LLM' 뱃지에 모델·호출 수·토큰·비용이 함께 온다.
// 화면에서 사람이 의견마다 반영/미반영을 정하면 자동 후보와의 오차율(기준 6% 이내)을 바로 센다.
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../lib/api.js";
import { plainReason } from "../lib/plain.js";
import { Spinner } from "../components/Badge.jsx";
import { FileSlot } from "../components/FileSlot.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { RawJson } from "../components/RawJson.jsx";
import { ResultHead } from "../components/ResultHead.jsx";
import { CaseLinkNote, useCaseManuscript } from "../components/CaseLink.jsx";
import { formatDate } from "../lib/format.jsx";
import { usePageTitle } from "../lib/hooks.js";

// 판정 후보 → KRDS 배지 색
const VERDICT_BADGE = { "반영 후보": "bg-light-success", "미반영 후보": "bg-light-danger", "확인 필요": "bg-light-warning", "조치 불필요": "bg-light-gray" };
const FILTERS = ["전체", "반영 후보", "미반영 후보", "확인 필요", "조치 불필요"];

export default function OpinionPage() {
  usePageTitle("의견 반영 검토");
  const [first, setFirst] = useState(null);
  const [second, setSecond] = useState(null);
  const [third, setThird] = useState(null);
  const [file, setFile] = useState(null);
  useCaseManuscript(setFile);
  const [printCopy, setPrintCopy] = useState(null);
  const [previous, setPrevious] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const aborter = useRef(null);
  const ready = file && (first || second || third);
  // 세분류 건에서 돌려 보관한 검토를 다시 연다(?record=). 의견별 결과와 담당자 확정, 의견서 파일이 그대로 보인다
  const [params] = useSearchParams();
  const recordId = params.get("record");
  const [kept, setKept] = useState(null);
  useEffect(() => {
    if (!recordId) return undefined;
    let alive = true;
    setBusy(true);
    api.opinionRecord(recordId).then(({ ok, data, error: message }) => {
      if (!alive) return;
      setBusy(false);
      if (!ok) { setError(message); return; }
      setKept({ ...data, id: recordId });
      setResult(data.result);
    });
    return () => { alive = false; };
  }, [recordId]);

  async function submit(e) {
    e.preventDefault();
    if (!ready) return;
    aborter.current = new AbortController();
    setBusy(true);
    setError(null);
    const opinions = [first && { file: first, round: "1차" }, second && { file: second, round: "2차" }, third && { file: third, round: "심의" }].filter(Boolean);
    const { ok, data, error: message, aborted } = await api.opinion({ file, opinions, printCopy, previous, signal: aborter.current.signal });
    setBusy(false);
    if (aborted) return;
    if (!ok) { setError(message); setResult(null); return; }
    setKept(null);
    setResult(data);
  }

  return (
    <>
    <Header anchors={[]} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page opinion-page">
      <h1 className="page-title">의견 반영 검토</h1>
      {/* 설명은 2~3줄: 무엇을 올리면 무엇이 나오는지 → 판정의 성격 → 파일 처리. 판정별 세부(확인 필요가 되는 경우, 용어 변경 의견)는 결과 표에서 그 자리에 보인다 */}
      <p className="page-desc">
        검토의견서나 심의의견서(PDF, hwp, hwpx)와 의견을 반영한 최종 원고(hwp, hwpx)를 올리면, 생성형 AI가 의견마다
        <strong> 반영 후보, 미반영 후보, 확인 필요</strong>를 근거 문단과 함께 보여 줍니다.
        판정은 참고용이며 최종 판단은 담당자가 합니다. 생성형 AI를 쓸 수 없을 때는 모든 의견을 확인 필요로 표시합니다. 올린 파일은 검토 뒤 바로 지웁니다. 세분류 건에서 연 검토만 의견서와 결과를 그 건에 보관합니다.
      </p>
      <CaseLinkNote />

      {/* 입력 묶음은 구획 셋: 원고 → 의견서 → 실행(권리 증빙 점검과 같은 구조). 필수인 최종 원고를 맨 앞에 둔다 */}
      <form className="fieldset review-form is-sectioned" onSubmit={submit}>
        <div className="form-section" role="group" aria-labelledby="opinion-manuscript-title">
        <h2 className="form-section-title" id="opinion-manuscript-title">원고</h2>
        <div className="form-section-grid">
        <FileSlot id="opinion-final" label="최종 원고" required accept=".hwp,.hwpx" file={file} onChange={setFile} disabled={busy}
                  hint="의견을 반영한 원고(hwp, hwpx)." />
        <FileSlot id="opinion-previous" label="반영 전 원고" accept=".hwp,.hwpx" file={previous} onChange={setPrevious} disabled={busy}
                  hint="hwp, hwpx. 올리면 원래 있던 표현을 반영으로 보지 않습니다." />
        <FileSlot id="opinion-print" label="출력본 PDF" accept=".pdf" file={printCopy} onChange={setPrintCopy} disabled={busy}
                  hint="pdf. 올리면 근거 문장이 실린 쪽을 함께 보여 줍니다." />
        </div>
        </div>
        <div className="form-section" role="group" aria-labelledby="opinion-opinions-title" aria-describedby="opinion-opinions-desc">
        <h2 className="form-section-title" id="opinion-opinions-title">의견서</h2>
        <p className="form-section-desc" id="opinion-opinions-desc">세 칸 중 하나 이상 올려 주세요.</p>
        <div className="form-section-grid">
        <FileSlot id="opinion-first" label="1차 검토의견서" accept=".pdf,.hwp,.hwpx" file={first} onChange={setFirst} disabled={busy}
                  hint="개발계획서 및 초고본 검토의견서(PDF, hwp, hwpx)." />
        <FileSlot id="opinion-second" label="2차 검토의견서" accept=".pdf,.hwp,.hwpx" file={second} onChange={setSecond} disabled={busy}
                  hint="완성본 검토의견서(PDF, hwp, hwpx)." />
        <FileSlot id="opinion-third" label="심의의견서" accept=".hwp,.hwpx" file={third} onChange={setThird} disabled={busy}
                  hint="hwp, hwpx. 소위원회 심의의견서 양식(심의 항목, 세분류, 심의 의견)을 읽습니다." />
        </div>
        </div>
        <div className="form-actions">
          <div className="run-buttons">
            <button className="krds-btn primary large" type="submit" disabled={busy || !ready}>{busy ? "검토하는 중" : "반영 여부 검토"}</button>
            {busy && <button className="krds-btn tertiary large" type="button" onClick={() => aborter.current?.abort()}>취소</button>}
          </div>
          <PageAlert kind="danger">{error}</PageAlert>
        </div>
      </form>

      {busy && <ResultHead status={<Spinner label={recordId && !result ? "보관한 검토를 불러오는 중" : "생성형 AI가 의견서와 원고를 대조하는 중"} />} />}
      {result && !busy && <OpinionResult key={kept?.id || result["진행 현황 기록"]?.id || "new"} result={result} kept={kept}
                                         backTo={params.get("case") && `/cases?case=${encodeURIComponent(params.get("case"))}${params.get("volume") ? `&volume=${encodeURIComponent(params.get("volume"))}` : ""}`} />}
      <TopButton />
    </main>
    <Footer />
    </>
  );
}

// 사람 확정값과 자동 후보의 오차율 — 서버 ncs_opinion.error_rate와 같은 셈(확인 필요는 보류, 조치 불필요는 뺀다)
function errorRate(rows, decisions) {
  let judged = 0, wrong = 0, held = 0;
  rows.forEach((row) => {
    const truth = decisions[row.번호];
    if (!truth || row.판정 === "조치 불필요") return;
    if (row.판정 === "확인 필요") { held += 1; return; }
    judged += 1;
    if ((row.판정 === "반영 후보") !== (truth === "반영")) wrong += 1;
  });
  return { judged, wrong, held, rate: judged ? (wrong / judged) * 100 : null };
}

function OpinionResult({ result, kept, backTo }) {
  const [filter, setFilter] = useState("전체");
  const [decisions, setDecisions] = useState(kept?.decisions || {});
  const [working, setWorking] = useState(null);     // "export" | "save"
  const [note, setNote] = useState(null);           // { kind, text } — 결과표·확정 저장 안내
  const picked = Object.fromEntries(Object.entries(decisions).filter(([, value]) => value));
  async function exportSheet() {
    setWorking("export"); setNote(null);
    const { ok, error } = await api.opinionExport({ manuscript: result.원고, rows: result.의견, decisions: picked, llm: result.LLM });
    setWorking(null);
    if (!ok) setNote({ kind: "danger", text: error });
  }
  async function saveDecisions() {
    setWorking("save"); setNote(null);
    const { ok, data, error } = await api.opinionDecisions({ recordId: result["진행 현황 기록"]?.id, rows: result.의견, decisions: picked });
    setWorking(null);
    setNote(ok ? { kind: data.저장 ? "success" : "warning", text: data.안내 } : { kind: "danger", text: error });
  }
  const summary = result.요약;
  const rows = useMemo(() => result.의견.filter((row) => filter === "전체" || row.판정 === filter), [result, filter]);
  const rate = errorRate(result.의견, decisions);
  const decided = Object.values(decisions).filter(Boolean).length;
  return (
    <section className="opinion-result">
      <ResultHead
        status={<span className="krds-badge large bg-light-gray">의견 {summary["총 의견"]}개</span>}
        meta={`${result.원고} / ${result.의견서.map((s) => `${s.차수 || "차수 모름"} ${s.파일}`).join(", ")}${result.출력본 ? ` / 출력본 ${result.출력본}` : ""}`}
        badges={<span id="opinion-llm-state" className="krds-badge bg-light-gray">생성형 AI: {plainReason(result.LLM)}</span>}
      />
      <dl className="upscale-summary">
        <div><dt>조치 요구 의견</dt><dd><strong>{summary["조치 요구"]}</strong>개</dd><dd className="meta">조치 불필요(적합 확인) {summary["조치 불필요"]}개 제외{summary["심의 의견"] > 0 && `, 심의 의견 ${summary["심의 의견"]}개 포함`}</dd></div>
        <div><dt>반영 후보</dt><dd><strong>{summary["반영 후보"]}</strong>개</dd></div>
        <div><dt>미반영 후보</dt><dd><strong>{summary["미반영 후보"]}</strong>개</dd></div>
        <div><dt>확인 필요</dt><dd><strong>{summary["확인 필요"]}</strong>개</dd><dd className="meta">그중 용어 변경(집필자 확인) {summary["용어 변경(집필자 확인)"]}개</dd></div>
        <div>
          <dt>담당자 확정 대비 오차율 (기준 6% 이내)</dt>
          <dd><strong>{rate.rate == null ? "-" : `${rate.rate.toFixed(1)}%`}</strong></dd>
          <dd className="meta">확정 {decided}개, 후보와 다름 {rate.wrong}, 보류(확인 필요) {rate.held}</dd>
        </div>
      </dl>
      {result.알림.length > 0 && <PageAlert kind="info">{result.알림.map((note) => <p key={note}>{note}</p>)}</PageAlert>}
      {kept && (
        <div className="opinion-kept">
          <p>
            세분류 건에 보관한 검토입니다. {formatDate(kept.created_at)}{kept.kept_by ? `, ${kept.kept_by}` : ""}.
            {kept.decided ? ` 담당자 확정: ${formatDate(kept.decided.at)}${kept.decided.by ? `, ${kept.decided.by}` : ""}.` : " 아직 확정을 저장하지 않았습니다."}
            {backTo && <> <Link to={backTo}>건 화면으로 돌아가기</Link></>}
          </p>
          {kept.files.length > 0 && (
            <ul className="krds-info-list">
              {kept.files.map((item) => (
                <li key={item.id}>{item.round ? `${item.round} ` : ""}<a href={api.opinionRecordFileUrl(kept.id, item.id)}>{item.filename}</a></li>
              ))}
            </ul>
          )}
        </div>
      )}
      {!kept && result.보관 && <PageAlert kind="success">의견서 파일과 의견별 결과를 이 건에 보관했습니다. 확정을 저장하면 확정도 함께 남고, 건의 권 화면에서 다시 열 수 있습니다.</PageAlert>}

      <h2 className="section-title">의견별 반영 여부</h2>
      <p className="meta section-desc">{result["판정 원칙"]} 표의 '담당자 확정'에서 반영/미반영을 고르면 위 오차율이 바뀝니다. 확정은 [확정 저장]으로 진행 현황 기록에 남기고, [결과표 내려받기]로 후보와 확정을 함께 적은 표를 보관합니다.</p>
      <div className="opinion-keep" role="group" aria-label="확정 보관">
        <button type="button" className="krds-btn small secondary" disabled={!!working} onClick={exportSheet}>{working === "export" ? "만드는 중" : "결과표 내려받기(xlsx)"}</button>
        <button type="button" className="krds-btn small tertiary" disabled={!!working || !decided} onClick={saveDecisions}>{working === "save" ? "저장하는 중" : `확정 저장 (${decided}개)`}</button>
      </div>
      <PageAlert kind={note?.kind || "info"}>{note?.text}</PageAlert>
      <div className="opinion-filter" role="group" aria-label="판정으로 거르기">
        {FILTERS.map((name) => (
          <button key={name} type="button" className={`krds-btn small ${filter === name ? "primary" : "tertiary"}`} aria-pressed={filter === name}
                  onClick={() => setFilter(name)}>
            {name}{name !== "전체" && ` ${result.의견.filter((r) => r.판정 === name).length}`}
          </button>
        ))}
      </div>
      <div className="krds-table-wrap">
        <table className="tbl col data opinion-table">
          <caption>의견별 판정 후보와 근거</caption>
          <thead>
            <tr><th scope="col">번호</th><th scope="col">차수와 위치</th><th scope="col">의견</th><th scope="col">유형</th><th scope="col">판정 후보</th><th scope="col">근거 문단과 비고</th><th scope="col">담당자 확정</th></tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.번호}>
                <th scope="row">{row.번호}</th>
                <td>{row.차수} {row.구분}{row.구성 && ` ${row.구성}`}{row.쪽 && <><br /><span className="meta">{row.쪽}쪽</span></>}</td>
                <td className="opinion-text">{row.의견}</td>
                <td>{row.유형}</td>
                <td><span className={`krds-badge ${VERDICT_BADGE[row.판정] || "bg-light-gray"}`}>{row.판정}</span></td>
                <td className="opinion-evidence">
                  {row.근거.slice(0, 3).map((e, i) => (
                    <p key={i}><span className="meta">{e.위치}{e["출력본 쪽"] ? `, ${e["출력본 쪽"]}쪽` : ""}</span> {e.문단}</p>
                  ))}
                  {row["집필자 확인"] && <p className="opinion-ask">집필자 확인: {row["집필자 확인"]}</p>}
                  {row["수정 제안"] && <p className="opinion-suggest">수정 제안: {row["수정 제안"]}</p>}
                  {(row["검수 기준"] || []).map((text) => <p key={text} className="opinion-criteria">{text}</p>)}
                  {row.비고.length > 0 && (
                    <details><summary>비고 {row.비고.length}개{row["찾은 범위"] && `, ${row["찾은 범위"]}`}</summary>
                      <ul className="krds-info-list dash">{[...row.비고, ...row["의견서 읽기 추정"]].map((note, i) => <li key={i}>{note}</li>)}</ul>
                    </details>
                  )}
                  {row.LLM && <p className="meta">생성형 AI: {row.LLM.상태 === "사용" ? `${row.LLM.모델}, ${row.LLM.판정}` : plainReason(row.LLM.상태)}</p>}
                </td>
                <td>
                  {row.판정 !== "조치 불필요" && (
                    <select className="krds-form-select small" aria-label={`의견 ${row.번호} 담당자 확정`} value={decisions[row.번호] || ""}
                            onChange={(e) => setDecisions({ ...decisions, [row.번호]: e.target.value })}>
                      <option value="">-</option>
                      <option value="반영">반영</option>
                      <option value="미반영">미반영</option>
                    </select>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <RawJson data={result} title="원본 데이터 보기(개발자용)" />
    </section>
  );
}

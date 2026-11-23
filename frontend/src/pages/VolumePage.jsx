// 원고 분량 산정(REQ-02-013) — 최종 원고를 올리면 구성별 행·쪽과 계약서에 기입할 분량(매)을 낸다.
// 기존 원고를 함께 올리면 올해 바뀐 분량(1자 이상 바뀐 행)을, 수작업 산정 쪽수를 넣으면 오차율을 함께 보여 준다.
// 출력본 PDF를 함께 올리면 쪽을 PDF에서 재어 한글 계산값과 나란히 보여 주고, 계약서 기준 집필료(분량 × 단가)를 낸다. 계산은 서버(ncs_volume)가 한다.
// 서버가 DB 이력을 쓰면(/api/health의 history) 산정할 때마다 이력에 남고, 아래 '산정 이력'에서 다시 열거나 지운다(원고 파일은 남기지 않는다).
import React, { useEffect, useRef, useState } from "react";

import { api } from "../lib/api.js";
import { formatDate, formatDateLines } from "../lib/format.jsx";
import { Spinner } from "../components/Badge.jsx";
import { ConfirmDialog } from "../components/ConfirmDialog.jsx";
import { FileSlot } from "../components/FileSlot.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { Pagination } from "../components/Pagination.jsx";
import { RawJson } from "../components/RawJson.jsx";
import { ResultHead } from "../components/ResultHead.jsx";
import { CaseLinkNote, useCaseManuscript } from "../components/CaseLink.jsx";
import { usePageTitle } from "../lib/hooks.js";

// 권고 분량 상태 → KRDS 배지 색
const HISTORY_PAGE = 10;   // 이력 표 한 쪽 행 수(원고 검수 이력과 같다)
const RANGE_BADGE = { "권고 범위 안": "bg-light-success", "권고보다 적음": "bg-light-warning", "권고보다 많음": "bg-light-warning", 판단불가: "bg-light-gray" };

export default function VolumePage() {
  usePageTitle("원고 분량 산정");
  const [file, setFile] = useState(null);
  useCaseManuscript(setFile);
  const [previous, setPrevious] = useState(null);
  const [printCopy, setPrintCopy] = useState(null);
  const [manual, setManual] = useState("");
  const [unitPrice, setUnitPrice] = useState("");
  const [contractPages, setContractPages] = useState("");
  const [appendix, setAppendix] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const aborter = useRef(null);
  const [history, setHistory] = useState(null);          // null = 이력 없음(파일 저장 모드) → 이력 영역을 그리지 않는다
  const [historyPage, setHistoryPage] = useState(1);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  async function refreshHistory() {
    const { ok, data } = await api.volumes.list();
    if (ok) setHistory(data);
  }

  useEffect(() => {
    let alive = true;
    api.health().then(({ data }) => { if (alive && data?.history) refreshHistory(); });
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    const pages = Math.max(1, Math.ceil((history?.length || 0) / HISTORY_PAGE));
    if (historyPage > pages) setHistoryPage(pages);
  }, [history, historyPage]);

  async function openHistory(id) {
    setError(null);
    const { ok, data, error: message } = await api.volumes.get(id);
    if (!ok) return setError(message);
    setResult(data);
    document.getElementById("volume-result")?.scrollIntoView({ block: "start" });
  }

  async function deleteHistory(row) {
    setError(null);
    setDeleting(true);
    const { ok, error: message } = await api.volumes.remove(row.id);
    if (!ok) setError(message);
    else {
      if (result?.id === row.id) setResult(null);   // 지운 이력의 결과가 화면에 열려 있으면 함께 내린다
      await refreshHistory();
    }
    setDeleting(false);
    setPendingDelete(null);
  }

  async function submit(e) {
    e.preventDefault();
    if (!file) return;
    aborter.current = new AbortController();
    setBusy(true);
    setError(null);
    const { ok, data, error: message, aborted } = await api.volume({ file, previous, printCopy, manualPages: manual, unitPrice, contractPages, includeAppendix: appendix, signal: aborter.current.signal });
    setBusy(false);
    if (aborted) return;
    if (!ok) { setError(message); setResult(null); return; }
    setResult(data);
    if (data.id) refreshHistory();
  }

  return (
    <>
    <Header anchors={[]} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page volume-page">
      <h1 className="page-title">원고 분량 산정</h1>
      <p className="page-desc">
        최종 원고(hwp, hwpx)를 올리면 집필료 산정 기준(계약서 제13조 4항)대로 구성별 행과 쪽을 세어 계약서에 기입할 분량(매)을 냅니다.
        1행에 1자 이상이면 1행으로 세고, 전체 분량의 끝수가 ½쪽 이상이면 1쪽으로 올립니다. 행 띄움, 표, 출처를 밝힌 인용은 넣고 사진과 삽화 등 시각 자료, 표지, ‘NCS학습모듈의 이해’, 개발진은 뺍니다.
        기존 학습모듈 원고를 함께 올리면 올해 바뀐 분량을 따로 셉니다. 올린 파일은 계산 뒤 바로 지웁니다.
        {history && " 산정 결과와 입력한 값은 산정 이력에 저장합니다. 원고 파일은 저장하지 않고 파일 이름만 기록합니다."}
      </p>
      <CaseLinkNote />

      {/* 입력 묶음은 구획 셋: 파일 올리기 → 산정 조건 → 실행(다른 화면과 같은 구조). 칸 아래 도움말은 한 줄로 두고, 긴 설명은 구획 설명(.form-section-desc)에 모은다 */}
      <form className="fieldset review-form is-sectioned" onSubmit={submit}>
        <div className="form-section" role="group" aria-labelledby="volume-files-title" aria-describedby="volume-files-desc">
        <h2 className="form-section-title" id="volume-files-title">파일 올리기</h2>
        <p className="form-section-desc" id="volume-files-desc">
          최종 원고는 한글에서 저장한 파일이어야 줄과 쪽을 정확히 셉니다. 출력본 PDF를 올리면 전체 쪽 수, 구성별 쪽, 쪽마다 채운 높이를 PDF에서 직접 재어 산정에 씁니다.
        </p>
        <div className="form-section-grid">
        <FileSlot id="volume-final" label="최종 원고" required accept=".hwp,.hwpx" file={file} onChange={setFile} disabled={busy}
                  hint="hwp, hwpx. 3차 검토까지 반영한 최종 완성본입니다." />
        <FileSlot id="volume-previous" label="기존 원고" accept=".hwp,.hwpx" file={previous} onChange={setPrevious} disabled={busy}
                  hint="hwp, hwpx. 한 글자라도 바뀐 행을 변경 분량으로 셉니다." />
        <FileSlot id="volume-print" label="출력본 PDF" accept=".pdf" file={printCopy} onChange={setPrintCopy} disabled={busy}
                  hint="pdf. 최종 원고를 한글에서 PDF로 저장한 파일입니다." />
        </div>
        </div>
        <div className="form-section" role="group" aria-labelledby="volume-options-title" aria-describedby="volume-options-desc">
        <h2 className="form-section-title" id="volume-options-title">산정 조건</h2>
        <p className="form-section-desc" id="volume-options-desc">
          계약서에는 단가가 없어(제2조 계약금액 빈칸), 단가를 비우면 예산집행 및 정산지침의 상한인 50,000원/쪽으로 계산합니다.
          계약 분량을 넣으면 넘는 분량은 인정하지 않고(추가금 없음), 모자라면 제출 분량만큼 계산합니다.
        </p>
        <div className="form-section-grid">
        <div className="form-group">
          <div className="form-tit"><label htmlFor="volume-manual">수작업 산정 쪽수 (선택)</label></div>
          <div className="form-conts">
            <input id="volume-manual" type="number" min="1" step="0.5" className="krds-input" value={manual} disabled={busy}
                   onChange={(e) => setManual(e.target.value)} aria-describedby="volume-manual-hint" placeholder="예: 80" />
          </div>
          <p className="form-hint" id="volume-manual-hint">넣으면 자동 산정과의 오차율을 보여 줍니다(기준 0.5% 이내).</p>
        </div>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="volume-unit-price">원고료 단가 (원/쪽, 선택)</label></div>
          <div className="form-conts">
            <input id="volume-unit-price" type="number" min="1" step="1" className="krds-input" value={unitPrice} disabled={busy}
                   onChange={(e) => setUnitPrice(e.target.value)} aria-describedby="volume-unit-price-hint" placeholder="50000" />
          </div>
          <p className="form-hint" id="volume-unit-price-hint">비우면 상한인 50,000원으로 계산합니다.</p>
        </div>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="volume-contract-pages">계약 분량 (매, 선택)</label></div>
          <div className="form-conts">
            <input id="volume-contract-pages" type="number" min="1" step="1" className="krds-input" value={contractPages} disabled={busy}
                   onChange={(e) => setContractPages(e.target.value)} aria-describedby="volume-contract-pages-hint" placeholder="예: 80" />
          </div>
          <p className="form-hint" id="volume-contract-pages-hint">과업지시서에 적은 원고 분량입니다.</p>
        </div>
        <div className="form-group">
          <div className="form-tit"><span>부록</span></div>
          <div className="form-conts">
            <div className="krds-form-check">
              <input type="checkbox" id="volume-appendix" checked={appendix} disabled={busy} onChange={(e) => setAppendix(e.target.checked)} />
              <label htmlFor="volume-appendix">부록을 산정에 넣기 (계약서 제13조 4항 ①, 정산지침 F16 인쇄 19쪽, 매뉴얼 F11 인쇄 20~21쪽)</label>
            </div>
          </div>
        </div>
        </div>
        </div>
        <div className="form-actions">
          <div className="run-buttons">
            <button className="krds-btn primary large" type="submit" disabled={busy || !file}>{busy ? "세는 중" : "분량 산정"}</button>
            {busy && <button className="krds-btn tertiary large" type="button" onClick={() => aborter.current?.abort()}>취소</button>}
          </div>
          <PageAlert kind="danger">{error}</PageAlert>
        </div>
      </form>

      {busy && <ResultHead status={<Spinner label="원고 분량을 세는 중" />} />}
      {result && !busy && <VolumeResult result={result} />}

      {history && (
        <section id="volume-history" className="history volume-history">
          <div className="section-head">
            <h2 className="section-title">산정 이력</h2>
          </div>
          {history.length === 0 ? <p className="empty">저장된 산정 이력이 없습니다.</p> : (
            <div className="krds-table-wrap">
              <table className="tbl col data history-table">
                <caption>최근 원고 분량 산정</caption>
                <colgroup>
                  <col className="col-when" />
                  <col />
                  <col className="col-num" />
                  <col className="col-num" />
                  <col className="col-num" />
                  <col className="col-action" />
                  <col className="col-action" />
                </colgroup>
                <thead><tr><th scope="col">산정 시각</th><th scope="col">원고</th><th scope="col">기입 분량</th><th scope="col">단가</th><th scope="col">집필료</th><th scope="col">열기</th><th scope="col">삭제</th></tr></thead>
                <tbody>{history.slice((historyPage - 1) * HISTORY_PAGE, historyPage * HISTORY_PAGE).map((row) => (
                  <tr key={row.id} className={row.id === result?.id ? "is-open" : undefined}>
                    <td className="when">{formatDateLines(row.created_at).map((line, i) => <span key={i}>{line}</span>)}</td>
                    <td className="module" title={row.manuscript}>{row.manuscript}</td>
                    <td>{row.pages}매{row.estimated && " (추정)"}</td>
                    <td>{row.unit_price.toLocaleString()}원{!row.unit_given && <span className="meta"> 기본값</span>}</td>
                    <td>{row.fee.toLocaleString()}원</td>
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
          <Pagination page={historyPage} total={Math.ceil(history.length / HISTORY_PAGE)} onChange={setHistoryPage} label="산정 이력 페이지" />
        </section>
      )}
      <TopButton />

      {pendingDelete && (
        <ConfirmDialog title="산정 이력 삭제" confirmLabel="삭제" busy={deleting}
                       onConfirm={() => deleteHistory(pendingDelete)} onCancel={() => setPendingDelete(null)}>
          <p>정말 삭제하시겠습니까?</p>
          <p className="meta">{formatDate(pendingDelete.created_at)}, {pendingDelete.manuscript}, {pendingDelete.pages}매, {pendingDelete.fee.toLocaleString()}원</p>
          <p className="meta">삭제한 이력은 되돌릴 수 없습니다.</p>
        </ConfirmDialog>
      )}
    </main>
    <Footer />
    </>
  );
}

// 알림 묶음: 경고(산정값·금액을 그대로 믿거나 쓰기 전에 확인할 것)는 경고색 상자로 먼저, 나머지는 안내색 상자로.
// warnings는 서버가 알림 가운데 경고로 표시한 문장들(예전에 저장된 이력에는 없을 수 있다). children은 안내 상자 끝에 붙는다(버튼 등).
function Notes({ notes, warnings = [], children }) {
  const warn = notes.filter((note) => warnings.includes(note));
  const info = notes.filter((note) => !warnings.includes(note));
  return (
    <>
      <PageAlert kind="warning">{warn.length > 0 && warn.map((note) => <p key={note}>{note}</p>)}</PageAlert>
      <PageAlert kind="info">{info.length > 0 && <>{info.map((note) => <p key={note}>{note}</p>)}{children}</>}</PageAlert>
    </>
  );
}

function VolumeResult({ result }) {
  const total = result.합계;
  const band = result["권고 분량"];
  const change = result.변경;
  const manual = result["수작업 대조"];
  const adopted = result["채택 분량"];
  const gap = adopted["출력본 측정"] != null ? adopted["출력본 측정"] - total["기입 분량"] : null;
  return (
    <section id="volume-result" className="volume-result nav-anchor">
      <ResultHead
        status={<span className={`krds-badge large ${RANGE_BADGE[band.상태] || "bg-light-gray"}`}>{band.상태}</span>}
        meta={`${result.원고}, ${band.비고}${result.created_at ? `, ${formatDate(result.created_at)} 산정(이력)` : ""}`}
        badges={result.추정 && <span className="krds-badge bg-light-warning">추정값(줄 배치 정보 없음)</span>}
      />
      <PageAlert kind="danger">{result["저장 오류"] && <p>{result["저장 오류"]} 이 화면의 산정 결과는 정상이며, 이력에만 남지 않았습니다.</p>}</PageAlert>
      <dl className="upscale-summary">
        <div><dt>기입 분량(계약서에 적을 분량)</dt><dd><strong>{adopted["기입 분량"]}매</strong> ({adopted.근거})</dd></div>
        {gap != null && <div><dt>한글 줄 배치 계산</dt><dd>{total["기입 분량"]}매 (출력본 측정과 차이 {gap > 0 ? "+" : ""}{gap}매)</dd></div>}
        <div><dt>꽉 찬 쪽과 남은 행</dt><dd>{total.쪽}쪽 {total.행}행</dd></div>
        <div><dt>행 합계</dt><dd>{total["행 합계"].toLocaleString()}행</dd></div>
        <div><dt>높이로 환산한 쪽수</dt><dd>{total["쪽 환산"]}쪽</dd></div>
        {result["물리 쪽 수"] != null && <div><dt>원고 전체 쪽수</dt><dd>{result["물리 쪽 수"]}쪽</dd></div>}
        {change && <div><dt>변경 분량</dt><dd><strong>{change["변경 분량"]["기입 분량"]}매</strong> ({change["변경 행"].toLocaleString()}행을 이어 붙여 {change["변경 분량"]["쪽 환산"]}쪽, {change["변경 비율"]})</dd></div>}
        {manual && <div><dt>수작업 대조</dt><dd>오차율 {manual.오차율} ({manual.결과})</dd></div>}
      </dl>
      <Notes notes={result.알림} warnings={result.경고} />

      <FeeCard fee={result.집필료} />
      {result.출력본 && <PrintedResult printed={result.출력본} />}

      <h2 className="section-title">구성별 분량</h2>
      <p className="meta section-desc">측정 방식: {result["측정 방식"]}</p>
      <div className="krds-table-wrap">
        <table className="tbl col data">
          <caption>구성별 행과 쪽 산정표</caption>
          <thead>
            <tr><th scope="col">구성</th><th scope="col">산정</th><th scope="col">행</th><th scope="col">환산 쪽수</th><th scope="col">원고 쪽</th><th scope="col">시각 자료 제외(쪽)</th>{change && <th scope="col">변경 행</th>}</tr>
          </thead>
          <tbody>
            {result.구성.map((row) => (
              <tr key={row.구성} className={row.반영 ? "" : "muted"}>
                <th scope="row">{row.구성}</th>
                <td>{row.반영 ? "반영" : "제외"}</td>
                <td>{row.행.toLocaleString()}</td>
                <td>{row["쪽 환산"]}</td>
                <td>{row["물리 쪽"] || "-"}</td>
                <td>{row["시각 자료 제외(쪽)"]}</td>
                {change && <td>{change["구성별 변경 행"].find((r) => r.구성 === row.구성)?.["변경 행"] ?? 0}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {change && (
        <p className="meta section-desc">
          기존 원고 {change["기존 원고"]}: {change["기존 원고 분량"]["기입 분량"]}매{change["기존 원고 추정"] ? "(추정)" : ""}. {change.방법}
          <br />변경 분량: {change["변경 분량"].방법}. 온 쪽 {change["변경 분량"]["온 쪽"]}쪽, 남은 부분 {change["변경 분량"]["남은 부분(쪽)"]}쪽
          {change["물리 쪽 기준(참고)"]?.["쪽마다 기준"] && (
            <><br />참고(산정에 쓰지 않음): 바뀐 행을 원고의 쪽에 둔 채 세면 ½쪽 이상 바뀐 쪽이 {change["물리 쪽 기준(참고)"]["쪽마다 기준"].쪽}쪽입니다.</>
          )}
        </p>
      )}

      {result["½쪽 해석 비교"] && (
        <>
          <h3 className="table-title" id="volume-half-title">½쪽 규칙 해석 비교 <span className="meta">계약서 제13조 4항 '½쪽 이상은 1쪽'을 읽는 법에 따른 분량</span></h3>
          <div className="krds-table-wrap">
            <table className="tbl col data" aria-labelledby="volume-half-title">
              <thead><tr><th scope="col">읽는 법</th><th scope="col">기입 분량(매)</th><th scope="col">셈</th></tr></thead>
              <tbody>
                {result["½쪽 해석 비교"].행.map((row, i) => (
                  <tr key={row.해석}><th scope="row">{row.해석}</th><td>{row["기입 분량"]}{i === 0 && <span className="krds-badge bg-light-gray">산정에 씀</span>}</td><td>{row.셈}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h2 className="section-title">산정 가정</h2>
      <ul className="krds-info-list dash">
        {Object.entries(result.가정).map(([key, value]) => <li key={key}>{key}: {String(value)}</li>)}
      </ul>
      <RawJson data={result} title="원본 데이터 보기(개발자용)" />
    </section>
  );
}

// 집필료 카드: 금액, 산식 한 줄, 쓴 값과 근거 조항. 기존 원고가 있으면 개선 기준(변경 분량) 금액도.
// 알림은 금액보다 먼저 읽히도록 카드 위에 둔다(경고 — 상한 초과·계약 분량 초과/미달·추정 — 는 경고색). 단가를 넣지 않았으면 입력 칸으로 가는 버튼을 붙인다.
function FeeCard({ fee }) {
  const defaultUnit = !fee["단가 입력"];
  const toUnitPrice = () => document.getElementById("volume-unit-price")?.focus();
  return (
    <section id="volume-fee" className="volume-fee" aria-labelledby="volume-fee-title">
      <h2 className="section-title" id="volume-fee-title">집필료 (계약서 기준)</h2>
      <Notes notes={fee.알림} warnings={fee.경고}>
        {defaultUnit && <button type="button" className="krds-btn small tertiary" onClick={toUnitPrice}>단가 입력하기</button>}
      </Notes>
      <dl className="upscale-summary">
        <div><dt>집필료</dt><dd><strong>{fee.집필료.toLocaleString()}원</strong>{fee.추정 && " (추정 분량 기준 참고값)"}</dd></div>
        <div><dt>산식</dt><dd>{fee.산식}</dd></div>
        <div>
          <dt>단가 <span className={`krds-badge ${defaultUnit ? "bg-light-warning" : "bg-light-gray"}`}>{defaultUnit ? "기본값(지침 상한)" : "입력값"}</span></dt>
          <dd>{fee.단가.toLocaleString()}원/쪽</dd>
          {defaultUnit && <dd className="meta">{fee["단가 근거"]}</dd>}
        </div>
        <div><dt>분량</dt><dd>산정 {fee["산정 분량"]}매{fee["계약 분량"] != null && `, 계약 ${fee["계약 분량"]}매, 인정 ${fee["인정 분량"]}매`} ({fee["분량 근거"]})</dd></div>
        {fee["개선 기준"] && <div><dt>개선 기준(변경 분량)</dt><dd><strong>{fee["개선 기준"].집필료.toLocaleString()}원</strong> ({fee["개선 기준"].산식})</dd></div>}
        <div><dt>세금</dt><dd>{fee.세금}</dd></div>
      </dl>
      <h3 className="table-title" id="volume-fee-basis-title">집필료 산정 근거 <span className="meta">계약서(F07), 예산집행 및 정산지침(F16)</span></h3>
      <div className="krds-table-wrap">
        <table className="tbl col data" aria-labelledby="volume-fee-basis-title">
          <caption>집필료 산정 근거(계약서 F07, 예산집행 및 정산지침 F16)</caption>
          <thead><tr><th scope="col">근거</th><th scope="col">내용</th></tr></thead>
          <tbody>
            {fee.근거.map((row) => <tr key={row.조항}><th scope="row">{row.조항}</th><td>{row.내용}</td></tr>)}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const show = (value) => (value == null ? "-" : value);
const signed = (value) => (value > 0 ? `+${value}` : `${value}`);

// 출력본 측정: 한글 줄 배치 계산과 나란히, 무엇이 측정이고 무엇이 계산인지 항목별로.
function PrintedResult({ printed }) {
  if (!printed.사용) {
    return (
      <section id="volume-print-result" className="volume-printed">
        <h2 className="section-title">출력본 측정</h2>
        <PageAlert kind="danger"><p>{printed.파일}: {printed.사유}</p></PageAlert>
      </section>
    );
  }
  const total = printed.합계;
  return (
    <section id="volume-print-result" className="volume-printed">
      <h2 className="section-title">출력본 측정 (한글 계산과 비교)</h2>
      <dl className="upscale-summary">
        <div><dt>전체 쪽 수</dt><dd>출력본 <strong>{printed["전체 쪽 수"]}쪽</strong> / 한글 줄 배치 {show(printed["한글 물리 쪽 수"])}쪽{printed["쪽 수 차이"] != null && ` (차이 ${signed(printed["쪽 수 차이"])})`}</dd></div>
        <div><dt>기입 분량</dt><dd>출력본 <strong>{total["기입 분량"]}매</strong> ({total.쪽}쪽 {total.행}행) / 한글 {total["한글 계산 기입 분량"]}매 (차이 {signed(total.차이)})</dd></div>
        <div><dt>같은 원고 확인</dt><dd>모듈 코드 {show(printed["모듈 코드"])}, 원고 문단 일치 {show(printed["같은 글 비율"])}</dd></div>
      </dl>
      {printed.알림.length > 0 && <PageAlert kind="info">{printed.알림.map((note) => <p key={note}>{note}</p>)}</PageAlert>}
      <h3 className="table-title" id="volume-print-method-title">측정과 계산의 구분 <span className="meta">출력본에서 직접 잰 값과 계산한 값</span></h3>
      <div className="krds-table-wrap">
        <table className="tbl col data" aria-labelledby="volume-print-method-title">
          <caption>측정과 계산의 구분</caption>
          <thead><tr><th scope="col">항목</th><th scope="col">방법</th><th scope="col">설명</th></tr></thead>
          <tbody>
            {printed["측정 구분"].map((row) => <tr key={row.항목}><th scope="row">{row.항목}</th><td>{row.방법}</td><td>{row.설명}</td></tr>)}
          </tbody>
        </table>
      </div>
      <h3 className="table-title" id="volume-print-segments-title">구성별 쪽 <span className="meta">출력본 측정과 한글 계산 비교</span></h3>
      <div className="krds-table-wrap">
        <table className="tbl col data" aria-labelledby="volume-print-segments-title">
          <caption>구성별 쪽: 출력본 측정과 한글 계산</caption>
          <thead>
            <tr><th scope="col">구성</th><th scope="col">출력본 쪽</th><th scope="col">인쇄 쪽</th><th scope="col">환산 쪽수(출력본)</th><th scope="col">환산 쪽수(한글)</th><th scope="col">차이</th><th scope="col">한글 원고 쪽</th></tr>
          </thead>
          <tbody>
            {printed.구성.map((row) => (
              <tr key={row.구성} className={row.반영 ? "" : "muted"}>
                <th scope="row">{row.구성}</th>
                <td>{row["출력본 쪽"] || "-"}</td>
                <td>{row["인쇄 쪽"] || "-"}</td>
                <td>{show(row["쪽 환산(출력본)"])}</td>
                <td>{show(row["쪽 환산(한글)"])}</td>
                <td>{show(row.차이)}</td>
                <td>{row["한글 물리 쪽"] || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>쪽별 채움 ({printed.쪽별.length}쪽)</summary>
        <div className="krds-table-wrap">
          <table className="tbl col data">
            <caption>출력본 쪽마다 산정 대상이 차지한 높이(본문 높이 대비)와 산정 반영 여부</caption>
            <thead><tr><th scope="col">쪽</th><th scope="col">인쇄 쪽</th><th scope="col">구성</th><th scope="col">채움</th><th scope="col">산정</th></tr></thead>
            <tbody>
              {printed.쪽별.map((row) => (
                <tr key={row.쪽} className={row.인정 === "제외" ? "muted" : ""}>
                  <th scope="row">{row.쪽}</th><td>{show(row["인쇄 쪽"])}</td><td>{row.구성 || "-"}</td><td>{row.채움}</td><td>{row.인정}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

// 원고 분량 산정(REQ-02-013) — 최종 원고를 올리면 구성별 행·쪽과 계약서에 기입할 분량(매)을 낸다.
// 기존 원고를 함께 올리면 올해 바뀐 분량(1자 이상 바뀐 행)을, 수작업 산정 쪽수를 넣으면 오차율을 함께 보여 준다.
// 출력본 PDF를 함께 올리면 쪽을 PDF에서 재어 한글 계산값과 나란히 보여 주고, 계약서 기준 집필료(분량 × 단가)를 낸다. 계산은 서버(ncs_volume)가 한다.
import React, { useRef, useState } from "react";

import { api } from "../lib/api.js";
import { Spinner } from "../components/Badge.jsx";
import { FileSlot } from "../components/FileSlot.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { RawJson } from "../components/RawJson.jsx";
import { ResultHead } from "../components/ResultHead.jsx";
import { usePageTitle } from "../lib/hooks.js";

// 권고 분량 상태 → KRDS 배지 색
const RANGE_BADGE = { "권고 범위 안": "bg-light-success", "권고보다 적음": "bg-light-warning", "권고보다 많음": "bg-light-warning", 판단불가: "bg-light-gray" };

export default function VolumePage() {
  usePageTitle("원고 분량 산정");
  const [file, setFile] = useState(null);
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
  }

  return (
    <>
    <Header anchors={[]} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page volume-page">
      <h1 className="page-title">원고 분량 산정</h1>
      <p className="page-desc">
        최종 원고(hwp/hwpx)를 올리면 집필료 산정 기준(계약서 제13조 4항)대로 구성별 행·쪽을 세어 계약서에 기입할 분량(매)을 냅니다.
        1행에 1자 이상이면 1행, ½쪽 이상이면 1쪽이며 행 띄움·표·출처 밝힌 인용은 넣고 사진·삽화 등 시각 자료와 표지·NCS학습모듈의 이해·개발진은 뺍니다.
        기존 학습모듈 원고를 함께 올리면 올해 바뀐 분량을 따로 셉니다. 올린 파일은 계산 뒤 바로 지웁니다.
      </p>

      <form className="fieldset review-form" onSubmit={submit}>
        <FileSlot id="volume-final" label="최종 원고" required accept=".hwp,.hwpx" file={file} onChange={setFile} disabled={busy}
                  hint="3차 검토까지 반영한 최종 완성본(hwp/hwpx). 한글에서 저장한 파일이어야 줄·쪽을 정확히 셉니다." />
        <FileSlot id="volume-previous" label="기존 원고" accept=".hwp,.hwpx" file={previous} onChange={setPrevious} disabled={busy}
                  hint="비교할 기존 학습모듈 원고 — 올리면 1자 이상 바뀐 행을 변경 분량으로 셉니다." />
        <FileSlot id="volume-print" label="출력본 PDF" accept=".pdf" file={printCopy} onChange={setPrintCopy} disabled={busy}
                  hint="최종 원고를 한글에서 PDF로 저장한 것 — 올리면 전체 쪽 수·구성별 쪽·쪽마다 채운 높이를 PDF에서 직접 재어 산정에 씁니다." />
        <div className="form-group">
          <div className="form-tit"><label htmlFor="volume-manual">수작업 산정 쪽수 (선택)</label></div>
          <div className="form-conts">
            <input id="volume-manual" type="number" min="1" step="0.5" className="krds-input" value={manual} disabled={busy}
                   onChange={(e) => setManual(e.target.value)} aria-describedby="volume-manual-hint" placeholder="예: 80" />
          </div>
          <p className="form-hint" id="volume-manual-hint">넣으면 자동 산정과의 오차율(기준 0.5% 이내)을 함께 보여 줍니다.</p>
        </div>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="volume-unit-price">원고료 단가 (원/쪽, 선택)</label></div>
          <div className="form-conts">
            <input id="volume-unit-price" type="number" min="1" step="1" className="krds-input" value={unitPrice} disabled={busy}
                   onChange={(e) => setUnitPrice(e.target.value)} aria-describedby="volume-unit-price-hint" placeholder="50000" />
          </div>
          <p className="form-hint" id="volume-unit-price-hint">계약서에는 단가가 없고(제2조 계약금액 빈칸), 예산·정산지침의 원고료 50,000원/쪽은 상한입니다. 비우면 상한으로 계산합니다.</p>
        </div>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="volume-contract-pages">계약 분량 (매, 선택)</label></div>
          <div className="form-conts">
            <input id="volume-contract-pages" type="number" min="1" step="1" className="krds-input" value={contractPages} disabled={busy}
                   onChange={(e) => setContractPages(e.target.value)} aria-describedby="volume-contract-pages-hint" placeholder="예: 80" />
          </div>
          <p className="form-hint" id="volume-contract-pages-hint">과업지시서에 적은 원고 분량 — 넣으면 넘는 분량은 인정하지 않고(추가금 없음), 모자라면 제출 분량만큼 계산합니다.</p>
        </div>
        <div className="form-group">
          <div className="form-tit"><span>부록</span></div>
          <div className="form-conts">
            <div className="krds-form-check">
              <input type="checkbox" id="volume-appendix" checked={appendix} disabled={busy} onChange={(e) => setAppendix(e.target.checked)} />
              <label htmlFor="volume-appendix">부록을 산정에 넣기 (계약서 제13조 4항 ①)</label>
            </div>
          </div>
        </div>
        <div className="form-group form-actions">
          <div className="form-tit form-tit-spacer" aria-hidden="true"><label>&nbsp;</label></div>
          <div className="run-buttons">
            <button className="krds-btn primary large" type="submit" disabled={busy || !file}>{busy ? "세는 중…" : "분량 산정"}</button>
            {busy && <button className="krds-btn tertiary large" type="button" onClick={() => aborter.current?.abort()}>취소</button>}
          </div>
          <PageAlert kind="danger">{error}</PageAlert>
        </div>
      </form>

      {busy && <ResultHead status={<Spinner label="원고 분량을 세는 중" />} />}
      {result && !busy && <VolumeResult result={result} />}
      <TopButton />
    </main>
    <Footer />
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
    <section className="volume-result">
      <ResultHead
        status={<span className={`krds-badge large ${RANGE_BADGE[band.상태] || "bg-light-gray"}`}>{band.상태}</span>}
        meta={`${result.원고} · ${band.비고}`}
        badges={result.추정 && <span className="krds-badge bg-light-warning">추정치 — 줄 배치 정보 없음</span>}
      />
      <dl className="upscale-summary">
        <div><dt>기입 분량(산정에 씀)</dt><dd><strong>{adopted["기입 분량"]}매</strong> — {adopted.근거}</dd></div>
        {gap != null && <div><dt>한글 줄 배치 계산</dt><dd>{total["기입 분량"]}매 (출력본 측정과 차이 {gap > 0 ? "+" : ""}{gap}매)</dd></div>}
        <div><dt>쪽 + 남은 행</dt><dd>{total.쪽}쪽 {total.행}행</dd></div>
        <div><dt>행 합계</dt><dd>{total["행 합계"].toLocaleString()}행</dd></div>
        <div><dt>쪽 환산(높이 기준)</dt><dd>{total["쪽 환산"]}쪽</dd></div>
        {result["물리 쪽 수"] != null && <div><dt>물리 쪽 수(전체)</dt><dd>{result["물리 쪽 수"]}쪽</dd></div>}
        {change && <div><dt>변경 분량</dt><dd><strong>{change["변경 분량"]["기입 분량"]}매</strong> ({change["변경 행"].toLocaleString()}행, {change["변경 비율"]})</dd></div>}
        {manual && <div><dt>수작업 대조</dt><dd>오차율 {manual.오차율} — {manual.결과}</dd></div>}
      </dl>
      {result.알림.length > 0 && <PageAlert kind="info">{result.알림.map((note) => <p key={note}>{note}</p>)}</PageAlert>}

      <FeeCard fee={result.집필료} />
      {result.출력본 && <PrintedResult printed={result.출력본} />}

      <h2 className="section-title">구성별 분량</h2>
      <p className="meta section-desc">측정 방식: {result["측정 방식"]}</p>
      <div className="krds-table-wrap">
        <table className="tbl col data">
          <caption>구성별 행·쪽 산정표</caption>
          <thead>
            <tr><th scope="col">구성</th><th scope="col">산정</th><th scope="col">행</th><th scope="col">쪽 환산</th><th scope="col">물리 쪽</th><th scope="col">시각 자료 제외(쪽)</th>{change && <th scope="col">변경 행</th>}</tr>
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
          기존 원고 {change["기존 원고"]}: {change["기존 원고 분량"]["기입 분량"]}매{change["기존 원고 추정"] ? "(추정)" : ""} · 변경 {change["변경 분량"].쪽}쪽 {change["변경 분량"].행}행 · {change.방법}
        </p>
      )}

      <h2 className="section-title">산정 가정</h2>
      <ul className="krds-info-list dash">
        {Object.entries(result.가정).map(([key, value]) => <li key={key}>{key}: {String(value)}</li>)}
      </ul>
      <RawJson data={result} title="원본 JSON" />
    </section>
  );
}

// 집필료 카드: 금액, 산식 한 줄, 쓴 값과 근거 조항. 기존 원고가 있으면 개선 기준(변경 분량) 금액도.
function FeeCard({ fee }) {
  return (
    <section id="volume-fee" className="volume-fee" aria-labelledby="volume-fee-title">
      <h2 className="section-title" id="volume-fee-title">집필료 (계약서 기준)</h2>
      <dl className="upscale-summary">
        <div><dt>집필료</dt><dd><strong>{fee.집필료.toLocaleString()}원</strong>{fee.추정 && " (추정 분량 기준 — 참고값)"}</dd></div>
        <div><dt>산식</dt><dd>{fee.산식}</dd></div>
        <div><dt>단가</dt><dd>{fee.단가.toLocaleString()}원/쪽 — {fee["단가 근거"]}</dd></div>
        <div><dt>분량</dt><dd>산정 {fee["산정 분량"]}매{fee["계약 분량"] != null && ` · 계약 ${fee["계약 분량"]}매 → 인정 ${fee["인정 분량"]}매`} ({fee["분량 근거"]})</dd></div>
        {fee["개선 기준"] && <div><dt>개선 기준(변경 분량)</dt><dd><strong>{fee["개선 기준"].집필료.toLocaleString()}원</strong> — {fee["개선 기준"].산식}</dd></div>}
        <div><dt>세금</dt><dd>{fee.세금}</dd></div>
      </dl>
      {fee.알림.length > 0 && <PageAlert kind="info">{fee.알림.map((note) => <p key={note}>{note}</p>)}</PageAlert>}
      <div className="krds-table-wrap">
        <table className="tbl col data">
          <caption>집필료 산정 근거(계약서 F07·예산집행 및 정산지침 F16)</caption>
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
        <div><dt>같은 원고 확인</dt><dd>모듈 코드 {show(printed["모듈 코드"])} · 원고 문단 일치 {show(printed["같은 글 비율"])}</dd></div>
      </dl>
      {printed.알림.length > 0 && <PageAlert kind="info">{printed.알림.map((note) => <p key={note}>{note}</p>)}</PageAlert>}
      <div className="krds-table-wrap">
        <table className="tbl col data">
          <caption>측정과 계산의 구분</caption>
          <thead><tr><th scope="col">항목</th><th scope="col">방법</th><th scope="col">설명</th></tr></thead>
          <tbody>
            {printed["측정 구분"].map((row) => <tr key={row.항목}><th scope="row">{row.항목}</th><td>{row.방법}</td><td>{row.설명}</td></tr>)}
          </tbody>
        </table>
      </div>
      <div className="krds-table-wrap">
        <table className="tbl col data">
          <caption>구성별 쪽 — 출력본 측정과 한글 계산</caption>
          <thead>
            <tr><th scope="col">구성</th><th scope="col">출력본 쪽</th><th scope="col">인쇄 쪽</th><th scope="col">쪽 환산(출력본)</th><th scope="col">쪽 환산(한글)</th><th scope="col">차이</th><th scope="col">한글 물리 쪽</th></tr>
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
            <caption>출력본 쪽마다 산정 대상이 차지한 높이(본문 높이 대비)와 ½쪽 규칙 결과</caption>
            <thead><tr><th scope="col">쪽</th><th scope="col">인쇄 쪽</th><th scope="col">구성</th><th scope="col">채움</th><th scope="col">인정</th></tr></thead>
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

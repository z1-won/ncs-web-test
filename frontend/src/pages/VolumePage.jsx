// 원고 분량 산정(REQ-02-013) — 최종 원고를 올리면 구성별 행·쪽과 계약서에 기입할 분량(매)을 낸다.
// 기존 원고를 함께 올리면 올해 바뀐 분량(1자 이상 바뀐 행)을, 수작업 산정 쪽수를 넣으면 오차율을 함께 보여 준다. 계산은 서버(ncs_volume)가 한다.
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
  const [manual, setManual] = useState("");
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
    const { ok, data, error: message, aborted } = await api.volume({ file, previous, manualPages: manual, includeAppendix: appendix, signal: aborter.current.signal });
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
        <div className="form-group">
          <div className="form-tit"><label htmlFor="volume-manual">수작업 산정 쪽수 (선택)</label></div>
          <div className="form-conts">
            <input id="volume-manual" type="number" min="1" step="0.5" className="krds-input" value={manual} disabled={busy}
                   onChange={(e) => setManual(e.target.value)} aria-describedby="volume-manual-hint" placeholder="예: 80" />
          </div>
          <p className="form-hint" id="volume-manual-hint">넣으면 자동 산정과의 오차율(기준 0.5% 이내)을 함께 보여 줍니다.</p>
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
  return (
    <section className="volume-result">
      <ResultHead
        status={<span className={`krds-badge large ${RANGE_BADGE[band.상태] || "bg-light-gray"}`}>{band.상태}</span>}
        meta={`${result.원고} · ${band.비고}`}
        badges={result.추정 && <span className="krds-badge bg-light-warning">추정치 — 줄 배치 정보 없음</span>}
      />
      <dl className="upscale-summary">
        <div><dt>기입 분량</dt><dd><strong>{total["기입 분량"]}매</strong></dd></div>
        <div><dt>쪽 + 남은 행</dt><dd>{total.쪽}쪽 {total.행}행</dd></div>
        <div><dt>행 합계</dt><dd>{total["행 합계"].toLocaleString()}행</dd></div>
        <div><dt>쪽 환산(높이 기준)</dt><dd>{total["쪽 환산"]}쪽</dd></div>
        {result["물리 쪽 수"] != null && <div><dt>물리 쪽 수(전체)</dt><dd>{result["물리 쪽 수"]}쪽</dd></div>}
        {change && <div><dt>변경 분량</dt><dd><strong>{change["변경 분량"]["기입 분량"]}매</strong> ({change["변경 행"].toLocaleString()}행, {change["변경 비율"]})</dd></div>}
        {manual && <div><dt>수작업 대조</dt><dd>오차율 {manual.오차율} — {manual.결과}</dd></div>}
      </dl>
      {result.알림.length > 0 && <PageAlert kind="info">{result.알림.map((note) => <p key={note}>{note}</p>)}</PageAlert>}

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

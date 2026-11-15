// 그림 해상도·업스케일: 원고(hwpx)의 목표 DPI 미만 그림을 원본 그대로 보여 주고, 사람이 고른 그림만 한 장씩 업스케일한다.
// [업스케일링] → 서버가 그림을 키움(엔진·GPU에 따라 수 초~수십 초) → 원본·결과를 나란히 보여 주고 결과 파일을 내려받는다.
// 업스케일한 그림이 있으면 [제안본 hwpx 받기]로 그 그림들만 같은 자리에 넣은 원고 사본을 받는다(본문·그림 크기·위치는 그대로).
import React, { useEffect, useState } from "react";

import { api } from "../lib/api.js";
import { Spinner } from "./Badge.jsx";
import { PageAlert } from "./PageAlert.jsx";

const GRADE = { O: "bg-light-success", "△": "bg-light-warning", X: "bg-light-danger" };

function fileStem(name) {
  return (name || "원고").replace(/\.[^.]+$/, "");
}

// 브라우저 다운로드(같은 출처 GET 링크)
function saveFrom(url) {
  const a = document.createElement("a");
  a.href = url;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export function UpscalePanel({ token, manuscriptName, moduleCode }) {
  const [state, setState] = useState({ status: "loading" });   // { status: loading|ready|error, data, error }
  const [results, setResults] = useState({});                   // bin_id → 업스케일 결과 정보(서버 JSON)
  const [busy, setBusy] = useState(null);                       // 업스케일 중인 bin_id 또는 "proposal"
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    let alive = true;
    setState({ status: "loading" });
    setResults({});
    setError(null);
    setNotice(null);
    api.pictures.list(token).then(({ ok, data, error: message }) => {
      if (!alive) return;
      if (!ok) { setState({ status: "error", error: message }); return; }
      const done = {};
      data.pictures.forEach((p) => { if (p.upscaled) done[p.bin_id] = { ...p.upscaled, v: Date.now() }; });
      setResults(done);
      setState({ status: "ready", data });
    });
    return () => { alive = false; };
  }, [token]);

  const base = moduleCode || fileStem(manuscriptName);

  async function upscale(picture) {
    setBusy(picture.bin_id);
    setError(null);
    setNotice(null);
    const { ok, data, error: message } = await api.pictures.upscale(token, picture.bin_id);
    setBusy(null);
    if (!ok) { setError(message); return; }
    setResults((prev) => ({ ...prev, [picture.bin_id]: { ...data, v: Date.now() } }));
    if (data.status === "완료") saveFrom(api.pictures.downloadUrl(token, picture.bin_id, `${base}_${picture.label}_업스케일`));
  }

  async function proposal() {
    setBusy("proposal");
    setError(null);
    setNotice(null);
    const { ok, error: message, summary } = await api.pictures.proposal(token, moduleCode, `${fileStem(manuscriptName)}_업스케일제안.hwpx`);
    setBusy(null);
    if (!ok) setError(message);
    else if (summary) setNotice(`업스케일한 그림 ${summary["바꾼 그림"]}장을 원고의 같은 자리에 넣은 제안본을 내려받았습니다. 한글에서 열어 그림을 확인하세요.`);
  }

  if (state.status === "loading") {
    return <section className="upscale-panel"><Spinner label="원고의 그림을 읽는 중" /></section>;
  }
  if (state.status === "error") {
    return <section className="upscale-panel"><PageAlert kind="danger">{state.error}</PageAlert></section>;
  }

  const data = state.data;
  const engine = data.engine || {};
  const ready = Object.values(results).filter((r) => r.status === "완료").length;
  const low = data.pictures.filter((p) => p.dpi < data.min_dpi).length;      // 최소 기준에도 못 미침
  const mid = data.pictures.length - low;                                    // 최소 기준 이상, 목표 미만
  const { 그림: total = 0, "그림 파일": fileCount = 0 } = data.counts;
  return (
    <section className="upscale-panel">
      <h2 className="section-title">해상도 점검 결과</h2>
      {/* 한눈에: 원고 그림 수 → 기준 미달 수(등급별) → 업스케일 진행. 숫자를 먼저, 설명은 그 아래 작은 글씨로 */}
      <dl className="upscale-summary">
        <div>
          <dt>원고의 그림</dt>
          <dd><strong>{total}</strong>개</dd>
          <dd className="meta">{fileCount !== total ? `같은 그림을 여러 번 쓴 곳을 묶으면 그림 파일 ${fileCount}개` : "원고에 넣은 그림 전체"}</dd>
        </div>
        <div>
          <dt>해상도 기준 미달</dt>
          <dd><strong>{data.pictures.length}</strong>개</dd>
          <dd className="meta">
            {data.pictures.length === 0 ? `모두 ${data.target_dpi} DPI 이상`
              : <>
                  <span className="krds-badge bg-light-danger">{data.min_dpi} DPI 미만 {low}</span>{" "}
                  <span className="krds-badge bg-light-warning">{data.min_dpi}~{data.target_dpi - 1} DPI {mid}</span>
                </>}
          </dd>
        </div>
        <div>
          <dt>업스케일 완료</dt>
          <dd><strong>{ready}</strong> / {data.pictures.length}개</dd>
          <dd className="meta">완료한 그림만 제안본에 들어갑니다</dd>
        </div>
      </dl>
      <ul className="krds-info-list dash upscale-notes">
        <li>기준은 쪽에 출력되는 크기에서의 실효 해상도 {data.target_dpi} DPI입니다. 아래 목록은 해상도가 낮은 순서입니다.</li>
        <li>업스케일은 화질만 올립니다. 모델이 글자·선을 바꿀 수 있으니 결과를 원본과 나란히 놓고 확인하세요.</li>
      </ul>
      {!engine.available && <PageAlert kind="danger">업스케일 엔진을 쓸 수 없습니다. 그림 목록과 원본 보기만 됩니다.{"\n"}{engine.problem}</PageAlert>}
      {data.pictures.length === 0 && <p className="empty">{data.target_dpi} DPI 미만 그림이 없습니다.</p>}

      <ul className="upscale-list">
        {data.pictures.map((p) => {
          const result = results[p.bin_id];
          const running = busy === p.bin_id;
          return (
            <li key={p.bin_id} className="upscale-card">
              <div className="upscale-head">
                <h3 className="upscale-title">{p.label}</h3>
                <span className={`krds-badge ${GRADE[p.grade] || "bg-light-gray"}`}>{p.dpi} DPI</span>
              </div>
              <p className="meta">
                {p.px[0]}×{p.px[1]}px · 출력 {p.mm[0]}×{p.mm[1]}mm · {p.format} · {p.places.join(", ")}
                {" · "}목표까지 {p.need}배 필요, {p.scale}배로 키움{p.reaches_target ? "" : " (목표 미달)"}
              </p>
              <div className="upscale-pair">
                <figure>
                  <img src={api.pictures.originalUrl(token, p.bin_id)} alt={`${p.label} 원본`} loading="lazy" />
                  <figcaption>원본 {p.px[0]}×{p.px[1]}px</figcaption>
                </figure>
                {result?.status === "완료" && (
                  <figure>
                    <img src={api.pictures.upscaledUrl(token, p.bin_id, result.v)} alt={`${p.label} 업스케일`} loading="lazy" />
                    <figcaption>업스케일 {result.out_px[0]}×{result.out_px[1]}px · {result.out_dpi} DPI · {result.seconds}초</figcaption>
                  </figure>
                )}
              </div>
              {result?.note && <p className={`upscale-note${result.status === "실패" ? " failed" : ""}`}>{result.status === "실패" ? "실패: " : ""}{result.note}</p>}
              <div className="upscale-actions">
                <button type="button" className="krds-btn small primary" disabled={!engine.available || busy !== null} onClick={() => upscale(p)}>
                  {running ? "업스케일 중…" : result?.status === "완료" ? "다시 업스케일링" : "업스케일링"}
                </button>
                {result?.status === "완료" && (
                  <a className="krds-btn small tertiary" href={api.pictures.downloadUrl(token, p.bin_id, `${base}_${p.label}_업스케일`)} download>
                    결과 다시 받기
                  </a>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {data.pictures.length > 0 && (
        <div className="upscale-foot">
          <button type="button" className="krds-btn medium secondary" disabled={!ready || busy !== null} onClick={proposal}
                  title="업스케일한 그림만 원고의 같은 자리에 넣은 사본(hwpx). 본문·그림 크기·위치는 그대로">
            {busy === "proposal" ? "만드는 중…" : `업스케일한 그림 ${ready}장으로 제안본 hwpx 받기`}
          </button>
        </div>
      )}
      {error && <PageAlert kind="danger">{error}</PageAlert>}
      {notice && !error && <PageAlert kind="success">{notice}</PageAlert>}
    </section>
  );
}

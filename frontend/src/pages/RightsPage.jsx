// 권리 증빙 점검(REQ-02-014) — 원고와 제출 서류(작성된 한글 양식)를 올려 모듈별 증빙 제출 현황표와 누락 목록을 본다.
// 표로 읽을 수 없는 서류(양도 동의서·초상권 동의서·서약서 본문)의 제출 여부와 기한 계산용 날짜는 화면에서 받는다.
// 데이터베이스가 연결되어 있으면 확인된 증빙을 이미지 저작권 DB에 반영할 수 있다.
import React, { useEffect, useRef, useState } from "react";

import { api } from "../lib/api.js";
import { copyText } from "../lib/clipboard.js";
import { Badge, BADGE } from "../components/Badge.jsx";
import { FileSlot, MultiFileSlot } from "../components/FileSlot.jsx";
import { KrdsDateField } from "../components/KrdsDateField.jsx";
import { KrdsSelect } from "../components/KrdsSelect.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { usePageTitle } from "../lib/hooks.js";
import { loadName, saveName } from "../lib/imageTerms.js";

const ANCHORS = [{ id: "rights-run", label: "점검 실행" }, { id: "rights-result", label: "점검 결과" }];
const PORTRAIT_OPTIONS = [
  { value: "unknown", label: "확인하지 않음" },
  { value: "none", label: "인물이 든 사진 없음(확인함)" },
  { value: "submitted", label: "초상권 사용 동의서 제출됨" },
];
const ALERT_KIND = { 적합: "success", 부적합: "danger", 판단불가: "info" };
const STATE_TONE = { 제출: "bg-light-success", 누락: "bg-light-danger", "확인 필요": "bg-light-warning", "해당 없음": "bg-light-gray" };

function mark(value) {
  if (value === null || value === undefined) return <><span aria-hidden="true">-</span><span className="sr-only">해당 없음</span></>;
  return <><span aria-hidden="true">{value ? "○" : "×"}</span><span className="sr-only">{value ? "있음" : "없음"}</span></>;
}

export default function RightsPage() {
  usePageTitle("권리 증빙 점검");
  const [manuscript, setManuscript] = useState(null);
  const [forms, setForms] = useState([]);
  const [printCopy, setPrintCopy] = useState(null);   // 출력본 PDF(선택)
  const [copied, setCopied] = useState(null);         // 방금 복사한 알림의 받는 곳
  const [options, setOptions] = useState({ firstReviewOn: "", submittedOn: "", transferAuthor: false, transferMaker: false, pledge: false, portrait: "unknown" });
  const [busy, setBusy] = useState(null);       // "check" | "save" | "export"
  const [error, setError] = useState(null);
  const [report, setReport] = useState(null);
  const [imageDb, setImageDb] = useState(false);
  const [by, setBy] = useState(loadName);
  const [moduleCode, setModuleCode] = useState("");
  const [saved, setSaved] = useState(null);     // { kind, text } — DB 반영 결과
  const result = useRef(null);

  useEffect(() => { api.health().then(({ ok, data }) => { if (ok) setImageDb(!!data.image_db); }); }, []);

  const set = (key) => (value) => setOptions((prev) => ({ ...prev, [key]: value }));
  const check = (key, label, hint) => (
    <div className="krds-form-check">
      <input type="checkbox" id={`rights-${key}`} checked={options[key]} onChange={(e) => set(key)(e.target.checked)} />
      <label htmlFor={`rights-${key}`}><span className="check-text">{label}{hint && <span className="check-hint">{hint}</span>}</span></label>
    </div>
  );

  async function run() {
    setBusy("check");
    setError(null);
    setSaved(null);
    const { ok, data, error: message } = await api.rights.check(manuscript, forms, { ...options, printCopy });
    setBusy(null);
    if (!ok) { setError(message); setReport(null); return; }
    setReport(data);
    requestAnimationFrame(() => result.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }));
  }

  async function saveToDb() {
    setBusy("save");
    setSaved(null);
    const { ok, data, error: message } = await api.rights.check(manuscript, forms, { ...options, printCopy, save: true, by, moduleCode });
    setBusy(null);
    if (!ok) { setSaved({ kind: "danger", text: message }); return; }
    setReport(data);
    const s = data.저장;
    setSaved({ kind: s.거부.length ? "danger" : "success",
               text: `이미지 저작권 DB에 반영했습니다(모듈 ${s["모듈 코드"]}). 그림 ${s.그림}개(새 그림 ${s["새 그림"]}), 새로 이은 증빙 ${s.증빙}건`
                 + (s.건너뜀 ? `, 그림 파일을 찾지 못해 건너뜀 ${s.건너뜀}개` : "") + (s.거부.length ? `, 거부 ${s.거부.length}건` : "") + "." });
  }

  async function copyNotice(notice) {
    if (await copyText(notice.글)) {
      setCopied(notice["받는 곳"]);
      setTimeout(() => setCopied(null), 2000);
    }
  }

  async function exportXlsx() {
    setBusy("export");
    const { ok, error: message } = await api.rights.exportXlsx(report);
    setBusy(null);
    if (!ok) setError(message);
  }

  const summary = report?.요약;
  const deadline = report?.기한;
  const seen = report ? Object.entries(report.서류["읽은 양식"]) : [];
  return (
    <>
    <Header anchors={report ? ANCHORS : []} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page rights-page">
      <h1 className="page-title">권리 증빙 점검</h1>
      <p className="page-desc">
        원고의 그림과 제출 서류를 대조해 빠진 권리 증빙을 찾습니다. 원고와 함께, 작성한 한글 양식(사진·삽화 수록 현황 목록, 제작 목록,
        이용허락 동의서, 생성형 AI 결과물 집필자 서약서)을 올리면 그림마다 필요한 증빙과 제출 여부를 표로 보여 줍니다.
        서류는 파일 이름과 상관없이 안에 든 표로 알아보므로, 계약서 한 파일에 붙임이 여러 개 있어도 됩니다.
      </p>
      {/* 칸 아래 도움말은 한 줄로 두고, 긴 설명은 여기에 모은다 */}
      <p className="page-desc">
        출력본 PDF를 올리면 그림이 놓인 쪽을 읽어 생성형 AI 결과물 현황의 쪽수와 대조합니다. 수록 현황 목록은 1차 검토 이후 4주 이내에 내야 하므로,
        1차 검토일을 넣으면 제출 기한을 계산합니다. 사진에 인물이 있는지는 자동으로 알 수 없어 초상권 확인 상태를 직접 선택합니다.
      </p>

      <section id="rights-run" className="nav-anchor">
        {/* 입력 묶음은 구획 셋: 파일 올리기 → 점검 조건 → 실행. 구획 안에서만 3열 격자(.form-section-grid)를 쓴다. 구획 제목은 보이는 h2 — KRDS가 legend를 화면에서 숨기므로 fieldset 대신 role=group으로 묶는다 */}
        <div className="fieldset review-form is-sectioned">
          <div className="form-section" role="group" aria-labelledby="rights-files-title">
          <h2 className="form-section-title" id="rights-files-title">파일 올리기</h2>
          <div className="form-section-grid">
          <FileSlot id="rights-manuscript" label="원고" required accept=".hwpx,.hwp" file={manuscript} onChange={(file) => { setManuscript(file); setReport(null); }}
                    hint="hwp, hwpx. 이미지 저작권 DB에 등록하려면 hwpx여야 합니다." />
          <MultiFileSlot id="rights-forms" label="제출 서류" accept=".hwp,.hwpx" files={forms} disabled={!!busy}
                         onChange={(picked) => { setForms(picked); setReport(null); }}
                         hint="hwp, hwpx 여러 개. 없으면 원고만으로 점검합니다." />
          <FileSlot id="rights-print" label="출력본 PDF" accept=".pdf" file={printCopy} disabled={!!busy} onChange={(file) => { setPrintCopy(file); setReport(null); }}
                    hint="pdf. 올리면 결과물 현황의 쪽수와 대조합니다." />
          </div>
          </div>
          <div className="form-section" role="group" aria-labelledby="rights-options-title">
          <h2 className="form-section-title" id="rights-options-title">점검 조건</h2>
          <div className="form-section-grid">
          <KrdsDateField id="rights-first" label="1차 검토일" value={options.firstReviewOn} onChange={set("firstReviewOn")} disabled={!!busy}
                         hint="이 날짜에서 4주 뒤가 제출 기한입니다." />
          <KrdsDateField id="rights-submitted" label="수록 현황 목록 제출일" value={options.submittedOn} onChange={set("submittedOn")} disabled={!!busy}
                         hint="아직 제출하지 않았으면 비워 둡니다." />
          <div className="form-group">
            <div className="form-tit"><label htmlFor="rights-portrait">초상권</label></div>
            <div className="form-conts">
              <KrdsSelect id="rights-portrait" value={options.portrait} options={PORTRAIT_OPTIONS} onChange={set("portrait")} title="초상권 확인 상태 선택" />
            </div>
            <p className="form-hint">확인하지 않으면 사진마다 ‘확인 필요’로 나옵니다.</p>
          </div>
          <div className="form-group form-group-wide">
            <div className="form-tit"><span id="rights-signed-label">서명 서류 제출 여부</span></div>
            <div className="form-conts krds-check-area chk-column rights-checks" role="group" aria-labelledby="rights-signed-label">
              {check("transferAuthor", "집필자 지식재산권 양도 동의서", "원고 집필 계약서 붙임 4")}
              {check("transferMaker", "제작자 지식재산권 양도 동의서", "사진·삽화 제작 계약서 붙임 3")}
              {check("pledge", "생성형 AI 결과물 집필자 서약서", "생성형 AI를 활용한 그림이 있을 때 제출")}
            </div>
            <p className="form-hint">서명 문서는 파일에서 읽지 못하므로 제출 여부를 직접 표시합니다.</p>
          </div>
          </div>
          </div>
          <div className="form-actions">
            {error && <PageAlert kind="danger">{error}</PageAlert>}
            <div className="run-buttons image-actions">
              <button type="button" className="krds-btn large primary" disabled={!manuscript || !!busy} onClick={run}>{busy === "check" ? "점검하는 중" : "점검 실행"}</button>
            </div>
          </div>
        </div>
      </section>

      {report && (
        <section id="rights-result" className="nav-anchor rights-result" ref={result}>
          <div className="section-head">
            <h2 className="section-title">점검 결과 <Badge value={summary.판정} large /></h2>
            <button type="button" className="krds-btn small tertiary" disabled={!!busy} onClick={exportXlsx}>{busy === "export" ? "만드는 중" : "현황표 내려받기(엑셀)"}</button>
          </div>
          <dl className="upscale-summary image-summary">
            <div><dt>원고의 그림</dt><dd><strong>{summary["원고 그림"]}</strong>개</dd>
              <dd className="meta">{summary["목록 행"] === null ? "수록 현황 목록 없음" : `수록 현황 목록 ${summary["목록 행"]}행${summary.학습모듈명 ? `, ${summary.학습모듈명}` : ""}`}</dd></div>
            <div><dt>적합</dt><dd><strong>{summary.적합}</strong>개</dd></div>
            <div><dt>부적합</dt><dd><strong>{summary.부적합}</strong>개</dd><dd className="meta">누락 또는 불일치 {summary.누락}건</dd></div>
            <div><dt>판단불가</dt><dd><strong>{summary.판단불가}</strong>개</dd><dd className="meta">담당자 확인 {summary["확인 필요"]}건</dd></div>
          </dl>
          <PageAlert kind={ALERT_KIND[deadline.판정]}>
            <strong>제출 기한: {deadline.판정}</strong>{"\n"}{deadline.내용}
          </PageAlert>
          <p className="rights-forms-seen">
            읽은 양식: {seen.length ? seen.map(([name, files]) => `${name}(${files.join(", ")})`).join(" / ") : "없음"}
            {report.출력본 && ` / 출력본 ${report.출력본.파일}(${report.출력본.쪽}쪽, 캡션을 찾은 그림 ${report.출력본["캡션 찾은 그림"]}개)`}
          </p>
          {report.안내.length > 0 && <PageAlert kind="info">{report.안내.join("\n")}</PageAlert>}

          <h3 className="sub-title">증빙 제출 현황표</h3>
          {report.현황표.length === 0 ? <p className="empty">원고에서 그림을 찾지 못했습니다.</p> : (
            <div className="krds-table-wrap">
              <table className="tbl col data rights-table">
                <caption>그림마다 필요한 증빙과 제출 여부</caption>
                <colgroup><col className="col-figure" /><col className="col-mark" /><col className="col-mark" /><col className="col-method" /><col className="col-evidence" /><col className="col-ai" /><col className="col-verdict" /><col /></colgroup>
                <thead><tr><th scope="col">그림</th><th scope="col">원고</th><th scope="col">목록</th><th scope="col">제작 방식</th><th scope="col">증빙</th><th scope="col">AI 표기</th><th scope="col">판정</th><th scope="col">비고</th></tr></thead>
                <tbody>{report.현황표.map((row, index) => (
                  <tr key={index}>
                    <td><strong>{row["그림 번호"] || "번호 없음"}</strong><span className="sub">{row.그림명}</span>{row.쪽 && <span className="sub">출력본 {row.쪽}</span>}</td>
                    <td className="center">{mark(row.원고)}</td>
                    <td className="center">{mark(row.목록)}</td>
                    <td>{row["제작 방식"].length ? row["제작 방식"].map((name) => <span className="line" key={name}>{name}</span>) : "-"}</td>
                    <td>{row.증빙.length ? row.증빙.map((item) => (
                      <span className="line" key={item.증빙} title={item.근거 || undefined}>{item.증빙} <span className={`krds-badge ${STATE_TONE[item.상태] || "bg-light-gray"}`}>{item.상태}</span></span>
                    )) : <span className="sub">낼 증빙 없음</span>}</td>
                    <td>{row["AI 표기"] || "-"}{row["결과물 현황"] && <span className="sub">현황: {row["결과물 현황"]}</span>}</td>
                    <td><span className={`krds-badge ${BADGE[row.판정]}`}>{row.판정}</span></td>
                    <td>{row.비고.map((text, i) => <span className="line" key={i}>{text}</span>)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}

          <h3 className="sub-title">누락과 확인할 것 {report.지적사항.length}건</h3>
          {report.지적사항.length === 0 ? <p className="empty">빠진 증빙이 없습니다.</p> : (
            <ul className="findings-list">
              {report.지적사항.map((finding, index) => (
                <li className="finding" key={index}>
                  <div className="finding-head"><Badge value={finding.수준} /><span className="finding-check">{finding.그림}</span><span className="meta">{finding.종류}, {finding["받는 곳"]}</span></div>
                  <dl className="finding-body">
                    <dt>내용</dt><dd>{finding.내용}</dd>
                    {finding.조치 && <><dt>조치</dt><dd>{finding.조치}</dd></>}
                  </dl>
                </li>
              ))}
            </ul>
          )}

          <h3 className="sub-title">기관별 알림</h3>
          <p className="form-hint">서류를 내거나 원고나 목록을 고쳐야 하는 것은 개발기관에, 같은 것인지 사람이 가려야 하는 것은 에디팅 기관에 보냅니다.
            글을 복사해 그대로 전달할 수 있고, 현황표 xlsx에도 기관별 시트로 들어 있습니다. 이 화면이 직접 보내지는 않습니다.</p>
          <div className="rights-notices">
            {(report.알림 || []).map((notice) => (
              <div className="rights-notice" key={notice["받는 곳"]}>
                <div className="rights-notice-head">
                  <strong>{notice["받는 곳"]}</strong>
                  <span className="meta">{notice.건수}건(부적합 {notice.부적합}, 판단불가 {notice.판단불가})</span>
                  <button type="button" className="krds-btn small tertiary" onClick={() => copyNotice(notice)}>
                    {copied === notice["받는 곳"] ? "복사했습니다" : "알림 글 복사"}
                  </button>
                </div>
                <pre className="rights-notice-text">{notice.글}</pre>
              </div>
            ))}
          </div>

          <h3 className="sub-title">이미지 저작권 DB에 등록</h3>
          {!imageDb ? <p className="empty">데이터베이스가 연결되어 있지 않아 등록할 수 없습니다. 점검 결과는 위 표와 엑셀 현황표로 확인해 주세요.</p> : (
            <div className="fieldset review-form">
              <div className="form-group">
                <div className="form-tit"><label htmlFor="rights-by">변경한 사람</label></div>
                <div className="form-conts"><input id="rights-by" type="text" className="krds-input" maxLength={50} value={by} placeholder="예: 에디팅기관 홍길동"
                                                   onChange={(e) => { setBy(e.target.value); saveName(e.target.value); }} /></div>
                <p className="form-hint">변경 이력에 남습니다.</p>
              </div>
              <div className="form-group">
                <div className="form-tit"><label htmlFor="rights-module">모듈 코드</label></div>
                <div className="form-conts"><input id="rights-module" type="text" className="krds-input" value={moduleCode} placeholder="LM1203020201_24v3" onChange={(e) => setModuleCode(e.target.value)} /></div>
                <p className="form-hint">원고 파일 이름에 모듈 코드가 있으면 비워 둬도 됩니다.</p>
              </div>
              <div className="form-group form-group-wide form-actions">
                <p className="form-hint">원고의 그림과 수록 위치, 목록의 제작 방식을 이미지 저작권 DB에 넣고, 위 표에서 ‘제출’로 확인된 증빙을 그림에 잇습니다.
                  이미 있는 그림은 합쳐지고, 기관이 확정한 권리 정보는 바뀌지 않습니다.</p>
                {saved && <PageAlert kind={saved.kind}>{saved.text}</PageAlert>}
                <div className="run-buttons image-actions">
                  <button type="button" className="krds-btn large secondary" disabled={!!busy || !by.trim()} onClick={saveToDb}>{busy === "save" ? "등록하는 중" : "이미지 저작권 DB에 등록"}</button>
                </div>
              </div>
            </div>
          )}
        </section>
      )}
      <TopButton />
    </main>
    <Footer />
    </>
  );
}

// 결과 표 셋: 검수 확인서(SheetTable), 지적사항(FindingsTable), 전체 체크리스트(ChecklistTable).
import React, { useState } from "react";
import { Badge, MARK } from "./Badge.jsx";
import { asText, withBoxNumbers } from "../lib/format.jsx";

/* F02 검수 확인서 모양: 구성요소 | 체크 항목 | 검수 결과(적합/부적합/판단불가) | 비고 */
// 확인서 행에 속한 지적사항: item_id가 그 번호로 끝나거나(F02-필요지식-⑤), 체크 이름이 그 번호로 시작(위치 ②③④처럼 한 item_id를 나눠 쓰는 엔진)
// 여러 구성요소를 한 표에 모을 때는 행·지적사항에 _check(엔진 이름)를 붙여 같은 번호(차례 ①·개요 ①)가 섞이지 않게 한다.
export function findingsOfRow(findings, row) {
  return (findings || []).filter((f) => (!row._check || !f._check || f._check === row._check)
    && (f.item_id.endsWith(row.번호) || String(f.check).startsWith(row.번호)));
}

const rowKey = (row) => `${row._check || ""}-${row.번호}`;

// sheet: 확인서 행 목록. 한 구성요소만, 또는 여러 구성요소를 이어 붙인 것(구성요소 머리칸은 연속 묶음마다 rowSpan).
export function SheetTable({ sheet, findings }) {
  const [expanded, setExpanded] = useState(() => new Set());
  if (!sheet.length) return null;
  function toggle(key) {
    setExpanded((prev) => { const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next; });
  }
  // 구성요소 묶음: 첫 행 인덱스 → 묶음 길이(펼친 지적사항 행 포함)
  const groups = new Map();
  let start = 0;
  sheet.forEach((row, i) => {
    if (i === 0 || row.구성요소 !== sheet[i - 1].구성요소 || row._check !== sheet[i - 1]._check) start = i;
    groups.set(start, (groups.get(start) || 0) + 1 + (expanded.has(rowKey(row)) ? 1 : 0));
  });
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
            const key = rowKey(row);
            const open = expanded.has(key);
            return (
              <React.Fragment key={key}>
                <tr>
                  {groups.has(i) && <th scope="rowgroup" className="component" rowSpan={groups.get(i)}>{row.구성요소}</th>}
                  <td style={{ whiteSpace: "pre-wrap" }}>
                    {row.번호} {withBoxNumbers(row["체크 항목"])}
                    {own.length > 0 && (
                      <div className="sheet-more">
                        {/* 확인서 비고는 요약이므로, 어디가 어떻게 틀렸는지는 이 행의 지적사항을 펼쳐서 본다. 펼쳐지는 자리(이 열 시작선)와 맞춰 여기에 둔다 */}
                        <button type="button" className="krds-btn xsmall text" aria-expanded={open} aria-controls={`sheet-detail-${key}`}
                                onClick={() => toggle(key)}>
                          {open ? "지적사항 접기" : `지적사항 ${own.length}건 보기`}
                        </button>
                      </div>
                    )}
                  </td>
                  <td className={`mark ${MARK[row.검수결과] || ""}`}>{row.검수결과 === "적합" ? "✓" : ""}</td>
                  <td className={`mark ${MARK[row.검수결과] || ""}`}>{row.검수결과 === "부적합" ? "✓" : ""}</td>
                  <td className={`mark ${MARK[row.검수결과] || ""}`}>{row.검수결과 === "판단불가" ? "△" : ""}</td>
                  <td style={{ whiteSpace: "pre-line" }}>{withBoxNumbers(row.비고)}</td>
                </tr>
                {open && (
                  <tr className="sheet-detail" id={`sheet-detail-${key}`}>
                    <td colSpan={5}><FindingsList findings={own} /></td>
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

// 확인서 행 아래에 펼쳐지는 지적사항 — 표 안의 표 대신 "행에 딸린 상세 목록". 지적사항마다 판정 배지 + 체크명, 그 아래 위치/사유/수정 제안을 레이블-값으로
export function FindingsList({ findings }) {
  if (!findings.length) return <p className="empty">지적사항이 없습니다.</p>;
  return (
    <ul className="findings-list">
      {findings.map((f, i) => (
        <li key={`${f.item_id}|${f.check}|${f.region_path}|${i}`} className="finding">
          <div className="finding-head">
            <Badge value={f.verdict} />
            <strong className="finding-check">{f.check}</strong>
          </div>
          <dl className="finding-body">
            {f.region_path && <><dt>위치</dt><dd className="path">{f.region_path}</dd></>}
            {f.reason && <><dt>사유</dt><dd>{withBoxNumbers(f.reason)}</dd></>}
            {f.suggestion && <><dt>수정 제안</dt><dd>{asText(f.suggestion)}</dd></>}
          </dl>
        </li>
      ))}
    </ul>
  );
}

export function FindingsTable({ findings, compact = false }) {
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
            <tr key={`${f.item_id}|${f.check}|${f.region_path}|${i}`}>
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

export function ChecklistTable({ rows }) {
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
            <tr key={`${r.item_id}|${r.region_path}|${i}`}>
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

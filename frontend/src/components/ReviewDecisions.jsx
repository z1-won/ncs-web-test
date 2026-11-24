// 원고 검수 결과 아래의 두 가지 — 담당자 판정 확정(REQ-02-002 사람 작업 5번)과 앞 검수와의 비교(4번).
// 확정: 자동 판정이 부적합·판단불가인 항목을 담당자가 적합/부적합으로 정하고 사유를 적는다. 내려받는 확인서(hwpx, 엑셀, F03 표)에 반영된다.
//       확정은 검수하는 쪽(에디터, 직능연)의 일이다 — 집필진·검토진·위원 계정에는 확정 표를 보이지 않는다(useCanManage).
// 비교: 같은 학습모듈의 앞 전체 검수(검수 이력)를 골라 판정이 바뀐 항목과 그대로 남은 부적합을 본다. 검수 이력을 저장하는 서버에서만 된다.
import React, { useEffect, useMemo, useState } from "react";

import { Badge } from "./Badge.jsx";
import { PageAlert } from "./PageAlert.jsx";
import { api } from "../lib/api.js";
import { useCanManage } from "../lib/auth.jsx";
import { compareSheets, decisionKey } from "../lib/decisions.js";
import { formatDate } from "../lib/format.jsx";

const CHOICES = ["", "적합", "부적합"];
const CHANGE_CLASS = { "해결": "bg-light-success", "새 부적합": "bg-light-danger", "그대로 부적합": "bg-light-warning", "판정 바뀜": "bg-light-gray" };

export function ReviewDecisions({ rows, decisions, onChange, saved, onServer = false, moduleCode, groupId }) {
  const open = useMemo(() => (rows || []).filter((row) => row.검수결과 === "부적합" || row.검수결과 === "판단불가"), [rows]);
  const decided = open.filter((row) => decisions[decisionKey(row)]?.verdict).length;
  const canDecide = useCanManage();
  const [groups, setGroups] = useState(null);     // 같은 학습모듈의 앞 검수 묶음. null: 아직 안 물음
  const [picked, setPicked] = useState("");
  const [diff, setDiff] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => { setGroups(null); setPicked(""); setDiff(null); setError(null); }, [groupId, moduleCode]);

  function set(row, patch) {
    const key = decisionKey(row);
    const next = { ...decisions, [key]: { verdict: "", reason: "", ...decisions[key], ...patch } };
    if (!next[key].verdict && !next[key].reason) delete next[key];
    onChange(next);
  }

  async function loadGroups() {
    setError(null);
    const { ok, data, error: message } = await api.groups.list();
    if (!ok) return setError(message);
    setGroups(data.filter((g) => g.module_code === moduleCode && g.group_id !== groupId));
  }

  async function compare(id) {
    setPicked(id);
    setDiff(null);
    if (!id) return;
    const { ok, data, error: message } = await api.groups.get(id);
    if (!ok) return setError(message);
    setDiff(compareSheets(data.runs.flatMap((run) => run.검수확인서 || []), rows));
  }

  if (!rows?.length) return null;
  return (
    <section id="review-decide" className="review-decide nav-anchor">
      <h2 className="section-title">판정 확정 {canDecide && <span className="meta">자동 판정이 부적합이거나 판단불가인 {open.length}개 항목 가운데 {decided}개를 확정했습니다.</span>}</h2>
      {!canDecide ? (
        <p className="empty">판정 확정은 에디터와 직능연 계정에서 합니다. 이 계정에서는 자동 판정 결과를 보고 확인서와 수정 메모 원고를 내려받을 수 있습니다.</p>
      ) : open.length === 0 ? <p className="empty">확정할 항목이 없습니다. 모든 항목이 적합입니다.</p> : (
        <>
          <p className="form-hint">
            담당자가 정한 판정과 사유는 내려받는 확인서(hwpx, 엑셀, F03 표)의 판정과 비고에 들어갑니다. 자동 판정도 비고에 함께 남습니다.
            {onServer
              ? (saved ? " 확정한 내용은 서버에 저장되어 다른 담당자도 같은 확정을 봅니다. 누가 언제 정했는지 함께 남습니다." : " 서버에 저장하지 못했습니다. 잠시 후 다시 고쳐 보고, 계속되면 확인서를 내려받아 주세요.")
              : (saved ? " 확정한 내용은 이 브라우저에 저장됩니다." : " 이 브라우저에 저장하지 못했습니다. 창을 닫기 전에 확인서를 내려받아 주세요.")}
          </p>
          <div className="krds-table-wrap">
            <table className="tbl col data decide-table">
              <caption className="sr-only">판정 확정: 항목, 자동 판정, 담당자 확정, 사유</caption>
              <colgroup><col style={{ width: "13%" }} /><col /><col style={{ width: "9%" }} /><col className="decide-col" /><col style={{ width: "26%" }} /></colgroup>
              <thead><tr><th scope="col">구성요소</th><th scope="col">체크 항목</th><th scope="col">자동 판정</th><th scope="col">담당자 확정</th><th scope="col">사유</th></tr></thead>
              <tbody>
                {open.map((row) => {
                  const key = decisionKey(row);
                  const mine = decisions[key] || {};
                  return (
                    <tr key={key}>
                      <td>{row.구성요소}</td>
                      <td>{row.번호} {row["체크 항목"]}</td>
                      <td><Badge value={row.검수결과} /></td>
                      <td>
                        <select className="krds-form-select small" aria-label={`${row.구성요소} ${row.번호} 담당자 확정`} value={mine.verdict || ""}
                                onChange={(e) => set(row, { verdict: e.target.value })}>
                          {CHOICES.map((c) => <option key={c} value={c}>{c || "확정 안 함"}</option>)}
                        </select>
                      </td>
                      <td>
                        <input type="text" className="krds-input small" maxLength={200} aria-label={`${row.구성요소} ${row.번호} 확정 사유`}
                               value={mine.reason || ""} onChange={(e) => set(row, { reason: e.target.value })} placeholder="확정한 까닭" />
                        {mine.by && <span className="meta">{mine.by}, {formatDate(mine.at)}</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h2 className="section-title">앞 검수와 비교</h2>
      {error && <PageAlert kind="danger">{error}</PageAlert>}
      {groups === null ? (
        <div className="decide-actions">
          <button type="button" className="krds-btn small secondary" onClick={loadGroups} disabled={!moduleCode}>같은 학습모듈의 앞 검수 찾기</button>
          <span className="form-hint">초고본과 수정본처럼 같은 학습모듈을 두 번 이상 전체 검수했을 때, 판정이 바뀐 항목을 봅니다.</span>
        </div>
      ) : groups.length === 0 ? (
        <p className="empty">같은 학습모듈({moduleCode})의 앞 검수가 검수 이력에 없습니다.</p>
      ) : (
        <div className="decide-actions">
          <select className="krds-form-select small" aria-label="비교할 앞 검수" value={picked} onChange={(e) => compare(e.target.value)}>
            <option value="">비교할 앞 검수 선택</option>
            {groups.map((g) => <option key={g.group_id} value={g.group_id}>{formatDate(g.created_at)} 전체 검수</option>)}
          </select>
        </div>
      )}
      {diff && (diff.length === 0 ? <p className="empty">판정이 바뀐 항목도, 남은 부적합도 없습니다.</p> : (
        <div className="krds-table-wrap">
          <table className="tbl col data decide-table">
            <caption className="sr-only">앞 검수와 비교: 항목, 앞 판정, 지금 판정, 변화</caption>
            <thead><tr><th scope="col">구성요소</th><th scope="col">체크 항목</th><th scope="col">앞 판정</th><th scope="col">지금 판정</th><th scope="col">변화</th></tr></thead>
            <tbody>
              {diff.map((d) => (
                <tr key={d.key}>
                  <td>{d.구성요소}</td><td>{d.번호} {d.항목}</td><td>{d.앞}</td><td>{d.지금}</td>
                  <td><span className={`krds-badge ${CHANGE_CLASS[d.변화]}`}>{d.변화}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}

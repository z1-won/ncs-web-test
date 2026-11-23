// 담당자 판정 확정(REQ-02-002 사람 작업 5번)과 판본 비교(4번) — 확인서 행을 다루는 순수 함수와 브라우저 저장.
// 확정은 자동 판정을 지우지 않는다: 확인서 비고 맨 앞에 "[담당자 확정: 적합. 사유] (자동 판정: 판단불가)"를 적어 둘 다 남긴다.
export const decisionKey = (row) => `${row.구성요소}-${row.번호}`;

export function applyDecisions(rows, decisions) {
  return (rows || []).map((row) => {
    const picked = decisions?.[decisionKey(row)];
    if (!picked?.verdict || picked.verdict === row.검수결과) return row;
    const head = `[담당자 확정: ${picked.verdict}${picked.reason ? `. ${picked.reason}` : ""}] (자동 판정: ${row.검수결과})`;
    return { ...row, 검수결과: picked.verdict, 적합: picked.verdict === "적합", 부적합: picked.verdict === "부적합",
             비고: row.비고 ? `${head}\n${row.비고}` : head };
  });
}

// 앞 판본(base)과 지금 판본(target)의 확인서 행을 항목으로 짝지어 판정이 바뀐 것과 그대로 남은 부적합을 낸다
export function compareSheets(base, target) {
  const before = new Map((base || []).map((row) => [decisionKey(row), row]));
  const out = [];
  (target || []).forEach((row) => {
    const old = before.get(decisionKey(row));
    const was = old?.검수결과 || "없음";
    const now = row.검수결과;
    let change = null;
    if (was === now) change = now === "부적합" ? "그대로 부적합" : null;
    else if (now === "부적합") change = "새 부적합";
    else if (was === "부적합" && now === "적합") change = "해결";
    else change = "판정 바뀜";
    if (change) out.push({ key: decisionKey(row), 구성요소: row.구성요소, 번호: row.번호, 항목: row["체크 항목"], 앞: was, 지금: now, 변화: change, 비고: row.비고 });
  });
  return out;
}

const storageKey = (id) => `ncs-decisions:${id}`;

export function loadDecisions(id) {
  if (!id) return {};
  try { return JSON.parse(window.localStorage.getItem(storageKey(id)) || "{}") || {}; } catch { return {}; }
}

export function saveDecisions(id, decisions) {
  if (!id) return false;
  try { window.localStorage.setItem(storageKey(id), JSON.stringify(decisions)); return true; } catch { return false; }
}

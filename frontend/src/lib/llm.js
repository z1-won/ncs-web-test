// LLM 검토 결과를 구성요소 확인서에 합친다. 행은 item_id(F02-수행-③ 등)로 찾는다.
// 비고에 LLM 판정·근거·수정 제안을 바로 적는다(펼치지 않아도 보이게). 지적사항에도 같은 내용을 붙인다.
//   지적 있음                 → 부적합
//   지적 없음 + 규칙이 판단불가 → 적합
//   지적 없음 + 규칙 판정 있음  → 규칙 판정 그대로, 비고에 'LLM 지적 없음'
// 확인서에 행이 없는 항목(출처 검토 008)은 합치지 않는다.
import { overallVerdict } from "./checks.js";

const COMPONENT = { 수행: "perform", 평가: "evaluation", 개요: "overview", 기타: "misc", 교수: "teaching", 참고: "references" };
const SHOWN = 5;

function tasksOf(llm, check) {
  return Object.entries(llm?.item_ids || {}).filter(([, id]) => COMPONENT[id.split("-")[1]] === check);
}

export function llmTouches(llm, check) {
  return tasksOf(llm, check).length > 0;
}

// 확인서 비고에는 짧게만 — 자세한 판정·사유·수정은 'LLM 검토' 칸의 표에서 본다
function llmNote(mine, chunks) {
  if (!mine.length) return chunks === 0 ? "[LLM 검토] 검토할 문단을 원고에서 찾지 못함" : "[LLM 검토] 지적 없음";
  return `[LLM 검토] 부적합 ${mine.length}건 — 'LLM 검토'에서 사유·수정 보기`;
}

// 'LLM 검토' 칸의 표 — 항목마다 LLM 검토 전(규칙 판정·비고)과 LLM 지적들.
// components: [{check, data}] — LLM을 합치기 전의 구성요소 결과(규칙 판정)
export function llmRows(llm, components, labels = {}) {
  if (!llm) return [];
  return (llm.tasks || []).map((task) => {
    const itemId = llm.item_ids?.[task];
    const check = itemId ? COMPONENT[itemId.split("-")[1]] : null;
    const number = itemId?.split("-").pop();
    const data = (components || []).find((c) => c.check === check)?.data;
    const row = check ? (data?.검수확인서 || []).find((r) => r.번호 === number) : null;
    return {
      task, itemId, label: labels[task] || task,
      before: row ? { verdict: row.검수결과, note: row.비고 || "" } : null,
      findings: (llm.findings || []).filter((f) => f.task === task),
      chunks: llm.chunks?.[task],
    };
  });
}

export function applyLlm(check, data, llm) {
  const tasks = tasksOf(llm, check);
  if (!data || !tasks.length) return data;
  let rows = data.검수확인서 || [];
  let findings = data.지적사항 || [];
  tasks.forEach(([task, itemId]) => {
    const number = itemId.split("-").pop();
    const mine = (llm.findings || []).filter((f) => f.item_id === itemId);
    const note = llmNote(mine, llm.chunks?.[task]);
    rows = rows.map((row) => {
      if (row.번호 !== number) return row;
      if (mine.length) {
        // 규칙이 판단불가로 둔 행의 비고(LLM 검토 전 등)는 LLM 결과로 바꾸고, 규칙이 부적합으로 본 행은 뒤에 덧붙인다
        const keep = row.검수결과 === "부적합" && row.비고;
        return { ...row, 검수결과: "부적합", 적합: false, 부적합: true, 비고: keep ? `${row.비고}\n${note}` : note, llm: true };
      }
      if (row.검수결과 === "판단불가" && llm.chunks?.[task] !== 0) {
        return { ...row, 검수결과: "적합", 적합: true, 부적합: false, 비고: note, llm: true };
      }
      return { ...row, 비고: row.비고 ? `${row.비고}\n${note}` : note, llm: true };
    });
    // 규칙이 'LLM 검토 전' 등으로 남긴 판단불가 지적은 LLM 결과로 바꾼다
    if (llm.chunks?.[task] !== 0) findings = findings.filter((f) => !(f.item_id === itemId && f.verdict === "판단불가"));
    findings = findings.concat(mine.map((f) => ({
      item_id: itemId,
      check: `LLM 검토 · ${f.근거_종류 || f.항목}`,
      region_path: [f.위치, f.블록_제목].filter(Boolean).join(" · "),
      verdict: "부적합",
      reason: `「${f.인용 || f["수정해야 하는 부분"]}」 — ${f.근거}`,
      suggestion: f["수정 방안"] || null,
    })));
  });
  const verdict = overallVerdict(rows.map((r) => r.검수결과));
  return { ...data, 검수확인서: rows, 지적사항: findings, 요약: { ...(data.요약 || {}), 검수결과: verdict || data.요약?.검수결과 } };
}

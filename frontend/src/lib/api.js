// 서버 호출을 한 곳에 모은다. 모든 함수는 { ok, status, data, error }를 돌려주고 예외를 던지지 않는다.
// error는 사용자에게 바로 보여 줄 문장: 서버가 준 error 메시지(+ 개발용 traceback) 또는 연결 실패 안내.

const CONNECT_FAILED = "서버에 연결하지 못했습니다";
const CONNECT_HINT = "(가상환경의 ncs-web 서버가 실행 중인지 확인)";

export async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (e) {
    if (e.name === "AbortError") return { ok: false, status: 0, data: null, error: "취소됨", aborted: true };
    return { ok: false, status: 0, data: null, error: `${CONNECT_FAILED}: ${e.message}\n${CONNECT_HINT}` };
  }
  if (response.status === 204) return { ok: true, status: 204, data: null, error: null };
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (response.ok) return { ok: true, status: response.status, data, error: null };
  const message = data?.error || `${response.status} ${response.statusText}`.trim();
  return { ok: false, status: response.status, data, error: message + (data?.traceback ? "\n\n" + data.traceback : "") };
}

function multipart(fields, files = []) {
  const form = new FormData();
  Object.entries(fields).forEach(([key, value]) => { if (value != null) form.append(key, value); });
  files.forEach((file) => form.append("files", file, file.name));
  return form;
}

// POST로 파일을 받아 브라우저 다운로드로 넘긴다. 실패하면 { ok:false, error } (성공은 { ok:true }).
export async function download(path, body, filename) {
  let response;
  try {
    const init = body instanceof FormData
      ? { method: "POST", body }
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
    response = await fetch(path, init);
  } catch (e) {
    return { ok: false, error: `${CONNECT_FAILED}: ${e.message}` };
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    return { ok: false, error: data?.error || `${response.status} ${response.statusText}` };
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  const summary = response.headers.get("x-memo-summary") || response.headers.get("x-upscale-summary");
  const check = response.headers.get("x-plan-check");   // 개발계획서 초안 — 함께 돌린 ①~⑩ 점검 요약(URL 인코딩 JSON)
  return { ok: true, summary: summary ? JSON.parse(summary) : null, check: check ? JSON.parse(decodeURIComponent(check)) : null };
}

export const api = {
  health: () => request("/api/health"),
  // 검수 1건: files로 직접 올리거나 upload(토큰)+group으로 올려 둔 파일을 쓴다
  // signal: AbortController.signal — 취소 버튼
  // stage: 개발계획서 점검(plan)만 — "final" 최종본(기본) / "draft" 직능연 1차본(기관 기재 칸은 해당 없음)
  review: ({ check, moduleCode, files = [], upload, group, stage, signal }) =>
    request("/api/review", { method: "POST", body: multipart({ check, module_code: moduleCode, upload, group, stage: check === "plan" ? stage : undefined }, files), signal }),
  uploads: {
    create: (files, signal) => request("/api/uploads", { method: "POST", body: multipart({}, files), signal }),
    remove: (token) => request(`/api/uploads/${token}`, { method: "DELETE" }),
  },
  reviews: {
    list: ({ standalone = true } = {}) => request(`/api/reviews${standalone ? "?standalone=true" : ""}`),
    get: (id) => request(`/api/reviews/${id}`),
    remove: (id) => request(`/api/reviews/${id}`, { method: "DELETE" }),
    zipUrl: (id) => `/api/reviews/${id}/zip`,
  },
  // F02 확인서 파일: rows = 여러 구성요소의 검수확인서 행을 이어 붙인 것
  exportSheet: ({ moduleCode, rows, createdAt, format }) =>
    download(`/api/export/sheet?format=${format}`, { module_code: moduleCode, rows, created_at: createdAt || null },
             `F02_검수확인서_${moduleCode || "모듈"}.${format}`),
  // 원고 hwpx에 지적사항을 한글 메모로 단 파일. upload = 원고가 들어 있는 업로드 토큰, rows = 체크리스트 행(적합 제외)
  // upload(방금 올린 원고 토큰) 또는 runId(이력 실행 id — 실행과 함께 보관된 원고) 중 하나
  exportAnnotated: ({ moduleCode, upload, runId, rows, createdAt }) =>
    download("/api/export/annotated", multipart({ upload: upload || "", run_id: runId || "", rows: JSON.stringify(rows), module_code: moduleCode, created_at: createdAt || "" }),
             `원고_검수메모_${moduleCode || "모듈"}.hwpx`),
  // 개발계획서 작성(REQ-02-001): 초안을 만들 수 있는 세분류와 초안 내려받기
  plan: {
    subclasses: () => request("/api/plan/subclasses"),
    draft: (body) => download("/api/plan/draft", body, `개발계획서_초안_${body.duty}.hwpx`),
  },
  // 그림 업스케일: 업로드 토큰의 원고 그림 목록 → 원본 보기 → 한 장씩 업스케일(20~40초) → 업스케일한 그림으로 제안본 hwpx
  pictures: {
    list: (token) => request(`/api/uploads/${token}/pictures`),
    originalUrl: (token, binId) => `/api/uploads/${token}/pictures/${encodeURIComponent(binId)}/original`,
    upscale: (token, binId) => request(`/api/uploads/${token}/pictures/${encodeURIComponent(binId)}/upscale`, { method: "POST" }),
    // v: 다시 업스케일했을 때 브라우저가 예전 그림을 쓰지 않게 붙이는 값
    upscaledUrl: (token, binId, v) => `/api/uploads/${token}/pictures/${encodeURIComponent(binId)}/upscaled?v=${v || 0}`,
    downloadUrl: (token, binId, name) => `/api/uploads/${token}/pictures/${encodeURIComponent(binId)}/upscaled?download=${encodeURIComponent(name)}`,
    proposal: (token, moduleCode, filename) =>
      download(`/api/uploads/${token}/proposal`, multipart({ module_code: moduleCode || "" }), filename),
  },
  groups: {
    list: () => request("/api/groups"),
    get: (id) => request(`/api/groups/${id}`),
    remove: (id) => request(`/api/groups/${id}`, { method: "DELETE" }),
  },
};

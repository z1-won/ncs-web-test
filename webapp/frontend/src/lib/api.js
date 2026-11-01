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
    response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
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
  return { ok: true };
}

export const api = {
  health: () => request("/api/health"),
  // 검수 1건: files로 직접 올리거나 upload(토큰)+group으로 올려 둔 파일을 쓴다
  // signal: AbortController.signal — 취소 버튼
  review: ({ check, moduleCode, files = [], upload, group, signal }) =>
    request("/api/review", { method: "POST", body: multipart({ check, module_code: moduleCode, upload, group }, files), signal }),
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
  groups: {
    list: () => request("/api/groups"),
    get: (id) => request(`/api/groups/${id}`),
    remove: (id) => request(`/api/groups/${id}`, { method: "DELETE" }),
  },
};

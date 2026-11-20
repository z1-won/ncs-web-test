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
    // 응답 머리는 왔는데 본문을 읽는 중에 취소되면(파일을 연달아 바꿀 때) 여기로 온다 — 빈 성공(ok, data=null)이 아니라 취소로 돌려준다
    if (options.signal?.aborted) return { ok: false, status: 0, data: null, error: "취소됨", aborted: true };
    data = null;
  }
  if (response.ok) return { ok: true, status: response.status, data, error: null };
  const message = data?.error || `${response.status} ${response.statusText}`.trim();
  return { ok: false, status: response.status, data, error: message + (data?.traceback ? "\n\n" + data.traceback : "") };
}

// roles: files와 같은 순서의 역할 배열(["manuscript", "plan", "print"]) — 업로드 칸이 정한 역할. 주면 서버가 내용 판별 대신 그대로 쓴다.
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
  saveBlob(await response.blob(), filename);
  const summary = response.headers.get("x-memo-summary") || response.headers.get("x-upscale-summary");
  return { ok: true, summary: summary ? JSON.parse(summary) : null };
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// 개발계획서 초안: 응답 본문 {filename, content(base64 hwpx), check(①~⑩ 점검 요약)} — 파일을 저장하고 요약을 돌려준다
async function planDraft(body) {
  const { ok, data, error } = await request("/api/plan/draft", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!ok) return { ok, error };
  const bytes = Uint8Array.from(atob(data.content), (c) => c.charCodeAt(0));
  saveBlob(new Blob([bytes], { type: "application/octet-stream" }), data.filename || `개발계획서_초안_${body.duty}.hwpx`);
  return { ok: true, check: data.check || null };
}

export const api = {
  health: () => request("/api/health"),
  // 검수 1건: files로 직접 올리거나 upload(토큰)+group으로 올려 둔 파일을 쓴다
  // signal: AbortController.signal — 취소 버튼
  // stage: 개발계획서 점검(plan)만 — "final" 최종본(기본) / "draft" 직능연 1차본(기관 기재 칸은 해당 없음)
  // imageDpi: 이미지 해상도 기준(150/300) — 기타(misc) 검수의 ⑤·⑧에만 쓰인다
  review: ({ check, moduleCode, files = [], roles, upload, group, stage, imageDpi, signal }) =>
    request("/api/review", { method: "POST", body: multipart({ check, module_code: moduleCode, upload, group, stage: check === "plan" ? stage : undefined,
                                                              roles: roles ? JSON.stringify(roles) : undefined,
                                                              image_dpi: check === "misc" && imageDpi ? String(imageDpi) : undefined }, files), signal }),
  uploads: {
    create: (files, signal, roles) => request("/api/uploads", { method: "POST", body: multipart({ roles: roles ? JSON.stringify(roles) : undefined }, files), signal }),
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
    draft: planDraft,
  },
  // 그림 업스케일: 업로드 토큰의 원고 그림 목록 → 원본 보기 → 한 장씩 업스케일(20~40초) → 업스케일한 그림으로 제안본 hwpx
  pictures: {
    // targetDpi: 해상도 기준(150/300). 이 값 미만인 그림만 목록에 나온다
    list: (token, targetDpi) => request(`/api/uploads/${token}/pictures${targetDpi ? `?target_dpi=${targetDpi}` : ""}`),
    originalUrl: (token, binId) => `/api/uploads/${token}/pictures/${encodeURIComponent(binId)}/original`,
    // engine: 모델 이름(목록 응답의 engines[].name). 비우면 서버 기본 모델
    upscale: (token, binId, targetDpi, engine) => {
      const query = new URLSearchParams();
      if (targetDpi) query.set("target_dpi", targetDpi);
      if (engine) query.set("engine", engine);
      const tail = query.toString();
      return request(`/api/uploads/${token}/pictures/${encodeURIComponent(binId)}/upscale${tail ? `?${tail}` : ""}`, { method: "POST" });
    },
    // v: 다시 업스케일했을 때 브라우저가 예전 그림을 쓰지 않게 붙이는 값
    // engine: 모델 이름을 주면 그 모델로 키운 결과(없으면 마지막에 돌린 결과 = 제안본에 들어갈 그림)
    upscaledUrl: (token, binId, v, engine) =>
      `/api/uploads/${token}/pictures/${encodeURIComponent(binId)}/upscaled?v=${v || 0}${engine ? `&engine=${encodeURIComponent(engine)}` : ""}`,
    downloadUrl: (token, binId, name, engine) =>
      `/api/uploads/${token}/pictures/${encodeURIComponent(binId)}/upscaled?download=${encodeURIComponent(name)}${engine ? `&engine=${encodeURIComponent(engine)}` : ""}`,
    // targetDpi: 이 기준으로 키운 그림만 제안본에 넣는다(화면의 '완료'와 같게)
    proposal: (token, moduleCode, filename, targetDpi) =>
      download(`/api/uploads/${token}/proposal`, multipart({ module_code: moduleCode || "", target_dpi: targetDpi ? String(targetDpi) : undefined }), filename),
  },
  // 원고 분량 산정(REQ-02-013): 최종 원고(+ 기존 원고)의 구성별 행·쪽 산정표
  volume: ({ file, previous, manualPages, includeAppendix = true, signal }) => {
    const form = new FormData();
    form.append("manuscript", file, file.name);
    if (previous) form.append("previous", previous, previous.name);
    if (manualPages) form.append("manual_pages", String(manualPages));
    form.append("include_appendix", includeAppendix ? "true" : "false");
    return request("/api/volume", { method: "POST", body: form, signal });
  },
  // 원고 문장 추천(REQ-02-004): 원고 → 구성별 정정 후보, 문장 하나 → 후보, 문장 종류 목록
  suggest: {
    kinds: () => request("/api/suggest/kinds"),
    manuscript: ({ file, useLlm = false, signal }) =>
      request("/api/suggest", { method: "POST", body: multipart({ use_llm: useLlm ? "true" : "false", manuscript: file }), signal }),
    sentence: ({ text, kind, useLlm = false }) =>
      request("/api/suggest/sentence", { method: "POST", body: multipart({ text, kind, use_llm: useLlm ? "true" : "false" }) }),
  },
  groups: {
    list: () => request("/api/groups"),
    get: (id) => request(`/api/groups/${id}`),
    remove: (id) => request(`/api/groups/${id}`, { method: "DELETE" }),
  },
  // 검토의견서 반영 여부 검토(REQ-02-003): opinions = [{ file, round: "1차"|"2차" }], 최종 원고 file(+ 출력본·반영 전 원고)
  opinion: ({ file, opinions, printCopy, previous, signal }) => {
    const form = new FormData();
    form.append("manuscript", file, file.name);
    opinions.forEach(({ file: sheet, round }) => { form.append("opinions", sheet, sheet.name); form.append("rounds", round || ""); });
    if (printCopy) form.append("print_pdf", printCopy, printCopy.name);
    if (previous) form.append("previous", previous, previous.name);
    return request("/api/opinion", { method: "POST", body: form, signal });
  },
};

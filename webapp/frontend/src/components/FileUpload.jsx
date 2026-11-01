// 파일 올리기 — KRDS 파일 업로드(krds-file-upload.line) 마크업: 끌어다 놓는 영역 + 파일 목록(역할 배지·삭제).
// 파일을 고르면 App이 바로 /api/uploads에 올려 역할(원고/개발계획서)을 판별하므로, 실행 전에 "개발계획서 없음"을 알 수 있다.
import React, { useRef, useState } from "react";

import { Spinner } from "./Badge.jsx";

const ACCEPT = [".hwp", ".hwpx"];

function sizeText(bytes) {
  return bytes >= 1 << 20 ? `${(bytes / (1 << 20)).toFixed(1)}MB` : `${Math.max(1, Math.round(bytes / 1024))}KB`;
}

// upload: { status: "idle"|"uploading"|"ready"|"error", roles?: {manuscript, plan}, error? }
export function FileUpload({ files, onChange, upload, disabled }) {
  const input = useRef(null);
  const [dragging, setDragging] = useState(false);

  function add(list) {
    const incoming = Array.from(list || []).filter((f) => ACCEPT.some((ext) => f.name.toLowerCase().endsWith(ext)));
    if (!incoming.length) return;
    // 같은 이름은 새 파일로 바꾼다(수정본을 다시 올리는 경우)
    const kept = files.filter((f) => !incoming.some((n) => n.name === f.name));
    onChange([...kept, ...incoming]);
  }
  function remove(name) { onChange(files.filter((f) => f.name !== name)); }
  function onDrop(event) {
    event.preventDefault();
    setDragging(false);
    if (!disabled) add(event.dataTransfer.files);
  }
  const roleOf = (name) => {
    if (upload?.status !== "ready") return null;
    if (upload.roles?.manuscript === name) return "원고";
    if (upload.roles?.plan === name) return "개발계획서";
    return "역할 미판별";
  };

  return (
    <div className="krds-file-upload line">
      <div className={`file-upload${dragging ? " is-dragging" : ""}`}
           onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
           onDragLeave={() => setDragging(false)} onDrop={onDrop}>
        <p className="txt">원고·개발계획서(.hwp/.hwpx)를 여기에 끌어다 놓거나, 파일 선택 버튼을 눌러 고르세요. 역할은 내용으로 판별합니다.</p>
        <div className="file-upload-btn-wrap">
          <input ref={input} id="files" type="file" multiple accept={ACCEPT.join(",")} className="sr-only" tabIndex={-1}
                 onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
          <button type="button" className="krds-btn medium" disabled={disabled} onClick={() => input.current?.click()}>
            <i className="svg-icon ico-upload" aria-hidden="true"></i>파일 선택
          </button>
        </div>
      </div>
      {files.length > 0 && (
        <div className="file-list">
          <div className="total">
            <span className="current">{files.length}개</span>
            {upload?.status === "ready" && (
              <span className="roles">
                {" · "}원고 {upload.roles?.manuscript ? "있음" : <strong className="missing">없음</strong>}
                {" · "}개발계획서 {upload.roles?.plan ? "있음" : <span className="missing">없음</span>}
              </span>
            )}
          </div>
          <ul className="upload-list">
            {files.map((file) => {
              const role = roleOf(file.name);
              const unknown = role === "역할 미판별";
              return (
                <li key={file.name} className={unknown ? "is-error" : undefined}>
                  <div className="file-info">
                    <div className="file-name">
                      {role && <span className={`krds-badge ${unknown ? "bg-light-warning" : role === "원고" ? "bg-light-primary" : "bg-light-secondary"}`}>{role}</span>}
                      {" "}{file.name} <span className="meta">[{file.name.split(".").pop()}, {sizeText(file.size)}]</span>
                    </div>
                    <div className="btn-wrap">
                      {upload?.status === "uploading"
                        ? <Spinner label="확인 중" />
                        : <button type="button" className="krds-btn medium text" disabled={disabled} onClick={() => remove(file.name)}>
                            삭제 <i className="svg-icon ico-delete-fill" aria-hidden="true"></i>
                          </button>}
                    </div>
                  </div>
                  {unknown && <p className="file-hint-invalid">원고도 개발계획서도 아닌 것으로 보입니다 — 첫 쪽에 '개발계획서' 또는 '차례'가 있는지 확인</p>}
                </li>
              );
            })}
          </ul>
          {upload?.status === "error" && <p className="file-hint-invalid" role="alert" style={{ whiteSpace: "pre-wrap" }}>{upload.error}</p>}
        </div>
      )}
    </div>
  );
}

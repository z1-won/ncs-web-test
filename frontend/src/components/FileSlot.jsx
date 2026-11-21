// 업로드 칸 하나 — 원고 / 개발계획서 / 출력본 PDF를 따로 고른다(#13). 한 칸에 파일 하나.
// KRDS 파일 업로드(.krds-file-upload)의 파일 목록 규격을 그대로 쓴다: .file-list › ul.upload-list › li(.is-error) › .file-info(.file-name + .btn-wrap) + p.file-hint-invalid,
// 상태는 업로드 중 스피너(.krds-spinner) → 완료 아이콘(.ico-invalid.complete), 삭제는 .krds-btn.medium.text + ico-delete-fill.
// 끌어다 놓기: KRDS의 큰 영역(.file-upload)은 세 칸을 한 줄에 두기엔 커서 두지 않고, 칸 자체(.form-group)가 놓는 자리다.
// 파일을 칸 위로 끌어오면 칸이 강조되고 버튼 글이 '여기에 놓기'로 바뀐다. 놓은 파일은 버튼으로 고른 것과 같은 길(onChange)로 간다.
// 버튼의 accept는 놓은 파일을 막지 못하므로 확장자·종류를 여기서 다시 보고, 맞지 않으면 칸에 이유를 적는다(useFileDrop).
// 숨긴 <input type=file>을 진짜 <button>이 대신 열어 키보드(Enter/Space)로도 동작한다. 삭제는 그 칸만 비운다(개발계획서는 두고 원고만 바꿔 올릴 수 있다).
import React, { useEffect, useRef, useState } from "react";

// accept(".hwp,.hwpx", ".json,image/*")에 맞는 파일인가. 확장자는 이름 끝으로, 'image/*'·'application/pdf' 꼴은 파일 종류로 본다
function accepts(file, accept) {
  if (!accept) return true;
  const name = file.name.toLowerCase();
  const type = (file.type || "").toLowerCase();
  return accept.split(",").map((rule) => rule.trim().toLowerCase()).filter(Boolean)
    .some((rule) => (rule.startsWith(".") ? name.endsWith(rule) : rule.endsWith("/*") ? type.startsWith(rule.slice(0, -1)) : type === rule));
}

// accept → 안내에 쓸 이름: ".hwp,.hwpx" → "hwp, hwpx", "image/*" → "그림"
function acceptNames(accept) {
  return (accept || "").split(",").map((rule) => rule.trim()).filter(Boolean)
    .map((rule) => (rule.startsWith(".") ? rule.slice(1) : rule === "image/*" ? "그림" : rule)).join(", ");
}

const hasFiles = (event) => [...(event.dataTransfer?.types || [])].includes("Files");

// 칸 밖에 파일을 놓으면 브라우저가 그 파일을 열어 화면을 떠난다(입력한 값이 사라진다). 업로드 칸이 있는 화면에서는 막는다
function useBlockStrayDrop() {
  useEffect(() => {
    const block = (event) => { if (hasFiles(event)) event.preventDefault(); };
    window.addEventListener("dragover", block);
    window.addEventListener("drop", block);
    return () => { window.removeEventListener("dragover", block); window.removeEventListener("drop", block); };
  }, []);
}

// 칸에 파일 끌어다 놓기. onFiles(맞는 파일들)를 부르고, 맞지 않는 파일은 error에 이유를 적는다. multiple이 아니면 파일 하나만 받는다.
// 돌려주는 over = 지금 파일이 칸 위에 있는가, handlers = 칸(.form-group)에 붙일 이벤트, clearError = 버튼으로 고르거나 지웠을 때 오류 지우기
function useFileDrop({ accept, disabled, multiple, onFiles }) {
  const [over, setOver] = useState(false);
  const [error, setError] = useState(null);
  const depth = useRef(0);   // 칸 안의 자식 요소를 지날 때마다 enter/leave가 번갈아 나므로 깊이를 센다
  useBlockStrayDrop();
  const handlers = {
    onDragEnter(event) {
      if (!hasFiles(event)) return;
      event.preventDefault();
      depth.current += 1;
      if (!disabled) setOver(true);
    },
    onDragOver(event) {
      if (!hasFiles(event)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = disabled ? "none" : "copy";
    },
    onDragLeave(event) {
      if (!hasFiles(event)) return;
      depth.current = Math.max(0, depth.current - 1);
      if (depth.current === 0) setOver(false);
    },
    onDrop(event) {
      if (!hasFiles(event)) return;
      event.preventDefault();
      event.stopPropagation();
      depth.current = 0;
      setOver(false);
      if (disabled) return;
      const dropped = [...event.dataTransfer.files];
      const good = dropped.filter((file) => accepts(file, accept));
      const bad = dropped.filter((file) => !accepts(file, accept));
      if (!multiple && dropped.length > 1) {
        setError(`이 칸에는 파일을 하나만 올릴 수 있습니다. 파일 ${dropped.length}개를 놓았습니다. 하나만 다시 놓아 주세요.`);
        return;
      }
      setError(bad.length ? `이 칸에는 ${acceptNames(accept)} 파일만 올릴 수 있습니다. 올리지 않은 파일: ${bad.map((file) => file.name).join(", ")}` : null);
      if (good.length) onFiles(good);
    },
  };
  return { over, error, handlers, clearError: () => setError(null) };
}

function describe(file) {   // KRDS 예제의 파일명 표기: 이름 [확장자, 크기]
  const ext = file.name.includes(".") ? file.name.split(".").pop().toLowerCase() : "";
  const size = file.size >= 1 << 20 ? `${(file.size / (1 << 20)).toFixed(1)}MB` : `${Math.max(1, Math.round(file.size / 1024))}KB`;
  return `${file.name} [${[ext, size].filter(Boolean).join(", ")}]`;
}

// file: 고른 File 또는 null. uploading: 서버가 역할을 확인하는 중. invalid: 이 칸의 오류 문구. hint: 파일이 없을 때의 안내 한 줄.
// 도움말은 칸마다 한 줄만 둔다 — 파일이 없으면 오류 또는 안내, 파일이 있으면 그 파일 행 안의 오류(file-hint-invalid)뿐.
export function FileSlot({ id, label, required, accept, file, onChange, disabled, uploading, invalid, hint }) {
  const input = useRef(null);
  const drop = useFileDrop({ accept, disabled, multiple: false, onFiles: ([dropped]) => onChange(dropped) });
  function clear() {
    if (input.current) input.current.value = "";   // 같은 파일을 다시 골라도 change가 나도록
    drop.clearError();
    onChange(null);
  }
  return (
    <div className={`form-group file-drop${drop.over ? " is-dragover" : ""}`} {...drop.handlers}>
      <div className="form-tit">
        <label htmlFor={id}>
          {label}
          {required
            ? <span className="required"> <i aria-hidden="true">*</i><span className="sr-only">필수</span></span>
            : " (선택)"}
        </label>
      </div>
      <div className="form-conts">
        <div className="krds-file-upload file-slot">
          <div className="file-upload-btn-wrap">
            <input ref={input} id={id} type="file" accept={accept} className="sr-only" tabIndex={-1} aria-describedby={`${id}-hint`}
                   aria-invalid={invalid ? "true" : undefined} aria-required={required ? "true" : undefined}
                   onChange={(e) => { drop.clearError(); onChange(e.target.files?.[0] || null); }} />
            {/* 셀렉트·입력칸과 같은 large 높이로 칸의 규격을 맞춘다 */}
            <button type="button" className="krds-btn large tertiary" disabled={disabled} onClick={() => input.current?.click()}>
              <i className="svg-icon ico-upload" aria-hidden="true"></i>{drop.over ? "여기에 놓기" : file ? "파일 바꾸기" : "파일 선택"}<span className="sr-only">: {label}</span>
            </button>
            {!file && <p className="file-drop-cue">또는 파일을 이 칸에 끌어다 놓으세요.</p>}
          </div>
          {file && (
            <div className="file-list">
              <ul className="upload-list">
                <li className={invalid ? "is-error" : undefined}>
                  <div className="file-info">
                    <div className="file-name" title={file.name}>{describe(file)}</div>
                    <div className="btn-wrap">
                      {uploading
                        ? <span className="krds-spinner" role="status"><span className="sr-only">확인 중</span></span>
                        : !invalid && <span className="ico-invalid complete"><em className="sr-only">확인 완료</em></span>}
                      <button type="button" className="krds-btn medium text" disabled={disabled} onClick={clear}>
                        삭제<span className="sr-only">: {label}</span> <i className="svg-icon ico-delete-fill" aria-hidden="true"></i>
                      </button>
                    </div>
                  </div>
                  {invalid && <p className="file-hint-invalid" id={`${id}-hint`} role="alert" style={{ whiteSpace: "pre-wrap" }}>{invalid}</p>}
                </li>
              </ul>
            </div>
          )}
        </div>
      </div>
      {drop.error && <p className="form-hint-invalid" id={`${id}-drop-error`} role="alert">{drop.error}</p>}
      {!file && !drop.error && (invalid
        ? <p className="form-hint-invalid" id={`${id}-hint`} role="alert">{invalid}</p>
        : <p className="form-hint" id={`${id}-hint`}>{hint || "선택된 파일 없음"}</p>)}
    </div>
  );
}

// 업로드 칸 하나에 파일 여러 개 — KRDS 파일 업로드의 목록 규격(.file-list › .total + ul.upload-list)을 그대로 쓴다.
// files: 고른 File 배열. 다시 고르면 목록에 더해지고(이름·크기가 같은 파일은 한 번만), 파일마다 삭제하거나 한꺼번에 비울 수 있다.
// countNote: 개수 옆에 붙일 글(예: "JSON 1개, 그림 3개"). invalid: 이 칸의 오류 문구.
export function MultiFileSlot({ id, label, required, accept, files, onChange, disabled, hint, countNote, invalid, wide }) {
  const input = useRef(null);
  function add(picked) {
    const known = new Set(files.map((file) => `${file.name}\n${file.size}`));
    onChange([...files, ...picked.filter((file) => !known.has(`${file.name}\n${file.size}`))]);
    if (input.current) input.current.value = "";   // 같은 파일을 다시 골라도 change가 나도록
  }
  const drop = useFileDrop({ accept, disabled, multiple: true, onFiles: add });
  return (
    <div className={`form-group file-drop${wide ? " form-group-wide" : ""}${drop.over ? " is-dragover" : ""}`} {...drop.handlers}>
      <div className="form-tit">
        <label htmlFor={id}>
          {label}
          {required
            ? <span className="required"> <i aria-hidden="true">*</i><span className="sr-only">필수</span></span>
            : " (선택)"}
        </label>
      </div>
      <div className="form-conts">
        <div className="krds-file-upload file-slot multi">
          <div className="file-upload-btn-wrap">
            <input ref={input} id={id} type="file" multiple accept={accept} className="sr-only" tabIndex={-1} aria-describedby={`${id}-hint`}
                   aria-invalid={invalid ? "true" : undefined} aria-required={required ? "true" : undefined}
                   onChange={(e) => { drop.clearError(); add([...(e.target.files || [])]); }} />
            <button type="button" className="krds-btn large tertiary" disabled={disabled} onClick={() => input.current?.click()}>
              <i className="svg-icon ico-upload" aria-hidden="true"></i>{drop.over ? "여기에 놓기" : files.length ? "파일 더 고르기" : "파일 선택"}<span className="sr-only">: {label}</span>
            </button>
            {files.length === 0 && <p className="file-drop-cue">또는 파일을 이 칸에 끌어다 놓으세요. 여러 개를 한 번에 놓아도 됩니다.</p>}
          </div>
          {files.length > 0 && (
            <div className="file-list">
              <div className="total">
                <span><span className="current">{files.length}개</span>{countNote ? ` (${countNote})` : ""}</span>
                <button type="button" className="krds-btn small text" disabled={disabled} onClick={() => onChange([])}>모두 삭제<span className="sr-only">: {label}</span></button>
              </div>
              <ul className="upload-list">
                {files.map((file, index) => (
                  <li key={`${file.name}-${file.size}`}>
                    <div className="file-info">
                      <div className="file-name" title={file.name}>{describe(file)}</div>
                      <div className="btn-wrap">
                        <button type="button" className="krds-btn medium text" disabled={disabled} onClick={() => onChange(files.filter((_, i) => i !== index))}>
                          삭제<span className="sr-only">: {file.name}</span> <i className="svg-icon ico-delete-fill" aria-hidden="true"></i>
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
      {drop.error && <p className="form-hint-invalid" id={`${id}-drop-error`} role="alert">{drop.error}</p>}
      {invalid
        ? <p className="form-hint-invalid" id={`${id}-hint`} role="alert">{invalid}</p>
        : <p className="form-hint" id={`${id}-hint`}>{hint}</p>}
    </div>
  );
}

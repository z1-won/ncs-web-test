// 업로드 칸 하나 — 원고 / 개발계획서 / 출력본 PDF를 따로 고른다(#13). 한 칸에 파일 하나.
// KRDS 파일 업로드(.krds-file-upload) 구조를 따른다: 레이블 → 놓는 자리(.file-upload: 안내 글 + 파일 선택 버튼) → 파일 목록(.file-list › ul.upload-list › li(.is-error)
// › .file-info(.file-name + .btn-wrap) + p.file-hint-invalid) → 도움말. 상태는 업로드 중 스피너(.krds-spinner) → 완료 아이콘(.ico-invalid.complete), 삭제는 .krds-btn.medium.text + ico-delete-fill.
// KRDS 가이드(컴포넌트 › 파일 업로드)에서 지키는 것:
// - 끌어다 놓기는 파일 선택 버튼과 함께 둔다. 버튼은 small(40px) — 칸이 여럿 나란히 놓여 medium(48px)은 실행 버튼만큼 눈에 띄었다. 누르는 대상이라 더 줄이지는 않는다. 놓는 자리는 평소에도 보이고(회색 면), 파일을 화면으로 끌어오면 모든 칸의 자리에 점선이, 그 칸 위에 오면 강조색이 든다
// - 파일을 올린 뒤에도 버튼과 놓는 자리는 그대로 둔다(글도 '파일 선택' 하나). 한 칸짜리는 다시 고르면 바뀐다
// - 형식 제한은 도움말에 적는다(페이지가 hint를 주지 않으면 accept에서 만든다)
// - 오류는 무엇이 왜 안 되는지 적는다: 형식이 다름, 빈 파일, 개수 초과. 버튼으로 골라도 끌어다 놓아도 같은 검사를 거친다(버튼의 accept는 '모든 파일'로 바꿔 고르면 막지 못한다)
// - 파일 이름은 한 줄, 길면 말줄임(전체 이름은 title). [확장자, 크기]는 잘리지 않게 따로 둔다. 삭제 버튼은 aria-describedby로 파일 이름과 잇는다
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

// 페이지가 도움말을 주지 않았을 때 칸 아래에 적는 형식 안내
function formatNote(accept, multiple) {
  const names = acceptNames(accept);
  return `${names ? `${names} 파일을` : "파일을"} ${multiple ? "여러 개" : "하나"} 올릴 수 있습니다.`;
}

const hasFiles = (event) => [...(event.dataTransfer?.types || [])].includes("Files");
const fileNames = (files) => files.map((file) => file.name).join(", ");

// 지금 파일을 화면 위로 끌고 있는가 — 끄는 동안 모든 칸의 놓는 자리를 드러내는 데 쓴다.
// 칸 밖에 놓으면 브라우저가 그 파일을 열어 화면을 떠나므로(입력한 값이 사라진다) 그것도 여기서 막는다
function useFileDragging() {
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    const enter = (event) => { if (hasFiles(event)) setDragging(true); };
    const over = (event) => { if (hasFiles(event)) { event.preventDefault(); setDragging(true); } };
    const leave = (event) => {   // 창 밖으로 나갈 때만 끈다(요소 사이를 지날 때는 relatedTarget이 있거나 좌표가 창 안이다)
      const outside = event.clientX <= 0 || event.clientY <= 0 || event.clientX >= window.innerWidth || event.clientY >= window.innerHeight;
      if (!event.relatedTarget && outside) setDragging(false);
    };
    const drop = (event) => { if (hasFiles(event)) event.preventDefault(); setDragging(false); };
    const end = () => setDragging(false);
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragover", over);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    window.addEventListener("dragend", end);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragover", over);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
      window.removeEventListener("dragend", end);
    };
  }, []);
  useEffect(() => {   // 끄는 동안에는 mousemove가 오지 않는다. 왔다면 끌기가 끝난 것이니, 끝 이벤트를 놓쳤어도 여기서 끈다
    if (!dragging) return undefined;
    const stop = () => setDragging(false);
    window.addEventListener("mousemove", stop);
    return () => window.removeEventListener("mousemove", stop);
  }, [dragging]);
  return dragging;
}

// 칸이 파일을 받는 길 하나 — 버튼으로 고른 것도, 끌어다 놓은 것도 take()를 거친다. 맞는 파일만 onFiles로 넘기고, 받지 않은 파일은 error에 이유와 이름을 적는다.
// 돌려주는 dragging = 화면 어딘가에서 파일을 끌고 있는가, over = 그 파일이 이 칸 위에 있는가, handlers = 칸(.form-group)에 붙일 이벤트
function useFileIntake({ accept, disabled, multiple, onFiles }) {
  const [over, setOver] = useState(false);
  const [error, setError] = useState(null);
  const depth = useRef(0);   // 칸 안의 자식 요소를 지날 때마다 enter/leave가 번갈아 나므로 깊이를 센다
  const dragging = useFileDragging();

  function take(list) {
    if (!list.length) return;   // 파일 창을 취소한 것 — 이미 고른 파일을 그대로 둔다
    if (!multiple && list.length > 1) {
      setError(`이 칸에는 파일을 하나만 올릴 수 있습니다. 파일 ${list.length}개를 놓았습니다. 하나만 다시 올려 주세요.`);
      return;
    }
    const wrong = list.filter((file) => !accepts(file, accept));
    const empty = list.filter((file) => accepts(file, accept) && file.size === 0);
    const good = list.filter((file) => accepts(file, accept) && file.size > 0);
    const reasons = [];
    if (wrong.length) reasons.push(`이 칸에는 ${acceptNames(accept)} 파일만 올릴 수 있습니다. 형식이 달라 올리지 않은 파일: ${fileNames(wrong)}`);
    if (empty.length) reasons.push(`내용이 없는 빈 파일은 올릴 수 없습니다. 올리지 않은 파일: ${fileNames(empty)}`);
    setError(reasons.join("\n") || null);
    if (good.length) onFiles(good);
  }

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
      depth.current = 0;
      setOver(false);
      if (!disabled) take([...event.dataTransfer.files]);
    },
  };
  return { dragging: dragging && !disabled, over, error, handlers, take, clearError: () => setError(null) };
}

function fileInfo(file) {   // KRDS 첨부파일 표기: 이름 [확장자, 크기]
  const ext = file.name.includes(".") ? file.name.split(".").pop().toLowerCase() : "";
  const size = file.size >= 1 << 20 ? `${(file.size / (1 << 20)).toFixed(1)}MB` : `${Math.max(1, Math.round(file.size / 1024))}KB`;
  return `[${[ext, size].filter(Boolean).join(", ")}]`;
}

// 파일 이름 한 줄(길면 말줄임) + [확장자, 크기]. nameId는 삭제 버튼이 aria-describedby로 가리킨다
function FileName({ file, nameId }) {
  return (
    <div className="file-name" id={nameId} title={file.name}>
      <span className="name">{file.name}</span> <span className="info">{fileInfo(file)}</span>
    </div>
  );
}

// 놓는 자리 — 안내 글 + 파일 선택 버튼. 파일을 올린 뒤에도 같은 모습으로 남는다
function DropArea({ id, label, accept, multiple, required, disabled, invalid, describedBy, intake, input }) {
  return (
    <div className={`file-upload${intake.dragging ? " active" : ""}${intake.over ? " is-over" : ""}`}>
      {/* 글은 한 칸짜리와 여러 개짜리가 같다 — 글 길이가 다르면 나란한 칸의 놓는 자리 높이가 달라진다. '여러 개'는 칸 아래 도움말이 알린다 */}
      <p className="txt">파일을 여기에 끌어다 놓거나 선택해 주세요.</p>
      <div className="file-upload-btn-wrap">
        <input ref={input} id={id} type="file" multiple={multiple} accept={accept} className="sr-only" tabIndex={-1} aria-describedby={describedBy}
               aria-invalid={invalid ? "true" : undefined} aria-required={required ? "true" : undefined}
               onChange={(event) => {
                 const picked = [...(event.target.files || [])];
                 event.target.value = "";   // 같은 파일을 다시 골라도 change가 나도록
                 intake.take(picked);
               }} />
        <button type="button" className="krds-btn small tertiary" disabled={disabled} aria-describedby={describedBy} onClick={() => input.current?.click()}>
          <i className="svg-icon ico-upload" aria-hidden="true"></i>파일 선택<span className="sr-only">: {label}</span>
        </button>
      </div>
    </div>
  );
}

function SlotLabel({ id, label, required }) {
  return (
    <div className="form-tit">
      <label htmlFor={id}>
        {label}
        {required
          ? <span className="required"> <i aria-hidden="true">*</i><span className="sr-only">필수</span></span>
          : " (선택)"}
      </label>
    </div>
  );
}

// file: 고른 File 또는 null. uploading: 서버가 역할을 확인하는 중. invalid: 이 칸의 오류 문구. hint: 파일이 없을 때의 안내 한 줄(없으면 형식 안내).
// 칸 아래 글은 한 줄만 둔다 — 받지 않은 파일의 이유, 없으면 (파일이 없을 때) 오류 또는 안내. 올린 파일의 오류는 그 파일 행 안(file-hint-invalid)에 적는다.
export function FileSlot({ id, label, required, accept, file, onChange, disabled, uploading, invalid, hint }) {
  const input = useRef(null);
  const intake = useFileIntake({ accept, disabled, multiple: false, onFiles: ([picked]) => onChange(picked) });
  function clear() {
    intake.clearError();
    onChange(null);
  }
  const below = intake.error || (!file && invalid) || null;   // 칸 아래에 적을 오류
  return (
    <div className={`form-group file-drop${intake.over ? " is-dragover" : ""}`} {...intake.handlers}>
      <SlotLabel id={id} label={label} required={required} />
      <div className="form-conts">
        <div className="krds-file-upload file-slot">
          <DropArea id={id} label={label} accept={accept} multiple={false} required={required} disabled={disabled} invalid={invalid || intake.error}
                    describedBy={`${id}-hint`} intake={intake} input={input} />
          {file && (
            <div className="file-list">
              <ul className="upload-list">
                <li className={invalid ? "is-error" : undefined}>
                  <div className="file-info">
                    <FileName file={file} nameId={`${id}-name`} />
                    <div className="btn-wrap">
                      {uploading
                        ? <span className="krds-spinner" role="status"><span className="sr-only">확인 중</span></span>
                        : !invalid && <span className="ico-invalid complete"><em className="sr-only">확인 완료</em></span>}
                      <button type="button" className="krds-btn medium text" disabled={disabled} aria-describedby={`${id}-name`} onClick={clear}>
                        삭제<span className="sr-only">: {label}</span> <i className="svg-icon ico-delete-fill" aria-hidden="true"></i>
                      </button>
                    </div>
                  </div>
                  {invalid && <p className="file-hint-invalid" role="alert" style={{ whiteSpace: "pre-wrap" }}>{invalid}</p>}
                </li>
              </ul>
            </div>
          )}
        </div>
      </div>
      {below
        ? <p className="form-hint-invalid" id={`${id}-hint`} role="alert" style={{ whiteSpace: "pre-line" }}>{below}</p>
        : !file && <p className="form-hint" id={`${id}-hint`}>{hint || formatNote(accept, false)}</p>}
    </div>
  );
}

// 업로드 칸 하나에 파일 여러 개 — KRDS 파일 업로드의 목록 규격(.file-list › .total + ul.upload-list)을 그대로 쓴다.
// files: 고른 File 배열. 다시 고르면 목록에 더해지고(이름·크기가 같은 파일은 한 번만), 파일마다 삭제하거나 한꺼번에 비울 수 있다.
// countNote: 개수 옆에 붙일 글(예: "JSON 1개, 그림 3개"). invalid: 이 칸의 오류 문구. hint: 안내 한 줄(없으면 형식 안내).
export function MultiFileSlot({ id, label, required, accept, files, onChange, disabled, hint, countNote, invalid, wide }) {
  const input = useRef(null);
  function add(picked) {
    const known = new Set(files.map((file) => `${file.name}\n${file.size}`));
    onChange([...files, ...picked.filter((file) => !known.has(`${file.name}\n${file.size}`))]);
  }
  const intake = useFileIntake({ accept, disabled, multiple: true, onFiles: add });
  const below = intake.error || invalid || null;
  return (
    <div className={`form-group file-drop${wide ? " form-group-wide" : ""}${intake.over ? " is-dragover" : ""}`} {...intake.handlers}>
      <SlotLabel id={id} label={label} required={required} />
      <div className="form-conts">
        <div className="krds-file-upload file-slot multi">
          <DropArea id={id} label={label} accept={accept} multiple required={required} disabled={disabled} invalid={below}
                    describedBy={`${id}-hint`} intake={intake} input={input} />
          {files.length > 0 && (
            <div className="file-list">
              <div className="total">
                <span><span className="current">{files.length}개</span>{countNote ? ` (${countNote})` : ""}</span>
                <button type="button" className="krds-btn small text" disabled={disabled} onClick={() => { intake.clearError(); onChange([]); }}>모두 삭제<span className="sr-only">: {label}</span></button>
              </div>
              <ul className="upload-list">
                {files.map((file, index) => (
                  <li key={`${file.name}-${file.size}`}>
                    <div className="file-info">
                      <FileName file={file} nameId={`${id}-name-${index}`} />
                      <div className="btn-wrap">
                        <button type="button" className="krds-btn medium text" disabled={disabled} aria-describedby={`${id}-name-${index}`}
                                onClick={() => onChange(files.filter((_, i) => i !== index))}>
                          삭제 <i className="svg-icon ico-delete-fill" aria-hidden="true"></i>
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
      {below
        ? <p className="form-hint-invalid" id={`${id}-hint`} role="alert" style={{ whiteSpace: "pre-line" }}>{below}</p>
        : <p className="form-hint" id={`${id}-hint`}>{hint || formatNote(accept, true)}</p>}
    </div>
  );
}

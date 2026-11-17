import React, { useEffect, useMemo, useRef, useState } from "react";

// KRDS 날짜 입력 + 달력. 브라우저 기본 날짜 칸(<input type="date">)은 달력 모양이 브라우저마다 다르고 바꿀 수 없어서,
// 입력칸은 KRDS 날짜 입력(calendar-conts › calendar-input), 달력은 KRDS 달력(krds-calendar-area › calendar-wrap)으로 그린다.
// 값(value)은 'YYYY-MM-DD' 또는 빈 글. 칸에는 KRDS 표기 'YYYY.MM.DD'로 보이고, 손으로 적을 때는 20261001 · 2026.10.1 · 2026-10-01 모두 받는다.
// 동작은 KRDS 달력 가이드대로: 달력 버튼(클릭·Enter·Space)으로 열고, 날짜를 고른 뒤 [확인]을 눌러야 값이 바뀐다. [취소]·Esc·바깥 클릭은 그대로 닫는다.
// 달력 안에서는 ←→↑↓로 하루·한 주, PageUp·PageDown으로 한 달, Home·End로 그 주의 처음·끝으로 옮긴다. Tab은 달력 안에서 돈다.
const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];
const WEEKDAY_NAMES = ["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"];
const pad = (n) => String(n).padStart(2, "0");
const iso = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
const shown = (value) => (value ? value.replaceAll("-", ".") : "");

function fromIso(value) {
  const found = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
  return found ? new Date(Number(found[1]), Number(found[2]) - 1, Number(found[3])) : null;
}

// 손으로 적은 글 → 'YYYY-MM-DD' | ""(비움) | null(날짜가 아님)
export function parseDateText(text) {
  const clean = (text || "").trim();
  if (!clean) return "";
  const found = /^(\d{4})[.\-/\s]*(\d{1,2})[.\-/\s]*(\d{1,2})\.?$/.exec(clean);
  if (!found) return null;
  const [year, month, day] = [Number(found[1]), Number(found[2]), Number(found[3])];
  const date = new Date(year, month - 1, day);
  if (year < 1900 || date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;   // 2월 30일 같은 없는 날
  return iso(date);
}

// 그 달이 걸친 주들(일요일 시작) — 첫 주와 끝 주의 빈칸은 앞뒤 달의 날짜로 채운다(KRDS대로 흐리게 보이고 고를 수 없다)
function weeksOf(year, month) {
  const first = new Date(year, month, 1);
  const start = new Date(year, month, 1 - first.getDay());
  const weeks = Math.ceil((first.getDay() + new Date(year, month + 1, 0).getDate()) / 7);
  return Array.from({ length: weeks }, (_, week) => Array.from({ length: 7 }, (_, day) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + week * 7 + day)));
}

export function KrdsDateField({ id, label, value, onChange, hint, disabled }) {
  const [text, setText] = useState(shown(value));
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [above, setAbove] = useState(false);          // 아래 자리가 모자라면 입력칸 위로 연다
  const [view, setView] = useState(() => new Date());  // 달력에 보이는 달
  const [picked, setPicked] = useState(null);          // 달력에서 고른 날([확인] 전)
  const [focused, setFocused] = useState(null);        // 방향키로 옮겨 다니는 날
  const [drop, setDrop] = useState(null);              // 열린 선택 목록: "year" | "month" | null
  const wrap = useRef(null);
  const button = useRef(null);
  const calendar = useRef(null);
  const today = useMemo(() => iso(new Date()), []);

  useEffect(() => { setText(shown(value)); setError(""); }, [value]);

  useEffect(() => {
    if (!open) return undefined;
    function onDocumentDown(event) { if (!wrap.current?.contains(event.target)) setOpen(false); }
    document.addEventListener("mousedown", onDocumentDown);
    return () => document.removeEventListener("mousedown", onDocumentDown);
  }, [open]);

  // 열리거나 방향키로 옮기면 그 날짜 버튼에 초점을 둔다
  useEffect(() => {
    if (open && focused && !drop) calendar.current?.querySelector(`[data-date="${focused}"]`)?.focus();
  }, [open, focused, drop, view]);

  // 연도·월 목록을 열면 지금 값이 보이게 한다
  useEffect(() => {
    if (drop) calendar.current?.querySelector(".calendar-select.active .active")?.scrollIntoView({ block: "center" });
  }, [drop]);

  function openCalendar() {
    const start = fromIso(parseDateText(text) || value) || new Date();
    setPicked(parseDateText(text) || value || null);
    setView(new Date(start.getFullYear(), start.getMonth(), 1));
    setFocused(iso(start));
    setDrop(null);
    const box = wrap.current?.getBoundingClientRect();
    setAbove(!!box && window.innerHeight - box.bottom < 480 && box.top > 480);
    setOpen(true);
  }

  function close() {
    setOpen(false);
    button.current?.focus();
  }

  function commit(next) {
    setError("");
    setText(shown(next));
    if (next !== (value || "")) onChange(next);
  }

  function onBlur() {
    const parsed = parseDateText(text);
    if (parsed === null) { setError("YYYY.MM.DD로 적어 주세요(예: 2026.10.01)."); return; }
    commit(parsed);
  }

  function move(date) {
    setFocused(iso(date));
    setView(new Date(date.getFullYear(), date.getMonth(), 1));
  }

  function onCalendarKey(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      if (drop) setDrop(null); else close();
      return;
    }
    if (event.key === "Tab") {      // 달력 안에서만 돈다
      const items = [...calendar.current.querySelectorAll("button:not([disabled])")].filter((item) => item.offsetParent !== null && item.tabIndex !== -1);
      const [first, last] = [items[0], items[items.length - 1]];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      return;
    }
    const current = fromIso(event.target.dataset?.date);
    if (!current) return;
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -current.getDay(), End: 6 - current.getDay() }[event.key];
    if (step !== undefined) {
      event.preventDefault();
      move(new Date(current.getFullYear(), current.getMonth(), current.getDate() + step));
    } else if (event.key === "PageUp" || event.key === "PageDown") {
      event.preventDefault();
      const month = current.getMonth() + (event.key === "PageDown" ? 1 : -1);
      const last = new Date(current.getFullYear(), month + 1, 0).getDate();
      move(new Date(current.getFullYear(), month, Math.min(current.getDate(), last)));
    }
  }

  const year = view.getFullYear();
  const month = view.getMonth();
  const years = Array.from({ length: 21 }, (_, i) => new Date().getFullYear() - 15 + i);
  const shift = (months) => { setView(new Date(year, month + months, 1)); setFocused(null); };
  const hintId = `${id}-hint`;
  return (
    <div className="form-group">
      <div className="form-tit"><label htmlFor={id}>{label}</label></div>
      <div className="form-conts calendar-conts krds-date-field" ref={wrap}>
        <div className="calendar-input">
          <input id={id} type="text" inputMode="numeric" autoComplete="off" className={`krds-input datepicker cal${error ? " is-error" : ""}`} placeholder="YYYY.MM.DD"
                 maxLength={12} value={text} disabled={disabled} aria-invalid={error ? "true" : undefined} aria-describedby={hintId}
                 onChange={(e) => { setText(e.target.value); setError(""); }} onBlur={onBlur}
                 onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); onBlur(); } }} />
          <button ref={button} type="button" className="krds-btn medium icon form-btn-datepicker" disabled={disabled} aria-haspopup="dialog" aria-expanded={open}
                  onClick={() => (open ? setOpen(false) : openCalendar())}>
            <span className="sr-only">{label} 달력 {open ? "닫기" : "열기"}</span>
            <i className="svg-icon ico-calendar" aria-hidden="true"></i>
          </button>
        </div>
        {open && (
          <div className="krds-calendar-area active">
            <div className={`calendar-wrap single${above ? " bottom" : ""}`} role="dialog" aria-label={`${label} 달력`} ref={calendar} onKeyDown={onCalendarKey}>
              <div className="calendar-head">
                <button type="button" className="btn-cal-move prev" onClick={() => shift(-1)}><span className="sr-only">이전 달</span></button>
                <div className="calendar-switch-wrap">
                  <div className="calendar-drop-down">
                    <button type="button" className={`btn-cal-switch year${drop === "year" ? " active" : ""}`} aria-label={`연도 선택, 지금 ${year}년`} aria-expanded={drop === "year"}
                            onClick={() => setDrop(drop === "year" ? null : "year")}>{year}년</button>
                    <div className={`calendar-select calendar-year-wrap${drop === "year" ? " active" : ""}`}>
                      <ul className="sel year">
                        {years.map((item) => (
                          <li key={item}><button type="button" tabIndex={drop === "year" ? 0 : -1} className={item === year ? "active" : undefined}
                                                 onClick={() => { setView(new Date(item, month, 1)); setFocused(null); setDrop(null); }}>{item}년</button></li>
                        ))}
                      </ul>
                    </div>
                  </div>
                  <div className="calendar-drop-down">
                    <button type="button" className={`btn-cal-switch month${drop === "month" ? " active" : ""}`} aria-label={`월 선택, 지금 ${month + 1}월`} aria-expanded={drop === "month"}
                            onClick={() => setDrop(drop === "month" ? null : "month")}>{pad(month + 1)}월</button>
                    <div className={`calendar-select calendar-mon-wrap${drop === "month" ? " active" : ""}`}>
                      <ul className="sel month">
                        {Array.from({ length: 12 }, (_, item) => (
                          <li key={item}><button type="button" tabIndex={drop === "month" ? 0 : -1} className={item === month ? "active" : undefined}
                                                 onClick={() => { setView(new Date(year, item, 1)); setFocused(null); setDrop(null); }}>{pad(item + 1)}월</button></li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
                <button type="button" className="btn-cal-move next" onClick={() => shift(1)}><span className="sr-only">다음 달</span></button>
              </div>
              <div className="calendar-body">
                <div className="calendar-table-wrap">
                  <table className="calendar-tbl">
                    <caption className="sr-only">{year}년 {month + 1}월</caption>
                    <thead><tr>{WEEKDAYS.map((day, i) => <th key={day} scope="col"><abbr title={WEEKDAY_NAMES[i]}>{day}</abbr></th>)}</tr></thead>
                    <tbody>
                      {weeksOf(year, month).map((week) => (
                        <tr key={iso(week[0])}>
                          {week.map((date) => {
                            const key = iso(date);
                            const other = date.getMonth() !== month;
                            const classes = [other && (date < view ? "old" : "new"), date.getDay() === 0 && "day-off", key === today && "today",
                                             key === picked && "period start end"].filter(Boolean).join(" ");
                            const tabbable = key === (focused || picked || (today.startsWith(`${year}-${pad(month + 1)}`) ? today : iso(view)));
                            return (
                              <td key={key} className={classes || undefined}>
                                <button type="button" className="btn-set-date" data-date={other ? undefined : key} disabled={other} tabIndex={tabbable ? 0 : -1} aria-pressed={key === picked}
                                        aria-label={`${date.getFullYear()}년 ${date.getMonth() + 1}월 ${date.getDate()}일 ${WEEKDAY_NAMES[date.getDay()]}${key === today ? ", 오늘" : ""}`}
                                        onClick={() => { setPicked(key); setFocused(key); }}>
                                  <span>{date.getDate()}</span>
                                </button>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="calendar-footer">
                <div className="calendar-btn-wrap">
                  <button type="button" className="krds-btn small text" onClick={() => { setPicked(today); move(fromIso(today)); }}>오늘</button>
                  <button type="button" className="krds-btn small tertiary" onClick={close}>취소</button>
                  <button type="button" className="krds-btn small primary" disabled={!picked} onClick={() => { commit(picked); close(); }}>확인</button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
      {error ? <p className="form-hint-invalid" id={hintId} role="alert">{error}</p> : <p className="form-hint" id={hintId}>{hint}</p>}
    </div>
  );
}

// 로그인 화면 — 로그인이 필요한 서버에서 로그인하지 않았을 때 어느 주소로 들어와도 이 화면이 먼저 보인다(main.jsx의 AuthGate).
// 회원가입은 없다. 계정은 관리자가 만든다.
// 시연 계정 안내: 서버에 NCS_DEMO_PASSWORD가 있을 때만(/api/login/demo) 입력 칸 아래에 역할별 아이디와 비밀번호를 보인다. 운영 서버에는 그 값을 두지 않는다.
import React, { useEffect, useState } from "react";

import { Footer, Header } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { request } from "../lib/api.js";
import { useAuth } from "../lib/auth.jsx";
import { usePageTitle } from "../lib/hooks.js";

// 세분류 건의 흐름에서 먼저 움직이는 역할부터(제출 → 검수 → 검토 → 확인 → 심의)
const FLOW_ORDER = ["author", "editor", "reviewer", "krivet", "committee"];
const ROLE_WORK = {
  author: "개발계획서와 원고를 올려 제출합니다. 담당한 권만 보입니다.",
  editor: "세분류 건을 만들고 검수를 실행합니다. 보완 요청과 완료를 적습니다.",
  reviewer: "1차·2차 검토 단계의 원고를 확인합니다.",
  krivet: "모든 건과 기록을 봅니다. 이미지 저작권 DB의 권리 정보를 확정합니다.",
  committee: "심의 단계의 원고를 확인합니다.",
};

function DemoAccounts({ demo, onPick }) {
  const rows = [...demo.accounts].sort((a, b) => FLOW_ORDER.indexOf(a.role) - FLOW_ORDER.indexOf(b.role) || a.login.localeCompare(b.login));
  return (
    <section className="login-demo" aria-labelledby="login-demo-title">
      <h2 id="login-demo-title" className="login-demo-title">시연 계정 <span className="krds-badge bg-light-warning">시연 서버 전용</span></h2>
      <p className="login-demo-desc">[입력]을 누르면 아이디와 비밀번호가 위 칸에 들어갑니다. 순서는 세분류 건이 흘러가는 순서입니다.</p>
      <div className="krds-table-wrap">
        <table className="tbl col data login-demo-table">
          <caption>역할별 시연 계정의 아이디와 비밀번호</caption>
          <thead>
            <tr><th scope="col">역할</th><th scope="col">아이디</th><th scope="col">비밀번호</th><th scope="col">하는 일</th><th scope="col"><span className="sr-only">입력</span></th></tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.login}>
                <th scope="row">{row.role_name}<span className="meta">{row.name}{row.org ? `, ${row.org}` : ""}</span></th>
                <td><code>{row.login}</code></td>
                <td><code>{demo.password}</code></td>
                <td>{ROLE_WORK[row.role] || ""}</td>
                <td><button type="button" className="krds-btn tertiary small" onClick={() => onPick(row.login, demo.password)}>입력<span className="sr-only"> — {row.role_name} {row.login}</span></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function LoginPage() {
  usePageTitle("로그인");
  const { logIn } = useAuth();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [demo, setDemo] = useState(null);

  useEffect(() => {
    let alive = true;
    request("/api/login/demo").then(({ ok, data }) => {
      if (alive && ok && data?.password && data.accounts?.length) setDemo(data);
    });
    return () => { alive = false; };
  }, []);

  async function submit(e) {
    e.preventDefault();
    if (!login.trim() || !password) return;
    setBusy(true);
    setError(null);
    const { ok, error: message } = await logIn(login.trim(), password);
    setBusy(false);
    if (!ok) { setError(message); setPassword(""); }
  }

  function pick(id, secret) {
    setLogin(id);
    setPassword(secret);
    setError(null);
    document.getElementById("login-submit")?.focus();
  }

  return (
    <>
    <Header anchors={[]} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page login-page">
      <div className="login-card">
        <h1 className="page-title">로그인</h1>
        <p className="page-desc">아이디와 비밀번호를 입력해 주세요.</p>
        <form className="fieldset login-form" onSubmit={submit} noValidate>
          <div className="form-group">
            <div className="form-tit"><label htmlFor="login-id">아이디</label></div>
            <div className="form-conts">
              <input id="login-id" type="text" className="krds-input large" autoComplete="username" autoCapitalize="none" spellCheck={false} autoFocus maxLength={50}
                     value={login} onChange={(e) => setLogin(e.target.value)} />
            </div>
          </div>
          <div className="form-group">
            <div className="form-tit"><label htmlFor="login-password">비밀번호</label></div>
            <div className="form-conts">
              <input id="login-password" type="password" className="krds-input large" autoComplete="current-password" maxLength={200}
                     value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
          </div>
          <PageAlert kind="danger">{error}</PageAlert>
          <button id="login-submit" className="krds-btn primary xlarge login-submit" type="submit" disabled={busy || !login.trim() || !password}>{busy ? "확인하는 중" : "로그인"}</button>
        </form>
        <ul className="login-help">
          <li>회원가입은 없습니다. 계정이 없거나 비밀번호를 잊었으면 관리자에게 문의해 주세요.</li>
          <li>로그인에 5번 실패하면 60초 동안 다시 시도할 수 없습니다.</li>
        </ul>
      </div>
      {demo && <DemoAccounts demo={demo} onPick={pick} />}
    </main>
    <Footer />
    </>
  );
}

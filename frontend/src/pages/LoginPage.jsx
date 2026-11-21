// 로그인 화면 — 로그인이 필요한 서버에서 로그인하지 않았을 때 어느 주소로 들어와도 이 화면이 먼저 보인다(main.jsx의 AuthGate).
// 회원가입은 없다. 계정은 관리자가 만든다.
import React, { useState } from "react";

import { Footer, Header } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { useAuth } from "../lib/auth.jsx";
import { usePageTitle } from "../lib/hooks.js";

export default function LoginPage() {
  usePageTitle("로그인");
  const { logIn } = useAuth();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function submit(e) {
    e.preventDefault();
    if (!login.trim() || !password) return;
    setBusy(true);
    setError(null);
    const { ok, error: message } = await logIn(login.trim(), password);
    setBusy(false);
    if (!ok) { setError(message); setPassword(""); }
  }

  return (
    <>
    <Header anchors={[]} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page login-page">
      <h1 className="page-title">로그인</h1>
      <p className="page-desc">아이디와 비밀번호를 입력해 주세요. 계정이 없으면 관리자에게 문의해 주세요.</p>
      <form className="fieldset review-form login-form" onSubmit={submit}>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="login-id">아이디</label></div>
          <div className="form-conts">
            <input id="login-id" type="text" className="krds-input" autoComplete="username" autoFocus maxLength={50} value={login}
                   onChange={(e) => setLogin(e.target.value)} />
          </div>
        </div>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="login-password">비밀번호</label></div>
          <div className="form-conts">
            <input id="login-password" type="password" className="krds-input" autoComplete="current-password" maxLength={200} value={password}
                   onChange={(e) => setPassword(e.target.value)} />
          </div>
        </div>
        <div className="form-group form-actions">
          <div className="run-buttons">
            <button className="krds-btn primary large" type="submit" disabled={busy || !login.trim() || !password}>{busy ? "확인하는 중" : "로그인"}</button>
          </div>
          <PageAlert kind="danger">{error}</PageAlert>
        </div>
      </form>
    </main>
    <Footer />
    </>
  );
}

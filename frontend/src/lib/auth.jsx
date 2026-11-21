// 로그인 상태 — 앱 전체를 감싸 /api/me로 지금 계정을 확인한다.
//   status: "loading"(확인 중) | "open"(로그인을 쓰지 않는 서버 — DB 없음) | "in"(로그인함) | "out"(로그인 필요)
// 로그인한 뒤 어느 요청이든 401이 오면(세션 기한이 지남 등) api.js가 'ncs-auth-lost'를 알리고, 여기서 "out"으로 바꿔 로그인 화면을 보인다.
import React, { createContext, useContext, useEffect, useState } from "react";

import { api } from "./api.js";

const AuthContext = createContext({ status: "open", account: null, logIn: async () => ({ ok: false }), logOut: async () => {} });
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: "loading", account: null });

  useEffect(() => {
    let alive = true;
    (async () => {
      const { ok, status, data } = await api.auth.me();
      if (!alive) return;
      if (ok) setState(data.auth ? { status: "in", account: data.account } : { status: "open", account: null });
      else setState({ status: status === 401 ? "out" : "error", account: null });
    })();
    const lost = () => setState((now) => (now.status === "in" ? { status: "out", account: null } : now));
    window.addEventListener("ncs-auth-lost", lost);
    return () => { alive = false; window.removeEventListener("ncs-auth-lost", lost); };
  }, []);

  async function logIn(login, password) {
    const answer = await api.auth.login(login, password);
    if (answer.ok) setState({ status: "in", account: answer.data.account });
    return answer;
  }
  async function logOut() {
    await api.auth.logout();
    setState({ status: "out", account: null });
  }
  return <AuthContext.Provider value={{ ...state, logIn, logOut }}>{children}</AuthContext.Provider>;
}

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

// 건을 만들고 이미지 저작권 DB를 바꾸는 역할(에디터, 직능연). 로그인을 쓰지 않는 서버에서는 누구나 — 서버의 flow.MANAGER_ROLES와 같다.
// 판정을 정하는 일과 비용이 드는 검토도 이 역할만 한다: 판정 확정, LLM 검토, 그림 판독, 의견 반영 검토, 원고 폴더 일괄 검수
// (서버는 ncs_web.common.manager_only가 같은 일을 403으로 막는다). 집필진은 올리기, 작성 도움, 규칙 검수 결과 보기까지다.
export function useCanManage() {
  const { status, account } = useAuth();
  return status === "open" || ["editor", "krivet"].includes(account?.role);
}

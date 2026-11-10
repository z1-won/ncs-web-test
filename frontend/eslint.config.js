// ESLint 9 flat config — 문법·미사용 변수·훅 규칙(react-hooks)만. 포맷은 강제하지 않는다.
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default [
  { ignores: ["dist/**", "node_modules/**"] },
  js.configs.recommended,
  {
    files: ["src/**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: { ...globals.browser },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // JSX 안에서 쓰인 컴포넌트·React를 미사용으로 보지 않게: 대문자 식별자는 사용으로 간주
      "no-unused-vars": ["warn", { varsIgnorePattern: "^(React|[A-Z])", argsIgnorePattern: "^_" }],
    },
  },
];

# frontend

F02 검수 화면(React·Vite·KRDS). 서버(`src/ncs_web`)와 함께 띄우는 법, 빌드, DB 이력 설정은 [`docs/WEB.md`](../docs/WEB.md)를 봅니다.

```bash
cd frontend && npm install && npm run dev     # 개발 서버 5173, /api는 8765로 프록시
npm run lint && npm run build                # dist/ 생성 → 루트에서 ncs-web --dist frontend/dist
```

엔진 목록(`src/lib/checks.js`의 `CHECKS`·`FILE_HINTS`)은 서버 `ENGINES`와 같아야 하며 `tests/contract/test_engines.py`가 검사합니다.

# 벨라 수학 문제은행 — Claude Code 플러그인

문제은행(MCP)에 토큰 없이 붙고, 수동 추출·그림 전사·AI 요청함·문항 QA 스킬을 받는 플러그인입니다.
버전 `2026.10.21` — 문제은행 레포 `scripts/sync_plugin.ts` 가 만듭니다(손으로 고치지 마세요).

## 조건

1. **Tailscale** — 학원 데스크탑 노드를 공유받은 계정으로 로그인돼 있어야 합니다(브라우저에서
   `https://bboya.tail1d427e.ts.net` 이 열리면 됩니다).
2. **문제은행 계정** — 소유자가 「설정 › 함께 쓰는 사람」에서 만들어 준 계정.
3. **Claude Code**.

## 설치 (Claude Code 세션 안에서)

```
  /plugin marketplace add Nanazzoo/mathbank-claude-plugin
  /plugin install mathbank@mathbank
```

그 다음 `/mcp` → `plugin:mathbank:mathbank` 선택 → 브라우저가 문제은행 로그인 화면을 엽니다 →
기기 이름 적고 「허용」 → 돌아오면 연결됩니다. 토큰·환경 변수·레포 clone 은 없습니다.

확인: "problem_list 로 5건 보여줘" → 목록이 오면 성공. 스킬은 `/mathbank:manual-extract` 처럼 부릅니다.

## 끊기 · 다시 연결

- 끊기: 문제은행 「설정 › MCP 연결」에서 그 기기 폐기(즉시 끊김). Claude Code 쪽은 `/mcp` → Clear authentication.
- 연결은 30일마다 자동 갱신됩니다. 갱신이 거부되면 `/mcp` 에서 다시 인증하세요.

## 레포 없이는 안 되는 것

- `figure-transcribe` 의 렌더 눈 대조·벡터 초안, `item-qa` 의 sympy 동치 비교 — 각 SKILL.md 머리의 주의 참고.
- `claude -p`(헤드리스)·자동화 계정은 브라우저 로그인을 못 합니다 → 「설정 › MCP 연결 › 직접 토큰 발급」.

## 업데이트

`/plugin marketplace update mathbank` 또는 `/plugin` 에서 자동 업데이트를 켭니다. 마켓 레포: `Nanazzoo/mathbank-claude-plugin`.

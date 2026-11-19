---
name: manual-extract
description: "교재·기출 PDF 를 유료 vision LLM 없이 에이전트가 지면을 직접 읽어 옮겨 적는 '수동 추출' 배치를 처음부터 끝까지 돌리는 오케스트레이터. 윈도우 PC·맥 어디서든 같은 MCP 경로로 돈다. 범위 결정 → 지면 실측(README·SPLIT) → 전사 병렬 → 눈가림 솔버(aiChecks) → dryRun → 적재 → 등록 = 자동 검수(통과분 즉시 VERIFIED) → 남은 문항만 검산·승인·판정관 → 마감 기록. '수동 추출', '수동추출 다음 배치', '다음 장 추출', 'N장 옮겨 적어', 'RPM/쎈 N~M쪽 추출', 'extract_pages', '전사 에이전트', '추출 이어서/재실행', '전사 다시', '이 배치 마감', '판정관만 다시', '추출한 문제 검산하고 등록해줘', '검수해줘', '승인해줘', '검수하고 승인해줘', '실수로 등록한 잡 검수' 요청 시 반드시 이 스킬을 사용할 것. 그림 코드 전사(figure_transcribe)·검수 큐 일반 처리·vision LLM 자동 추출(과금)은 이 스킬이 아니다."
---

# 수동 추출 — 배치 오케스트레이터

추출 잡을 **에이전트가 지면을 읽어** 채우고, 등록·검산·판정까지 마쳐 `잡 = 전건 VERIFIED` 로 닫는다.
2026-09-03 ~ 09-15 에 같은 절차를 48번 손으로 돌린 것을 굳혔다(기록: `docs/claude/*수동추출*/README.md`).
유료 LLM 은 어디서도 부르지 않는다 — 잡의 `llmModel` 은 `manual-agent`.

> 저작권: 이 하네스는 `restricted` 지면을 읽는다. 허용 근거는 CLAUDE.md 「저작권 원칙」의 수동 추출 항목(학원 내부 사용·외부 배포 없음, 2026-10-11 사용자 결정). 적재 결과의 `license_status` 는 원본 그대로 두고 `self` 로 바꾸지 않는다.

**실행 모드: 서브 에이전트.** 전사관끼리 주고받을 것이 없고 산출은 전부 파일이라 팀 통신이 필요 없다.

| 에이전트                | 언제          | 수     | 모델     | 산출                                               |
| ----------------------- | ------------- | ------ | -------- | -------------------------------------------------- |
| `extract-surveyor`    | 범위 확정 후  | 1      | sonnet   | `<out>/README.md` · `<out>/SPLIT.md`               |
| `extract-transcriber` | 실측 직후     | **≤3** | opus     | `<out>/out/{pages,answers,specs}-<구분>.jsonl`     |
| `extract-judge`       | 검산·승인 후  | 1      | opus     | `<out>/review/{verdicts,difficulty}.jsonl`         |

- **시험지(≤12쪽)는 실측관을 생략하고 전사관 1명이 SPLIT 을 겸임한다**(Phase 2 건너뜀 — 점검 04: 모의 배치에서 실측관이 환산 비용의 28%, 시험지 SPLIT 은 단순). 문제집(코너·아치·오프셋)은 지금대로 실측관을 둔다.
- 모델: 지면 판독·문항 풀이 정확도가 곧 데이터 품질이라 전사·판정은 opus. 실측관은 CLAUDE.md 토큰 원칙
  (실측·문서 정리 → sonnet). SPLIT 구조 오판이 반복되면 opus 로 올리고 변경 이력에 남긴다.
- 전사관 3명 상한: CLAUDE.md 토큰 원칙(병렬 팬아웃 3개 이하). 예전 배치는 5명이었다.
- 전사관은 `run_in_background: true` 로 한 메시지에 함께 띄운다.
- 교재 공통 함정은 `references/lessons.md` — **실측관·전사관 브리프에 반드시 가리킨다.**

---

## 어느 기계에서나 같은 경로 — MCP

운영 앱·DB 는 윈도우 PC(Docker) 한 곳뿐이다. 그래서 **모든 읽기·쓰기는 앱 API 를 지나는 MCP 도구**로 한다 —
PC 든 맥이든 같은 도구, 같은 순서다. DB 에 직접 닿는 CLI(`verify:ids`·`apply_*`)는 이 하네스에서 쓰지 않는다
(맥은 운영 DB 에 닿지 않는다 — 맥의 로컬 DB 에 쓰면 운영에 안 들어간다). 옛 수동 추출 CLI `extract:manual` 은
2026-10-10 삭제했다 — "extract:manual" 이라는 요청이 와도 이 MCP 경로로 돈다.

| 단계 | 도구 |
| ---- | ---- |
| 현황 | `extract_status` · `document_list` |
| 지면 | `extract_pages_read`(본문 2쪽·해설 2쪽·이미지 4장씩, `zoom`) |
| 검산식 확인 | `sympy_verify` |
| 적재 | `extract_pages_apply`(기본 dryRun) → 잡 생성 |
| 무료 검산 | `verify_ids`(잡 번호로, 기본 dryRun) — DRAFT → 검수 큐, 검산식 없는 문항은 `skippedIds` |
| 판정 입력 | `problem_list`(`document`·`state` + 결과의 `source.page`) · `problem_get` · `problem_figures_read` |
| 판정 적재 | `review_verdicts_apply`(정답, verdict 별 `band` 로 난이도 같이) · `difficulty_verdicts_apply`(난이도, `overwrite`) |
| 마감 점검 | `document_status`(문서별 상태·승인 막힘 사유) · `answer_lint`(자동채점 안 되는 정답) · `duplicate_check` · `problem_get_many` |
| 정답 교정 | `answer_corrections_apply`(새 revision DRAFT → 재검수, 기본 dryRun) |
| 승인 | `review_approve`(화면 일괄 승인과 같은 게이트, IN_REVIEW 만, 기본 dryRun) — **사용자가 승인하라고 했을 때만** dryRun:false |
| 정답·해설 PDF | `document_answer_pdf`(서명 URL 30분) |

**준비(기기마다 한 번):** Tailscale 로 같은 tailnet + 사용자 환경 변수 `MCP_REMOTE_TOKEN`
(PC: `setx`, 맥: `~/.zshrc` — `docs/claude/2026-09-14-MCP-원격-HTTP.md` §7). 그다음 이 레포 폴더에서 연
**새 세션**에서 `/mcp` 에서 `plugin:mathbank:mathbank` 가 「Connected」인지 본다(아니면 거기서 인증). 도구 이름 접두사는 `mcp__plugin_mathbank_mathbank__…` 다.
관리자 화면은 두 기기 모두 같은 tailnet 주소로 연다.

---

## Phase 0. 컨텍스트 확인

1. **도구 확인**: `extract_pages_read`·`verify_ids`·`difficulty_verdicts_apply` 가 보이는가. 없으면 멈추고
   "레포 폴더에서 새 세션 + MCP 서버 승인 + `MCP_REMOTE_TOKEN`" 을 안내한다(홈 폴더 세션이면 안 잡힌다).
   `verify_ids` 만 없으면 운영 앱이 옛 이미지다 — PC 에서 `docker compose up -d --build app` 이 필요하다(서비스가
   잠깐 끊기니 사용자에게 묻는다).
2. 문서·범위: 사용자가 안 줬으면 대상 문서의 **가장 최근 배치 README** 「전체 장 범위 표」에서 다음 행
   (`ls -d docs/claude/*수동추출* | tail`). 새 교재면 `extract_status` 로 빈 구간 — ⚠ `nextUnextracted` 는
   **해설 면도 미추출로 잡는다**(lessons L-1).
3. 이미 배치 폴더가 있나?
   - `out/*.jsonl` 이 일부만 → **이어받기**: 미완 구분만 Phase 3(jsonl 마지막 번호 다음부터).
   - 적재했는데 등록 안 됨(`extract_status` 의 검토 대기 잡) → Phase 5 의 등록 요청부터.
   - 등록됐는데 VERIFIED 아닌 문항이 남음 → Phase 5 의 검산 또는 Phase 6.
   - 특정 구분/단계만 다시 → 그 Phase 만.
4. 범위 · 폴더명을 **한 번에 보여 주고 확인받는다**(CLAUDE.md: 혼자 결정하지 않는다).
   폴더명: `docs/claude/YYYY-MM-DD-<교재약칭>-수동추출-<from>-<to>`.

## Phase 1. 준비 (메인)

`<out>/` 를 만들고 `extract_status(documentId)` 결과(쪽 상태 구간·검토 대기 잡)를 `<out>/README.md` 머리에 붙인다.
해설 범위는 **양 끝 한 쪽씩 겹쳐** 잡는다(lessons L-5). 오프셋은 직전 배치 README 「쪽 오프셋 규칙」.
잡은 Phase 5 적재 때 구분마다 하나씩 생긴다.

## Phase 2. 지면 실측 — `extract-surveyor` 1명

브리프(경로만, 짧게): 문서 id · `<out>` · 본문/해설 쪽 범위 · **직전 배치 폴더 경로** · `references/lessons.md`.
실측관은 `<out>/README.md`(오프셋·전체 장 범위 표·특이점·난이도 재판정 대상 쪽)와 `<out>/SPLIT.md`(구분 ≤3 ·
지면 구조 · 해설 인덱스 · 승계 규칙 링크 · 이 장 특유 검산 규칙)를 쓴다.

메인은 SPLIT 의 **분담 표만** `sed -n` 으로 읽어 구분 수·쪽·번호 범위를 확인한다(전문 읽지 않는다).
번호 범위가 끊기거나 해설 인덱스가 비었으면 실측관에게 1회 되돌린다.

## Phase 3. 전사 — `extract-transcriber` ≤3명 병렬

그림은 원본 크롭만 보존한다(`hasFigure`·`figureBox`·그림 보기 상자·해설 그림 상자). 기존 프리셋이 `transcribeFigures:true`여도 추출 단계에서 그림 코드를 새로 쓰지 않는다. 기존 코드는 보존하며, 사용자가 나중에 별도로 요청하면 `figure-transcribe`를 적용한다.

구분마다 한 명. 브리프: `<out>` · 구분 문자 · 본문 쪽 · 해설 쪽 · 번호 범위 · 문서 id.
전사관은 jsonl 을 쓰고 `extract_pages_apply` **dryRun 까지만** 한다. 끝나면 **12줄 이내 보고**만 돌려준다.
메인은 보고를 SPLIT 「진행 로그」에 `### <구분> 완료` 절로 append 한다 — 전사관이 SPLIT 을 동시에 고치지 않게
(lessons L-24). **에이전트 id 를 기록해 둔다** — 번호 수정·검산식 수정을 같은 전사관에게 `SendMessage` 로 돌리기 위해서다.

전사관은 본문·해설 줄마다 원본 영역 `region: {x, y, w, h}`(쪽 전체 기준 0~1, 문항 번호 박스 왼쪽 위 → 다음 문항 직전)를
적는다(`extract-transcriber` 원칙 6-1 · lessons L-25). 등록하면 `Problem.sourceRegion`·`answerKeyPage`·`answerKeyRegion` 으로 가고
문항 상세 「원본 대조」가 그 부분만 자른다. 영역 없이 등록된 과거 문항은 MCP `problem_region_update`(dryRun 기본)로 채운다.

**해설 지면이 없는 문서(기출 시험지 등)는 전사관이 `answers` 를 비우고 본문·검산식만 쓴다** — 정답·해설은 Phase 3.5 솔버의
`aiChecks`(answer + explanationLatex)로 서버가 채우고, 2차 독립 풀이는 적재 뒤 별도 호출로 넣는다(전사관 원칙 5-1, 2026-11-19 E-R3 —
`answers` 는 page 가 없어도 정답표로 들어가 전사관 답이 대조 기준이 돼 버린다). 요청함 `extract_pages` 가 `includeExplanations:false`
거나 문서에 정답지가 없을 때가 여기 해당한다 — "정답·해설 없이 문항만" 으로 끝내지 않는다(솔버가 반드시 aiChecks 를 쓴다). **그림은 원본 크롭만 보존한다**(2026-10-25 사용자 지시). `figureCode` 신규 작성·자동 전사를 하지 않고 나중에 별도 요청하면 `figure-transcribe`로 진행한다.
브리프에 "해설 지면 없음 → answers 비움(솔버가 aiChecks 로)" 와 "그림은 원본 크롭만" 을 명시한다.

한 명이 실패하면 1회만 다시 띄운다(이미 쓴 jsonl 을 이어 쓰라고). 또 실패하면 보고하고 나머지 구분은 대기.

## Phase 3.5. 눈가림 풀이 — 솔버 1명 (등록 = 자동 검수의 입력)

2026-10-20 「등록 = 자동 검수」(`docs/claude/2026-10-20-등록-자동검수.md`): 적재할 때 문항별 AI 눈가림 풀이(`aiChecks`)를
같이 실으면, 등록하는 순간 서버가 정답표+SymPy+AI 대조로 판정해 통과분을 **바로 VERIFIED** 로 올린다. 나머지는 IN_REVIEW + 사유.

- **정답을 본 에이전트는 풀지 않는다.** 전사관은 해설 지면을 읽었으니 독립 검산이 아니다. 솔버는 `general-purpose`(opus) 를
  **새로** 띄우고 브리프에 `out/pages-<구분>.jsonl` 경로만 준다 — `answers-*.jsonl`·`specs-*.jsonl`·해설 쪽 번호·`extract_pages_read`
  해설 지면은 주지 않는다(서버는 눈가림을 확인할 수 없다 — 이 규칙이 유일한 보장이다).
- 솔버는 지문·보기만 보고 풀어 `out/aichecks-<구분>.jsonl` 에 `{number, page, answer, explanationLatex?, note?}` 를 쓴다.
  객관식은 보기 키("1"~"5"), 그 외는 평문 값. 그림이 있어야 풀리는 문항은 본문 지면 그림(`extract_pages_read` **본문 쪽만**)을 보거나,
  못 풀면 `answer: null` + `note`. 추측하지 않는다. 난이도는 쓰지 않는다(추출 난이도 체인이 단일 소스).
- 구분이 여럿이면 솔버 1명이 차례로 푼다(병렬 상한 3 은 전사관이 이미 썼다).
- **정답표에 없는 문항(답지 없음)** 은 솔버가 `explanationLatex` 에 풀이 전 과정을 꼭 쓴다 — 서버가 그 답·풀이로 정답·해설을 채운다.
- **2차 독립 풀이(교차 확인)는 적재 뒤 별도 호출로만**(2026-11-19 결정 3 — `extract_pages_apply` 에 `aiCrossChecks` 를 실으면 400):
  Phase 5 적재로 잡 번호를 받은 뒤, 1차 솔버와 **다른** 에이전트를 새로 띄워 같은 `out/pages-<구분>.jsonl` 만 주고(1차 aichecks·answers·
  README·진행 로그는 열지 않는다, lessons L-39) 답지 없는 문항을 풀게 한다. 메인이 그 답을
  `extract_job_items_update(jobId, updates:[{index, aiCrossCheck:{answer}}], dryRun:true→false)`(index 는 `extract_job_get` 결과 위치) 로 문항별로 넣은 뒤 등록한다.
  2차 솔버가 지면 jsonl 대신 잡을 직접 읽어야 하면 반드시 `extract_job_get(blind:true)` 로 읽는다(정답·해설·1차 풀이 칸이 빠진다).
  1차와 일치하면 등록 즉시 VERIFIED, 불일치·없음이면 사람 승인. 정답을 직접 고친 항목에는 aiCheck·aiCrossCheck 가 거절된다(E-R1).

## Phase 4. 사전 점검 (메인)

전사관 보고의 dryRun 수치(문항·해설 매칭·검산식 실림/none·notes)를 구분별로 모은다.
- 번호 결손·형식 경고 → 그 구분 전사관에게 **그 번호만** 고치게 1회 재호출. 재검 루프는 한 바퀴(CLAUDE.md).
- 검산 실패(통과도 none 도 아닌 것) → 검산식만 고치게 한다. 정답표 오식 의심은 고치지 말고 「확인 요청」.
- ⛔ **여기서 사용자에게 한 번 묻는다**: 구분별 문항 수 · 해설 매칭 · 통과/none · 경고 → "적재할까요?".
  승인이 나면 이 배치의 MCP 쓰기(적재·검산·판정 적재)를 연달아 해도 된다(배치가 바뀌면 다시 묻는다).

## Phase 5. 적재 → 등록 → 무료 검산 → 승인

1. **메인이 직접 적재한다**: 구분마다 `out/{pages,answers,specs,aichecks}-<구분>.jsonl` 을 읽어 전사관이 보고한 쪽 범위 그대로
   `extract_pages_apply(…, aiChecks, dryRun:false)` → 잡 번호 회수. answers 에 page 가 있으면 해설 범위 `keyFromPage`·`keyToPage` 를
   함께 적는다(해설 PDF 가 따로 있는 문서에서 빼거나 한쪽만 적으면 400 — 2026-11-19 E-R4). 응답의 `aiChecks: {attached, unknown, ambiguous}` 에서
   `unknown`·`ambiguous` 가 있으면 번호·page 를 고쳐 다시 싣는다(안 붙은 문항은 자동 검수 없이 DRAFT 로 등록된다). 서브에이전트의 쓰기는 auto mode 분류기가 들쭉날쭉 막는다
   (2026-10-10 그림 전사 첫 배치: 3명 중 1명 차단). items 를 메인이 한 번 싣는 비용이 그보다 싸다.
2. **등록 = 자동 검수** — `extract_job_register(jobId, dryRun:true)` 로 건수·중복 후보를 보고 `dryRun:false`
   (또는 사용자가 화면 "검토·등록"). 응답 `autoApprove: {verified, inReview[{id, reasons}], failed}` 가 판정 결과다 —
   `verified` 는 이미 VERIFIED 이니 3·4 를 건너뛴다. 아래 3·4 와 Phase 6 은 **`inReview` 와 aiChecks 없이 등록된 문항에만** 돈다.
3. `verify_ids(extractionJobIds:[…])` dryRun → 대상 수 확인 → `dryRun:false`. 한 번에 150건까지라 잡이 크면
   잡별로 나눠 부른다. 결과의 `skippedIds` = 검산식 `none` 문항 → 판정관의 정답 판정 대상. `failed` 는 보고.
4. **승인** — `document_status` 로 막힘 사유를 보고 `review_approve` dryRun 으로 건수를 센 뒤, 사용자가 승인하라고
   하면 `dryRun:false`(아니면 `/admin/review` 기계 줄에서 사용자가 직접). 난이도가 비어 막히는 건(`blockedByNoDifficulty`)
   Phase 6 뒤에 다시. 승인 전에 `answer_lint` 로 자동채점 안 되는 정답을 걸러 `answer_corrections_apply` 로 고친다.

판정 대상 정리 → `<out>/review/targets.md` 에 두 목록:
- **정답 판정**: `skippedIds`.
- **난이도 판정**: README 「난이도 재판정 대상」 쪽의 문항 — `problem_list(document, limit 50, offset…)` 결과에서
  `source.page` 가 그 쪽인 id(지면 단위로 잡는다, lessons L-11) + `difficultyBand: unrated` 인 것.

## Phase 6. 판정 — `extract-judge` 1명

브리프: `<out>/review/targets.md` · README 「난이도 재판정 대상」 · 같은 장 기준선(유형 익히기 문항 밴드).
판정관은 `problem_get`·`problem_figures_read` 로 문항을 읽어 풀고 `review/verdicts.jsonl`·`review/difficulty.jsonl`·
`review/README.md` 를 쓴 뒤, **dryRun 으로만** 적재해 수치를 보고한다(10줄).

메인은 dryRun 수치를 확인하고 `review/verdicts.jsonl`·`review/difficulty.jsonl` 을 읽어 **직접** 적재한다:
- `review_verdicts_apply(dryRun:false)` — pass 는 게이트를 지나 VERIFIED 로 오른다(서버 판단).
- `difficulty_verdicts_apply(dryRun:false)` — 지면 매핑 임시값이 박혀 `protectedRated` 가 나오면 **사용자에게
  알리고** `overwrite:true`.

그 뒤 남은 IN_REVIEW 는 Phase 5-4 와 같이 `review_approve` 로 승인한다(사용자 지시가 있을 때). `fail` 은 승인하지 않고 「확인 요청」으로.

## Phase 7. 마감 (메인)

1. `<out>/README.md` 끝에 `## 마감 (YYYY-MM-DD)` — 기존 배치와 같은 5줄: 전사(명·구분별 건수) / 판정·적재 결과와
   **잡 = x/x VERIFIED**·문서 누적 검증완료(`problem_list(document, state:VERIFIED)` 의 `total`) / 새 검산 수법 /
   전사 함정 / 확인 요청(후속). 「전체 장 범위 표」 이번 행에 `✅ 잡 N`, 다음 행을 실측값으로.
2. 교재를 가리지 않는 새 함정이면 `references/lessons.md` 에 한 줄(L-번호) 추가.
3. `docs/HANDOFF.md` ★ 절의 실측 표·다음 작업 갱신.
4. 커밋은 사용자에게 묻고 한다. 다른 기기와는 git 으로 공유하므로 **배치 폴더·lessons 를 커밋해야** 다음
   기기가 이어받는다.
5. 최종 응답 5줄: 잡 · 건수/VERIFIED · none·판정 결과 · 확인 요청 수 · 다음 배치 범위.
6. "이번 배치에서 하네스에 고칠 점이 있었나요?" 한 줄. 피드백은 해당 에이전트/스킬에 반영하고
   CLAUDE.md 「하네스: 수동 추출」 변경 이력에 남긴다.

---

## 데이터 흐름

```
extract_status ─► README 머리
      │
surveyor ─► README.md · SPLIT.md(분담 ≤3)
      │
transcriber×≤3 ─► out/{pages,answers,specs}-{A,B,C}.jsonl ─► extract_pages_apply(dryRun) ─► SPLIT 진행 로그
      │
solver(눈가림, pages-*.jsonl 만) ─► out/aichecks-{A,B,C}.jsonl
      │
⛔ 사용자 승인 ─► apply(aiChecks, dryRun:false) = 잡 ─► extract_job_register = 자동 검수(통과분 VERIFIED)
      │                                                     │ inReview·aiChecks 없음만
      │                                              verify_ids ─► 🙋 승인
      │                                                          │
      └──────────── review/targets.md(skippedIds + 재판정 쪽) ◄───┘
                         │
                     judge ─► verdicts·difficulty jsonl ─► *_apply(dryRun→false) ─► 🙋 승인
                         │
                     README 마감 · lessons · HANDOFF · 커밋(기기 간 공유)
```

## 에러 핸들링

| 상황 | 대응 |
| ---- | ---- |
| MCP 도구가 안 보임 | 멈추고 "레포 폴더 새 세션 + 서버 승인 + `MCP_REMOTE_TOKEN`" 안내 |
| 원격 401 `토큰 모양이 아닙니다` | 토큰 env 가 빈 채 세션이 떴다 — 영구 env 로 박고 새 세션(원격 문서 §7) |
| `verify_ids` 만 없음 | 운영 앱 옛 이미지 — PC 에서 재빌드 필요, 사용자 확인 후 |
| 전사관 실패/중단 | 1회 재호출(이어 쓰기) → 또 실패면 보고, 적재 승인은 묻지 않는다 |
| 번호 결손 | 지면에 정말 없는 번호(교재 결번)인지 전사관이 확인 — 결번이면 README 특이점에 |
| 사전 검산 실패 | 검산식 수정 1회. 정답표 오식 의심은 고치지 않고 「확인 요청」 |
| 등록 화면의 중복 후보 | 기본은 제외. 강제 등록은 사용자 판단 |
| `verify_ids` 150건 초과 | 잡별로 나눠 부른다 |
| 판정 `fail` | 승인하지 않는다. 근거를 README 「확인 요청」에 |
| `extract_pages_apply` 가 `aiChecks` 를 모름 | 운영 앱 옛 이미지(2026-10-20 등록 자동검수 이전) — 재빌드 전에는 aiChecks 없이 싣고 기존 3·4·Phase 6 경로 |
| `autoApprove.inReview` 사유 "검산 근거 없음" | 정답표·AI 답 불일치 또는 AI 미풀이 — 판정관 정답 판정 대상에 넣는다 |

## 테스트 시나리오

**정상(맥):** "RPM 미적분Ⅰ 08장 수동 추출 돌려줘" → 원격 MCP 도구 확인 → 직전 배치(96-106) README 표에서 본문
108~121 · 해설 100~114 를 찾아 확인받음 → 실측관 README·SPLIT(구분 3) → 전사관 3명 병렬, 각자 dryRun → 사용자
"올려" → 메인이 실제 적재(잡 3개) → 사용자가 화면에서 등록 → `verify_ids` → 사용자 승인 → 판정관(skippedIds·
`시험에 꼭 나오는 문제` 쪽 난이도) dryRun → 실제 적재 → 사용자 승인 → `잡 3개 = x/x VERIFIED` → 마감·커밋.
PC 에서도 같은 문장으로 같은 흐름이 돈다.

**에러:** 전사관 B 가 컨텍스트 한도로 중단 → 1회 재호출(jsonl 이어 쓰기) → 또 중단 → A·C 는 dryRun 까지 마친
상태로 대기, 사용자에게 "B 구분 0640~0654 미완 — jsonl 은 0647 까지" 보고. 적재 승인을 묻지 않는다.

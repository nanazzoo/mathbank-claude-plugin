---
name: ai-inbox
description: "관리자 화면이 AI 요청함(`ai_task`)에 적어 둔 할 일을 MCP 로 가져가 kind 별 기존 하네스(manual-extract · figure-transcribe · 검수 판정관 · 관계 판정관 · 솔버)로 처리하고 complete/fail 로 닫는 상시 처리기. 윈도우 PC·맥 공통(MCP). '요청함 처리', 'AI 요청함', 'ai-inbox', '요청함 비워', '/loop 10m /ai-inbox', '요청함 멈췄어' 요청 시 반드시 이 스킬. 유료 LLM 호출·승인(VERIFIED)·화면 등록은 하지 않는다 — 결과는 전부 DRAFT·기록으로만 들어간다(단, ai_review 판정의 pass 는 review_verdicts_apply 에서 게이트 통과 시 VERIFIED)."
---

# AI 요청함 처리기

> 초안(2026-10-12, 2차 재설계 0a). 정본 `docs/claude/2026-10-12-문제은행-2차-재설계/_workspace/02_design2_ai-inbox.md` §7.
> 이 스킬은 **배차표**다 — 함정·세부 절차는 각 하네스의 `references/lessons.md` 가 정본이다(`references/` 를 따로 두지 않는다).

한 번 돌 때: ① `ai_task_next({limit:3})` ② 받은 건마다 kind 별 절차 ③ `ai_task_complete`(dryRun → 적용) 또는 `ai_task_fail` ④ 한 줄 요약(`처리 N · 실패 N · 남은 N`). 받은 것이 0건이면 `요청함 비어 있음` 한 줄로 끝낸다(토큰 절약).

상시 운용: `/loop 10m /ai-inbox`. 한 루프 상한 3건(전사·판정은 건당 수 분). **가져간 건은 반드시 닫는다** — 못 닫으면 회수 시간(기본 60분, extract_pages·figure_transcribe·ai_review·relation_wave 는 240분 — `lib/ai-task-kinds.ts`) 뒤 되돌아가 다른 세션이 다시 가져간다(attempt 3 → failed). `claimedBy` 는 생략하면 이 연결의 값이 들어가며(로컬 stdio 는 기계 이름, 원격 HTTP 는 initialize 때 받은 `Mcp-Session-Id` — 그 헤더를 안 보내는 클라이언트는 생략하면 거절되니 명시한다), next·complete·fail 이 같은 값이어야 닫힌다. 원격 연결은 다시 붙으면 값이 바뀌므로 **`ai_task_next` 응답의 `claimedBy` 를 complete·fail 에 그대로 넣는다**(2026-11-19). complete·fail 이 「다른 세션이 가져간 요청」 409 를 내면 그 건은 손을 떼고 다음 일감으로 간다.

| kind | 절차(기존 하네스 재사용) | 에이전트 · 모델 | 닫기 |
|---|---|---|---|
| extract_pages | manual-extract Phase 1~3(실측관 → 전사관 ≤3 → `extract_pages_apply` dryRun→적재). 시험지(≤12쪽)는 실측관 생략. **해설 지면이 없으면(`includeExplanations:false`·정답지 없음) 전사관이 문항을 직접 풀어 정답·해설·검산식을 같이 쓰고, 그림 문항은 `figureCode` 까지 같은 패스에서**(2026-10-19). 등록·승인은 **사람**(화면). `mode:'vision'` 이어도 vision 라우트를 부르지 않는다(제1 규칙) | extract-surveyor sonnet · extract-transcriber opus | complete `{jobId, pagesDone}` |
| figure_transcribe | figure-transcribe(`figure_transcribe_read` → DSL → 렌더 대조 → `figure_transcribe_apply`, 항상 DRAFT). 단건(`payload.assetId` — 코드 있는 DRAFT·FAILED 그림의 재전사 요청)은 전사관 1, **`mode:"retranscribe"`·`afterAssetId=assetId-1`·`limit:1`** 로 받아 같은 assetId 인지 확인한다(기본 missing 모드는 코드 없는 그림만 줘서 그 그림이 안 온다) | figure-transcriber opus | complete `{applied, failed}` |
| ai_check | item-qa 솔버 절차(지문만 보고 풀기 — 정답표를 보지 않는다. `problem_get`·`problem_figures_read` 모두 `blind:true`). 정답표 대조는 서버가 한다 | item-qa-solver sonnet | complete `{answer, explanationLatex?}` (못 풀면 `answer:null`) |
| specgen | `problem_get` → 식 작성 → `sympy_verify` → `verify_spec_update`(dryRun→적용) | 메인 직접(sonnet) | complete `{kind, expr, passed}` |
| ai_review | manual-extract 판정관 절차(`review_queue_list` → `problem_get` → `review_verdicts_apply`). 추출 보완 초안(`ai_draft` 해설·유형)이 틀리면 판정에 `fix` 로 고쳐서 낸다(S3) | extract-judge opus | complete `{applied, promoted, blocked}` |
| relation_wave | 관계 판정관(후보 → verdict) → complete 의 result 로 전달(서버가 `applyRelationJudgements`, payload 의 `batchKey`). ⚠ 2026-10-19 부터 등록 직후 자동 연결(`lib/relation-auto-link`, producer `heuristic`)이 기본이라 이 일감은 보조다. 한 문항의 유사 현황·후보는 읽기 도구 `relation_suggest`(id 또는 `#표시번호`) | 판정관 opus | complete `{judgements:[{problemId, candidateId, verdict, note}]}` |
| templatize | 템플릿 JSON 작성(서버가 형식 검증 + SymPy self-check 후 DRAFT 저장) | 솔버 sonnet | complete `{templates:[{problemId, template}]}` |
| extract_enrich | 일감의 `context`(문항·`missing`(채울 칸)·학년·`allowedConcepts`·`typeCandidates`) 읽기(그림은 `problem_get`) → **missing 이 true 인 칸만** 채운다: 유형은 `typeCandidates` 중 하나(없으면 null), 정답은 직접 풀어서(객관식은 보기 키), 해설은 **허용 개념 안에서만**(상위 학년 개념 금지). 정답이 이미 있어도 `answer` 를 적는다(서버가 대조해 틀린 답의 해설을 거른다). complete **dryRun** 으로 가드 확인 → 통과면 dryRun=false. 서버가 유형(AI 추정)·정답·해설을 채운 새 revision(DRAFT·`ai_draft`)을 만든다 | 메인 또는 솔버 sonnet | complete `{questionTypeId, answer, explanationLatex, usedConceptNodeIds:[id…], verify?:{kind,expr}}` |
| derive(extend) · rephrase · generate | 모델이 초안 작성, **저장은 하지 않는다** → result 로 전달(교사가 배너에서 골라 기존 save 라우트로 저장) | 메인 또는 솔버(심화·생성은 opus) | complete `{items[]}` / `{candidates[]}` |

스킬 없는 클라이언트용으로 `ai_task_next` 응답의 일감마다 이 표의 최소 절차(`nextSteps`)와 결과 모양(`resultShape`)이 붙는다 — 원천 `mcp/workflow.ts` 의 `AI_TASK_GUIDES`. **이 표를 고치면 그쪽도 맞춘다**(2026-10-21).

complete 는 **항상 dryRun 먼저**(기본값) — `valid:true` 를 확인하고 `dryRun:false` 로 닫는다. `valid:false` 면 issues 를 보고 고치거나 `ai_task_fail`.

금지: 유료 LLM API · `review_verdicts_apply` 로 승인 승격 외 전이 · 라이선스 변경 · 화면 등록(`/admin/bank/problems/extract`) 대행 · `handwriting_solve`(항상 API — 요청함에 오지 않는다). 실패는 `ai_task_fail({error, retry: 일시 오류만})` — error 는 교사가 화면에서 읽는 한국어 한두 문장.

---
name: item-qa
description: "이미 VERIFIED 인 문항을 표본으로 뽑아 **눈가림 재풀이**로 정답표·전사 품질을 감사하는 오케스트레이터. 표본 설계(문서·정답형식·난이도·라이선스 층화, 기본 50건) → 추출관(haiku, 지문/정답 분리) → 솔버(sonnet, 정답 안 보고 풀기) → 스크립트 비교(SymPy 동치) → 불일치만 판정관(opus, 정답표 오류/전사 오류/솔버 오류 원인 가리기) → 보고서 + 수정 대상 목록. '문항 품질 감사', '검증완료 문항 표본 검사', '정답표 오류 찾아', 'VERIFIED 문항 다시 풀어 봐', '눈가림 재풀이', '정답 재검증', 'item-qa', '문항 QA 이어서/재실행', '판정관만 다시', '이 감사 마감' 요청 시 반드시 이 스킬을 사용할 것. 검수 큐(DRAFT·IN_REVIEW)의 판정·승인은 manual-extract 판정관이나 /admin/review 이고, CAS 재검산(verify_ids)·정답률 통계 기반 강등·그림 검수는 이 스킬이 아니다."
---

> ⚠ **플러그인판 한계**: 동치 비교 `scripts/compare_answers.py` 는 sympy 가 있는 파이썬이 필요하다. 없으면 `sympy_verify` MCP 도구로 한 건씩 대조한다.

# 문항 품질 감사(item-qa) — 오케스트레이터

VERIFIED 12,423건(2026-10-10) 중 CAS 근거 없이 통과한 문항(사람 검수·AI 검수)이 출제 풀에 그대로 들어간다.
이 하네스는 표본을 **정답을 모르는 솔버**에게 다시 풀려 정답표와 대조하고, 어긋난 것만 강한 모델이 원인을 가린다.
핵심 원칙 하나: **풀이를 본 검증자는 동의 쪽으로 기운다**(math-olympiad 원칙) — 솔버는 key 를 절대 보지 않는다.

**실행 모드: 서브에이전트 파이프라인**(팀 통신 없음, 산출은 전부 파일, 메인이 오케스트레이터). 병렬 ≤3.

| 에이전트            | 언제               | 수  | 모델   | 산출                                   |
| ------------------- | ------------------ | --- | ------ | -------------------------------------- |
| `item-qa-extractor` | 표본 확정 후       | 1   | haiku  | `<out>/stems.jsonl` · `<out>/key.jsonl` |
| `item-qa-solver`    | 추출 직후          | ≤3  | sonnet | `<out>/solved/<구분>.jsonl`            |
| (스크립트)          | 풀이 직후          | —   | —      | `<out>/compare.jsonl`                  |
| `item-qa-judge`     | 불일치·skip 만     | 1   | opus   | `<out>/review/judged.jsonl` · `README.md` |

- 모델(토큰 원칙 T6): 추출은 필드 복사라 haiku — **첫 실행 때 앞 10건을 sonnet 으로 한 번 더 뽑아 diff**, 다르면 sonnet 으로
  올리고 변경 이력에 남긴다. 전수 풀이는 sonnet, 불일치 원인 판정은 opus(T2 cascade). 대조는 스크립트(T1).
- 솔버는 3명까지 구분(줄 구간)으로 나눠 `run_in_background: true` 로 한 메시지에 띄운다. 50건이면 2명이면 된다.
- 프롬프트 순서(T5): 고정 머리말(에이전트 정의 경로) → `<out>/BRIEF.md` 경로 → 가변부(구분·id 범위)는 맨 뒤.
- 에이전트 최종 응답 ≤10줄. 메인은 `review/README.md` 를 `grep -n "^## "` 로 절만 보고 필요한 절만 읽는다.

## 도구

| 단계 | 도구 |
| ---- | ---- |
| 표본 | `problem_list(state:"VERIFIED", document, answerType, difficulty, license, limit≤50, offset)` → `total`·`items[].source` |
| 추출 | `problem_get(id, withVerify, withFigures)` — 지문·보기·정답·해설·검산 기록(**솔버 금지**) |
| 풀이 | `problem_figures_read(id)`(그림 슬롯 stem·choice 만) · `sympy_verify` · `python -I` |
| 대조 | `scripts/compare_answers.py` — 레포 `.venv` 파이썬(sympy 1.14, antlr 없음 → LaTeX 폴백 파서) |
| 판정 | `problem_get` · `problem_figures_read` · `extract_pages_read`(원본 지면 대조) |

파이썬: 윈도우 `.venv/Scripts/python.exe`, 맥 `.venv/bin/python3`. 워크트리에는 `.venv` 가 없으니 메인 트리의 것을 쓴다.
시스템 파이썬에는 sympy 가 없다(2026-10-10 PC 실측). 패키지 설치는 하지 않는다.

```
python -I ${CLAUDE_PLUGIN_ROOT}/skills/item-qa/scripts/compare_answers.py --selftest      # 22/22
python -I ${CLAUDE_PLUGIN_ROOT}/skills/item-qa/scripts/compare_answers.py --key <out>/key.jsonl --solved <out>/solved/all.jsonl --out <out>/compare.jsonl
```

---

## 판정 결과의 처리 — 확인한 사실 (2026-10-10 코드 대조)

`review_verdicts_apply`(→ `app/api/admin/problems/ai-review/route.ts` → `lib/ai-review-apply.ts`)를 VERIFIED 문항에 부르면:

| 문항 | 판정 | 실제로 일어나는 일 |
| ---- | ---- | ------------------ |
| 검산식 있음(CAS 대상) | fail/pass | **아무것도 안 씀** — `notEligible`, "검산식이 있다 — CAS 경로로 가야 한다". (예외: pass + `explanationChecked` + 해설 `ai_draft` 면 해설 출처만 `ai_judged`) |
| 검산식 없음 | fail | 이전 `ai_review` 기록을 대체(`supersededAt`)하고 `passed:false` 기록을 만든다. **`contentState` 는 VERIFIED 그대로** |
| 검산식 없음 | pass | 기록 재작성 + VERIFIED 재설정(무변화) |
| 아무 문항 | skip | 아무것도 안 씀 |

- **즉 VERIFIED 를 강등하는 경로가 이 도구에 없다.** 강등은 `contentState` 를 바꾸는 pass 경로만 있다.
- **fail 적재는 해롭다**: 그 문항이 `ai_review` 통과로 VERIFIED 가 된 경우, 통과 기록이 대체되어 `verifiedByOf` 가 `null` —
  상태는 VERIFIED 인데 검증 근거 배지가 사라진 "근거 없는 VERIFIED" 가 된다. 문항은 출제 풀에 그대로 남는다.
- 실제 강등 경로는 사람 단건뿐이다: 관리자 화면의 강등 버튼 → `POST /api/admin/problems/[id]/review` `decision:"demote"`
  (VERIFIED → CHANGES_REQUESTED, `lib/review-decision.ts`). 사유는 `cas_recheck|low_correct_rate|human_review_undo` 셋뿐이고
  "자동 강등은 없다(출제·추천·오답복습 풀에 직결이라 파괴적)"가 코드 주석의 설계 의도다. MCP 에는 강등 도구가 없다.

**그래서 이 하네스는 보고서 + 수정 대상 목록으로 끝난다.** `review_verdicts_apply` 는 dryRun 도 부르지 않는다.
수정 대상은 사람이 화면에서 단건 강등·수정한다. 사유 코드에 "표본 감사"가 없다는 점은 🙋 결정 항목으로 올린다(코드 변경).

---

## Phase 0. 컨텍스트 확인 (메인)

1. **도구 확인**: `problem_list`·`problem_get`·`problem_figures_read` 가 보이는가. 없으면 "레포 폴더 새 세션 + MCP 서버 승인 +
   `MCP_REMOTE_TOKEN`" 안내 후 멈춘다.
2. **이어받기 판별**: `ls -d docs/claude/*문항QA* | tail -2` 의 최근 폴더.
   - `sample.jsonl` 만 → Phase 2. `stems/key` 있음·`solved/` 일부 → 미완 구분만 Phase 3.
   - `solved/` 다 있음·`compare.jsonl` 없음 → Phase 4. `compare.jsonl` 있음·`review/` 없음 → Phase 5.
   - "판정관만 다시" → Phase 5 만(지적 id). "이 감사 마감" → Phase 6.
3. **새 실행**: 폴더 `docs/claude/YYYY-MM-DD-문항QA-<범위약칭>/`(`_workspace` 규칙대로 산출 파일은 이 폴더 안).

## Phase 1. 표본 설계 (메인) — ⛔ 사용자 확인

1. 층(strata): 문서(교재·기출) × `answerType`(choice·numeric·short·expression) × 난이도 밴드 × `licenseStatus`.
   층별 모수는 `problem_list(state:"VERIFIED", …, limit:1)` 의 `total` 로 센다.
2. 기본 50건 — 비례 배분하되 **층마다 최소 2건**, 검증 근거가 CAS 가 아닌 문항(사람·AI 검수)을 절반 이상 싣는다(위험이 거기 있다).
   `essay` 는 비교기가 못 맞추므로 기본 제외(사용자가 원하면 판정관 직행 묶음으로).
3. 뽑기: 층마다 `offset = random(seed)` 로 `problem_list` 를 불러 id 를 고른다. seed 를 README 에 남겨 재현 가능하게.
4. `<out>/sample.jsonl`: `{"id","stratum","documentId","answerType","difficultyBand","licenseStatus","hasFigure"}`.
5. 층 표·건수·seed 를 보여 주고 **확인받는다**(CLAUDE.md: 혼자 결정하지 않는다).

## Phase 2. 추출 — `item-qa-extractor`(haiku) 1명

브리프: `<out>` · sample 경로. 산출 `stems.jsonl`·`key.jsonl`(같은 순서·같은 줄 수).
**첫 실행이면** 앞 10건을 같은 정의로 `model:"sonnet"` 한 번 더 → 두 결과 diff. 다르면 haiku 결과를 버리고 sonnet 으로 다시.
메인 확인: `wc -l` 일치 · stems 에 `answer`·`explanation` 키가 없음(`grep -c '"explanation"' stems.jsonl` = 0).

## Phase 3. 눈가림 풀이 — `item-qa-solver`(sonnet) ≤3명 병렬

브리프: `<out>` · 구분 문자 · 줄 구간 · `references/playbooks.md`. **key.jsonl 경로는 브리프에 쓰지 않는다.**
산출 `solved/<구분>.jsonl`. 끝나면 메인이 `cat solved/*.jsonl > solved/all.jsonl`.
한 명이 실패하면 1회만 이어서 재호출(마지막 id 다음부터).

## Phase 4. 비교 (메인, 스크립트)

`compare_answers.py` 실행 → `compare.jsonl` + 집계 한 줄(match·mismatch·unparsed·skip·missing·figureLeak).
`figureLeak` 인 match 는 근거가 약하므로 판정 대상에 함께 넣는다.

## Phase 5. 판정 — `item-qa-judge`(opus) 1명

대상 = `mismatch`·`unparsed`·`skip`·`missing` + `figureLeak` match. 대상이 0 이면 건너뛴다.
브리프: `<out>` · `references/playbooks.md` · 대상 id 목록(맨 뒤). 산출 `review/judged.jsonl`·`review/README.md`.
재검은 한 바퀴(지적 id 만 SendMessage).

## Phase 6. 보고서 → 마감 (메인)

1. `<out>/README.md` 에: 표본 설계(층 표·seed) · 일치율(전체·층별·검증 근거별) · 원인별 수 · **수정 대상 목록**(id · 문서·쪽 ·
   원인 · 고칠 내용) · 비교기 개선 후보.
2. ⛔ 사용자에게 수정 대상을 보여 준다: "화면에서 강등(`/admin/bank/problems/<id>` 강등 버튼)·수정할 문항입니다."
   쓰기는 하지 않는다(위 「판정 결과의 처리」).
3. 표본 오류율이 높은 층(예: 특정 교재 AI 검수 문항)은 다음 감사 범위 후보로 HANDOFF 에 한 줄.
4. 최종 응답 5줄: 표본 수 · 일치율 · 원인별 수 · 수정 대상 수 · 다음 범위 제안.

---

## 데이터 흐름

```
problem_list(층별 total·offset) ─► sample.jsonl ─⛔확인
      │
extractor(haiku) ─► problem_get ─┬─► stems.jsonl (지문·보기·그림 슬롯) ──► solver×≤3 ─► solved/*.jsonl
                                 └─► key.jsonl   (정답·해설·검증 근거) ─┐        │
                                                                        ▼        ▼
                                                     compare_answers.py ─► compare.jsonl
                                                                        │ mismatch·unparsed·skip·leak
                                                                        ▼
                                                     judge(opus) ─► review/judged.jsonl · README
                                                                        │
                                                     메인 보고서 + 수정 대상 목록 ─► 🙋 사람이 화면에서 강등·수정
```

## 에러 핸들링

| 상황 | 대응 |
| ---- | ---- |
| MCP 도구 없음 | 멈추고 연결 안내 |
| 솔버가 key·problem_get 을 봤다고 보고 | 그 id 는 판정 대상으로 보내고 일치 집계에서 뺀다(눈가림 파기) |
| haiku 추출이 sonnet 과 다름 | haiku 결과 폐기, sonnet 으로 재추출, 변경 이력에 남김 |
| `compare_answers.py` 가 sympy 없음으로 종료 | `.venv` 파이썬 경로로 다시. 설치하지 않는다 |
| unparsed 가 30% 넘음 | 비교기 한계 — 판정관 부담이 커지니 꼴을 모아 비교기 개선을 먼저 제안 |
| 판정관이 `key_error` 를 근거(반례·대입) 없이 냄 | 그 줄을 돌려보낸다(1회). 그래도 없으면 `ambiguous` 로 집계 |
| 표본 중 그사이 상태가 바뀐 문항 | 집계에서 빼고 README 에 적는다 |

## 테스트 시나리오

**정상:** "검증완료 문항 50개 표본으로 정답표 감사해 줘" → 층 표(쎈·RPM·기출 × 4형식 × 밴드, 비CAS 28건) 확인 →
추출(haiku, 첫 실행 sonnet diff 일치) → 솔버 2명 → 비교: match 41 · mismatch 5 · unparsed 2 · skip 2 →
판정관 9건: key_error 1 · transcription_error 1 · solver_error 4 · equivalent_notation 2 · undecidable 1 →
보고서 + 수정 대상 2건을 사용자에게 → 화면 강등은 사용자가.

**에러:** 솔버 한 명이 "그림이 해설 슬롯이라 정답 표시가 보였다"고 보고(figureLeak 3) → 그 3건은 match 여도 판정관에게 →
판정관이 원본 지면으로 대조해 2건 확인·1건 undecidable. 일치율 집계에서 leak 3건을 분리해 적는다.

## 트리거 검증

**should-trigger (8)**: "검증완료 문항 품질 표본 감사해 줘" · "VERIFIED 문항 정답표 틀린 거 있나 50개 뽑아 봐" ·
"정답 안 보고 다시 풀어서 대조해" · "눈가림 재풀이 돌려" · "AI 검수로 통과한 문항 믿을 만한지 확인" ·
"item-qa 이어서" · "문항 QA 판정관만 다시" · "이번 문항 감사 마감해 줘".

**should-NOT-trigger (6, near-miss)**:
- "검수 큐 문항 판정해서 승인까지" → `manual-extract` 판정관 / `/admin/review`(대상이 DRAFT·IN_REVIEW).
- "검산식 있는 문항 SymPy 로 다시 검산" → `verify_ids`(CAS 경로).
- "정답률 낮은 문항 강등" → 강등 버튼(`low_correct_rate`) — 통계 기반, 재풀이 아님.
- "그림 코드 맞는지 검수" → `figure-transcribe` 판정관.
- "이 설계 문서의 채점 로직 검토" → `design-review`.
- "OCR 엔진 수식 인식률 비교" → `ocr-bench`.

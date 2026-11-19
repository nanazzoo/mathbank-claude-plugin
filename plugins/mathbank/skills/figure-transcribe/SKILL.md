---
name: figure-transcribe
description: "로컬 PDF와 쪽 범위에서 원본 크롭·그림 DSL·렌더 PNG를 만들거나, MCP로 문제은행 그림을 전사·재검수할 때 사용한다. '그림 전사', '그림 다시 확인', '색상이 이상해', '그림 전사 이어서', '그림 판정관만 다시'에 적용한다. 지면 문항 전체 추출은 manual-extract."
---

> ⚠ **플러그인판 한계**: 렌더 눈 대조(`scripts/render_figure_dsl.ts`)·벡터 초안·`figure_mcp_apply.py` 는 문제은행 레포가 있어야 돈다. 레포 없는 PC 에서는 MCP 도구(`figure_transcribe_read`/`_apply`)만으로 전사·dryRun 까지 하고, 렌더 대조는 건너뛴 사실을 README 에 적는다.

# 그림 전사 — 배치 오케스트레이터

## 모드 선택

- **PDF 파일과 쪽 범위로 그림 전사** → [로컬 PDF 절차](references/local-pdf.md). 현재 세션이 바로 진행해 파일을 남긴다. MCP 연결·문서 ID·자산 ID·운영 장부가 필요 없다. 이 모드는 아래 MCP 배치 절차와 별개다.
- **문제은행 문서·자산·추출 잡의 그림 전사 및 재검수** → 아래 MCP 배치 절차. 운영 배치에서 좌표를 읽기 위한 참고 PDF는 해당 MCP 배치의 입력으로 쓴다.

## MCP 배치

에이전트가 **원본 크롭을 보고** 그림을 DSL로 옮기거나 기존 초안을 보완한다. 판정관이 `figure_render({assetId})`(저장된
코드를 서버가 다시 그린 그림)를 원본과 대조해 approve 한 것만 메인이 `figure_approve` 로 승인(READY)한다(2026-11-19 결정 1). 유료 LLM은 어디서도 부르지 않는다. 기존 이력 보완은 같은 이력에 저장한다.
2026-09-05~06 손 전사 배치(773·256건)의 절차와 함정을 굳혔다(`docs/claude/2026-09-0[56]-그림-*`).

**실행 모드: 서브 에이전트.** 전사관끼리 주고받을 것이 없고(문서별로 갈라 겹치지 않는다) 산출은 전부 파일이다.

| 에이전트             | 언제         | 수     | 모델   | 산출                                                    |
| -------------------- | ------------ | ------ | ------ | ------------------------------------------------------- |
| `figure-transcriber` | 범위 확정 후 | **≤3** | opus   | `<out>/out/<구분>.jsonl` · `<out>/render/<assetId>.png` |
| `figure-judge`       | DRAFT 적재 후 | 1      | sonnet | `<out>/review/verdicts.jsonl` · `<out>/review/README.md` |

- 모델: 전사는 원본 판독·좌표 실측·DSL 작성이라 opus. 판정은 원본↔렌더 **눈 대조**(스크린샷 판독)라 CLAUDE.md
  토큰 원칙대로 sonnet. 판정관이 명백한 결함을 놓치는 일이 반복되면 opus 로 올리고 변경 이력에 남긴다.
- 전사관 3명 상한(CLAUDE.md 토큰 원칙). 한 명이 한 배치에 **최대 20건**(MCP 한 번 상한과 같다).
- 그림 공통 함정은 `references/lessons.md` — **전사관·판정관 브리프에 반드시 가리킨다.**
- 라벨 재검수는 F-36~38과 `references/review.md`의 글자 중심·anchor·원본 크기·glyphPx 기준으로 진행한다. 작업 기록에는 이번 전사 주체·방식·규칙 버전을 남기고, 추출 잡 모델과 그림의 최종 전사자를 구분한다.
- 어휘(요소·필드·한계값)의 단일 소스는 `figure_transcribe_read` 가 주는 `rules` 다. 스킬·에이전트에 어휘를 베껴 적지 않는다
  — 검증기와 옮겨 적는 쪽의 어휘가 갈린다.

---

## 도구 — 어느 기계에서나 같은 MCP

| 단계 | 도구 |
| ---- | ---- |
| 대상 | `figure_transcribe_read`(`documentId`·`afterAssetId`·`limit≤20` — 크롭 이미지 + `imageSize` + `rules`) · `document_list` |
| 벡터 초안(PC, RPM 18·19) | `npx tsx scripts/figure_vector_skeleton.ts --pdf <pdf> --document <id> --after <커서> --limit 5 --out-dir <out>/render` — PDF 벡터 경로 → `<id>.draft.json`(라벨 `text:""`) · `<id>.orig.png`. PyMuPDF·`MCP_REMOTE_TOKEN` 필요, 실패하면 기존 경로 |
| 렌더 눈 대조 | MCP `figure_render({assetId, code})`(서버가 그 그림의 크기·glyphPx 를 적재 때와 같이 정한다 — 원본 크기를 손으로 넘기지 않는다). 레포·Chrome이 있으면 `npx tsx scripts/render_figure_dsl.ts --batch <batch.jsonl> --out-dir <out>/render --sheet <sheet.png>` 접촉 시트로 묶어 대조 |
| 묶음 dryRun | `python -I scripts/figure_mcp_apply.py <out> <구분> --ids=<…>` — 기본이 판정만, jsonl `dryRun` 필드에 되씀 |
| 검증·적재 | `figure_transcribe_apply`(기본 dryRun — 판정만, `dryRun:false` 면 DRAFT 적재. 원본 PNG 는 안 건드린다) · 배치 적재는 `scripts/figure_mcp_apply.py … --apply`(같은 도구, 요약만. `--apply` 없으면 판정만) |
| 판정 입력 | `problem_figures_read`(문항의 원본 크롭) + **`figure_render({assetId})`**(code 없이 — 저장된 코드를 서버가 다시 그린 그림). 전사관의 `render/<assetId>.png` 는 참고만 |
| 승인 | `figure_approve`(기본 dryRun — 계획만, `dryRun:false` 면 READY. `action:"useOriginal"` 은 되돌리기) — 2026-10-22 사용자 결정으로 MCP 에 열었다. 검수 큐 `/admin/bank/figures` 와 같은 라우트·같은 판정. 판정관이 `figure_render({assetId})` 로 대조한 **approve 만** 올린다 |

⚠ MCP 검증 실패는 `FAILED` 로 굳지 않는다(에이전트가 DSL 을 잘못 쓴 것이지 못 그리는 그림이 아니다 — 굳히면 유료
배치가 그 자산을 영원히 건너뛴다). 그래서 **건너뛴 그림은 목록에 남는다** → 커서(`afterAssetId`)로 넘어간다.

---

## Phase 0. 컨텍스트 확인 (메인)

0. **대상 분기**: 신규 자산 / DRAFT·FAILED 재전사 / 등록 전 추출 잡을 구분한다. 기존 그림 재검수는
   [references/review.md](references/review.md)의 도구 경로로 바로 진행한다. READY는 읽고 차이를 보고할 뿐 덮어쓰지 않는다.
   사용자가 정한 범위와 저장 승인은 유지하며, 재검수 때문에 새 잡을 만들거나 문항을 등록하지 않는다.
1. **선택한 대상의 도구 확인**: 자산은 `figure_transcribe_read/apply`, 등록 전 잡은 `extract_job_get/items_update`와
   `extract_pages_read`를 확인한다. 원본 대조에는 MCP `figure_render` 또는 로컬 렌더 CLI를 쓴다. 해당 도구가 없으면
   MCP 연결·승인·도구 노출 상태를 확인한다. 로컬 레포·CLI가 없다는 이유만으로 MCP 전사를 중단하지 않는다.
2. **커서 지원 확인**: `figure_transcribe_read(afterAssetId: 2000000000, limit: 1)` → `returned` 가 0 이어야 한다.
   그림이 돌아오면 필터가 지원되지 않는 상태로 보고한다. 앱 수정·배포는 `deploy` 스킬의 별도 작업이다.
   MCP 데이터 수정과 앱 배포를 구분해 설명하고, 이 전사 절차에서 임의로 재시작하지 않는다.
3. **장부**: `docs/claude/그림전사-장부.md`. 없으면 만든다(아래 형식). 있으면 문서별 커서·남은 수를 읽는다.
4. **이어받기 판별**: 가장 최근 배치 폴더(`ls -d docs/claude/*그림전사* | tail -2`)를 본다.
   - `out/*.jsonl` 이 일부만 → 미완 구분만 Phase 2(jsonl 마지막 assetId 를 커서로).
   - 사전 점검까지 했는데 적재 안 됨 → Phase 3 의 승인 질문부터.
   - 적재했는데 `review/` 없음 → Phase 4. 판정 끝 → Phase 5.
   - "판정관만 다시" → Phase 4 만.
5. **범위 제안**: 장부(없으면 `document_list` 의 문서마다 `figure_transcribe_read(documentId, limit:1)` 의 `total`)에서
   남은 수가 큰 **문제집(쎈·RPM)부터** 고른다 — 크롭이 나쁜 AI허브 자산이 id 앞쪽에 몰려 있다(HANDOFF 09-15).
   구분 ≤3: 한 문서가 크면 한 문서를 커서 구간으로 나누지 말고 **문서 단위**로 준다(구간을 나누면 건너뛴 그림 때문에
   구간 경계가 어긋난다). 문서·구분·배치 폴더명을 **한 번에 보여 주고 확인받는다**(CLAUDE.md: 혼자 결정하지 않는다).
   폴더명: `docs/claude/YYYY-MM-DD-그림전사-<교재약칭들>-<n>`.

**장부 형식** (`docs/claude/그림전사-장부.md`):

```markdown
# 그림 전사 장부 — 문서별 커서

| 문서 id | 교재 | 남음(total) | 커서(afterAssetId) | 건너뜀(unsupported) | 마지막 배치 |
| ------- | ---- | ----------- | ------------------ | ------------------- | ----------- |
```

커서 = 그 문서에서 **이미 본 마지막 assetId**. 적재된 그림은 코드가 생겨 목록에서 빠지고, 건너뛴 그림만 커서 앞에
남는다. 건너뛴 그림을 나중에 다시 보려면 커서를 0 으로.

## Phase 1. 준비 (메인)

`<out>/` 를 만들고 `<out>/README.md` 머리에: 날짜 · 구분 표(구분 문자 · 문서 id · 교재 · 시작 커서 · 목표 건수 ≤20 ·
**벡터 문서면 `pdf` 경로**) · 장부 발췌 · 빈 「진행 로그」. `render/` 는 커밋하지 않는다(.gitignore `docs/claude/*그림전사*/render/`).

`pdf` 칸은 `document_get`으로 현재 문서명·원본 파일을 확인하고, 같은 파일·쪽임을 대조한 벡터 문서에만 적는다.
문서 번호에 교재명이나 PDF 경로를 고정하지 않는다. 확인된 로컬 파일이 없거나 래스터 문서면 비우고 MCP 이미지로 간다.

## Phase 2. 전사 — `figure-transcriber` ≤3명 병렬

구분마다 한 명, `run_in_background: true` 로 한 메시지에 함께 띄운다.
브리프(짧게, 경로만): `<out>` · 구분 문자 · 문서 id · 시작 커서 · 목표 건수 · `references/lessons.md`.

전사관은 **5건 묶음마다** (벡터 문서면 초안 받기 →) DSL N개 작성 → **일괄 렌더 1회 + 접촉 시트 1장으로 원본과 눈 대조**
(최대 2회 고침) → `figure_mcp_apply.py`(`--apply` 없이) 묶음 판정 1회 → `out/<구분>.jsonl` append 까지 한다. **실제 적재는 하지 않는다.**

| 5건 묶음당 턴(전사관) | 전(2026-10-10 1~4배치 실측) | 후(안 1) | 후(안 1+2, 벡터 문서) |
| --- | --- | --- | --- |
| 읽기 `figure_transcribe_read` | 1 | 1 | 1 |
| 초안 `figure_vector_skeleton`(+A형 `--unit` 재실행) | — | — | 1~2 |
| DSL 쓰기 | 5(자산마다 파일) | 1(묶음 jsonl) | 1(라벨만 채움) |
| 렌더 Bash + PNG Read | 10(자산마다 2) | 2(일괄 렌더 + 시트 1장) | 2 |
| dryRun | 5(자산마다 MCP) | 1(`--ids`, 기본 미리보기) | 1 |
| jsonl append | 5 | 1 | 1 |
| 고침 왕복(평균) | 2~4 | 1~2 | 1 |
| **합계 / 그림당** | **약 28~30 / 약 3**(실측 Bash 26~69·Read 17~40·apply 10~42 /20건) | **약 7~8 / 약 1.5**(추정) | **약 8~9 / 약 1.7**, 좌표 실측 0(추정) |

벡터 초안은 턴보다 **좌표 실측(가장 긴 생각)과 고침 왕복**을 줄인다 — 좌표가 PDF 그대로라 시트 대조가 한 번에 맞는다
(표본 3그림: `docs/claude/2026-10-12-수동추출-그림전사-점검/vector-skeleton/sheet.png`). 실측 수치는 첫 배치 마감 때 갱신한다. 끝나면 **10줄 이내 보고**만 돌려준다.
메인은 보고를 README 「진행 로그」에 `### <구분> 완료` 로 append 하고 **에이전트 id 를 기록**한다(판정관 `fix` 를 같은
전사관에게 `SendMessage` 로 돌려야 맥락을 다시 싣지 않는다). 전사관은 dryRun 도 `dryRun:true` 를 **명시**한다(F-23).

한 명이 실패하면 1회만 다시 띄운다(jsonl 마지막 assetId 다음부터). 또 실패하면 보고하고 나머지는 진행.

## Phase 3. 사전 점검 → 적재 (메인)

1. 구분별 수치를 모은다: `fix`(코드 씀)·`unsupported`(사유별)·dryRun 거부·렌더 대조 2회 실패.
2. dryRun 거부가 남은 구분 → 그 전사관에게 **그 assetId 만** 1회 재호출. 재검 루프는 한 바퀴(CLAUDE.md).
3. 구분별 fix/unsupported/거부 수를 확인한다. 요청·이전 승인에 보완 저장이 포함되면 그 범위에서 진행한다.
   검토만 요청한 경우에는 DRAFT 적재 여부를 한 번 묻는다. 같은 승인 범위의 MCP 쓰기는 연달아 해도 된다.
   이는 DRAFT 저장이고 READY 승인이 아니다(승인은 Phase 4 판정관 approve 뒤 Phase 5).
4. **메인이 직접 적재한다 — `scripts/figure_mcp_apply.py` 로**:
   `python -I scripts/figure_mcp_apply.py <out> A B C`(기본 미리보기) → 수치 확인 → `--apply` 를 붙여 다시. 결과는 `out/<구분>.loaded.txt`(이어 쓴다 — `--ids` 없는 재실행은 이미 ok 인 자산을 건너뛴다, 2026-11-19).
   수십 건을 MCP 도구로 한 건씩 부르면 응답이 쌓인다(2026-11-19 부터 `renderedSrc` 는 도구가 뺀다) — 스크립트는
   같은 도구를 JSON-RPC 로 불러 요약만 준다(`MCP_REMOTE_TOKEN` 필요). 서브에이전트의 쓰기는 auto mode 분류기가 들쭉날쭉 막으니
   (F-23) 사용자 승인을 받은 메인이 돌린다. 실패 id 는 README 에.
   로컬 레포·스크립트를 쓸 수 없으면 같은 `figure_transcribe_apply`를 MCP로 직접 호출하고 결과를 요약한다.

## Phase 4. 판정 — `figure-judge` 1명

브리프: `<out>` · 적재된 assetId 목록(`out/*.jsonl` 의 fix 중 적재 성공) · `references/lessons.md` · `references/review.md`.
판정관은 문항마다 `problem_figures_read` 의 원본과 `figure_render({assetId})`(저장본을 서버가 다시 그린 그림)를 대조해 `approve` / `fix` / `keep_original`
을 `review/verdicts.jsonl` 에 쓴다. **적재·승인은 하지 않는다.** 10줄 보고.

- `fix` → 그 구분 전사관에게 `SendMessage`(판정관 note 를 그대로) → 고친 코드 재렌더·dryRun·jsonl 줄 교체 →
  **메인이 적재**(`figure_mcp_apply.py <out> <구분> --ids=<id,…> --apply` → `.reloaded.txt`). 한 바퀴만.
  두 번째에도 판정관 기준을 못 넘으면 `keep_original` 로 돌린다.
- `keep_original` → 승인 목록에서 뺀다(DRAFT 로 두면 원본 PNG 가 계속 나간다).
- 메인은 [references/review.md](references/review.md)에 따라 저장 후 여러 그림을 같은 실제 화면에서 대조한다.
  단독 렌더만 맞으면 `코드 검증 완료`, 브라우저를 못 봤으면 `실제 표시 미확인`으로 보고에 남긴다(승인 목록에서는 빼지 않는다 — 2026-11-19 결정).

## Phase 5. 승인 → 마감 (메인)

1. **승인** — 판정관이 `figure_render({assetId})` 로 대조해 `approve` 한 id 만 `figure_approve(ids)` dryRun 으로 세고
   (`skippedIds` 가 있으면 그 id 를 다시 본다) `dryRun:false` 로 READY 로 올린다(2026-10-22 "승인도 다 열어줘", 2026-11-19 결정 1). 목록(id·문항)을 `review/README.md` 맨 위에 두고, `keep_original` 은 올리지 않는다.
   사용자가 "승인은 내가" 라고 한 배치면 종전대로 검수 큐 `/admin/bank/figures` 경로만 준다.
2. `<out>/README.md` 끝에 `## 마감 (YYYY-MM-DD)` 5줄: 전사(구분별 fix/unsupported) / 판정(approve·fix·keep) /
   적재 DRAFT 수 / 새 함정 / 확인 요청(크롭 잘림 등 원본 문제).
3. 장부 갱신: 문서별 커서 = 그 구분 jsonl 의 마지막 assetId, 남음 = 마감 시점 `figure_transcribe_read(documentId, limit:1)`
   의 `total`, 건너뜀 누적.
4. 그림을 가리지 않는 새 함정이면 `references/lessons.md` 에 한 줄(F-번호).
5. `docs/HANDOFF.md` ★ 절의 그림 실측(코드 없음 N)을 갱신.
6. 커밋은 사용자에게 묻고 한다 — 배치 폴더(`render/` 제외)·장부·lessons 를 커밋해야 다른 기기가 이어받는다.
7. 최종 응답 5줄: 대상 그림 수 · 코드 사용/원본 유지 수와 사유 · 코드 검증/실제 표시 확인 수 · 이력·등록 상태 · 승인 요청/남은 일.
8. "이번 배치에서 하네스에 고칠 점이 있었나요?" 한 줄. 피드백은 해당 에이전트/스킬에 반영하고 CLAUDE.md
   「하네스: 그림 전사」 변경 이력에 남긴다.

---

## 데이터 흐름

```
장부(문서별 커서) ─► README 구분 표(≤3, 문서 단위)
      │
transcriber×≤3 ─► figure_transcribe_read(documentId, afterAssetId) ─► DSL ─► render_figure_dsl --size ─► 눈 대조
      │                                                                         └─► figure_transcribe_apply(dryRun)
      └─► out/<구분>.jsonl · render/<id>.png ─► README 진행 로그
      │
⛔ 사용자 승인 ─► 메인이 apply(dryRun:false) = DRAFT
      │
judge ─► problem_figures_read(원본) ↔ figure_render({assetId}) ─► review/verdicts.jsonl
      │            └─ fix ─► transcriber 1회 수정 ─► 재적재
      │
메인 figure_approve(approve 만, READY) ─► README 마감 · 장부 커서 · lessons · HANDOFF · 커밋
```

## 에러 핸들링

| 상황 | 대응 |
| ---- | ---- |
| MCP 도구가 안 보임 | 멈추고 "레포 폴더 새 세션 + 서버 승인 + `MCP_REMOTE_TOKEN`" 안내 |
| 커서 확인에서 그림이 돌아옴 | 운영 앱 옛 이미지 — 재빌드 필요, 사용자 확인 전 진행 안 함 |
| 렌더 CLI 가 Chrome 을 못 찾음 | MCP `figure_render`로 원본 대조를 계속한다. 둘 다 못 쓰면 코드 검증 불가로 보고하고 적재하지 않는다 |
| 전사관 실패/중단 | 1회 재호출(jsonl 이어 쓰기) → 또 실패면 보고, 나머지 구분은 진행 |
| 한 문서에 20건 넘게 남음 | 이번 배치는 20건까지. 장부 커서로 다음 배치에 이어서 |
| 원본 크롭이 잘림·답이 원본에 없음 | 원본대로 전사하고 「확인 요청」에(지어내지 않는다 — 2088·2089·2092 선례) |
| 판정 `fix` 두 번째 실패 | `keep_original` — 원본 PNG 가 나가므로 학생이 잃는 것은 없다 |

## 테스트 시나리오

**정상(맥):** "그림 전사 다음 배치 돌려줘" → MCP 도구·커서 확인 → 장부에서 쎈 공통수학1(남음 64)·RPM 미적분Ⅰ(남음 41)·
쎈 대수(남음 38) 제안, 확인받음 → 전사관 3명 병렬, 각 20건: fix 52 · unsupported 8(회화적 삽화 3·곡선 경계 색칠 5) →
사용자 "올려" → 메인이 DRAFT 52 적재 → 판정관: approve 47 · fix 3 · keep 2 → fix 3 재적재 → 승인 요청(50건) →
장부 커서 갱신·마감·커밋. PC 에서도 같은 문장으로 같은 흐름이 돈다.

**에러:** 운영 앱이 옛 이미지 → 커서 확인에서 그림 1건이 돌아옴 → "PC 에서 앱 재빌드가 필요합니다(서비스 잠깐 끊김).
진행할까요?" 로 멈춘다. 전사관을 띄우지 않는다.

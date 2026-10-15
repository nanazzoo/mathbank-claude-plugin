---
name: figure-transcribe
description: "아직 도형 코드가 없는 문항 그림(크롭 PNG)을 유료 vision 없이 에이전트가 직접 보고 도형 DSL(figure-dsl/v0)로 옮겨 적는 '그림 전사' 배치를 처음부터 끝까지 돌리는 오케스트레이터. 윈도우 PC·맥 공통(MCP). 범위(문서별 커서) 결정 → 전사관 ≤3 병렬(렌더 눈 대조·dryRun) → 사용자 승인 → DRAFT 적재 → 판정관 사전 검수 → 사람 승인(READY) 요청 → 장부 갱신. '그림 전사', '그림 코드 전사', '전사 전 그림', '미전사 그림', '그림 DSL 로 옮겨', '그림 전사 다음 배치', '그림 전사 이어서/재실행', '쎈/RPM 그림 전사', 'figure_transcribe', '그림 판정관만 다시', '이 그림 배치 마감' 요청 시 반드시 이 스킬을 사용할 것. 이미 코드가 있는 그림의 검수·승인(검수 큐 `/admin/bank/figures`)·유료 vision 재전사 버튼·FAILED 재시도·그림 편집기·렌더러 수정은 이 스킬이 아니다. 지면 문항 전사는 manual-extract."
---

> ⚠ **플러그인판 한계**: 렌더 눈 대조(`scripts/render_figure_dsl.ts`)·벡터 초안·`figure_mcp_apply.py` 는 문제은행 레포가 있어야 돈다. 레포 없는 PC 에서는 MCP 도구(`figure_transcribe_read`/`_apply`)만으로 전사·dryRun 까지 하고, 렌더 대조는 건너뛴 사실을 README 에 적는다.

# 그림 전사 — 배치 오케스트레이터

`figureCode` 가 없는 지문 그림(2026-10-10 실측 **817건**)을 에이전트가 **원본 크롭을 보고** DSL 로 옮겨 DRAFT 로
적재하고, 판정관이 사전 검수한 뒤 사람이 승인(READY)하게 넘긴다. 유료 LLM 은 어디서도 부르지 않는다.
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
- 어휘(요소·필드·한계값)의 단일 소스는 `figure_transcribe_read` 가 주는 `rules` 다. 스킬·에이전트에 어휘를 베껴 적지 않는다
  — 검증기와 옮겨 적는 쪽의 어휘가 갈린다.

---

## 도구 — 어느 기계에서나 같은 MCP

| 단계 | 도구 |
| ---- | ---- |
| 대상 | `figure_transcribe_read`(`documentId`·`afterAssetId`·`limit≤20` — 크롭 이미지 + `imageSize` + `rules`) · `document_list` |
| 벡터 초안(PC, RPM 18·19) | `npx tsx scripts/figure_vector_skeleton.ts --pdf <pdf> --document <id> --after <커서> --limit 5 --out-dir <out>/render` — PDF 벡터 경로 → `<id>.draft.json`(라벨 `text:""`) · `<id>.orig.png`. PyMuPDF·`MCP_REMOTE_TOKEN` 필요, 실패하면 기존 경로 |
| 렌더 눈 대조 | 묶음: `npx tsx scripts/render_figure_dsl.ts --batch <batch.jsonl> --out-dir <out>/render --sheet <sheet.png>` → 접촉 시트 1장 · 한 건: `… <dsl.json> <out.png> --size <W>x<H>` (DB 안 씀, Chrome 필요) |
| 묶음 dryRun | `python -I scripts/figure_mcp_apply.py <out> <구분> --dry --ids=<…>` — 판정만, jsonl `dryRun` 필드에 되씀 |
| 검증·적재 | `figure_transcribe_apply`(기본 dryRun — 판정만, `dryRun:false` 면 DRAFT 적재. 원본 PNG 는 안 건드린다) · 배치 적재는 `scripts/figure_mcp_apply.py`(같은 도구, 요약만) |
| 판정 입력 | `problem_figures_read`(문항의 원본 크롭) + 전사관이 남긴 `render/<assetId>.png` |
| **사람만** | 승인(READY) — 검수 큐 `/admin/bank/figures`. MCP 는 일부러 열지 않는다 |

⚠ MCP 검증 실패는 `FAILED` 로 굳지 않는다(에이전트가 DSL 을 잘못 쓴 것이지 못 그리는 그림이 아니다 — 굳히면 유료
배치가 그 자산을 영원히 건너뛴다). 그래서 **건너뛴 그림은 목록에 남는다** → 커서(`afterAssetId`)로 넘어간다.

---

## Phase 0. 컨텍스트 확인 (메인)

1. **도구 확인**: `figure_transcribe_read`·`figure_transcribe_apply` 가 보이는가. 없으면 멈추고 "레포 폴더에서 새 세션 +
   MCP 서버 승인 + `MCP_REMOTE_TOKEN`" 을 안내한다(홈 폴더 세션이면 안 잡힌다).
2. **커서 지원 확인**: `figure_transcribe_read(afterAssetId: 2000000000, limit: 1)` → `returned` 가 0 이어야 한다.
   그림이 돌아오면 운영 앱이 옛 이미지다(필터를 무시한다) — PC 에서 `docker compose up -d --build app` 이 필요하다.
   서비스가 잠깐 끊기니 **사용자에게 묻는다.** 옛 이미지로는 병렬·커서가 안 되니 진행하지 않는다.
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

`pdf` 칸은 그림이 벡터인 문서만 적는다 — 지금은 RPM 대수(18) `C:/mathbank-data/uploads/documents/dac2f18a-eb30-414c-a70b-617e39da9005.pdf`,
RPM 미적분I(19) `…/381240af-7448-4e1a-985d-f7c4908e3919.pdf`(PC 에만 있다). 쎈(스캔)·시험지(래스터 임베드)는 비운다
(점검 04 「벡터 그림」 실측). 맥이면 비운다 — 전사관이 기존 경로로 간다.

## Phase 2. 전사 — `figure-transcriber` ≤3명 병렬

구분마다 한 명, `run_in_background: true` 로 한 메시지에 함께 띄운다.
브리프(짧게, 경로만): `<out>` · 구분 문자 · 문서 id · 시작 커서 · 목표 건수 · `references/lessons.md`.

전사관은 **5건 묶음마다** (벡터 문서면 초안 받기 →) DSL N개 작성 → **일괄 렌더 1회 + 접촉 시트 1장으로 원본과 눈 대조**
(최대 2회 고침) → `figure_mcp_apply.py --dry` 묶음 판정 1회 → `out/<구분>.jsonl` append 까지 한다. **실제 적재는 하지 않는다.**

| 5건 묶음당 턴(전사관) | 전(2026-10-10 1~4배치 실측) | 후(안 1) | 후(안 1+2, 벡터 문서) |
| --- | --- | --- | --- |
| 읽기 `figure_transcribe_read` | 1 | 1 | 1 |
| 초안 `figure_vector_skeleton`(+A형 `--unit` 재실행) | — | — | 1~2 |
| DSL 쓰기 | 5(자산마다 파일) | 1(묶음 jsonl) | 1(라벨만 채움) |
| 렌더 Bash + PNG Read | 10(자산마다 2) | 2(일괄 렌더 + 시트 1장) | 2 |
| dryRun | 5(자산마다 MCP) | 1(`--dry --ids`) | 1 |
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
3. ⛔ **사용자에게 한 번 묻는다**: 구분별 fix/unsupported/거부 수 → "DRAFT 로 적재할까요?".
   (DRAFT 는 학생·인쇄물에 안 나가고 원본 PNG 가 계속 나간다 — 되돌림 부담은 작지만 쓰기라서 묻는다.)
   승인이 나면 이 배치의 MCP 쓰기를 연달아 해도 된다(배치가 바뀌면 다시 묻는다).
4. **메인이 직접 적재한다 — `scripts/figure_mcp_apply.py` 로**:
   `python -I scripts/figure_mcp_apply.py <out> A B C --dry` → 수치 확인 → `--dry` 없이 다시. 결과는 `out/<구분>.loaded.txt`.
   MCP 도구로 한 건씩 부르면 응답마다 `renderedSrc`(SVG 수십 KB)가 실려 수십 건이면 컨텍스트가 터진다(2배치 실측) — 스크립트는
   같은 도구를 JSON-RPC 로 불러 요약만 준다(`MCP_REMOTE_TOKEN` 필요). 서브에이전트의 쓰기는 auto mode 분류기가 들쭉날쭉 막으니
   (F-23) 사용자 승인을 받은 메인이 돌린다. 실패 id 는 README 에.

## Phase 4. 판정 — `figure-judge` 1명

브리프: `<out>` · 적재된 assetId 목록(`out/*.jsonl` 의 fix 중 적재 성공) · `references/lessons.md`.
판정관은 문항마다 `problem_figures_read` 의 원본과 `render/<assetId>.png` 를 대조해 `approve` / `fix` / `keep_original`
을 `review/verdicts.jsonl` 에 쓴다. **적재·승인은 하지 않는다.** 10줄 보고.

- `fix` → 그 구분 전사관에게 `SendMessage`(판정관 note 를 그대로) → 고친 코드 재렌더·dryRun·jsonl 줄 교체 →
  **메인이 적재**(`figure_mcp_apply.py <out> <구분> --ids=<id,…>` → `.reloaded.txt`). 한 바퀴만.
  두 번째에도 판정관 기준을 못 넘으면 `keep_original` 로 돌린다.
- `keep_original` → 사람 승인 목록에서 뺀다(DRAFT 로 두면 원본 PNG 가 계속 나간다).

## Phase 5. 사람 승인 요청 → 마감 (메인)

1. **승인은 사용자에게 요청한다** — 검수 큐 `/admin/bank/figures` 에서 이 배치의 `approve` id 들. 목록(id·문항)을
   `review/README.md` 맨 위에 두고 그 경로를 준다. `keep_original` 은 승인하지 말라고 함께 적는다.
2. `<out>/README.md` 끝에 `## 마감 (YYYY-MM-DD)` 5줄: 전사(구분별 fix/unsupported) / 판정(approve·fix·keep) /
   적재 DRAFT 수 / 새 함정 / 확인 요청(크롭 잘림 등 원본 문제).
3. 장부 갱신: 문서별 커서 = 그 구분 jsonl 의 마지막 assetId, 남음 = 마감 시점 `figure_transcribe_read(documentId, limit:1)`
   의 `total`, 건너뜀 누적.
4. 그림을 가리지 않는 새 함정이면 `references/lessons.md` 에 한 줄(F-번호).
5. `docs/HANDOFF.md` ★ 절의 그림 실측(코드 없음 N)을 갱신.
6. 커밋은 사용자에게 묻고 한다 — 배치 폴더(`render/` 제외)·장부·lessons 를 커밋해야 다른 기기가 이어받는다.
7. 최종 응답 5줄: 배치 · fix/unsupported · 판정 · 승인 요청 수 · 다음 배치 범위.
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
judge ─► problem_figures_read(원본) ↔ render/<id>.png ─► review/verdicts.jsonl
      │            └─ fix ─► transcriber 1회 수정 ─► 재적재
      │
🙋 /admin/bank/figures 승인(READY) ─► README 마감 · 장부 커서 · lessons · HANDOFF · 커밋
```

## 에러 핸들링

| 상황 | 대응 |
| ---- | ---- |
| MCP 도구가 안 보임 | 멈추고 "레포 폴더 새 세션 + 서버 승인 + `MCP_REMOTE_TOKEN`" 안내 |
| 커서 확인에서 그림이 돌아옴 | 운영 앱 옛 이미지 — 재빌드 필요, 사용자 확인 전 진행 안 함 |
| 렌더 CLI 가 Chrome 을 못 찾음 | `CHROME_PATH` 지정 안내. 렌더 없이 dryRun 만으로 적재하지 않는다(눈 대조가 이 하네스의 품질 근거) |
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

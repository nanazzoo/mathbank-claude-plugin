"""item-qa 정답 비교기 — 정답표(key.jsonl)와 눈가림 풀이(solved.jsonl)를 id 로 맞춰 대조한다.

판단이 필요 없는 대조(번호 정규화·식 동치)는 LLM 이 아니라 이 스크립트가 한다(토큰 원칙 T1).
불일치·파싱 실패·skip 만 판정관(opus)에게 넘긴다(T2 cascade).

    python -I compare_answers.py --key key.jsonl --solved solved.jsonl --out compare.jsonl
    python -I compare_answers.py --selftest

입력 한 줄 형식
    key.jsonl    {"id","answerType","responseType","correctChoiceKeys":[...],"acceptedValues":[...]}
    solved.jsonl {"id","status":"solved|skip","answer":"<문자열>","confidence":"high|mid|low",
                  "usedFigure":bool,"figureLeak":bool,"note":"..."}
출력 한 줄 형식
    compare.jsonl {"id","result":"match|mismatch|unparsed|skip|missing","method","key","solved",
                   "confidence","figureLeak","detail"}

표준 라이브러리 + sympy 만 쓴다. ⚠ sympy 의 parse_expr 는 내부에서 eval 을 쓴다 — 입력은 우리 DB 의
정답표와 우리 에이전트의 풀이뿐이라는 전제로만 돌린다(외부에서 받은 파일을 넣지 않는다).
"""

from __future__ import annotations

import argparse
import io
import json
import random
import re
import sys
import warnings
from pathlib import Path

try:
    import sympy
    from sympy.parsing.sympy_parser import (
        convert_xor,
        implicit_multiplication_application,
        parse_expr,
        standard_transformations,
    )
except ImportError:  # pragma: no cover - 환경 안내만
    sys.exit("sympy 가 없다 — 레포 .venv 의 파이썬으로 돌려라(SKILL.md 「도구」 절).")

# ── 상수 ────────────────────────────────────────────────────────────────
CHOICE_TYPES = {"choice"}
CIRCLED_DIGITS = {chr(0x2460 + i): str(i + 1) for i in range(10)}  # ①~⑩ → 1~10
NUMERIC_SAMPLE_POINTS = 5
NUMERIC_REL_TOL = 1e-9
MAX_SIMPLIFY_LENGTH = 200  # 이보다 긴 식은 simplify 가 오래 걸릴 수 있어 수치 대입만 한다
# 파이썬 식별자는 한글을 허용해 '풀이 참조' 가 기호 곱으로 파싱된다 — 한글이 섞이면 식이 아니다.
HANGUL = re.compile(r"[ㄱ-ㆎ가-힣]")
TRANSFORMS = standard_transformations + (implicit_multiplication_application, convert_xor)

LATEX_REPLACEMENTS = [
    (r"\dfrac", r"\frac"),
    (r"\tfrac", r"\frac"),
    (r"\left", ""),
    (r"\right", ""),
    (r"\cdot", "*"),
    (r"\times", "*"),
    (r"\div", "/"),
    (r"\pi", " pi "),
    (r"\infty", " oo "),
    (r"\ln", " log"),
    (r"\,", ""),
    (r"\;", ""),
    (r"\!", ""),
    ("−", "-"),
    ("×", "*"),
    ("÷", "/"),
    ("π", " pi "),
    ("√", "sqrt"),
]


# ── 정규화 ──────────────────────────────────────────────────────────────
def normalize_choice(raw: object) -> str:
    """'③', '3번', '(3)', ' 3 ' → '3'. 번호가 없으면 공백만 지운 원문."""
    text = str(raw).strip()
    for circled, digit in CIRCLED_DIGITS.items():
        text = text.replace(circled, digit)
    digits = re.findall(r"\d+", text)
    return digits[0] if len(digits) == 1 else re.sub(r"\s+", "", text)


def choice_set(values: object) -> frozenset[str]:
    """정답 번호 묶음 — '2, 4' 처럼 한 문자열에 여러 개가 와도 나눈다."""
    items = values if isinstance(values, list) else [values]
    keys: set[str] = set()
    for item in items:
        for part in re.split(r"[,/\s]+|와|과|및", str(item)):
            if part.strip():
                keys.add(normalize_choice(part))
    return frozenset(keys)


def _replace_braced_command(text: str, command: str, render) -> str:
    """\\frac{a}{b} 처럼 중괄호 인자를 받는 명령을 안쪽부터 풀어 바꾼다."""
    pattern = re.compile(re.escape(command) + r"\{([^{}]*)\}" * render.__code__.co_argcount)
    previous = None
    while previous != text:
        previous = text
        text = pattern.sub(lambda match: render(*match.groups()), text)
    return text


def latex_to_sympy_text(raw: str) -> str:
    """간단 LaTeX → sympy 식 문자열. sympy.parsing.latex(antlr 필요)가 없을 때의 폴백."""
    text = raw.strip().strip("$").strip()
    for latex, plain in LATEX_REPLACEMENTS:
        text = text.replace(latex, plain)
    # 지수의 중괄호를 먼저 풀어야 \frac{x^{2}}{2} 의 인자가 중괄호 없는 꼴이 된다.
    text = _replace_braced_command(text, "^", lambda power: f"**({power})")
    text = text.replace("^", "**")
    text = re.sub(r"\\sqrt\[([^\]]*)\]\{([^{}]*)\}", r"((\2)**(1/(\1)))", text)
    text = _replace_braced_command(text, r"\sqrt", lambda body: f"sqrt({body})")
    text = _replace_braced_command(text, r"\frac", lambda top, bottom: f"(({top})/({bottom}))")
    text = re.sub(r"\\(sin|cos|tan|log|exp)", r"\1", text)
    text = text.replace("{", "(").replace("}", ")")
    return text.strip()


# JSON 에 "\\frac" 대신 "\frac" 로 쓰면 \f 가 폼피드가 된다(\t→탭 \times, \b→백스페이스 \beta).
# 에이전트가 손으로 쓴 jsonl 에서 실제로 나는 실수라 되살린다.
ESCAPED_CONTROL_CHARS = {"\f": "\\f", "\t": "\\t", "\b": "\\b", "\r": "\\r", "\v": "\\v"}


def restore_latex_escapes(text: str) -> str:
    for control, latex in ESCAPED_CONTROL_CHARS.items():
        text = text.replace(control, latex)
    return text


def strip_assignment(text: str) -> str:
    """'x=3' · 'a = 2' 처럼 변수 하나 = 값이면 값만 남긴다."""
    match = re.fullmatch(r"\s*[A-Za-z]\s*=\s*(.+)", text)
    return match.group(1) if match else text


def to_expression(raw: str):
    """문자열 → sympy 식. 실패하면 None."""
    candidate = strip_assignment(restore_latex_escapes(str(raw)))
    if HANGUL.search(candidate):
        return None
    try:
        from sympy.parsing.latex import parse_latex  # antlr 가 있을 때만 성공

        if "\\" in candidate:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # antlr 미설치 경고 — 폴백으로 간다
                return parse_latex(candidate)
    except Exception:  # noqa: BLE001 - antlr 없음·파싱 실패 모두 폴백으로
        pass
    try:
        return parse_expr(latex_to_sympy_text(candidate), transformations=TRANSFORMS, evaluate=True)
    except Exception:  # noqa: BLE001
        return None


def plain_text(raw: object) -> str:
    """문자열 비교용 — 공백·$·끝 마침표 제거, 소문자."""
    return re.sub(r"\s+|\$", "", str(raw)).rstrip(".").lower()


# ── 동치 판정 ───────────────────────────────────────────────────────────
def numerically_equal(left, right) -> bool:
    symbols = sorted(left.free_symbols | right.free_symbols, key=str)
    rng = random.Random(20261010)
    for _ in range(NUMERIC_SAMPLE_POINTS):
        point = {symbol: sympy.Float(rng.uniform(0.3, 2.7)) for symbol in symbols}
        left_value = complex(sympy.N(left.subs(point)))
        right_value = complex(sympy.N(right.subs(point)))
        scale = max(1.0, abs(left_value), abs(right_value))
        if abs(left_value - right_value) > NUMERIC_REL_TOL * scale:
            return False
    return True


def expressions_equal(left, right) -> tuple[bool | None, str]:
    """(같은가, 방법). 판단 불가면 (None, 사유)."""
    try:
        if len(str(left)) + len(str(right)) <= MAX_SIMPLIFY_LENGTH:
            if sympy.simplify(left - right) == 0:
                return True, "sympy_simplify"
        return numerically_equal(left, right), "numeric_sample"
    except Exception as error:  # noqa: BLE001
        return None, f"비교 실패: {type(error).__name__}"


def split_list(text: str) -> list[str]:
    """'1, 2' 같은 여러 값 답 — 괄호 안 쉼표는 나누지 않는다(좌표 (1,2) 보호)."""
    parts, depth, current = [], 0, ""
    for char in text:
        depth += char in "([{"
        depth -= char in ")]}"
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return [part.strip() for part in parts if part.strip()]


def compare_values(key_value: str, solved_value: str) -> tuple[str, str]:
    """값 하나 대 하나. ('match'|'mismatch'|'unparsed', 방법)."""
    if plain_text(key_value) == plain_text(solved_value):
        return "match", "string"
    key_parts, solved_parts = split_list(str(key_value)), split_list(str(solved_value))
    if len(key_parts) > 1 or len(solved_parts) > 1:
        if len(key_parts) != len(solved_parts):
            return "mismatch", "list_length"
        unmatched = list(solved_parts)
        for key_part in key_parts:
            hit = next((s for s in unmatched if compare_values(key_part, s)[0] == "match"), None)
            if hit is None:
                return "mismatch", "list_element"
            unmatched.remove(hit)
        return "match", "list_unordered"
    left, right = to_expression(key_value), to_expression(solved_value)
    if left is None or right is None:
        return "unparsed", "parse_failed"
    same, method = expressions_equal(left, right)
    if same is None:
        return "unparsed", method
    return ("match" if same else "mismatch"), method


def compare_row(key: dict, solved: dict | None) -> dict:
    row = {"id": key["id"], "key": None, "solved": None, "confidence": None, "figureLeak": False}
    if solved is None:
        return {**row, "result": "missing", "method": None, "detail": "풀이 줄 없음"}
    row.update(
        solved=solved.get("answer"),
        confidence=solved.get("confidence"),
        figureLeak=bool(solved.get("figureLeak")),
    )
    if solved.get("status") == "skip" or solved.get("answer") in (None, ""):
        return {**row, "result": "skip", "method": None, "detail": solved.get("note", "")}

    answer_type = key.get("answerType") or key.get("responseType")
    if answer_type in CHOICE_TYPES or (key.get("correctChoiceKeys") and not key.get("acceptedValues")):
        expected = choice_set(key.get("correctChoiceKeys") or [])
        got = choice_set(solved["answer"])
        row["key"] = sorted(expected)
        result = "match" if expected and expected == got else "mismatch"
        return {**row, "result": result, "method": "choice_set", "detail": f"{sorted(got)}"}

    accepted = [value for value in (key.get("acceptedValues") or []) if str(value).strip()]
    row["key"] = accepted
    if not accepted:
        return {**row, "result": "unparsed", "method": None, "detail": "정답표에 값 없음"}
    outcomes = [compare_values(str(value), str(solved["answer"])) for value in accepted]
    for result, method in outcomes:
        if result == "match":
            return {**row, "result": "match", "method": method, "detail": ""}
    if any(result == "unparsed" for result, _ in outcomes):
        return {**row, "result": "unparsed", "method": "parse_failed", "detail": ""}
    return {**row, "result": "mismatch", "method": outcomes[0][1], "detail": ""}


# ── 입출력 ──────────────────────────────────────────────────────────────
def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def run(key_path: Path, solved_path: Path, out_path: Path) -> dict[str, int]:
    keys = read_jsonl(key_path)
    solved_by_id = {row["id"]: row for row in read_jsonl(solved_path)}
    rows = [compare_row(key, solved_by_id.get(key["id"])) for key in keys]
    with out_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["result"]] = counts.get(row["result"], 0) + 1
    counts["figureLeak"] = sum(1 for row in rows if row["figureLeak"])
    return counts


# ── 자체 테스트 ─────────────────────────────────────────────────────────
SELFTEST_CASES = [
    # (key, solved answer, 기대 결과)
    ({"answerType": "choice", "correctChoiceKeys": ["3"]}, "③", "match"),
    ({"answerType": "choice", "correctChoiceKeys": ["3"]}, "3번", "match"),
    ({"answerType": "choice", "correctChoiceKeys": ["2", "4"]}, "④, ②", "match"),
    ({"answerType": "choice", "correctChoiceKeys": ["3"]}, "5", "mismatch"),
    ({"answerType": "numeric", "acceptedValues": ["0.5"]}, r"\frac{1}{2}", "match"),
    ({"answerType": "numeric", "acceptedValues": ["12"]}, "13", "mismatch"),
    ({"answerType": "short", "acceptedValues": [r"2\sqrt{3}"]}, "sqrt(12)", "match"),
    ({"answerType": "short", "acceptedValues": ["x=3"]}, "3", "match"),
    ({"answerType": "expression", "acceptedValues": ["(x+1)^2"]}, "x^2+2x+1", "match"),
    ({"answerType": "expression", "acceptedValues": [r"\dfrac{x^{2}}{2}"]}, "x**2/2", "match"),
    ({"answerType": "expression", "acceptedValues": [r"\sqrt[3]{8}"]}, "2", "match"),
    ({"answerType": "short", "acceptedValues": ["1, 2"]}, "2,1", "match"),
    ({"answerType": "short", "acceptedValues": ["(1,2)"]}, "(1, 2)", "match"),
    ({"answerType": "short", "acceptedValues": ["ㄱ, ㄷ"]}, "ㄱ,ㄷ", "match"),
    ({"answerType": "short", "acceptedValues": ["ㄱ, ㄷ"]}, "ㄴ", "mismatch"),
    ({"answerType": "short", "acceptedValues": ["풀이 참조"]}, "증명", "unparsed"),
    ({"answerType": "numeric", "acceptedValues": [r"\pi"]}, "3.14159", "mismatch"),
    ({"answerType": "numeric", "acceptedValues": []}, "3", "unparsed"),
    ({"answerType": "numeric", "acceptedValues": ["\frac{3}{4}"]}, "0.75", "match"),  # \f = 폼피드
]


def selftest() -> int:
    failures = 0
    for index, (key, answer, expected) in enumerate(SELFTEST_CASES):
        key_row = {"id": f"t{index}", **key}
        got = compare_row(key_row, {"id": f"t{index}", "status": "solved", "answer": answer})
        if got["result"] != expected:
            failures += 1
            print(f"FAIL #{index}: {key} vs {answer!r} → {got['result']} (기대 {expected})")
    skip = compare_row({"id": "s", "answerType": "numeric"}, {"id": "s", "status": "skip"})
    missing = compare_row({"id": "m", "answerType": "numeric"}, None)
    leak = compare_row(
        {"id": "l", "answerType": "choice", "correctChoiceKeys": ["1"]},
        {"id": "l", "status": "solved", "answer": "1", "figureLeak": True},
    )
    for name, row, expected in (("skip", skip, "skip"), ("missing", missing, "missing")):
        if row["result"] != expected:
            failures += 1
            print(f"FAIL {name}: {row['result']}")
    if not leak["figureLeak"]:
        failures += 1
        print("FAIL figureLeak 표시가 전달되지 않음")
    total = len(SELFTEST_CASES) + 3
    print(f"selftest: {total - failures}/{total} 통과")
    return 1 if failures else 0


def main() -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")  # 윈도우 콘솔(cp949)에서 한글이 깨지지 않게
    parser = argparse.ArgumentParser(description="item-qa 정답 비교")
    parser.add_argument("--key", type=Path)
    parser.add_argument("--solved", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if not (args.key and args.solved and args.out):
        parser.error("--key --solved --out 이 모두 필요하다(또는 --selftest)")
    counts = run(args.key, args.solved, args.out)
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

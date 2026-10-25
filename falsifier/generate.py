"""Nemotron: candidate patch, candidate test, N mutants.

Everything here proposes; nothing here judges. No function returns a verdict, a pass, a fail, or
any claim about whether code works. The validation below only checks that a proposal is
well-formed input for execution: the diff applies, the touched files parse, and a mutant that
touches a loop still has a reachable exit. Whether anything is correct is decided by running it.

Every model call goes through LLM.complete, which:
- turns thinking off (it is billed as output tokens, and with a small max_tokens the model
  returned no text at all; step 0) and fails loudly on an empty response;
- caches the response on disk, keyed on a hash of model id, messages and sampling params;
- logs tokens in, tokens out and cost per call, with a running total.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from falsifier.config import GenerationConfig

log = logging.getLogger("falsifier.generate")

THINKING_OFF = {"chat_template_kwargs": {"enable_thinking": False}}
MAX_REASK_ROUNDS = 2
CONTEXT_CHARS_PER_FILE = 60_000


class EmptyResponseError(RuntimeError):
    """The model returned no text. With thinking on this is what a small max_tokens produces."""


class GenerationFailed(RuntimeError):
    """No well-formed proposal after the initial ask and MAX_REASK_ROUNDS re-asks."""


class DiffError(ValueError):
    """A proposed diff is not well-formed input: bad paths, does not apply, or does not parse.
    `stage` is where it failed: "headers", "apply", "parse" or "noop"; `strict_clean` is set once
    the diff has applied, so "applied but did not parse" is still counted as applied."""

    def __init__(
        self,
        msg: str,
        stage: str = "headers",
        strict_clean: bool | None = None,
        repaired: bool = False,
    ):
        super().__init__(msg)
        self.stage, self.strict_clean, self.repaired = stage, strict_clean, repaired

    @property
    def applied(self) -> bool:
        return self.stage in ("parse", "noop")


# ---------------------------------------------------------------------------------------------
# Model calls: cache and ledger


@dataclass
class CallRecord:
    purpose: str
    model: str
    cached: bool
    tokens_in: int
    tokens_out: int
    cost_usd: float
    """Spent by this call: 0 for a cache hit."""
    total_usd: float
    cache_key: str
    at: str
    generated_cost_usd: float = 0.0
    """What the response cost when it was generated, for cached and fresh calls alike."""


@dataclass
class LLM:
    config: GenerationConfig = field(default_factory=GenerationConfig.from_env)
    client: object | None = None
    calls: list[CallRecord] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    """Per-round accept/reject counts from the propose_* functions, for evidence."""

    @property
    def total_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    def _client(self):
        if self.client is None:
            from openai import OpenAI

            key = os.environ.get(self.config.api_key_env)
            if not key:
                raise RuntimeError(f"{self.config.api_key_env} is not set")
            self.client = OpenAI(
                base_url=self.config.base_url,
                api_key=key,
                timeout=self.config.request_timeout_s,
                max_retries=self.config.max_retries,
            )
        return self.client

    def cache_key(self, messages: list[dict], max_tokens: int, temperature: float) -> str:
        blob = json.dumps(
            {
                "model": self.config.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "extra_body": THINKING_OFF,
            },
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()

    def complete(
        self, purpose: str, messages: list[dict], *, max_tokens: int, temperature: float
    ) -> str:
        key = self.cache_key(messages, max_tokens, temperature)
        path = self.config.cache_dir / f"{key}.json"
        if path.exists():
            hit = json.loads(path.read_text())
            self._record(
                purpose,
                key,
                cached=True,
                usage=hit["usage"],
                cost=0.0,
                generated=hit.get("cost_usd", 0.0),
            )
            return hit["content"]

        resp = self._client().chat.completions.create(
            model=self.config.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            extra_body=THINKING_OFF,
        )
        choice = resp.choices[0]
        content = choice.message.content
        usage = resp.usage.model_dump() if resp.usage else {}
        if not content or not content.strip():
            raise EmptyResponseError(
                f"{purpose}: {self.config.model} returned no text "
                f"(finish_reason={choice.finish_reason}, usage={usage}). Thinking must be off."
            )
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        if reasoning:
            log.warning("%s: %s reasoning tokens despite thinking off", purpose, reasoning)
        cost = self.config.cost_usd(
            usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "model": self.config.model,
                    "purpose": purpose,
                    "messages": messages,
                    "params": {"max_tokens": max_tokens, "temperature": temperature},
                    "content": content,
                    "finish_reason": choice.finish_reason,
                    "usage": usage,
                    "cost_usd": cost,
                    "created": datetime.now(UTC).isoformat(timespec="seconds"),
                },
                indent=2,
            )
        )
        self._record(purpose, key, cached=False, usage=usage, cost=cost, generated=cost)
        return content

    def _record(
        self, purpose: str, key: str, *, cached: bool, usage: dict, cost: float, generated: float
    ) -> None:
        rec = CallRecord(
            purpose=purpose,
            model=self.config.model,
            cached=cached,
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
            cost_usd=cost,
            total_usd=self.total_usd + cost,
            cache_key=key[:16],
            at=datetime.now(UTC).isoformat(timespec="seconds"),
            generated_cost_usd=generated,
        )
        self.calls.append(rec)
        log.info(
            "%s%s: in=%d out=%d cost=$%.6f total=$%.6f",
            purpose,
            " (cached)" if cached else "",
            rec.tokens_in,
            rec.tokens_out,
            rec.cost_usd,
            rec.total_usd,
        )

    def ledger(self) -> list[dict]:
        return [asdict(c) for c in self.calls]


# ---------------------------------------------------------------------------------------------
# Diff validation: well-formedness only


Reader = Callable[[str], "str | None"]


@dataclass
class Validated:
    diff: str
    paths: list[str]
    before: dict[str, str | None]
    after: dict[str, str | None]
    changed_lines: dict[str, set[int]]
    """1-based line numbers in the new file that were added, or next to a deletion."""
    strict_clean: bool
    """Applies with plain `git apply --check`. Otherwise only with --recount, which tolerates
    wrong hunk line counts but still needs exact context."""
    repaired: bool = False
    """git rejected the diff even with --recount, and it was re-anchored (see `reanchor`);
    `diff` is then the git-generated replacement, not the model's text."""


def extract_block(text: str, lang: str) -> str | None:
    m = re.search(rf"```{lang}[^\n]*\n(.*?)```", text, re.S)
    return m.group(1) if m else None


def diff_paths(diff: str) -> list[str]:
    paths = []
    for line in diff.splitlines():
        for prefix in ("--- a/", "+++ b/"):
            if line.startswith(prefix):
                p = line[len(prefix) :].split("\t")[0].strip()
                if p not in paths:
                    paths.append(p)
    return paths


def _check_path(p: str) -> None:
    pp = PurePosixPath(p)
    if pp.is_absolute() or ".." in pp.parts or not p:
        raise DiffError(f"unsafe path in diff: {p!r}")


def _git_apply(cwd: Path, diff: str, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "apply", "--whitespace=nowarn", *flags, "-"],
        cwd=cwd,
        input=diff,
        text=True,
        capture_output=True,
        timeout=30,
    )


def changed_new_lines(before: str, after: str) -> set[int]:
    a, b = before.splitlines(), after.splitlines()
    out: set[int] = set()
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        out.update(range(j1 + 1, j2 + 1) if j2 > j1 else {j1, j1 + 1})
    return out


def _norm(line: str) -> str:
    return " ".join(line.split())


def _hunks(diff: str) -> dict[str, list[list[tuple[str, str]]]]:
    """Hunks per file as (tag, text) pairs. A bare empty line inside a hunk is blank context
    (models often drop its leading space)."""
    files: dict[str, list] = {}
    path, cur = None, None
    for line in diff.splitlines():
        if line.startswith(("--- a/", "--- /dev/null")):
            path, cur = None, None
            continue
        if line.startswith("+++ "):
            p = line[4:].split("\t")[0].strip()
            path, cur = (p[2:] if p.startswith("b/") else p), None
            files.setdefault(path, [])
            continue
        if line.startswith("@@"):
            if path is None:
                raise DiffError("hunk before a file header", "apply")
            cur = []
            files[path].append(cur)
            continue
        if cur is None or line.startswith("\\"):
            continue
        cur.append((line[0], line[1:]) if line[:1] in (" ", "+", "-") else (" ", line))
    return files


def reanchor(diff: str, before: dict[str, str | None]) -> dict[str, str]:
    """Apply a diff whose context lines have blank-line or indentation slips, the dominant model
    error (59 of 64 apply failures, flask-5014, 2026-10-25).

    Each hunk's original-side lines (context and removed), ignoring blank lines and comparing
    whitespace-normalised text, must match exactly one place in the source. Context and removed
    lines are then taken from the source itself; added lines are taken verbatim and never moved
    or re-indented. Anything ambiguous raises DiffError."""
    after = {}
    for path, hunks in _hunks(diff).items():
        text = before.get(path)
        if text is None:
            raise DiffError(f"cannot re-anchor {path}: no source file", "apply")
        lines = text.splitlines(keepends=True)
        nonblank = [i for i, ln in enumerate(lines) if ln.strip()]
        normed = [_norm(lines[i]) for i in nonblank]
        edits = []
        for h in hunks:
            key = [_norm(t) for tag, t in h if tag in (" ", "-") and t.strip()]
            if not key:
                raise DiffError(f"hunk in {path} has no non-blank lines to anchor on", "apply")
            hits = [k for k in range(len(normed) - len(key) + 1) if normed[k : k + len(key)] == key]
            if len(hits) != 1:
                raise DiffError(f"cannot re-anchor a hunk in {path}: {len(hits)} matches", "apply")
            mapped = nonblank[hits[0] : hits[0] + len(key)]
            out, j, cursor = [], 0, mapped[0]
            for tag, t in h:
                if tag == "+":
                    out.append(t + "\n")
                    continue
                if not t.strip():
                    continue  # use the source's own blank lines, not the model's
                src = mapped[j]
                j += 1
                out.extend(lines[cursor:src])
                if tag == " ":
                    out.append(lines[src])
                cursor = src + 1
            edits.append((mapped[0], mapped[-1] + 1, out))
        edits.sort(key=lambda e: e[0])
        if any(b[0] < a[1] for a, b in zip(edits, edits[1:], strict=False)):
            raise DiffError(f"re-anchored hunks overlap in {path}", "apply")
        new, cursor = [], 0
        for start, end, out in edits:
            new.extend(lines[cursor:start])
            new.extend(out)
            cursor = end
        new.extend(lines[cursor:])
        after[path] = "".join(new)
    return after


def validate_diff(
    diff: str, read: Reader, *, allowed_paths: set[str] | None = None, repair: bool = False
) -> Validated:
    """git apply --check the diff against a scratch copy of the files it touches, then ast.parse
    every touched .py file. With repair=True, a diff git rejects is re-anchored (`reanchor`) and
    replaced by the git-generated equivalent, which must then apply strictly. Raises DiffError;
    never says whether the change is right."""
    if not diff or not diff.strip():
        raise DiffError("empty diff")
    if not diff.endswith("\n"):
        diff += "\n"
    paths = diff_paths(diff)
    if not paths:
        raise DiffError("no --- a/ or +++ b/ file headers")
    for p in paths:
        _check_path(p)
    if allowed_paths is not None and not set(paths) <= allowed_paths:
        raise DiffError(f"touches files outside {sorted(allowed_paths)}: {paths}")
    before = {p: read(p) for p in paths}
    with tempfile.TemporaryDirectory(prefix="falsifier-scratch-") as tmp:
        root = Path(tmp)
        for p, text in before.items():
            if text is not None:
                (root / p).parent.mkdir(parents=True, exist_ok=True)
                (root / p).write_text(text)
        strict = _git_apply(root, diff, "--check").returncode == 0
        check = _git_apply(root, diff, "--check", "--recount")
        repaired = False
        if check.returncode != 0:
            failure = f"git apply --check failed: {check.stderr.strip()[:500]}"
            if not repair:
                raise DiffError(failure, "apply")
            try:
                fixed = reanchor(diff, before)
            except DiffError as exc:
                raise DiffError(f"{failure}; re-anchoring failed: {exc}", "apply") from exc
            diff = make_diff({p: before[p] or "" for p in fixed}, fixed)
            if not diff or _git_apply(root, diff, "--check").returncode != 0:
                raise DiffError(f"{failure}; re-anchored diff does not apply", "apply")
            repaired = True
        done = _git_apply(root, diff, "--recount")
        if done.returncode != 0:
            raise DiffError(f"git apply failed: {done.stderr.strip()[:500]}", "apply")
        after = {p: (root / p).read_text() if (root / p).exists() else None for p in paths}
    changed = {}
    for p in paths:
        if after[p] is not None and p.endswith(".py"):
            try:
                ast.parse(after[p], filename=p)
            except SyntaxError as exc:
                raise DiffError(
                    f"{p} does not parse after the diff: {exc}", "parse", strict, repaired
                ) from exc
        if after[p] == before[p]:
            continue
        changed[p] = changed_new_lines(before[p] or "", after[p] or "")
    if not changed:
        raise DiffError("diff applies but changes nothing", "noop", strict, repaired)
    return Validated(diff, paths, before, after, changed, strict, repaired)


def tree_reader(repo_dir: Path) -> Reader:
    root = Path(repo_dir).resolve()

    def read(p: str) -> str | None:
        f = (root / p).resolve()
        if root not in f.parents:
            raise DiffError(f"path escapes the repo: {p!r}")
        return f.read_text() if f.is_file() else None

    return read


def overlay_reader(base: Reader, files: dict[str, str | None]) -> Reader:
    return lambda p: files[p] if p in files else base(p)


def make_diff(before: dict[str, str], after: dict[str, str]) -> str:
    """A unified diff from `before` to `after` written by git itself (`git diff --no-index`), so
    it applies with plain `git apply` and handles a missing final newline correctly."""
    out = []
    with tempfile.TemporaryDirectory(prefix="falsifier-diff-") as tmp:
        root = Path(tmp)
        for p in sorted(after):
            if before.get(p) == after[p]:
                continue
            for side, text in (("a", before[p]), ("b", after[p])):
                (root / side / p).parent.mkdir(parents=True, exist_ok=True)
                (root / side / p).write_text(text)
            r = subprocess.run(
                ["git", "diff", "--no-index", "--no-prefix", "--no-color", f"a/{p}", f"b/{p}"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode not in (0, 1):
                raise DiffError(f"git diff --no-index failed: {r.stderr.strip()[:300]}")
            out.append("".join(r.stdout.splitlines(keepends=True)[2:]))  # drop diff/index lines
    return "".join(out)


# ---------------------------------------------------------------------------------------------
# Termination: a mutant that touches a loop must keep a reachable exit


_LOOP_SCOPE_STOP = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
_INFINITE_ITERATORS = {"count", "cycle", "repeat"}


def _body_nodes(nodes):
    """Every node under `nodes`, not descending into nested function or class scopes."""
    stack = list(nodes)
    while stack:
        node = stack.pop()
        if isinstance(node, _LOOP_SCOPE_STOP):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _exits(nodes, count_breaks: bool = True) -> bool:
    """A break, return or raise that leaves this loop. A break inside a nested loop leaves only
    that loop, so it does not count; returns and raises at any depth do."""
    for node in nodes:
        if isinstance(node, _LOOP_SCOPE_STOP):
            continue
        if isinstance(node, (ast.Return, ast.Raise)) or (
            count_breaks and isinstance(node, ast.Break)
        ):
            return True
        nested = isinstance(node, (ast.While, ast.For, ast.AsyncFor))
        if _exits(ast.iter_child_nodes(node), count_breaks and not nested):
            return True
    return False


def _has_exit(loop: ast.While | ast.For | ast.AsyncFor) -> bool:
    return _exits(loop.body)


def _names(expr: ast.AST) -> set[str]:
    out = set()
    for n in ast.walk(expr):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            base = n
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                out.add(base.id)
    return out


def _target_names(t: ast.AST) -> set[str]:
    """The variable an assignment rebinds or mutates: `a[i] = 0` changes `a`, not `i`."""
    if isinstance(t, ast.Name):
        return {t.id}
    if isinstance(t, (ast.Attribute, ast.Subscript, ast.Starred)):
        return _target_names(t.value)
    if isinstance(t, (ast.Tuple, ast.List)):
        return set().union(*(_target_names(e) for e in t.elts)) if t.elts else set()
    return set()


def _changed_in_body(loop: ast.While, names: set[str]) -> bool:
    """Does the body plausibly change anything the condition reads? Only assignment targets and
    method calls on those names count. Deliberately conservative: `consume(q)` might pop from q,
    but a wrong rejection costs one re-ask while a wrong acceptance costs a runaway fork."""
    for n in _body_nodes(loop.body):
        targets = []
        if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.NamedExpr)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
        elif isinstance(n, (ast.For, ast.AsyncFor, ast.comprehension)):
            targets = [n.target]
        elif isinstance(n, (ast.With, ast.AsyncWith)):
            targets = [i.optional_vars for i in n.items if i.optional_vars]
        elif isinstance(n, ast.Delete):
            targets = n.targets
        elif isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute) and _names(n.func.value) & names:
                return True
        if any(_target_names(t) & names for t in targets):
            return True
    return False


def loop_exit_problems(source: str, changed_lines: set[int]) -> list[str]:
    """Reasons a loop touched by the change may have no reachable exit. A heuristic: it cannot
    prove termination, and the per-run sandbox timeout remains the backstop."""
    problems = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.While, ast.For, ast.AsyncFor)):
            continue
        span = set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        if not span & changed_lines:
            continue
        where = f"loop at line {node.lineno}"
        if isinstance(node, ast.While):
            if _has_exit(node):
                continue
            test = node.test
            if isinstance(test, ast.Constant) and test.value:
                problems.append(f"{where}: `while {ast.unparse(test)}` with no break/return/raise")
            elif any(isinstance(n, ast.Call) for n in ast.walk(test)):
                continue  # the condition calls something; it may change on its own
            elif not _changed_in_body(node, _names(test)):
                problems.append(
                    f"{where}: nothing in the body changes `{ast.unparse(test)}` and there is "
                    "no break/return/raise"
                )
        else:
            it = node.iter
            fn = it.func if isinstance(it, ast.Call) else None
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name in _INFINITE_ITERATORS and not _has_exit(node):
                problems.append(f"{where}: iterates `{ast.unparse(it)}` with no exit")
    return problems


# ---------------------------------------------------------------------------------------------
# Prompts

SYSTEM = (
    "You are a careful Python engineer. You answer with exactly the requested blocks and "
    "nothing else. Code inside diff blocks must copy unchanged context lines exactly, "
    "including indentation."
)

PATCH_PROMPT = """\
Fix the issue below in the repository. The relevant source is shown after the issue.

Answer with one unified diff in a ```diff block and nothing else. Use `--- a/<path>` and
`+++ b/<path>` headers with repository-relative paths, and give at least 3 lines of unchanged
context around every change. Context lines must match the source exactly. Do not modify tests.

## Issue

{issue}

## Source

{context}
"""

TEST_PROMPT = """\
Write a pytest test that reproduces the issue below: it must fail on the current code and pass
once the issue is fixed. The relevant source is shown after the issue.

Answer with the complete contents of one new test file in a ```python block and nothing else.
Import what the test needs from the package, define one or more `test_` functions, and make each
test check the behaviour the issue describes, not an implementation detail. No network, no
sleeps, no randomness.

## Issue

{issue}

## Source

{context}
"""

MUTANT_PROMPT = """\
You are helping audit a test, not fix a bug. Below are an issue, a correct patch for it, and the
ORIGINAL source of every file the patch touches, before any fix.

Write {n} mutants of the patch. A mutant is a plausible WRONG fix: code a competent developer
could have written for this issue instead of the correct patch, which looks like a fix and might
pass a careless test, but does not fully fix the bug. Write each mutant as a unified diff against
the ORIGINAL source shown below, exactly as you would write an alternative fix.

Spread the mutants across these kinds of wrong fix:
- off-by-one: a boundary one too far or one short (< vs <=, len vs len-1, an index or range end).
- wrong-condition: the same shape as the patch, but the guard tests the wrong thing, the wrong
  variable, or the wrong combination (and/or, a missing case of a negation).
- too-narrow: handles exactly the case in the issue but not the general one (one literal value,
  one type, one code path, only the first occurrence).
- silences-symptom: makes the reported error or output go away without fixing the cause (catches
  and ignores the exception, returns a default, skips the check).

Every mutant must behave differently from the correct patch on at least one concrete input that
a test could pass in, and the rationale must name that input. A rewrite that behaves the same as
the patch for every input the code accepts is an equivalent mutant and worthless, however
different it looks: for a str, `not s`, `s == ""` and `len(s) < 1` are the same check.

Do NOT write:
- operator flips or constant swaps with no story behind them (+ to -, 0 to 1, True to False),
  including simply inverting the patch's condition;
- a mutant equivalent to the patch, or one that simply reverts it to the original code;
- changes to files the patch does not touch, to tests, or to comments or whitespace only;
- code that does not parse.

Every mutant MUST terminate. Each one is executed under a test runner billed per CPU-second
(about $0.62 per CPU-minute), and a mutant that loops forever costs money until it is killed. If
a mutant changes a loop or its condition, the loop must still have a reachable exit: the
condition must depend on something the loop body changes, or the body must break, return or
raise. Never write `while True` without a break, and never remove the statement that advances a
loop. Mutants that touch a loop without a reachable exit are rejected automatically.

Format each mutant exactly like this:

### MUTANT <k>
KIND: <off-by-one | wrong-condition | too-narrow | silences-symptom>
RATIONALE: <one sentence: what this gets wrong, and the concrete input on which it differs
from the correct patch>
WITNESS:
```python
<Python run from the repository root: import what it needs, then end with ONE expression
evaluating the input the rationale names. Its value, or the exception it raises, must differ
between the correct patch and this mutant. No network, files, randomness, time or printing.>
```
```diff
--- a/<path>
+++ b/<path>
@@ -<line>,<count> +<line>,<count> @@
<at least 3 lines of unchanged context around each change, copied exactly from the original source>
```

## Issue

{issue}

## Correct patch

```diff
{patch}```

## Original source

{context}
"""

MUTANT_REASK = """\
{accepted} of your mutants were accepted. These were rejected:

{rejected}

Write {k} new mutants in the same format, numbered from {start}. They must differ from every
accepted mutant (accepted kinds and rationales: {accepted_list}). Write them against the original
source, copy context lines exactly, give each a WITNESS that ends in one expression, and keep
every loop terminating."""

FIX_REASK = """\
That answer was rejected: {error}

Answer again with the corrected {what} only, in the same format."""


def format_context(files: dict[str, str | None]) -> str:
    parts = []
    for p, text in files.items():
        if text is None:
            continue
        if len(text) > CONTEXT_CHARS_PER_FILE:
            text = text[:CONTEXT_CHARS_PER_FILE] + "\n# ... truncated ...\n"
        parts.append(f"### {p}\n\n```python\n{text}```")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------------------------
# The three proposers


def reask_temperature(base: float, rnd: int) -> float:
    return min(1.0, round(base + 0.3 * rnd, 2))


def _llm(llm: LLM | None) -> LLM:
    return llm if llm is not None else LLM()


def _ask_until_valid(llm, purpose, messages, what, parse, *, max_tokens, temperature):
    """Initial ask plus up to MAX_REASK_ROUNDS re-asks, each fed the previous rejection. Re-asks
    raise the temperature: at 0.2 the model returned the identical rejected diff three times."""
    error = None
    for rnd in range(1 + MAX_REASK_ROUNDS):
        text = llm.complete(
            f"{purpose}[{rnd}]",
            messages,
            max_tokens=max_tokens,
            temperature=reask_temperature(temperature, rnd),
        )
        try:
            result = parse(text)
            llm.events.append({"purpose": purpose, "round": rnd, "accepted": 1, "rejected": []})
            return result
        except (DiffError, ValueError) as exc:
            error = str(exc)
            llm.events.append(
                {"purpose": purpose, "round": rnd, "accepted": 0, "rejected": [error]}
            )
            log.info("%s round %d rejected: %s", purpose, rnd, error)
            messages = [
                *messages,
                {"role": "assistant", "content": text},
                {"role": "user", "content": FIX_REASK.format(error=error, what=what)},
            ]
    raise GenerationFailed(f"{purpose}: no well-formed {what} after {rnd + 1} asks: {error}")


def propose_patch(
    issue_text: str, repo_context: str, *, repo_dir: Path, llm: LLM | None = None
) -> str:
    """A candidate fix as a unified diff that applies to `repo_dir` and leaves the touched files
    parseable. Says nothing about whether it fixes anything."""
    llm = _llm(llm)
    read = tree_reader(repo_dir)

    def parse(text: str) -> str:
        diff = extract_block(text, "diff")
        if diff is None:
            raise ValueError("no ```diff block in the answer")
        return validate_diff(diff, read, repair=True).diff

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": PATCH_PROMPT.format(issue=issue_text, context=repo_context)},
    ]
    return _ask_until_valid(llm, "patch", messages, "diff", parse, max_tokens=4096, temperature=0.2)


def propose_test(issue_text: str, repo_context: str, *, llm: LLM | None = None) -> str:
    """Candidate test file contents that parse and define at least one test function."""
    llm = _llm(llm)

    def parse(text: str) -> str:
        src = extract_block(text, "python")
        if src is None:
            raise ValueError("no ```python block in the answer")
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:
            raise ValueError(f"test file does not parse: {exc}") from exc
        if not any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")
            for n in ast.walk(tree)
        ):
            raise ValueError("test file defines no test_ function")
        return src

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": TEST_PROMPT.format(issue=issue_text, context=repo_context)},
    ]
    return _ask_until_valid(
        llm, "test", messages, "test file", parse, max_tokens=4096, temperature=0.2
    )


_MUTANT_HEAD = re.compile(r"^#{2,4}\s*MUTANT\s*\d+\s*$", re.M | re.I)


def _label(block: str, name: str) -> str | None:
    """`KIND: x`, tolerating markdown the model adds anyway (`**KIND:** x`, `- KIND: x`)."""
    m = re.search(rf"^[\s>*_-]*{name}[\s*_]*:[\s*_]*(.+?)[\s*_]*$", block, re.M | re.I)
    return m.group(1).strip() if m else None


_WITNESS = re.compile(r"WITNESS[\s*_]*:[\s*_]*\n*```python[^\n]*\n(.*?)```", re.S | re.I)


_PY_C = re.compile(r"^\s*python3?\s+-c\s+([\"'])(.*)\1\s*$", re.S)


def normalize_witness(src: str) -> str:
    """Deterministic clean-up of the two off-contract forms the model wrote on its first live run
    (phase 3, 2026-10-25): a shell wrapper `python3 -c "..."` (flask, requests-5414) and a doctest
    transcript with `>>>` prompts and claimed outputs (requests-6028). The claimed outputs are
    dropped: they are the model's assertions, and only execution counts."""
    src = src.strip("\n")
    if m := _PY_C.match(src):
        src = m.group(2).replace('\\"', '"') if m.group(1) == '"' else m.group(2)
    lines = src.splitlines()
    if any(ln.lstrip().startswith(">>>") for ln in lines):
        code = []
        for ln in lines:
            s = ln.lstrip()
            if s.startswith(">>>") or s.startswith("..."):
                code.append(s[4:] if s[3:4] == " " else s[3:])
        src = "\n".join(code)
    return src.strip("\n")


def witness_problem(src: str) -> str | None:
    """A witness must parse. verify runs it on the patch and on the mutant and compares its final
    expression's value or exception and everything it prints."""
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return f"WITNESS does not parse: {exc}"
    if not tree.body:
        return "WITNESS is empty"
    return None


def parse_mutants(text: str) -> list[dict]:
    """Split a mutant answer into {kind, rationale, witness, diff} blocks; malformed blocks keep a
    `parse_error` so they are reported as rejections rather than silently lost."""
    starts = [m.start() for m in _MUTANT_HEAD.finditer(text)]
    out = []
    for i, s in enumerate(starts):
        block = text[s : starts[i + 1] if i + 1 < len(starts) else len(text)]
        kind, why = _label(block, "KIND"), _label(block, "RATIONALE")
        w = _WITNESS.search(block)
        witness = normalize_witness(w.group(1)) if w else None
        diff = extract_block(block, "diff")
        m = {"kind": kind, "rationale": why, "witness": witness, "diff": diff}
        if not why:
            m["parse_error"] = "no RATIONALE line"
        elif witness is None:
            m["parse_error"] = "no WITNESS ```python block"
        elif problem := witness_problem(witness):
            m["parse_error"] = problem
        elif diff is None:
            m["parse_error"] = "no ```diff block"
        out.append(m)
    return out


def propose_mutants(patch: str, n: int, **kwargs) -> list[tuple[str, str]]:
    """(diff, rationale) pairs. propose_mutant_records gives full records, with witnesses."""
    return [(r["diff"], r["rationale"]) for r in propose_mutant_records(patch, n, **kwargs)]


def propose_mutant_records(
    patch: str,
    n: int,
    *,
    repo_dir: Path,
    issue_text: str = "",
    llm: LLM | None = None,
) -> list[dict]:
    """Up to n plausible wrong fixes of `patch`, as records with the unified diff against the
    patched tree, a one-sentence rationale, the kind, and a WITNESS: Python ending in one
    expression on which the mutant should differ from the patch. Every diff applies cleanly to
    the patched tree, touches only files the patch touches, leaves them parseable, differs from
    both the patch and the original, and keeps a reachable exit in any loop it touches. Whether
    a mutant is actually wrong is not decided here.

    The model writes each mutant as an alternative fix against the original source (it does so
    even when asked otherwise; first live run, 2026-10-25). Its diff is validated against the
    original tree, or the patched tree if it was written against that, and the returned diff is
    regenerated by git from the patched tree to the mutant's code.

    Initial ask plus at most MAX_REASK_ROUNDS re-asks for the shortfall; returns what it has."""
    if n < 1:
        return []
    llm = _llm(llm)
    original = tree_reader(repo_dir)
    patched = validate_diff(patch, original)
    patched_read = overlay_reader(original, patched.after)
    allowed = set(patched.paths)

    messages = [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": MUTANT_PROMPT.format(
                n=n,
                issue=issue_text or "(not given)",
                patch=patched.diff,
                context=format_context(patched.before),
            ),
        },
    ]
    accepted: list[dict] = []
    seen = {_fingerprint(patched.after), _fingerprint(patched.before)}

    bases = (("original", original, patched.before), ("patched", patched_read, patched.after))

    def validate_mutant(diff: str) -> tuple[Validated, dict[str, str | None]]:
        """Validate against the original tree, else the patched one. Returns the result and the
        full state of every file the patch touches after the mutant, so a mutant that reverts
        one file of a multi-file patch is still caught."""
        first = None
        for _name, read, base_state in bases:
            try:
                v = validate_diff(diff, read, allowed_paths=allowed, repair=True)
            except DiffError as exc:
                first = first or exc
                if exc.applied:  # it applied here, so the failure is about the content
                    raise
                continue
            return v, {p: v.after[p] if p in v.after else base_state[p] for p in patched.paths}
        raise first

    for rnd in range(1 + MAX_REASK_ROUNDS):
        want = n - len(accepted)
        text = llm.complete(
            f"mutants[{rnd}]",
            messages,
            max_tokens=min(16_000, 1_200 * want + 800),
            temperature=0.6 if rnd == 0 else reask_temperature(0.6, rnd),
        )
        rejected, applied, strict, repaired, parsed = [], 0, 0, 0, parse_mutants(text)
        for idx, m in enumerate(parsed, 1):
            reason = m.get("parse_error")
            if reason is None:
                try:
                    v, full = validate_mutant(m["diff"])
                    repaired += v.repaired
                    applied += not v.repaired
                    strict += v.strict_clean and not v.repaired
                    reason = _mutant_problem(v, full, seen)
                except DiffError as exc:
                    repaired += exc.applied and exc.repaired
                    applied += exc.applied and not exc.repaired
                    strict += bool(exc.applied and exc.strict_clean and not exc.repaired)
                    reason = str(exc)
            if reason is None and len(accepted) < n:
                seen.add(_fingerprint(full))
                canonical = make_diff(patched.after, full)
                check = validate_diff(canonical, patched_read, allowed_paths=allowed)
                assert check.strict_clean, "git-generated diff must apply without --recount"
                accepted.append(
                    {
                        **m,
                        "diff": canonical,
                        "model_diff": m["diff"],
                        "strict_clean": v.strict_clean,
                        "repaired": v.repaired,
                    }
                )
            elif reason is not None:
                rejected.append({"mutant": idx, "kind": m.get("kind"), "reason": reason})
        llm.events.append(
            {
                "purpose": "mutants",
                "round": rnd,
                "asked": want,
                "parsed": len(parsed),
                "applied": applied,
                "strict_clean": strict,
                "repaired": repaired,
                "accepted": len(accepted),
                "rejected": rejected,
            }
        )
        log.info(
            "mutants round %d: asked %d, parsed %d, accepted %d total, rejected %d",
            rnd,
            want,
            len(parsed),
            len(accepted),
            len(rejected),
        )
        if len(accepted) >= n or rnd == MAX_REASK_ROUNDS:
            break
        reask = MUTANT_REASK.format(
            accepted=len(accepted),
            rejected="\n".join(
                f"- mutant {r['mutant']} ({r['kind']}): {r['reason']}" for r in rejected
            )
            or "- (none parsed)",
            k=n - len(accepted),
            start=len(parsed) + 1,
            accepted_list="; ".join(f"{a['kind']}: {a['rationale']}" for a in accepted) or "none",
        )
        messages = [
            *messages,
            {"role": "assistant", "content": text},
            {"role": "user", "content": reask},
        ]
    if len(accepted) < n:
        log.warning("mutants: %d of %d after %d re-ask rounds", len(accepted), n, MAX_REASK_ROUNDS)
    keep = ("diff", "rationale", "kind", "witness", "model_diff", "strict_clean", "repaired")
    return [{k: a.get(k) for k in keep} for a in accepted]


def canonical(path: str, text: str | None) -> str | None:
    """Python files compared by structure (ast.dump: no comments, blank lines or formatting), so a
    mutant that reverts the patch with different whitespace is still caught. Other files by text."""
    if text is None or not path.endswith(".py"):
        return text
    try:
        return ast.dump(ast.parse(text))
    except SyntaxError:
        return text


def _fingerprint(files: dict[str, str | None]) -> str:
    norm = sorted((p, canonical(p, t)) for p, t in files.items())
    return hashlib.sha256(json.dumps(norm).encode()).hexdigest()


def _mutant_problem(v: Validated, full_state: dict, seen: set[str]) -> str | None:
    if _fingerprint(full_state) in seen:
        return "identical to the patch, the original, or an earlier mutant"
    for p, lines in v.changed_lines.items():
        if p.endswith(".py") and v.after[p] is not None:
            problems = loop_exit_problems(v.after[p], lines)
            if problems:
                return "non-terminating risk: " + "; ".join(problems)
    return None

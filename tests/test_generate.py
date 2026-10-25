"""generate.py: diff validation, the termination check, the response cache, and the re-ask loop.
Recorded responses only; no live API calls."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from falsifier.config import GenerationConfig
from falsifier.generate import (
    LLM,
    MAX_REASK_ROUNDS,
    THINKING_OFF,
    DiffError,
    EmptyResponseError,
    GenerationFailed,
    loop_exit_problems,
    parse_mutants,
    propose_mutants,
    propose_patch,
    propose_test,
    tree_reader,
    validate_diff,
)

FIXTURES = Path(__file__).parent / "fixtures" / "generate"

ORIGINAL = '''\
def last_n(items, n):
    """Return the last n items of a list."""
    return items[-n:]


def drain(queue):
    """Pop every item off the queue, last first."""
    out = []
    while queue:
        out.append(queue.pop())
    return out
'''

GOLD = '''\
--- a/pkg/window.py
+++ b/pkg/window.py
@@ -1,3 +1,5 @@
 def last_n(items, n):
     """Return the last n items of a list."""
+    if n <= 0:
+        return []
     return items[-n:]
'''


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "repo" / "pkg").mkdir(parents=True)
    (tmp_path / "repo" / "pkg" / "window.py").write_text(ORIGINAL)
    return tmp_path / "repo"


class FakeClient:
    """Records every request and replays canned answers in order."""

    def __init__(self, answers, usage=(1000, 200)):
        self.answers, self.requests, self.usage = list(answers), [], usage
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        content = self.answers.pop(0)
        usage = {"prompt_tokens": self.usage[0], "completion_tokens": self.usage[1]}
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")
            ],
            usage=SimpleNamespace(model_dump=lambda: usage),
        )


def make_llm(tmp_path, answers, **cfg):
    config = GenerationConfig(cache_dir=tmp_path / "cache", **cfg)
    return LLM(config=config, client=FakeClient(answers))


# --- diff validation ------------------------------------------------------------------------


def test_valid_diff_applies_and_reports_changed_lines(repo):
    v = validate_diff(GOLD, tree_reader(repo))
    assert v.paths == ["pkg/window.py"] and v.strict_clean
    assert "if n <= 0:" in v.after["pkg/window.py"]
    assert v.changed_lines["pkg/window.py"] == {3, 4}
    assert (repo / "pkg" / "window.py").read_text() == ORIGINAL  # scratch copy, repo untouched


def test_wrong_hunk_counts_apply_only_with_recount(repo):
    sloppy = GOLD.replace("@@ -1,3 +1,5 @@", "@@ -1,9 +1,9 @@")
    v = validate_diff(sloppy, tree_reader(repo))
    assert not v.strict_clean


def test_bad_context_is_rejected(repo):
    with pytest.raises(DiffError, match="git apply --check failed"):
        validate_diff(GOLD.replace("Return the last", "Return the first"), tree_reader(repo))


def test_syntax_error_is_rejected(repo):
    with pytest.raises(DiffError, match="does not parse"):
        validate_diff(GOLD.replace("if n <= 0:", "if n <= 0"), tree_reader(repo))


@pytest.mark.parametrize("path", ["../escape.py", "/etc/passwd"])
def test_unsafe_paths_are_rejected(repo, path):
    diff = GOLD.replace("a/pkg/window.py", f"a/{path}").replace("b/pkg/window.py", f"b/{path}")
    with pytest.raises(DiffError):
        validate_diff(diff, tree_reader(repo))


def test_files_outside_allowed_set_are_rejected(repo):
    with pytest.raises(DiffError, match="outside"):
        validate_diff(GOLD, tree_reader(repo), allowed_paths={"pkg/other.py"})


def test_empty_and_noop_diffs_are_rejected(repo):
    with pytest.raises(DiffError, match="empty"):
        validate_diff("  \n", tree_reader(repo))


# --- termination ----------------------------------------------------------------------------

LOOPS = {
    "while_true_no_exit": ("while True:\n    x = 1\n", True),
    "while_true_with_break": ("while True:\n    break\n", False),
    "while_true_with_return": ("def f():\n    while True:\n        return 1\n", False),
    "counter_advanced": ("i = 0\nwhile i < 3:\n    i += 1\n", False),
    "counter_not_advanced": ("i = 0\nwhile i < 3:\n    print(i)\n", True),
    "method_mutates": ("while q:\n    q.pop()\n", False),
    "derived_value_only": ("out = []\nwhile q:\n    out.append(q[-1])\n", True),
    "object_passed_is_not_trusted": ("while q:\n    consume(q)\n", True),
    "index_write_does_not_advance": ("i = 0\nwhile i < 3:\n    a[i] = 0\n", True),
    "attribute_advanced": ("while node:\n    node = node.next\n", False),
    "call_in_condition": ("while more():\n    pass\n", False),
    "nested_break_does_not_count": (
        "while True:\n    for x in y:\n        break\n",
        True,
    ),
    "itertools_count": ("import itertools\nfor i in itertools.count():\n    pass\n", True),
    "finite_for": ("for i in range(3):\n    pass\n", False),
}


@pytest.mark.parametrize("name", LOOPS)
def test_loop_exit_check(name):
    src, flagged = LOOPS[name]
    touched = set(range(1, src.count("\n") + 1))
    assert bool(loop_exit_problems(src, touched)) is flagged


def test_untouched_loops_are_not_checked():
    assert loop_exit_problems("while True:\n    x = 1\n\ny = 2\n", {4}) == []


# --- cache and ledger -----------------------------------------------------------------------


def test_cache_hit_makes_no_second_call(tmp_path):
    llm = make_llm(tmp_path, ["hello"])
    msgs = [{"role": "user", "content": "hi"}]
    assert llm.complete("t", msgs, max_tokens=10, temperature=0) == "hello"
    assert llm.complete("t", msgs, max_tokens=10, temperature=0) == "hello"
    assert len(llm.client.requests) == 1
    assert [c.cached for c in llm.calls] == [False, True]
    assert llm.calls[1].cost_usd == 0
    saved = json.loads(next((tmp_path / "cache").glob("*.json")).read_text())
    assert saved["content"] == "hello" and saved["model"] == llm.config.model


def test_cache_key_covers_model_and_prompt(tmp_path):
    a = make_llm(tmp_path, [])
    b = make_llm(tmp_path, [], model="other/model")
    m1, m2 = [{"role": "user", "content": "x"}], [{"role": "user", "content": "y"}]
    assert a.cache_key(m1, 10, 0) != b.cache_key(m1, 10, 0)
    assert a.cache_key(m1, 10, 0) != a.cache_key(m2, 10, 0)


def test_thinking_is_off_on_every_call(tmp_path):
    llm = make_llm(tmp_path, ["a", "b"])
    llm.complete("t", [{"role": "user", "content": "1"}], max_tokens=10, temperature=0)
    llm.complete("t", [{"role": "user", "content": "2"}], max_tokens=10, temperature=0)
    assert all(r["extra_body"] == THINKING_OFF for r in llm.client.requests)
    assert THINKING_OFF == {"chat_template_kwargs": {"enable_thinking": False}}


@pytest.mark.parametrize("empty", ["", "   \n", None])
def test_empty_response_fails_loudly_and_is_not_cached(tmp_path, empty):
    llm = make_llm(tmp_path, [empty])
    with pytest.raises(EmptyResponseError):
        llm.complete("t", [{"role": "user", "content": "x"}], max_tokens=10, temperature=0)
    assert not (tmp_path / "cache").exists() or not list((tmp_path / "cache").glob("*.json"))


def test_ledger_prices_tokens_from_config(tmp_path):
    llm = make_llm(tmp_path, ["a", "b"], usd_per_m_input=0.06, usd_per_m_output=0.24)
    for i in range(2):
        llm.complete("t", [{"role": "user", "content": str(i)}], max_tokens=10, temperature=0)
    per_call = (1000 * 0.06 + 200 * 0.24) / 1e6
    assert [c.cost_usd for c in llm.calls] == pytest.approx([per_call, per_call])
    assert llm.calls[-1].total_usd == pytest.approx(2 * per_call) == pytest.approx(llm.total_usd)


# --- proposers with recorded responses ------------------------------------------------------


def test_mutants_validated_rejected_and_reasked(repo, tmp_path):
    answers = [(FIXTURES / f"mutants_round{i}.txt").read_text() for i in (0, 1)]
    llm = make_llm(tmp_path, answers)
    out = propose_mutants(GOLD, 4, repo_dir=repo, issue_text="last_n(x, 0) returns x", llm=llm)

    assert len(out) == 4 and len(llm.client.requests) == 2
    assert [r for _, r in out] == [
        "Uses n < 0, so n=0 still slices items[-0:] and returns the whole list.",
        "Guards on an empty list instead of a non-positive n, so last_n([1, 2], 0) still "
        "returns everything.",
        "Only handles n == 0, so a negative n such as -2 still slices from the front.",
        "Treats n=1 as empty, so last_n([1, 2], 1) returns [] instead of [2].",
    ]
    r0 = llm.events[0]
    # applied counts every diff git accepted, whatever was rejected later: M1, M2, M4-M7;
    # strictly clean excludes M2, whose hunk counts are wrong
    assert (r0["parsed"], r0["applied"], r0["strict_clean"], r0["accepted"]) == (8, 6, 5, 2)
    reasons = {r["mutant"]: r["reason"] for r in r0["rejected"]}
    assert "git apply --check failed" in reasons[3]
    assert "does not parse" in reasons[4]
    assert "non-terminating" in reasons[5] and "non-terminating" in reasons[7]
    assert "identical" in reasons[6]
    assert "RATIONALE" in reasons[8]
    # the re-ask carries the rejections back to the model
    assert "non-terminating" in llm.client.requests[1]["messages"][-1]["content"]
    # every returned diff applies on top of the patched tree
    patched = validate_diff(GOLD, tree_reader(repo)).after
    for diff, _ in out:
        validate_diff(diff, lambda p: patched.get(p))


def test_mutant_reasks_are_capped(repo, tmp_path):
    llm = make_llm(tmp_path, ["no mutants here"] * 5)
    assert propose_mutants(GOLD, 3, repo_dir=repo, llm=llm) == []
    assert len(llm.client.requests) == 1 + MAX_REASK_ROUNDS


def test_mutant_prompt_states_the_termination_constraint(repo, tmp_path):
    llm = make_llm(tmp_path, ["nothing"] * 3)
    propose_mutants(GOLD, 2, repo_dir=repo, llm=llm)
    prompt = llm.client.requests[0]["messages"][1]["content"]
    assert "MUST terminate" in prompt and "$0.62 per CPU-minute" in prompt
    assert "operator flips" in prompt


def test_patch_reasks_with_the_error_then_succeeds(repo, tmp_path):
    bad = "```diff\n" + GOLD.replace("if n <= 0:", "if n <= 0") + "```"
    good = "```diff\n" + GOLD + "```"
    llm = make_llm(tmp_path, [bad, good])
    assert propose_patch("issue", "ctx", repo_dir=repo, llm=llm) == GOLD
    assert "does not parse" in llm.client.requests[1]["messages"][-1]["content"]


def test_patch_gives_up_after_the_cap(repo, tmp_path):
    llm = make_llm(tmp_path, ["no diff"] * 5)
    with pytest.raises(GenerationFailed):
        propose_patch("issue", "ctx", repo_dir=repo, llm=llm)
    assert len(llm.client.requests) == 1 + MAX_REASK_ROUNDS


def test_test_file_must_parse_and_define_a_test(tmp_path):
    llm = make_llm(
        tmp_path,
        [
            "```python\ndef helper(:\n```",
            "```python\nx = 1\n```",
            "```python\ndef test_a():\n    assert 1\n```",
        ],
    )
    assert propose_test("issue", "ctx", llm=llm).startswith("def test_a")
    assert len(llm.client.requests) == 3


def test_parse_mutants_keeps_malformed_blocks_as_errors():
    blocks = parse_mutants((FIXTURES / "mutants_round0.txt").read_text())
    assert len(blocks) == 8 and blocks[-1]["parse_error"] == "no RATIONALE line"


MUTANT_VS_ORIGINAL = '''\
### MUTANT 1
KIND: off-by-one
RATIONALE: Guards n < 0 instead of n <= 0, so n=0 still returns the whole list.
WITNESS:
```python
from pkg.window import last_n
last_n([1, 2, 3], 0)
```
```diff
--- a/pkg/window.py
+++ b/pkg/window.py
@@ -1,3 +1,5 @@
 def last_n(items, n):
     """Return the last n items of a list."""
+    if n < 0:
+        return []
     return items[-n:]
```
'''


def test_mutant_written_against_the_original_is_returned_against_the_patched_tree(repo, tmp_path):
    llm = make_llm(tmp_path, [MUTANT_VS_ORIGINAL])
    [(diff, why)] = propose_mutants(GOLD, 1, repo_dir=repo, llm=llm)
    assert why.startswith("Guards n < 0")
    assert llm.events[0]["strict_clean"] == 1
    patched = validate_diff(GOLD, tree_reader(repo)).after
    v = validate_diff(diff, lambda p: patched.get(p))
    assert v.strict_clean
    assert "-    if n <= 0:\n+    if n < 0:\n" in diff
    # the prompt shows the original source, not the patched one
    prompt = llm.client.requests[0]["messages"][1]["content"]
    assert (
        "## Original source" in prompt and "if n <= 0" not in prompt.split("## Original source")[1]
    )


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_live_recorded_responses_parse(version):
    """Real Nemotron answers from the three prompt versions, including the markdown-bold labels
    (`**KIND:**`) v2 and v3 produced."""
    text = (FIXTURES / f"pallets__flask-5014_live_{version}_round0.txt").read_text()
    blocks = parse_mutants(text)
    assert len(blocks) == 10
    assert all(b["rationale"] and b["diff"] and b["kind"] for b in blocks)


def test_reasks_raise_the_temperature(repo, tmp_path):
    llm = make_llm(tmp_path, ["no diff"] * 3)
    with pytest.raises(GenerationFailed):
        propose_patch("issue", "ctx", repo_dir=repo, llm=llm)
    assert [r["temperature"] for r in llm.client.requests] == [0.2, 0.5, 0.8]


# --- re-anchoring: blank-line and indentation slips in context ------------------------------

PATCHED = ORIGINAL.replace(
    '    """Return the last n items of a list."""\n',
    '    """Return the last n items of a list."""\n    if n <= 0:\n        return []\n',
)

# The live failure mode: an extra blank context line that is not in the source.
BLANK_SLIP = '''\
--- a/pkg/window.py
+++ b/pkg/window.py
@@ -6,6 +6,7 @@
 def drain(queue):
     """Pop every item off the queue, last first."""

     out = []
+    seen = 0
     while queue:
         out.append(queue.pop())
'''

# The other live failure mode: context lines dedented, the changed line correct.
INDENT_SLIP = '''\
--- a/pkg/window.py
+++ b/pkg/window.py
@@ -1,5 +1,5 @@
 def last_n(items, n):
 """Return the last n items of a list."""
-    if n <= 0:
+    if n < 0:
         return []
 return items[-n:]
'''


def test_blank_line_slip_is_rejected_strictly_but_repaired_on_request(repo):
    with pytest.raises(DiffError):
        validate_diff(BLANK_SLIP, tree_reader(repo))
    v = validate_diff(BLANK_SLIP, tree_reader(repo), repair=True)
    assert v.repaired and not v.strict_clean
    assert "    out = []\n    seen = 0\n    while queue:\n" in v.after["pkg/window.py"]
    assert v.after["pkg/window.py"].count("\n\n") == ORIGINAL.count("\n\n")  # no blank added
    assert validate_diff(v.diff, tree_reader(repo)).strict_clean  # the replacement is clean


def test_indentation_slip_is_repaired_and_added_lines_are_verbatim(tmp_path):
    root = tmp_path / "r" / "pkg"
    root.mkdir(parents=True)
    (root / "window.py").write_text(PATCHED)
    v = validate_diff(INDENT_SLIP, tree_reader(tmp_path / "r"), repair=True)
    assert v.repaired
    assert (
        '    """Return the last n items of a list."""\n    if n < 0:\n' in v.after["pkg/window.py"]
    )


def test_reanchoring_refuses_ambiguous_matches(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    (root / "m.py").write_text("x = 1\ny = 2\n\nx = 1\ny = 2\n")
    diff = "--- a/m.py\n+++ b/m.py\n@@ -1,2 +1,2 @@\n  x = 1\n-y = 2\n+y = 3\n"
    with pytest.raises(DiffError, match="2 matches"):
        validate_diff(diff, tree_reader(root), repair=True)


def test_reanchoring_refuses_real_content_mismatch(repo):
    wrong = BLANK_SLIP.replace("out = []", "result = []")
    with pytest.raises(DiffError, match="re-anchoring failed"):
        validate_diff(wrong, tree_reader(repo), repair=True)


def test_readme_records_the_configured_endpoint_and_model():
    readme = (Path(__file__).parent.parent / "README.md").read_text()
    c = GenerationConfig()
    assert c.base_url in readme and c.model in readme


def test_revert_with_different_formatting_is_still_a_revert(repo, tmp_path):
    """The structural check: removing the guard but leaving a stray comment and blank line is
    still the original code."""
    revert = (
        "### MUTANT 1\nKIND: silences-symptom\nRATIONALE: Drops the guard.\n"
        "WITNESS:\n```python\nfrom pkg.window import last_n\nlast_n([1], 0)\n```\n```diff\n"
        "--- a/pkg/window.py\n+++ b/pkg/window.py\n@@ -1,5 +1,5 @@\n"
        " def last_n(items, n):\n"
        '     """Return the last n items of a list."""\n'
        "-    if n <= 0:\n-        return []\n+    # guard removed\n+\n"
        "     return items[-n:]\n```\n"
    )
    llm = make_llm(tmp_path, [revert] * 3)
    assert propose_mutants(GOLD, 1, repo_dir=repo, llm=llm) == []
    assert "identical" in llm.events[0]["rejected"][0]["reason"]


def test_witness_is_required_and_must_end_in_an_expression():
    def block(witness):
        return (
            "### MUTANT 1\nKIND: off-by-one\nRATIONALE: r\n"
            + (f"WITNESS:\n```python\n{witness}\n```\n" if witness is not None else "")
            + "```diff\n--- a/x.py\n+++ b/x.py\n```\n"
        )

    assert parse_mutants(block("from m import f\nf(0)"))[0].get("parse_error") is None
    assert parse_mutants(block("from m import f\nf(0)"))[0]["witness"] == "from m import f\nf(0)"
    assert "no WITNESS" in parse_mutants(block(None))[0]["parse_error"]
    assert "end with one expression" in parse_mutants(block("x = 1"))[0]["parse_error"]
    assert "does not parse" in parse_mutants(block("f(("))[0]["parse_error"]


def test_records_carry_the_witness(repo, tmp_path):
    from falsifier.generate import propose_mutant_records

    answers = [(FIXTURES / f"mutants_round{i}.txt").read_text() for i in (0, 1)]
    recs = propose_mutant_records(GOLD, 4, repo_dir=repo, llm=make_llm(tmp_path, answers))
    assert [r["witness"].splitlines()[-1] for r in recs] == [
        "last_n([1, 2, 3], 0)",
        "last_n([1, 2], 0)",
        "last_n([1, 2, 3], -2)",
        "last_n([1, 2], 1)",
    ]

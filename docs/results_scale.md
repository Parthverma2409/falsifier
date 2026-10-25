# Results

**Scope: five SWE-bench Verified instances across three repositories (pallets/flask, psf/requests, pytest-dev/pytest). Configuration A: mutants of the gold patch, held to SWE-bench's full resolution criterion (FAIL_TO_PASS passes and PASS_TO_PASS does not regress). No claim is made about the rest of the benchmark.**

| Instance | Benchmark oracle | SWE-bench says | Falsifier says | Distinguishable mutants | Equivalent discarded | Survived FAIL_TO_PASS | **Survived both lists** | Canary exit | Mutants generated |
|---|---|---|---|---|---|---|---|---|---|
| `pallets__flask-5014` | FAIL_TO_PASS, 1 test(s) | RESOLVED | **UNEARNED** | 21 | 7 | 10 | **8** | 1 | 28 of 50 |
| `psf__requests-2931` | FAIL_TO_PASS, 1 test(s) | RESOLVED | **EARNED** | 2 | 2 | 0 | **0** | 1 | 4 of 50 |
| `psf__requests-6028` | FAIL_TO_PASS, 2 test(s) | RESOLVED | **UNEARNED** | 12 | 13 | 3 | **2** | 1 | 25 of 50 |
| `pytest-dev__pytest-10081` | FAIL_TO_PASS, 1 test(s) | RESOLVED | **EARNED** | 23 | 13 | 0 | **0** | 1 | 36 of 50 |
| `pytest-dev__pytest-5787` | FAIL_TO_PASS, 2 test(s) | RESOLVED | **EARNED** | 26 | 0 | 0 | **0** | 1 | 26 of 50 |
| `pytest-dev__pytest-5809` | FAIL_TO_PASS, 1 test(s) | RESOLVED | **EARNED** | 36 | 2 | 0 | **0** | 1 | 38 of 50 |
| `pytest-dev__pytest-7324` | FAIL_TO_PASS, 3 test(s) | RESOLVED | **EARNED** | 5 | 1 | 0 | **0** | 3 | 6 of 50 |
| `pytest-dev__pytest-7432` | FAIL_TO_PASS, 1 test(s) | RESOLVED | **EARNED** | 23 | 0 | 0 | **0** | 3 | 23 of 50 |
| `pytest-dev__pytest-7490` | FAIL_TO_PASS, 2 test(s) | RESOLVED | **EARNED** | 4 | 7 | 0 | **0** | 1 | 11 of 50 |
| `pytest-dev__pytest-7571` | FAIL_TO_PASS, 1 test(s) | RESOLVED | **EARNED** | 8 | 4 | 0 | **0** | 1 | 12 of 50 |

**28 instances enumerated, 10 included.** Why each of the 18 others is out:

- `psf__requests-1142`: zero applicable mutant diffs: 0 of 50 generated mutants were applicable well-formed diffs
- `psf__requests-1724`: failed the environment check: FAIL_TO_PASS on the original is PASS, not FAIL (exit 0, 6 passed, 21 warnings in 2.97s)
- `psf__requests-1766`: failed the environment check: PASS_TO_PASS on the gold patch: exit -1, timed out at 20 s, 79 of 79 ids not PASSED (e.g. ['test_requests.py::RequestsTestCase::test_BASICAUTH_TUPLE_HTTP_200_OK_GET', 'test_requests.py::RequestsTestCase::test_DIGESTAUTH_WRONG_HTTP_401_GET'])
- `psf__requests-1921`: failed the environment check: PASS_TO_PASS on the gold patch: exit None, 107 of 107 ids not PASSED (e.g. ['test_requests.py::RequestsTestCase::test_DIGESTAUTH_QUOTES_QOP_VALUE', 'test_requests.py::RequestsTestCase::test_DIGEST_AUTH_RETURNS_COOKIE'])
- `psf__requests-2317`: failed the environment check: PASS_TO_PASS on the gold patch: exit -1, timed out at 20 s, 133 of 133 ids not PASSED (e.g. ['test_requests.py::RequestsTestCase::test_BASICAUTH_TUPLE_HTTP_200_OK_GET', 'test_requests.py::RequestsTestCase::test_DIGESTAUTH_QUOTES_QOP_VALUE'])
- `psf__requests-5414`: hit the per-instance ceiling: psf__requests-5414 guard refusing to launch 'psf__requests-5414/witness-mutant-m43': spent $0.4352 + worst case $0.1549 exceeds ceiling $0.5000
- `pytest-dev__pytest-10051`: zero applicable mutant diffs: 0 of 50 generated mutants were applicable well-formed diffs
- `pytest-dev__pytest-10356`: mutant forks did not run cleanly: all 5 mutant forks ended with pytest exit 4 (usage error), deterministically on all three attempts: mutants of pytest's own mark code break pytest's command line. First labelled an infrastructure failure, wrongly; corrected after reading the evidence.
- `pytest-dev__pytest-5262`: failed the environment check: PASS_TO_PASS on the gold patch: exit 0, 1 of 108 ids not PASSED (e.g. ['[100%]'])
- `pytest-dev__pytest-5631`: zero distinguishable mutants:  1, 1 failed in 0.20 seconds) and passes on the patch (exit 0, 1 passed in 0.10 seconds); all 15 PASS_TO_PASS tests PASSED, but no mutant could be distinguished from the patch (1 equivalent discarded)
- `pytest-dev__pytest-5840`: failed the environment check: DiffError: git apply --check failed: error: patch failed: src/_pytest/config/__init__.py:453
error: src/_pytest/config/__init__.py: patch does not apply
- `pytest-dev__pytest-6197`: zero applicable mutant diffs: 0 of 50 generated mutants were applicable well-formed diffs
- `pytest-dev__pytest-6202`: hit the per-instance ceiling: pytest-dev__pytest-6202 guard refusing to launch 'pytest-dev__pytest-6202/mutant-m24+test': spent $0.4186 + worst case $0.1549 exceeds ceiling $0.5000
- `pytest-dev__pytest-7205`: zero applicable mutant diffs: 0 of 50 generated mutants were applicable well-formed diffs
- `pytest-dev__pytest-7236`: zero applicable mutant diffs: 0 of 50 generated mutants were applicable well-formed diffs
- `pytest-dev__pytest-7521`: failed the environment check: PASS_TO_PASS on the gold patch: exit 0, 1 of 125 ids not PASSED (e.g. ['[100%]'])
- `pytest-dev__pytest-7982`: hit the per-instance ceiling: pytest-dev__pytest-7982 guard refusing to launch 'pytest-dev__pytest-7982/mutant-m23+p2p': spent $0.2381 + worst case $0.3305 exceeds ceiling $0.5000
- `pytest-dev__pytest-8399`: zero applicable mutant diffs: 0 of 50 generated mutants were applicable well-formed diffs

**Headline: 10 mutant(s) cleared both FAIL_TO_PASS and PASS_TO_PASS** across 10 instance(s), i.e. SWE-bench's full resolution criterion, while provably behaving differently from the gold patch on their own witness.

"Benchmark oracle" means the repository's own FAIL_TO_PASS tests, not a reproduction of SWE-bench's harness. Every distinguishable survivor of FAIL_TO_PASS is also run against PASS_TO_PASS: UNEARNED means a mutant cleared both lists; UNPINNED means PASS_TO_PASS caught every such mutant. Full evidence: `reports/instances/<instance>.html` and `.json`.

## Survivors of FAIL_TO_PASS

### `pallets__flask-5014` m1 (off-by-one): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): The condition `if not name:` catches empty strings and `None`, but using `if len(name) == 0:` only catches the empty string case and would pass `None` through, allowing a Blueprint to be created with a `None` name.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,7 +190,7 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if len(name) == 0:
             raise ValueError("'name' may not be empty.")
 
         if "." in name:
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask.blueprints import Blueprint
# Correct patch raises ValueError for empty name
try:
    b = Blueprint('', 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for empty name')
# Mutant 1: len(name) == 0 passes None through
try:
    b = Blueprint(None, 'test_mod')
    print('Mutant 1: Blueprint created with None name - BUG')
except ValueError as e:
    print('Mutant 1: ValueError raised for None name - OK')
```

- Patch (exit 0): returns None, prints 'Correct patch: ValueError raised for empty name\nMutant 1: ValueError raised for None name - OK'
- Mutant (exit 0): raises TypeError("object of type 'NoneType' has no len()"), prints 'Correct patch: ValueError raised for empty name'
- PASS_TO_PASS on the mutant (exit 0, 60 passed in 0.23s): every PASS_TO_PASS test PASSED

### `pallets__flask-5014` m5 (too-narrow): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): The fix only checks `if not name:` but a developer might restrict the check to only `if name == '':` which would not catch `None` as an invalid name.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,7 +190,7 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if name == '':
             raise ValueError("'name' may not be empty.")
 
         if "." in name:
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask.blueprints import Blueprint
# Correct patch raises ValueError for both empty string and None
try:
    b = Blueprint('', 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for empty string name')
try:
    b = Blueprint(None, 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for None name')
# Mutant 5: 'if name == ""' only catches empty string, None passes through
try:
    b = Blueprint(None, 'test_mod')
    print('Mutant 5: Blueprint created with None name - BUG')
except ValueError as e:
    print('Mutant 5: ValueError raised for None name - OK')
```

- Patch (exit 0): returns None, prints 'Correct patch: ValueError raised for empty string name\nCorrect patch: ValueError raised for None name\nMutant 5: ValueError raised for None name - OK'
- Mutant (exit 0): raises TypeError("argument of type 'NoneType' is not iterable"), prints 'Correct patch: ValueError raised for empty string name'
- PASS_TO_PASS on the mutant (exit 0, 60 passed in 0.23s): every PASS_TO_PASS test PASSED

### `pallets__flask-5014` m6 (off-by-one): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): Using `if len(name) < 1:` is logically equivalent to `if not name:` for strings, but a developer might mistakenly use `if len(name) <= 0:` which has the same effect but the wrong condition form.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,7 +190,7 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if len(name) <= 0:
             raise ValueError("'name' may not be empty.")
 
         if "." in name:
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask.blueprints import Blueprint
# Both correct patch and mutant 9 behave the same for strings
# But the rationale is about the condition form being different
try:
    b = Blueprint('', 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for empty name')
try:
    b = Blueprint(None, 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for None name')
# Mutant 9: len(name) <= 0 - same behavior for strings but different condition form
try:
    b = Blueprint(None, 'test_mod')
    print('Mutant 9: Blueprint created with None name - BUG (len(None) fails)')
except TypeError as e:
    print('Mutant 9: TypeError for None - BUG (crashes instead of proper validation)')
```

- Patch (exit 0): raises ValueError("'name' may not be empty."), prints 'Correct patch: ValueError raised for empty name\nCorrect patch: ValueError raised for None name'
- Mutant (exit 0): raises TypeError("object of type 'NoneType' has no len()"), prints 'Correct patch: ValueError raised for empty name'
- PASS_TO_PASS on the mutant (exit 0, 60 passed in 0.20s): every PASS_TO_PASS test PASSED

### `pallets__flask-5014` m9 (off-by-one): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): The condition `if not name:` could be written as `if not name or name is None:` which is redundant but a developer might think it's more explicit; however, the off-by-one aspect is using `if len(name) < 1 and name is not None:` which incorrectly requires name to not be None while checking length.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,7 +190,7 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if len(name) < 1 and name is not None:
             raise ValueError("'name' may not be empty.")
 
         if "." in name:
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask.blueprints import Blueprint
# Correct patch raises ValueError for empty name and None
try:
    b = Blueprint('', 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for empty name')
try:
    b = Blueprint(None, 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for None name')
# Mutant 15: 'if len(name) < 1 and name is not None:' requires name to not be None
# so None passes the length check (len(None) TypeError) but the condition structure is wrong
try:
    b = Blueprint(None, 'test_mod')
    print('Mutant 15: Blueprint created with None name - BUG')
except (ValueError, TypeError) as e:
    print(f'Mutant 15: {type(e).__name__} raised - OK')
```

- Patch (exit 0): returns None, prints 'Correct patch: ValueError raised for empty name\nCorrect patch: ValueError raised for None name\nMutant 15: ValueError raised - OK'
- Mutant (exit 0): raises TypeError("object of type 'NoneType' has no len()"), prints 'Correct patch: ValueError raised for empty name'
- PASS_TO_PASS on the mutant (exit 0, 60 passed in 0.23s): every PASS_TO_PASS test PASSED

### `pallets__flask-5014` m15 (wrong-condition): caught by PASS_TO_PASS

Rationale (the model's words): The guard tests `if not name:` but a developer might mistakenly write `if not name or name is not None:` which is always True (De Morgan's law), always raising the error even for valid names.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,7 +190,7 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if not name or name is not None:
             raise ValueError("'name' may not be empty.")
 
         if "." in name:
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask.blueprints import Blueprint
# Correct patch only raises for empty/None names
try:
    b = Blueprint('myblueprint', 'test_mod')
    print('Correct patch: Valid name accepted - OK')
except ValueError as e:
    print(f'Correct patch: {e} - BUG')
# Mutant 24: 'if not name or name is not None:' is always True, always raises
try:
    b = Blueprint('myblueprint', 'test_mod')
    print('Mutant 24: Valid name rejected - BUG (always raises)')
except ValueError as e:
    print(f'Mutant 24: {e} - OK (always raises as expected)')
```

- Patch (exit 0): returns None, prints 'Correct patch: Valid name accepted - OK\nMutant 24: Valid name rejected - BUG (always raises)'
- Mutant (exit 0): returns None, prints "Correct patch: 'name' may not be empty. - BUG\nMutant 24: 'name' may not be empty. - OK (always raises as expected)"
- PASS_TO_PASS on the mutant (exit 1, 58 failed, 2 passed in 0.92s): 58 not PASSED, e.g. tests/test_blueprints.py::test_blueprint_specific_error_handling, tests/test_blueprints.py::test_blueprint_specific_user_error_handling, tests/test_blueprints.py::test_blueprint_app_error_handling

### `pallets__flask-5014` m19 (off-by-one): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): The condition `if not name:` could be written as `if name == '' or name is None:` which is explicit but the off-by-one aspect is `if name == '' and name is not None:` which is never True.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,7 +190,7 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if name == '' and name is not None:
             raise ValueError("'name' may not be empty.")
 
         if "." in name:
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask.blueprints import Blueprint
# Correct patch raises ValueError for empty name and None
try:
    b = Blueprint('', 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for empty name')
try:
    b = Blueprint(None, 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for None name')
# Mutant 35: 'if name == "" and name is not None:' is always False, never raises
try:
    b = Blueprint('', 'test_mod')
    print('Mutant 35: Blueprint created with empty name - BUG (condition always False)')
except ValueError as e:
    print('Mutant 35: ValueError raised - OK')
```

- Patch (exit 0): returns None, prints 'Correct patch: ValueError raised for empty name\nCorrect patch: ValueError raised for None name\nMutant 35: ValueError raised - OK'
- Mutant (exit 0): raises TypeError("argument of type 'NoneType' is not iterable"), prints 'Correct patch: ValueError raised for empty name'
- PASS_TO_PASS on the mutant (exit 0, 60 passed in 0.22s): every PASS_TO_PASS test PASSED

### `pallets__flask-5014` m21 (too-narrow): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): The fix only checks `if not name:` but a developer might add a type check that only applies to string names, missing the case where name is a non-string empty value.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,7 +190,7 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if type(name) == str and name == '':
             raise ValueError("'name' may not be empty.")
 
         if "." in name:
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask.blueprints import Blueprint
# Correct patch raises ValueError for any falsy name
try:
    b = Blueprint('', 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for empty string name')
try:
    b = Blueprint(None, 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for None name')
# Mutant 37: only checks if name is an empty string, not None
# Using type name == '' misses None
try:
    b = Blueprint(None, 'test_mod')
    print('Mutant 37: Blueprint created with None name - BUG')
except ValueError as e:
    print('Mutant 37: ValueError raised for None name - OK')
```

- Patch (exit 0): returns None, prints 'Correct patch: ValueError raised for empty string name\nCorrect patch: ValueError raised for None name\nMutant 37: ValueError raised for None name - OK'
- Mutant (exit 0): raises TypeError("argument of type 'NoneType' is not iterable"), prints 'Correct patch: ValueError raised for empty string name'
- PASS_TO_PASS on the mutant (exit 0, 60 passed in 0.22s): every PASS_TO_PASS test PASSED

### `pallets__flask-5014` m24 (off-by-one): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): The condition `if not name:` could be written as `if len(name) < 1:` which is equivalent for strings, but the off-by-one story is `if len(name) <= 1:` which is one too many - it would raise for single-character names too.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,7 +190,7 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if len(name) <= 1:
             raise ValueError("'name' may not be empty.")
 
         if "." in name:
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask.blueprints import Blueprint
# Correct patch raises ValueError for empty name ''
try:
    b = Blueprint('', 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for empty name')
# Mutant 43: 'if len(name) <= 1:' raises for both empty and single-character names
try:
    b = Blueprint('a', 'test_mod')
    print('Mutant 43: Single-char name accepted - OK')
except ValueError as e:
    print(f'Mutant 43: {e} - BUG (single char rejected)')
```

- Patch (exit 0): returns None, prints 'Correct patch: ValueError raised for empty name\nMutant 43: Single-char name accepted - OK'
- Mutant (exit 0): returns None, prints "Correct patch: ValueError raised for empty name\nMutant 43: 'name' may not be empty. - BUG (single char rejected)"
- PASS_TO_PASS on the mutant (exit 0, 60 passed in 0.21s): every PASS_TO_PASS test PASSED

### `pallets__flask-5014` m25 (too-narrow): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): The fix only checks `if not name:` but a developer might restrict it to only check when name is a string type, missing the case where name is a list or other falsy container.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,7 +190,7 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if isinstance(name, str) and not name:
             raise ValueError("'name' may not be empty.")
 
         if "." in name:
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask.blueprints import Blueprint
# Correct patch raises ValueError for any falsy name
try:
    b = Blueprint('', 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for empty string name')
try:
    b = Blueprint(None, 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for None name')
# Mutant 45: only checks if name is a string, list([]) would pass
try:
    b = Blueprint([], 'test_mod')
    print('Mutant 45: Blueprint created with empty list name - BUG')
except ValueError as e:
    print('Mutant 45: ValueError raised - OK')
```

- Patch (exit 0): returns None, prints 'Correct patch: ValueError raised for empty string name\nCorrect patch: ValueError raised for None name\nMutant 45: ValueError raised - OK'
- Mutant (exit 0): raises TypeError("argument of type 'NoneType' is not iterable"), prints 'Correct patch: ValueError raised for empty string name'
- PASS_TO_PASS on the mutant (exit 0, 60 passed in 0.21s): every PASS_TO_PASS test PASSED

### `pallets__flask-5014` m27 (wrong-condition): caught by PASS_TO_PASS

Rationale (the model's words): The guard tests `if not name:` but a developer might mistakenly write `if name is not None:` which only catches `None` and misses empty strings entirely.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,7 +190,7 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if name is not None:
             raise ValueError("'name' may not be empty.")
 
         if "." in name:
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask.blueprints import Blueprint
# Correct patch raises ValueError for both empty string and None
try:
    b = Blueprint('', 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for empty string name')
try:
    b = Blueprint(None, 'test_mod')
except ValueError:
    print('Correct patch: ValueError raised for None name')
# Mutant 7: 'if name is not None:' only catches None
try:
    b = Blueprint('', 'test_mod')
    print('Mutant 7: Blueprint created with empty string name - BUG')
except ValueError as e:
    print('Mutant 7: ValueError raised for empty string - OK')
```

- Patch (exit 0): returns None, prints 'Correct patch: ValueError raised for empty string name\nCorrect patch: ValueError raised for None name\nMutant 7: ValueError raised for empty string - OK'
- Mutant (exit 0): raises TypeError("argument of type 'NoneType' is not iterable"), prints 'Correct patch: ValueError raised for empty string name'
- PASS_TO_PASS on the mutant (exit 1, 58 failed, 2 passed in 0.90s): 58 not PASSED, e.g. tests/test_blueprints.py::test_blueprint_specific_error_handling, tests/test_blueprints.py::test_blueprint_specific_user_error_handling, tests/test_blueprints.py::test_blueprint_app_error_handling

### `psf__requests-6028` m4 (wrong-condition): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): The correct patch adds auth when `auth` is truthy. A wrong-condition mutant might check `if scheme is not None:` instead, which would add the scheme regardless of auth, potentially duplicating or misplacing it.

```diff
--- a/requests/utils.py
+++ b/requests/utils.py
@@ -974,7 +974,7 @@ def prepend_scheme_if_needed(url, new_scheme):
     if not netloc:
         netloc, path = path, netloc
 
-    if auth:
+    if scheme is not None:
         # parse_url doesn't provide the netloc with auth
         # so we'll add it ourselves.
         netloc = '@'.join([auth, netloc])
```

The test that missed it: `tests/test_utils.py::test_prepend_scheme_if_needed[http://user:pass@example.com/path?query-http://user:pass@example.com/path?query] tests/test_utils.py::test_prepend_scheme_if_needed[http://user@example.com/path?query-http://user@example.com/path?query]`, exit 0 on the mutant (exit 0, 2 passed in 0.05s).

Witness:

```python
from requests.utils import prepend_scheme_if_needed
# URL without auth but with scheme, correct patch only adds scheme if None, this mutant adds scheme always
prepend_scheme_if_needed('http://example.com', 'https')
```

- Patch (exit 0): returns 'http://example.com'
- Mutant (exit 0): raises TypeError('sequence item 0: expected str instance, NoneType found')
- PASS_TO_PASS on the mutant (exit 1, 195 passed, 11 skipped, 8 errors in 0.30s): every PASS_TO_PASS test PASSED

### `psf__requests-6028` m11 (wrong-condition): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): The correct patch checks `if auth:` after the netloc swap. A wrong-condition mutant might check `if scheme:` instead, which would be True for any non-empty scheme string, potentially adding auth incorrectly.

```diff
--- a/requests/utils.py
+++ b/requests/utils.py
@@ -974,7 +974,7 @@ def prepend_scheme_if_needed(url, new_scheme):
     if not netloc:
         netloc, path = path, netloc
 
-    if auth:
+    if scheme:
         # parse_url doesn't provide the netloc with auth
         # so we'll add it ourselves.
         netloc = '@'.join([auth, netloc])
```

The test that missed it: `tests/test_utils.py::test_prepend_scheme_if_needed[http://user:pass@example.com/path?query-http://user:pass@example.com/path?query] tests/test_utils.py::test_prepend_scheme_if_needed[http://user@example.com/path?query-http://user@example.com/path?query]`, exit 0 on the mutant (exit 0, 2 passed in 0.05s).

Witness:

```python
from requests.utils import prepend_scheme_if_needed
# URL with scheme 'https', correct patch only adds auth when auth exists, this mutant adds auth for any scheme
prepend_scheme_if_needed('http://example.com', 'https')
```

- Patch (exit 0): returns 'http://example.com'
- Mutant (exit 0): raises TypeError('sequence item 0: expected str instance, NoneType found')
- PASS_TO_PASS on the mutant (exit 1, 195 passed, 11 skipped, 8 errors in 0.34s): every PASS_TO_PASS test PASSED

### `psf__requests-6028` m15 (wrong-condition): caught by PASS_TO_PASS

Rationale (the model's words): The correct patch checks `if auth:` to decide whether to add auth prefix. A wrong-condition mutant might check `if netloc:` instead, which would add auth only when netloc already exists, missing the case where netloc is empty and auth needs to be prepended.

```diff
--- a/requests/utils.py
+++ b/requests/utils.py
@@ -974,7 +974,7 @@ def prepend_scheme_if_needed(url, new_scheme):
     if not netloc:
         netloc, path = path, netloc
 
-    if auth:
+    if netloc:
         # parse_url doesn't provide the netloc with auth
         # so we'll add it ourselves.
         netloc = '@'.join([auth, netloc])
```

The test that missed it: `tests/test_utils.py::test_prepend_scheme_if_needed[http://user:pass@example.com/path?query-http://user:pass@example.com/path?query] tests/test_utils.py::test_prepend_scheme_if_needed[http://user@example.com/path?query-http://user@example.com/path?query]`, exit 0 on the mutant (exit 0, 2 passed in 0.05s).

Witness:

```python
from requests.utils import prepend_scheme_if_needed
# URL without netloc but with auth, correct patch swaps netloc/path and adds auth@new_netloc, this mutant only adds auth when netloc already exists
prepend_scheme_if_needed('example.com', 'https')
```

- Patch (exit 0): returns 'https://example.com'
- Mutant (exit 0): raises TypeError('sequence item 0: expected str instance, NoneType found')
- PASS_TO_PASS on the mutant (exit 1, 3 failed, 192 passed, 11 skipped, 8 errors in 0.38s): 3 not PASSED, e.g. tests/test_utils.py::test_prepend_scheme_if_needed[example.com/path-http://example.com/path], tests/test_utils.py::test_prepend_scheme_if_needed[//example.com/path-http://example.com/path], tests/test_utils.py::test_prepend_scheme_if_needed[example.com:80-http://example.com:80]

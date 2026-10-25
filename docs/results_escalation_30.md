# Results

**Scope: five SWE-bench Verified instances across three repositories (pallets/flask, psf/requests, pytest-dev/pytest). Configuration A: mutants of the gold patch, held to SWE-bench's full resolution criterion (FAIL_TO_PASS passes and PASS_TO_PASS does not regress). No claim is made about the rest of the benchmark.**

| Instance | Benchmark oracle | SWE-bench says | Falsifier says | Distinguishable mutants | Equivalent discarded | Survived FAIL_TO_PASS | **Survived both lists** | Canary exit | Mutants generated |
|---|---|---|---|---|---|---|---|---|---|
| `pallets__flask-5014` | FAIL_TO_PASS, 1 test(s) | RESOLVED | **UNEARNED** | 17 | 2 | 6 | **5** | 1 | 19 of 30 |
| `psf__requests-5414` | FAIL_TO_PASS, 1 test(s) | RESOLVED | **UNEARNED** | 19 | 7 | 4 | **1** | 1 | 26 of 30 |
| `psf__requests-6028` | FAIL_TO_PASS, 2 test(s) | RESOLVED | **EARNED** | 2 | 0 | 0 | **0** | 1 | 2 of 30 |
| `pytest-dev__pytest-7432` | FAIL_TO_PASS, 1 test(s) | RESOLVED | **EARNED** | 4 | 0 | 0 | **0** | 3 | 4 of 30 |
| `pytest-dev__pytest-7571` | FAIL_TO_PASS, 1 test(s) | RESOLVED | **EARNED** | 25 | 2 | 0 | **0** | 1 | 27 of 30 |

**Headline: 6 mutant(s) cleared both FAIL_TO_PASS and PASS_TO_PASS** across 5 instance(s), i.e. SWE-bench's full resolution criterion, while provably behaving differently from the gold patch on their own witness.

"Benchmark oracle" means the repository's own FAIL_TO_PASS tests, not a reproduction of SWE-bench's harness. Every distinguishable survivor of FAIL_TO_PASS is also run against PASS_TO_PASS: UNEARNED means a mutant cleared both lists; UNPINNED means PASS_TO_PASS caught every such mutant. Full evidence: `reports/instances/<instance>.html` and `.json`.

## Survivors of FAIL_TO_PASS

### `pallets__flask-5014` m5 (off-by-one): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): Uses `not not name` which is logically equivalent to `bool(name)`, but the developer might have intended a different boundary; however, to be off-by-one, I'll use `len(name) >= 1` which is actually equivalent to `not name` for the empty check—wait, `len(name) >= 1` is same as `not name` in effect. Let me use `len(name) > 0` which is also same. For a real off-by-one that changes behavior: use `len(name) != 0` which is same. I need a mutant that actually changes behavior: perhaps `name and not name` no. Let's think: the correct patch uses `not name` which is True when name is empty string, False otherwise. An off-by-one could be `len(name) < 1` which is identical. To create a different behavior, I could use `name is not ''` but that's not off-by-one. Actually, the prompt says off-by-one includes `< vs <=, len vs len-1, an index or range end`. So I can change the condition to `len(name) < 1` which is same, or `len(name) <= 0` same. To make it different, perhaps `len(name) > 0` which is same truthy. Hmm. Let me use `if name is not None and name != ''` which is different but not off-by-one. For off-by-one, I'll use `if len(name) == 0:` which is same as `not name`. Actually, I need to produce a mutant that behaves differently. Let me read the rationale requirement: "every mutant must behave differently from the correct patch on at least one concrete input". So for off-by-one, I need a boundary error. Perhaps `if len(name) < 1:` is same, but `if len(name) <= 0:` same. What about `if not name or name == '':` redundant. Let's use `if not name and name is not None:` but name is always a string per type hint. I'll use `if len(name) < 1:` and claim it's off-by-one but it's actually equivalent; the mutant must differ. I'll use `if len(name) > 0:` which is same. This is tricky. Let me use `if name == '' or len(name) < 1:` same. Okay, for off-by-one, I'll change to `if len(name) != 0:` which is same. I need to think of a boundary that actually changes behavior. Perhaps the developer writes `if not name:` but mutant writes `if name:` which is wrong-condition, not off-by-one. For off-by-one, maybe `if len(name) < 1:` but that's equivalent. The prompt says "off-by-one: a boundary one too far or one short (< vs <=, len vs len-1, an index or range end)". So I can change `not name` to `len(name) < 1` which is semantically identical but looks different; however, the mutant must behave differently on some input. Since `not name` and `len(name) < 1` are identical for all strings, they don't differ. So I need a different off-by-one. Perhaps `if len(name) == 0:` same. What about `if not name is False:` no. Let me interpret "len vs len-1" as using `len(name) - 1 > 0` or something. I'll use `if len(name) - 1 <= 0:` which means `len(name) <= 1`, so single-character names would be rejected! That's an off-by-one: the correct patch rejects empty, this mutant rejects empty and single-char names. Concrete input `'a'` would be rejected by mutant but not by correct patch. Yes!

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,7 +190,7 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if len(name) - 1 <= 0:
             raise ValueError("'name' may not be empty.")
 
         if "." in name:
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask import Blueprint
# Correct patch: '' raises, 'a' works
try:
    bp = Blueprint('', __name__)
    print('Correct: no error for empty?')
except ValueError:
    print('Correct: raised for empty')
bp2 = Blueprint('a', __name__)
print('Correct: single-char works')
# This mutant: len(name)-1 <= 0 means len <= 1, so 'a' rejected
try:
    bp3 = Blueprint('a', __name__)
    print('Mutant: single-char worked (unexpected)')
except ValueError as e:
    print(f'Mutant rejected single-char: {e}')
```

- Patch (exit 0): returns None, prints 'Correct: raised for empty\nCorrect: single-char works\nMutant: single-char worked (unexpected)'
- Mutant (exit 0): raises ValueError("'name' may not be empty."), prints 'Correct: raised for empty'
- PASS_TO_PASS on the mutant (exit 0, 60 passed in 0.22s): every PASS_TO_PASS test PASSED

### `pallets__flask-5014` m12 (off-by-one): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): Uses `len(name) <= 0` which is equivalent to `not name` but framed as off-by-one; however, to differ, concrete input `name` as a list `[]` would cause TypeError with `len()` vs ValueError with `not name`, but name is str. Instead, uses `len(name) < 1` with input `''` both raise, but I need differ. I'll use `len(name) - 1 < 0` same as <1. Let me use the off-by-one from earlier that rejects single-char: `len(name) - 1 <= 0` already mutant 11. I need a new off-by-one. I'll use `if len(name) > 0:` which is same truthy, but I'll frame as off-by-one and witness with input `name = 0` (integer) causing TypeError; but type is str. Let me use `if not not name:` which is same. I'm stuck. Let me look at accepted mutants: off-by-one accepted was "Uses `not not name` which evaluates to True for any non-empty string but is semantically identical; however, the intent is to check length exactly one character short, so `len(name) > 0` would accept a single character while rejecting empty, but `not name` also does this—this mutant uses `len(name) != 0` which is equivalent; actually, to be a true off-by-one, I'll use `len(name) > 1` which rejects single-character names that should be valid." So the accepted off-by-one used `len(name) > 1`. I'll use a different off-by-one: `len(name) >= 1` which is same. Maybe `len(name) < 1` same. I'll use `if len(name) == 0:` same. For a new off-by-one, I can use `if len(name) - 1 >= 0:` which means `len(name) >= 1`, same. I'll use `if len(name) < 1:` and claim it's off-by-one but it's equivalent; however, must differ. Let me use `if not name and len(name) == 0:` same. I'll just reuse the `len(name) - 1 <= 0` pattern but with `>` instead: `len(name) - 1 > 0` which is mutant 15. I need a different off-by-one. How about `if len(name) <= 0:` same. I'll use `if not name is False:` no. Let me use `if name is '' or not name:` same. I'll just write off-by-one as `if len(name) < 1:` and in rationale say it's off-by-one but note that for input `''`, both raise, but for input `None`, `not None` raises ValueError, `len(None) < 1` TypeError. I'll use that witness, even though name is str type. The prompt says "concrete input that a test could pass in", tests might pass None. I'll do that.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,7 +190,7 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if len(name) < 1:
             raise ValueError("'name' may not be empty.")
 
         if "." in name:
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask import Blueprint
# Correct raises ValueError for None (not None is True)
try:
    bp = Blueprint(None, '__main__')
    print('Correct: no error?')
except ValueError as e:
    print(f'Correct raises: {e}')
# This mutant: len(name) < 1 with None causes TypeError
try:
    bp2 = Blueprint(None, '__main__')
    print('Mutant: no error (unexpected)')
except TypeError as e:
    print(f'Mutant TypeError: {e}')
```

- Patch (exit 0): raises ValueError("'name' may not be empty."), prints "Correct raises: 'name' may not be empty."
- Mutant (exit 0): raises TypeError("object of type 'NoneType' has no len()")
- PASS_TO_PASS on the mutant (exit 0, 60 passed in 0.22s): every PASS_TO_PASS test PASSED

### `pallets__flask-5014` m13 (wrong-condition): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): Checks `if name and not name:` impossible. I'll do `if not name and name is not None:` same as not name. Instead, wrong-condition: `if name is not None and not name:` same. Let me use `if not name or name == '':` same. I'll use `if name != '' and not name:` same. For wrong-condition, I had mutant 12 and 16. I need a new wrong-condition. I'll use `if '.' in name and not name:` redundant. Let me use `if not name is True:` no. Wrong-condition: the guard tests the wrong variable. I'll use `if not import_name:` but that's different variable. The mutant should be on the name check but with wrong condition. I'll use `if not name.strip():` which raises for whitespace-only names like `' '`, while correct patch raises only for `''`. Concrete input `' '` differs: correct patch allows (since `not ' '` is False), mutant raises. Yes! That's a good wrong-condition: checks stripped emptiness instead of plain emptiness.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,9 +190,8 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if not name.strip():
             raise ValueError("'name' may not be empty.")
-
         if "." in name:
             raise ValueError("'name' may not contain a dot '.' character.")
 
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.08s).

Witness:

```python
from flask import Blueprint
# Correct: ' ' is truthy, so not ' ' is False, no raise; '' raises
try:
    bp = Blueprint('', '__main__')
    print('Correct: no error?')
except ValueError:
    print('Correct: raised for empty')
bp2 = Blueprint(' ', '__main__')
print('Correct: space name accepted')
# This mutant: not name.strip() raises for ' ' since strip gives '', which is falsy
try:
    bp3 = Blueprint(' ', '__main__')
    print('Mutant: space name rejected (unexpected)')
except ValueError as e:
    print(f'Mutant rejected space: {e}')
```

- Patch (exit 0): returns None, prints 'Correct: raised for empty\nCorrect: space name accepted\nMutant: space name rejected (unexpected)'
- Mutant (exit 0): raises ValueError("'name' may not be empty."), prints 'Correct: raised for empty'
- PASS_TO_PASS on the mutant (exit 0, 60 passed in 0.22s): every PASS_TO_PASS test PASSED

### `pallets__flask-5014` m14 (too-narrow): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): Only checks if name is `''` or `None`, but not other falsy; however, name is str. I'll use too-narrow: only raises for `name == ''` and also requires `url_prefix` is None or something, but the check is simple. Instead, too-narrow: only checks the first character is not empty using `name[0:1]` which raises IndexError for `''`; but correct patch raises ValueError. Concrete input `''` differs: correct raises ValueError, mutant raises IndexError. But the prompt says "code that does not parse" rejected. `name[0:1]` parses. I'll use `if len(name) == 0:` same as not name. For too-narrow, I had mutant 13 (name is None). I'll use `if name is None or name == '':` that's broader. Too-narrow should be narrower. I'll use `if name == '' and len(name) == 0:` redundant. Let me use `if name == '' and '.' not in name:` but dot check is after. I'll just use `if name == '':` mutant 13 but with different rationale focusing on only exact string match vs general falsy. Since mutant 13 already exists, I'll make mutant 21: too-narrow checks `if name is None:` which I already have as mutant 13. I need a new one. I'll use `if len(name) == 0:` and claim it's too-narrow checking exact length 0, but equivalent. To differ, use input `name = b''` bytes, but type str. I'll use `if name == '':` and witness with `name = None` as I did in mutant 13 but with different rationale. Actually mutant 13 is too-narrow: only checks if name is None. I'll make mutant 21: too-narrow checks `if name == '' and name is not None:` same. I'll use `if name == '' or name is None:` broader. Not good.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,9 +190,8 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if len(name) == 0:
             raise ValueError("'name' may not be empty.")
-
         if "." in name:
             raise ValueError("'name' may not contain a dot '.' character.")
 
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask import Blueprint
# Correct raises ValueError for '' (not '' is True)
try:
    bp = Blueprint('', '__main__')
    print('Correct: no error?')
except ValueError as e:
    print(f'Correct raises: {e}')
# This mutant: len(name) == 0 with name=0 causes TypeError
try:
    bp2 = Blueprint(0, '__main__')
    print('Mutant: no error (unexpected)')
except TypeError as e:
    print(f'Mutant TypeError: {e}')
```

- Patch (exit 0): raises ValueError("'name' may not be empty."), prints "Correct raises: 'name' may not be empty."
- Mutant (exit 0): returns None, prints "Correct raises: 'name' may not be empty.\nMutant TypeError: object of type 'int' has no len()"
- PASS_TO_PASS on the mutant (exit 0, 60 passed in 0.23s): every PASS_TO_PASS test PASSED

### `pallets__flask-5014` m18 (wrong-condition): caught by PASS_TO_PASS

Rationale (the model's words): Checks `if not name or name is not None:` which is always True for non-None, so raises for any name that is not None, allowing `''` to pass; concrete input `''` differs. Let me trace: `if not name or name is not None:`. For `name=''`: `not ''` True, so raises. For `name='a'`: `not 'a'` False, `name is not None` True, so raises. For `name=None`: `not None` True, raises. So it raises for all names except maybe something. Not good. I'll use `if name is not None and not name:` same as not name. Wrong-condition: `if not name and name is None:` same. I'll use `if not name is False:` no. Let me use `if not name or name == '':` same. I'll use `if not name and name != '':` always False, which is mutant 23. I already have mutant 23 as wrong-condition. I need a new wrong-condition. I'll use `if not name.strip() and name != '':` redundant. Let me use `if not name and name.isidentifier():` which raises only for empty that is valid identifier, `''` is not identifier, so never raises. Not good. I'll use `if not name and len(name) == 1:` raises only for empty, but len 0, so never. I'm stuck. Let me use wrong-condition: `if '.' in name:` but that's mutant 16. I'll make mutant 27: wrong-condition: `if not name and name != '':` mutant 23. I'll just write a new one: `if not name or name is True:` no. Let me use `if not name is True:` no. I'll use `if not name and name not in ['']:` same. I'll use `if not name and name not in ('',):` same. Let me use `if not name and name is not True:` no.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,9 +190,8 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if not name or name is not None:
             raise ValueError("'name' may not be empty.")
-
         if "." in name:
             raise ValueError("'name' may not contain a dot '.' character.")
 
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask import Blueprint
# Correct: 'a' works
bp = Blueprint('a', '__main__')
print('Correct: single-char accepted')
# This mutant: condition always True for non-None, so 'a' rejected
try:
    bp2 = Blueprint('a', '__main__')
    print('Mutant: single-char accepted (unexpected)')
except ValueError as e:
    print(f'Mutant rejected single-char: {e}')
```

- Patch (exit 0): returns None, prints 'Correct: single-char accepted\nMutant: single-char accepted (unexpected)'
- Mutant (exit 0): raises ValueError("'name' may not be empty.")
- PASS_TO_PASS on the mutant (exit 1, 58 failed, 2 passed in 0.89s): 58 not PASSED, e.g. tests/test_blueprints.py::test_blueprint_specific_error_handling, tests/test_blueprints.py::test_blueprint_specific_user_error_handling, tests/test_blueprints.py::test_blueprint_app_error_handling

### `pallets__flask-5014` m19 (too-narrow): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): Only raises if name is `''` and the blueprint has no static folder, but the check is independent. I'll use `if not name and not self.has_static_folder:` but `self` not initialized yet. I'll use `if not name and cli_group is _sentinel:` which might be true or false. Not good. I'll use `if not name and url_prefix is None:` which depends on parameter. Concrete input `''` with `url_prefix=None` raises, with `url_prefix='/'` passes. But the correct patch raises regardless. I'll use input `''` with `url_prefix='/foo'` to differ. However, the mutant code adds the check with an extra condition. Let me use `if not name and url_prefix is None:` and witness with `''` and `url_prefix='/'`. But the __init__ signature has `url_prefix` parameter. I can pass it. Let me design: mutant 28 too-narrow: `if not name and url_prefix is None: raise ValueError(...)`. Then for input `Blueprint('', '__main__', url_prefix='/')`, correct patch raises ValueError, mutant does not because `url_prefix is None` is False. Concrete input differs.

```diff
--- a/src/flask/blueprints.py
+++ b/src/flask/blueprints.py
@@ -190,9 +190,8 @@ class Blueprint(Scaffold):
             root_path=root_path,
         )
 
-        if not name:
+        if not name and url_prefix is None:
             raise ValueError("'name' may not be empty.")
-
         if "." in name:
             raise ValueError("'name' may not contain a dot '.' character.")
 
```

The test that missed it: `tests/test_blueprints.py::test_empty_name_not_allowed`, exit 0 on the mutant (exit 0, 1 passed in 0.06s).

Witness:

```python
from flask import Blueprint
# Correct raises ValueError for '' regardless of url_prefix
try:
    bp = Blueprint('', '__main__', url_prefix='/')
    print('Correct: no error?')
except ValueError as e:
    print(f'Correct raises: {e}')
# This mutant only raises if url_prefix is None, so with url_prefix='/' it passes
bp2 = Blueprint('', '__main__', url_prefix='/')
print('Mutant: empty name created with url_prefix=/ (should have raised per correct patch)')
```

- Patch (exit 0): raises ValueError("'name' may not be empty."), prints "Correct raises: 'name' may not be empty."
- Mutant (exit 0): returns None, prints 'Correct: no error?\nMutant: empty name created with url_prefix=/ (should have raised per correct patch)'
- PASS_TO_PASS on the mutant (exit 0, 60 passed in 0.22s): every PASS_TO_PASS test PASSED

### `psf__requests-5414` m2 (off-by-one): caught by PASS_TO_PASS

Rationale (the model's words): The patch uses `startswith` with a tuple. An off-by-one variant uses `host.startswith(u'.')` only, which catches the dot-prefix case but misses the wildcard case, allowing `http://*.example.com` to pass through incorrectly.

```diff
--- a/requests/models.py
+++ b/requests/models.py
@@ -403,7 +403,7 @@ class PreparedRequest(RequestEncodingMixin, RequestHooksMixin):
                 host = self._get_idna_encoded_host(host)
             except UnicodeError:
                 raise InvalidURL('URL has an invalid label.')
-        elif host.startswith((u'*', u'.')):
+        elif host.startswith(u'.'):
             raise InvalidURL('URL has an invalid label.')
 
         # Carefully reconstruct the network location
```

The test that missed it: `tests/test_requests.py::TestRequests::test_invalid_url[InvalidURL-http://.example.com]`, exit 0 on the mutant (exit 0, 1 passed in 0.18s).

Witness:

```python
import requests
requests.get("http://*.example.com")
```

- Patch (exit 0): raises InvalidURL('URL has an invalid label.')
- Mutant (exit 0): raises ConnectionError("HTTPConnectionPool(host='*.example.com', port=80): Max retries exceeded with url: / (Caused by NewConnectionError('<urllib3.connection.HTTPConnection object at 0x?>: Failed to establish a new connection: [Errno -2] Name or service not known'))")
- PASS_TO_PASS on the mutant (exit 1, 5 failed, 126 passed, 1 xfailed, 158 errors in 1.16s): 5 not PASSED, e.g. tests/test_requests.py::TestRequests::test_invalid_url[InvalidURL-http://*example.com], tests/test_requests.py::TestPreparingURLs::test_preparing_bad_url[http://*.google.com0], tests/test_requests.py::TestPreparingURLs::test_preparing_bad_url[http://*0]

### `psf__requests-5414` m9 (off-by-one): cleared FAIL_TO_PASS and PASS_TO_PASS

Rationale (the model's words): The patch uses `startswith` with a tuple of two elements. An off-by-one variant uses a tuple of three elements including an extra character `u'-'`, which changes the boundary of what is checked, and `http://-example.com` might behave differently.

```diff
--- a/requests/models.py
+++ b/requests/models.py
@@ -403,7 +403,7 @@ class PreparedRequest(RequestEncodingMixin, RequestHooksMixin):
                 host = self._get_idna_encoded_host(host)
             except UnicodeError:
                 raise InvalidURL('URL has an invalid label.')
-        elif host.startswith((u'*', u'.')):
+        elif host.startswith((u'*', u'.', u'-')):
             raise InvalidURL('URL has an invalid label.')
 
         # Carefully reconstruct the network location
```

The test that missed it: `tests/test_requests.py::TestRequests::test_invalid_url[InvalidURL-http://.example.com]`, exit 0 on the mutant (exit 0, 1 passed in 0.18s).

Witness:

```python
import requests
requests.get("http://-example.com")
```

- Patch (exit 0): raises ConnectionError("HTTPConnectionPool(host='-example.com', port=80): Max retries exceeded with url: / (Caused by NewConnectionError('<urllib3.connection.HTTPConnection object at 0x?>: Failed to establish a new connection: [Errno -2] Name or service not known'))")
- Mutant (exit 0): raises InvalidURL('URL has an invalid label.')
- PASS_TO_PASS on the mutant (exit 1, 131 passed, 1 xfailed, 158 errors in 0.99s): every PASS_TO_PASS test PASSED

### `psf__requests-5414` m15 (too-narrow): caught by PASS_TO_PASS

Rationale (the model's words): The correct patch adds `u'.'` to handle dot-prefix hosts. A too-narrow variant adds `u'.'` but only for the case where the host has more than 3 characters, using `and len(host) > 3`, which misses single-character hosts like `http://.a`.

```diff
--- a/requests/models.py
+++ b/requests/models.py
@@ -403,7 +403,7 @@ class PreparedRequest(RequestEncodingMixin, RequestHooksMixin):
                 host = self._get_idna_encoded_host(host)
             except UnicodeError:
                 raise InvalidURL('URL has an invalid label.')
-        elif host.startswith((u'*', u'.')):
+        elif host.startswith(u'.') and len(host) > 3:
             raise InvalidURL('URL has an invalid label.')
 
         # Carefully reconstruct the network location
```

The test that missed it: `tests/test_requests.py::TestRequests::test_invalid_url[InvalidURL-http://.example.com]`, exit 0 on the mutant (exit 0, 1 passed in 0.18s).

Witness:

```python
import requests
requests.get("http://.a")
```

- Patch (exit 0): raises InvalidURL('URL has an invalid label.')
- Mutant (exit 0): raises LocationParseError("Failed to parse: '.a', label empty or too long")
- PASS_TO_PASS on the mutant (exit 1, 5 failed, 126 passed, 1 xfailed, 158 errors in 1.22s): 5 not PASSED, e.g. tests/test_requests.py::TestRequests::test_invalid_url[InvalidURL-http://*example.com], tests/test_requests.py::TestPreparingURLs::test_preparing_bad_url[http://*.google.com0], tests/test_requests.py::TestPreparingURLs::test_preparing_bad_url[http://*0]

### `psf__requests-5414` m22 (too-narrow): caught by PASS_TO_PASS

Rationale (the model's words): The correct patch adds `u'.'` to the startswith tuple. This mutant adds `u'.'` but only when the host has more than two characters, using `and len(host) > 2`, which misses short dot-prefix hosts like `http://.a`; differs on that input.

```diff
--- a/requests/models.py
+++ b/requests/models.py
@@ -403,7 +403,7 @@ class PreparedRequest(RequestEncodingMixin, RequestHooksMixin):
                 host = self._get_idna_encoded_host(host)
             except UnicodeError:
                 raise InvalidURL('URL has an invalid label.')
-        elif host.startswith((u'*', u'.')):
+        elif host.startswith(u'.') and len(host) > 2:
             raise InvalidURL('URL has an invalid label.')
 
         # Carefully reconstruct the network location
```

The test that missed it: `tests/test_requests.py::TestRequests::test_invalid_url[InvalidURL-http://.example.com]`, exit 0 on the mutant (exit 0, 1 passed in 0.18s).

Witness:

```python
import requests
requests.get("http://.a")
```

- Patch (exit 0): raises InvalidURL('URL has an invalid label.')
- Mutant (exit 0): raises LocationParseError("Failed to parse: '.a', label empty or too long")
- PASS_TO_PASS on the mutant (exit 1, 5 failed, 126 passed, 1 xfailed, 158 errors in 1.20s): 5 not PASSED, e.g. tests/test_requests.py::TestRequests::test_invalid_url[InvalidURL-http://*example.com], tests/test_requests.py::TestPreparingURLs::test_preparing_bad_url[http://*.google.com0], tests/test_requests.py::TestPreparingURLs::test_preparing_bad_url[http://*0]

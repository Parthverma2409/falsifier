# Results

**Scope: five SWE-bench Verified instances across three repositories (pallets/flask, psf/requests, pytest-dev/pytest), Configuration A: the gold patch, audited against the benchmark's own FAIL_TO_PASS tests. No claim is made about the rest of the benchmark.**

| Instance | Benchmark oracle | SWE-bench says | Falsifier says | Killed / distinguishable | Equivalent discarded | Canary exit | Mutants generated |
|---|---|---|---|---|---|---|---|
| `pallets__flask-5014` | FAIL_TO_PASS, 1 test(s) | RESOLVED | **EARNED** | 1 / 1 | 0 | 1 | 1 of 10 |
| `psf__requests-5414` | FAIL_TO_PASS, 1 test(s) | RESOLVED | **UNEARNED** | 5 / 7 | 1 | 1 | 8 of 10 |
| `psf__requests-6028` | FAIL_TO_PASS, 2 test(s) | RESOLVED | **UNEARNED** | 4 / 5 | 5 | 1 | 10 of 10 |
| `pytest-dev__pytest-7432` | FAIL_TO_PASS, 1 test(s) | RESOLVED | **INCONCLUSIVE** | 0 / 0 | 0 | 3 | 0 of 10 |
| `pytest-dev__pytest-7571` | not completed: phase 3 spend ceiling ($2) tripped during its mutant forks | | | | | | |

"Benchmark oracle" means the repository's own FAIL_TO_PASS tests, not a reproduction of SWE-bench's harness. Under Configuration A mutants never run against PASS_TO_PASS, so UNEARNED means the FAIL_TO_PASS tests do not pin the behaviour, not that nothing in the repository would. Full evidence: `reports/instances/<instance>.html` and `.json`.

## Survivors

### `psf__requests-5414` m1 (off-by-one)

Rationale (the model's words): The condition `host.startswith((u'*', u'.'))` uses `startswith` with a tuple of two prefixes, but a developer might mistakenly use `startswith(u'.')` alone, catching only the dot case and missing the wildcard case. The input `http://*.example.com` would raise `InvalidURL` with the correct patch but pass through with just the dot check.

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

The test that missed it: `tests/test_requests.py::TestRequests::test_invalid_url[InvalidURL-http://.example.com]`, exit 0 on the mutant (exit 0, 1 passed in 0.17s).

Witness:

```python
import requests
# Correct patch raises InvalidURL for wildcard
try:
    requests.get('http://*.example.com')
    print('Wildcard: no error (WRONG)')
except requests.exceptions.InvalidURL as e:
    print('Wildcard: InvalidURL raised (CORRECT)')
# Mutant with only dot check passes wildcard
try:
    requests.get('http://*.example.com')
    print('Wildcard passes (MUTANT)')
except requests.exceptions.InvalidURL:
    print('Wildcard also raises (unexpected)')
# Both should raise for dot prefix
try:
    requests.get('http://.example.com')
    print('Dot: no error')
except requests.exceptions.InvalidURL:
    print('Dot: InvalidURL raised')
```

- Patch (exit 0): returns None, prints 'Wildcard: InvalidURL raised (CORRECT)\nWildcard also raises (unexpected)\nDot: InvalidURL raised'
- Mutant (exit 0): raises ConnectionError("HTTPConnectionPool(host='*.example.com', port=80): Max retries exceeded with url: / (Caused by NewConnectionError('<urllib3.connection.HTTPConnection object at 0x?>: Failed to establish a new connection: [Errno -2] Name or service not known'))")

### `psf__requests-5414` m4 (too-narrow)

Rationale (the model's words): The correct patch handles both `*` and `.` prefixes in the IDNA encoding error path. A too-narrow mutant might only add the `.` check but keep the `*` check as a separate `if`, or only handle the first occurrence of the issue. The input `http://example.com` with a mutant that adds an extra check for `.` only in the `elif` after the `try/except` would not affect the `UnicodeError` path, but a too-narrow mutant could be one that changes the `except UnicodeError` to only catch for specific hosts. Actually, too-narrow: handles exactly the case in the issue but not the general one. The issue is about `http://.example.com`. A too-narrow mutant might catch only that specific case by checking `host == '.example.com'` literally instead of `host.startswith(u'.')`. The input `http://.evil.com` would not be caught.

```diff
--- a/requests/models.py
+++ b/requests/models.py
@@ -403,7 +403,7 @@ class PreparedRequest(RequestEncodingMixin, RequestHooksMixin):
                 host = self._get_idna_encoded_host(host)
             except UnicodeError:
                 raise InvalidURL('URL has an invalid label.')
-        elif host.startswith((u'*', u'.')):
+        elif host == '.example.com':
             raise InvalidURL('URL has an invalid label.')
 
         # Carefully reconstruct the network location
```

The test that missed it: `tests/test_requests.py::TestRequests::test_invalid_url[InvalidURL-http://.example.com]`, exit 0 on the mutant (exit 0, 1 passed in 0.17s).

Witness:

```python
import requests
# Correct patch raises InvalidURL for any host starting with .
try:
    requests.get('http://.example.com')
    print('Dot example: no error (WRONG)')
except requests.exceptions.InvalidURL:
    print('Dot example: InvalidURL raised (CORRECT)')
# Too-narrow mutant: only checks for exact '.example.com' string
# Input http://.evil.com would pass through
try:
    requests.get('http://.evil.com')
    print('Evil dot: no error (MUTANT differs)')
except requests.exceptions.InvalidURL:
    print('Evil dot: InvalidURL raised')
# Correct patch should raise for .evil.com too
```

- Patch (exit 0): returns None, prints 'Dot example: InvalidURL raised (CORRECT)\nEvil dot: InvalidURL raised'
- Mutant (exit 0): raises LocationParseError("Failed to parse: '.evil.com', label empty or too long"), prints 'Dot example: InvalidURL raised (CORRECT)'

### `psf__requests-6028` m1 (wrong-condition)

Rationale (the model's words): The patch adds `if auth:` to prepend auth when netloc is missing. This mutant changes the guard to `if netloc:` so auth is prepended only when netloc already exists, missing the case where netloc is empty and auth needs to be injected. Input: `url='http://user:pass@example.org/'` with a scheme swap — the correct patch produces `https://user:pass@example.org/` (auth injected into netloc), while this mutant produces `https://example.org/` (auth stripped because netloc was already present and guard passed, but the swap didn't happen).

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
prepend_scheme_if_needed('http://example.org/', 'https')
```

- Patch (exit 0): returns 'http://example.org/'
- Mutant (exit 0): raises TypeError('sequence item 0: expected str instance, NoneType found')

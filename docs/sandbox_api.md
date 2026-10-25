# Nebius Sandboxes: contree-sdk 0.3.6 API surface

Read from the installed source (`.venv/lib/python3.12/site-packages/contree_sdk/`) and checked against
the docs at https://docs.tokenfactory.nebius.com/sandboxes/. Where the source and the docs disagree, this
file says so. Items marked *(inferred)* come from reading the code, not from a documented guarantee.

## Mental model

There is **no sandbox object to create or destroy**. The unit is an **image**, an immutable filesystem
snapshot identified by a UUID and optionally named by a mutable tag. Each command is an **operation** that
runs one container from an image:

```
base image ──run(disposable=False)──▶ new image UUID   (this is the "checkpoint")
     │
     └──────run(disposable=True)───▶ stdout/stderr/exit code, no image kept
```

| Wanted operation | What it is in contree-sdk |
|---|---|
| create | `client.images.use(ref)` / `client.images.oci(ref)` to get an image handle |
| run a command | `image.run(...)` then `await` (async) or `.wait()` (sync) |
| checkpoint | `run(..., disposable=False)` returns an object whose `.uuid` is the new image |
| fork a checkpoint | call `.run()` on the same checkpoint more than once, or `images.use(uuid)` again |
| roll back | no API: reuse an earlier UUID (`images.use(old_uuid)`), or repoint a tag with `tag_as` |
| destroy | no delete call: use `disposable=True`, `untag()`, and let retention expire the rest; cancel a live operation with `DELETE /v1/operations/{id}` |

## Clients

```python
from contree_sdk import Contree, ContreeSync      # the only two public exports

Contree(config: ContreeConfig | None = None, *, base_url: str | None = None, token: str | None = None)
ContreeSync(config: ContreeConfig | None = None, *, base_url: str | None = None, token: str | None = None)

client.images   # ImagesManager / ImagesManagerSync
client.files    # FilesManager / FilesManagerSync
client.config   # ContreeConfig
client.get_token_info(refresh: bool = False) -> WhoAmI   # async on Contree, sync on ContreeSync
```

`WhoAmI(token_uuid: str, token_expiration: int | None, permissions: dict[str, bool], limits: dict[str, int], operations_stat: dict)`
comes from `GET /v1/whoami`. This call is the cheapest way to check access and read the
account's real limits.

### Auth (`contree_sdk.auth`)

```python
IAMAuth(token="NEBIUS_API_KEY", project_id="NEBIUS_PROJECT_ID",
        base_url="https://api.tokenfactory.nebius.com/sandboxes/")   # the default
JWTAuth(token="CONTREE_TOKEN", base_url="CONTREE_BASE_URL")           # legacy
```

- Each string field holds **either a literal value or the name of an environment variable**. The variable is looked up in `resolve()` when the client is constructed. So with `NEBIUS_API_KEY` and `NEBIUS_PROJECT_ID` set (for example via `load_dotenv()`), `ContreeSync()` needs no arguments.
- If a field is missing, `resolve()` falls back to `$CONTREE_HOME/auth.ini` or `${XDG_CONFIG_HOME:-~/.config}/contree/auth.ini`.
- Request headers are `Authorization: Bearer <key>` and `Project: <project_id>`. **`NEBIUS_PROJECT_ID` is required.** The docs note that `NEBIUS_AI_PROJECT`, which the CLI uses, does not replace it.

### `ContreeConfig` (`contree_sdk.config`), defaults

| Field | Default | Note |
|---|---|---|
| `auth` | `IAMAuth()` | |
| `transport_timeout` | 10.0 s | per HTTP request |
| `operation_timeout` | 1000.0 s | wait budget per operation |
| `operation_run_timeout` / `operation_import_timeout` | None | fall back to `operation_timeout` |
| `operation_poll_secs_min` / `_max` / `_backoff_grow` | 0.1 / 10.0 / 1.75 | status polling backoff |
| `operation_poll_not_found_limit` | 10 | |
| `default_truncate_output_at` | 65535 bytes | **The SDK sends 64 KiB by default. The docs say the server default is 1 MiB (max 10 MiB).** Pass `truncate_output_at=` to get more. |
| `images_list_batch_size` | 100 | |

## Images manager

Async methods return coroutines. The sync versions have the same signatures and return directly.

```python
images.use(ref: str | UUID | OCIReference, strict: bool = False) -> Image
    # No network call unless strict=True, which checks that the UUID/tag exists.
images.oci(ref, *, tag=None, username=None, password=None, timeout=None) -> Image
    # Use the existing image with that tag, or import it from a registry. Aliases: docker, podman, pull_by_oci.
images.import_from(image: str | OCIReference, *, tag=None, username=None, password=None, timeout=None) -> Image
images(number=100, kind=None, tagged=False, since=None, until=None) -> list[Image]   # __call__ = list
async for img in client.images / for img in client.images                       # iterate all
images.pull(...)                                                                 # deprecated
```

## Running commands (`ContreeImage` / `ContreeImageSync`)

```python
image.run(
    command: str | None = None, *, shell: str | None = None,   # exactly one of the two
    args=None, env=None, cwd=None, hostname=None,
    stdin=None, stdout=None, stderr=None,                      # str/bytes/IO targets
    tag: str | None = None,                                    # tag the resulting image
    files: list | dict | None = None,                          # upload into the container
    timeout: float | timedelta | None = None,
    disposable: bool = True,                                   # True: no image kept
    truncate_output_at: int | None = None,
    preserve_env: bool = False,
) -> Image   # a *prepared* copy; nothing has run yet
```

- `run()` is **lazy**: it only builds the request. Execution happens on `await prepared` (async) or `prepared.wait()` (sync). That call does `POST /v1/instances`, then polls `GET /v1/operations/{id}`.
- The executed object exposes `.exit_code`, `.stdout`, `.stderr`, `.elapsed`, `.uuid` and `.tag`. `.result` is a `ContreeResult(stdout, stderr, exit_code, elapsed_time, cost)` with a `.truncated` property. The docs say not to use `cost` for invoice reconciliation.
  - **`.elapsed` / `elapsed_time` is CPU time (user+sys), not wall time.** A `sleep 60` reports about 0.0025 s. Real duration is in `result._raw.result.resources.monotonic_time`.
  - **`cost` is USD and follows CPU time:** about $0.0103 per CPU-second plus $4.2e-05 per run (R² = 1.000 over 95 runs; the console moved by about $0.13 for a reported 0.1316). See `docs/probe.md`.
- A nonzero exit code is **not** an exception, so check `exit_code` yourself. Platform failures raise `FailedOperationError`, `OperationTimedOutError` or `CancelledOperationError`.
- After `disposable=True` the result's `.uuid` is `None` (**verified live**), and calling `.run()` on it raises `DisposableImageRunError` (from the source: `run()` raises it when there is neither a uuid nor a tag).
- Other helpers:
  - `image.ls(path="/")`
  - `image.read(path) -> bytes`
  - `image.download(image_path, local_path=None) -> Path`
  - `image.apply_files(*files, files=None) -> Image`, which is shorthand for `run(shell="true", files=..., disposable=False)`, so it also creates a checkpoint.
- Sync only: `image.popen(args, *, stdin, input, stdout, stderr, shell, cwd, timeout, check, text, env) -> ContreeProcessSync` with `.wait()`, `.communicate(input=None, timeout=None)`, `.returncode`, `.stdout` and `.stderr`. It is a subprocess-style wrapper over one `run()`. It does not stream, and `check=True` raises `CalledProcessError`.
- Files: `client.files.upload(local_path) -> UploadedFile`. Uploads are content-addressed by sha256 (`HEAD/GET /v1/files/{sha256}`, `POST /v1/files`).

## Checkpoint, fork, roll back

```python
base = await client.images.use("python:3.12-slim", strict=True)

# checkpoint
ckpt = await base.run(shell="pip install -e . && git apply red.patch", disposable=False)
ckpt_uuid = ckpt.uuid                       # persist this

# fork: run() copies the handle, so ckpt itself is unchanged and reusable
a, b = await asyncio.gather(
    ckpt.run(shell="git apply cand_a.diff && pytest -x", disposable=False),
    ckpt.run(shell="git apply cand_b.diff && pytest -x", disposable=False),
)

# roll back: start again from the recorded UUID
clean = await client.images.use(ckpt_uuid, strict=True)

# name / re-point
await ckpt.tag_as("falsifier/inst-123/red")     # PATCH /v1/images/{uuid}/tag
await ckpt.untag()                              # DELETE /v1/images/{uuid}/tag
```

- **No merge.** The docs say no API merges two images. A process does not carry over from one run to the next; only the filesystem does.
- **Tags are mutable pointers.** Record UUIDs for reproducibility and use tags only for discovery.

### Sessions (linear history)

`image.session() -> ContreeSession / ContreeSessionSync`. A session overrides `_copy_self` to return
`self`, so each executed `run()` **advances the same object** to the new image UUID: it is a
linear chain of checkpoints, much like a shell session. Run sessions with `disposable=False`. A disposable run sets the
session's uuid to `None` and breaks later runs *(inferred)*.

### Verified live on 2026-10-25 (`alpine:3.19`, this account)

| Check | Observed |
|---|---|
| checkpoint `run(disposable=False)` | new image uuid in ~1.0 s |
| fork: two `ckpt.run(...)` via `asyncio.gather` | both finished in ~1.9 s, with distinct uuids; files `base A` and `base B` |
| checkpoint after the forks | `/state.txt` still `base`, so forks are isolated |
| rollback: `images.use(ckpt.uuid, strict=True).run(...)` | sees `base` only |
| session: two runs | `session.uuid` advanced in place; file shows `1 2` |
| `result.cost` of a trivial disposable run | `4.975e-05`. The unit was later established as USD, billed per CPU-second (`docs/probe.md`). |
| `whoami().token_expiration` | about 300 s ahead of now, so the SDK logs `Token expires in 0 hours` on every client. Runs still succeed. |

## Destroy and cleanup

- The SDK has **no delete-image call**. Its full endpoint list is `whoami`, `files` (get/head/post), `images` (list, import, tag, untag), `inspect` (list, download, get by uuid/tag), `instances` (spawn) and `operations` (get, cancel).
- Results of disposable runs are not kept.
- The docs say non-disposable images are kept for **180 days**, after which "untagged and unreferenced images may be deleted."
- `DELETE /v1/operations/{id}` cancels a running operation. The SDK calls this automatically if the awaiting coroutine is cancelled (`_operation_canceller`). The docs warn against project-wide cancel-all.

## Sync vs async

- `Contree` is native asyncio. Await managers and image methods, and await prepared runs.
- `ContreeSync` uses the same code, run on **one shared background event-loop thread** (`_internals/utils/wrapper.py`, `AsyncWrapper._shared_context`). Each call blocks until its future resolves. Calls from several threads run concurrently on that loop *(inferred)*.
- `popen()` exists only on the sync client.
- For fan-out (red/patch/green over many candidates), use `Contree` with `asyncio.gather` behind an `asyncio.Semaphore`.

## Concurrency limits

- **50 simultaneous operations** in Beta. The account's effective limit is reported by `whoami`. Higher limits are available through contree@nebius.com.
- `whoami` limits for this account (2026-10-25): `instance_max_concurrency=50`, `instance_max_timeout=3600` s, `instance_max_layer_bytes=12884901888` (12 GiB), `images_import_max_concurrency=8`, `images_import_max_timeout=3600` s.
- Images: `images.use(tag, strict=True)` returns 404 `Image not found by tag` for a public image this project hasn't imported yet. Use `images.oci("alpine:3.19")` to import on first use. The import leaves a **tagged** image in the project.
- Per-account maximum timeouts come from `WhoAmI.limits` (keys read by the SDK: `instance_max_timeout`, `images_import_max_timeout`). The SDK only **logs a warning** when a timeout exceeds them.
- On *start*, the SDK retries `TooManyRequestsError` (429) and `ApiTimeoutError` with a circuit retrier, up to the operation timeout. Polling has its own backoff.
- The docs have no idempotency key for spawns. After a transport error before an operation ID is returned, don't blindly resubmit. After a timeout that has an operation ID, query that operation first.
- Stdout/stderr: 1 MiB per stream server default, 10 MiB max, but 64 KiB SDK default (see above). Image retention is 180 days.

## Exceptions (`contree_sdk.sdk.exceptions`)

`ContreeError` is the base class. Its subclasses:

- **API errors:** `ContreeApiError`, `ApiTimeoutError`, `ContreeTransportError`, `ApiStatusCodeError`, `NotFoundError`, `TooManyRequestsError`, `ForbiddenError`, `UnprocessableEntityError`
- **Operation errors:** `OperationError`, `WrongOperationTypeError`, `CancelledOperationError`, `FailedOperationError`, `OperationTimedOutError`
- **Image errors:** `ContreeImageNotFoundError`, `ContreeImageParametersError`, `DisposableImageRunError`, `ContreeImageStateError`, `ContreeImageImpossibleStateError`, `ContreeImageEmptyRequestError`
- **Other:** `UnknownContreeError`

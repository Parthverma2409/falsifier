# Sandboxes access check

- Checked: 2026-10-25T06:55:06+00:00
- SDK: contree-sdk 0.3.6 (`ContreeSync`, default IAMAuth endpoint)
- Endpoint: `https://api.tokenfactory.nebius.com/sandboxes/`
- Result: **access is live**
- Permissions: `{'import': True, 'spawn': True, 'spawn_disposable': True, 'list': True, 'cancel': True, 'set_image_tag': True}`
- Limits: `{'instance_max_timeout': 3600, 'instance_max_concurrency': 50, 'instance_max_layer_bytes': 12884901888, 'images_import_max_concurrency': 8, 'images_import_max_timeout': 3600}`
- Base image: `alpine:3.19` uuid `7042c2ba-240f-39a7-bb7e-6dd481256952`
- Run: `echo sandbox-ok && uname -a`, exit code 0, elapsed 0:00:00.001140
- Result image uuid: `None` (disposable run, so no checkpoint kept; nothing to tear down)

```
sandbox-ok
Linux hostname 7.0.6 #1 SMP PREEMPT_DYNAMIC Mon Aug 24 09:29:13 UTC 2026 x86_64 Linux
```
## Earlier attempt, 2026-10-25 (not an access problem)

The first attempt used the quickstart's `client.images.use("alpine:3.19", strict=True)` and failed with:

```
NotFoundError: status=404, error="Image not found by tag 'alpine:3.19'"
GET https://api.tokenfactory.nebius.com/sandboxes/v1/inspect/?tag=alpine%3A3.19
```

`use(strict=True)` only resolves images that are already in the project. `images.oci("alpine:3.19")` imports
the image on first use, and the run then succeeded.

"""Sandboxes access check: whoami, then one disposable run on alpine.

Writes the outcome to docs/sandbox_access.md: the exact error on failure, run details on success.
"""

from __future__ import annotations

import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ACCESS_MD = ROOT / "docs" / "sandbox_access.md"


def record_failure(step: str, exc: BaseException) -> None:
    ACCESS_MD.write_text(
        "\n".join(
            [
                "# Sandboxes access check",
                "",
                f"- Checked: {datetime.now(UTC).isoformat(timespec='seconds')}",
                "- SDK: contree-sdk 0.3.6 (`ContreeSync`, default IAMAuth endpoint)",
                f"- Failed at: {step}",
                f"- Exception: `{type(exc).__module__}.{type(exc).__qualname__}`",
                "",
                "## Message",
                "",
                "```",
                str(exc),
                "```",
                "",
                "## Traceback",
                "",
                "```",
                "".join(traceback.format_exception(exc)).rstrip(),
                "```",
                "",
            ]
        )
    )
    print(f"FAILED at {step}: {type(exc).__name__}: {exc}")
    print(f"Wrote {ACCESS_MD.relative_to(ROOT)}")


def main() -> int:
    load_dotenv(ROOT / ".env")
    from contree_sdk import ContreeSync

    step = "client init"
    try:
        client = ContreeSync()
        print(f"endpoint: {client.config.auth.base_url}")

        step = "whoami (GET /v1/whoami)"
        info = client.get_token_info()
        print(f"permissions: {info.permissions}")
        print(f"limits: {info.limits}")

        # use(strict=True) only resolves images already in the project; oci() imports if missing.
        step = "images.oci('alpine:3.19')"
        image = client.images.oci("alpine:3.19")
        print(f"base image: uuid={image.uuid} tag={image.tag}")

        step = "run(shell='echo ok', disposable=True)"
        result = image.run(shell="echo sandbox-ok && uname -a", disposable=True).wait()
    except Exception as exc:
        record_failure(step, exc)
        return 1

    ACCESS_MD.write_text(
        "\n".join(
            [
                "# Sandboxes access check",
                "",
                f"- Checked: {datetime.now(UTC).isoformat(timespec='seconds')}",
                "- SDK: contree-sdk 0.3.6 (`ContreeSync`, default IAMAuth endpoint)",
                f"- Endpoint: `{client.config.auth.base_url}`",
                "- Result: **access is live**",
                f"- Permissions: `{info.permissions}`",
                f"- Limits: `{info.limits}`",
                f"- Base image: `alpine:3.19` uuid `{image.uuid}`",
                f"- Run: `echo sandbox-ok && uname -a`, exit code {result.exit_code}, "
                f"elapsed {result.elapsed}",
                f"- Result image uuid: `{result.uuid}` (disposable run, so no checkpoint kept; "
                "nothing to tear down)",
                "",
                "```",
                str(result.stdout).rstrip(),
                "```",
                "",
            ]
        )
    )
    print(f"exit_code={result.exit_code} elapsed={result.elapsed}")
    print(f"stdout={result.stdout!r}")
    print(f"result image uuid={result.uuid} (disposable run: no checkpoint kept)")
    print(f"Wrote {ACCESS_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

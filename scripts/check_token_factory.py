"""Service check: Token Factory models and a minimal chat completion. Run via `make check`.

Writes docs/models.md, prints the Nemotron subset, then makes one tiny chat completion
against the cheapest Nemotron (or --model). Pass --no-chat to skip the paid call.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import OpenAI
from rich.console import Console
from rich.table import Table

# From https://docs.tokenfactory.nebius.com/quickstart.md
BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
ROOT = Path(__file__).resolve().parent.parent
MODELS_MD = ROOT / "docs" / "models.md"

console = Console()


def per_million(price: str | None) -> float | None:
    """Token Factory pricing fields are USD per token as strings; convert to USD per 1M."""
    if price in (None, ""):
        return None
    return float(price) * 1_000_000


def fetch_models(api_key: str) -> list[dict]:
    resp = httpx.get(
        BASE_URL + "models",
        params={"verbose": "true"},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["data"]


def row(m: dict) -> dict:
    pricing = m.get("pricing") or {}
    return {
        "id": m["id"],
        "context": m.get("context_length"),
        "in": per_million(pricing.get("prompt")),
        "out": per_million(pricing.get("completion")),
        "quant": m.get("quantization"),
        "status": m.get("status"),
    }


def fmt(v: float | None) -> str:
    return "n/a" if v is None else f"${v:.4f}".rstrip("0").rstrip(".")


def write_models_md(rows: list[dict], models: list[dict]) -> None:
    lines = [
        "# Token Factory models",
        "",
        f"Source: `GET {BASE_URL}models?verbose=true`. Prices are USD per 1M tokens.",
        "",
        "| Model id | Context | Input $/1M | Output $/1M | Quant | Status |",
        "|---|---:|---:|---:|---|---|",
    ]
    for r in sorted(rows, key=lambda r: r["id"].lower()):
        lines.append(
            f"| `{r['id']}` | {r['context'] or 'n/a'} | {fmt(r['in'])} | {fmt(r['out'])} "
            f"| {r['quant'] or ''} | {r['status'] or ''} |"
        )
    lines += ["", f"Total: {len(rows)} models.", "", "## NVIDIA Nemotron detail", ""]
    for m in sorted(models, key=lambda m: m["id"].lower()):
        if "nemotron" not in m["id"].lower():
            continue
        limits = m.get("per_request_limits") or {}
        regions = ", ".join(r["name"] for r in m.get("regions") or [])
        cache = per_million((m.get("pricing") or {}).get("input_cache_read"))
        lines += [
            f"### `{m['id']}`",
            "",
            f"- {m.get('description') or ''}",
            f"- Features: {', '.join(m.get('supported_features') or [])}; "
            f"quantization {m.get('quantization')}; region {regions}",
            f"- Cached input $/1M: {fmt(cache)}",
            f"- Limits: {limits.get('tokens_per_minute')} tokens/min, "
            f"{limits.get('requests_per_minute')} requests/min",
            "",
        ]
    MODELS_MD.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="model id for the chat call (default: cheapest Nemotron)")
    parser.add_argument("--no-chat", action="store_true", help="skip the paid chat completion")
    parser.add_argument("--dump-raw", type=Path, help="write the raw /models JSON to this path")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        console.print("[red]NEBIUS_API_KEY is not set (put it in .env)[/red]")
        return 1

    models = fetch_models(api_key)
    if args.dump_raw:
        args.dump_raw.write_text(json.dumps(models, indent=2))
    rows = [row(m) for m in models]
    write_models_md(rows, models)
    console.print(f"Wrote {len(rows)} models to {MODELS_MD.relative_to(ROOT)}")

    nemotron = [r for r in rows if "nemotron" in r["id"].lower()]
    table = Table(title="NVIDIA Nemotron models")
    for col in ("Model id", "Context", "Input $/1M", "Output $/1M"):
        table.add_column(col)
    for r in sorted(nemotron, key=lambda r: (r["in"] is None, r["in"] or 0, r["out"] or 0)):
        table.add_row(r["id"], str(r["context"]), fmt(r["in"]), fmt(r["out"]))
    console.print(table)

    if args.no_chat:
        return 0

    model = args.model
    if model is None:
        priced = [r for r in nemotron if r["in"] is not None and r["out"] is not None]
        if not priced:
            console.print("[red]No priced Nemotron model found; pass --model[/red]")
            return 1
        model = min(priced, key=lambda r: (r["in"] + r["out"], r["in"]))["id"]

    client = OpenAI(base_url=BASE_URL, api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: ok"}],
        max_tokens=64,
        temperature=0,
    )
    console.print(f"[bold]Chat completion[/bold] model={resp.model}")
    console.print(repr(resp.choices[0].message.content))
    console.print(f"usage: {resp.usage.model_dump() if resp.usage else None}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

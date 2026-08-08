#!/usr/bin/env python3
"""Live smoke test against real Web Check API bases.

Unlike the unit suite (fully mocked, runs everywhere), this script performs
real network calls. Public bases rate-limit datacenter IPs, so a failure here
is informational by default -- it tells us *which* base is currently usable,
not that our code is broken. Use --strict to turn "no base answered" into a
non-zero exit.

Usage:
    python scripts/live_smoke.py
    python scripts/live_smoke.py --url github.com --group quick
    python scripts/live_smoke.py --base http://127.0.0.1:3000/api --strict
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.client import CHECK_GROUPS, PUBLIC_BASE_URLS, WebCheckClient

DEFAULT_TARGET = "https://example.com"
DEFAULT_CHECKS = ["get-ip", "status", "headers"]


def probe_base(
    base: str,
    target: str,
    checks: list[str],
    timeout: int,
) -> dict[str, Any]:
    """Run a small check batch against one base. Never raises."""
    started = time.monotonic()
    # fallback=False: we are deliberately testing this base in isolation,
    # otherwise a healthy mirror would mask a dead primary.
    client = WebCheckClient(base_url=base, timeout=timeout, fallback=False)
    try:
        health = client.health()
    except Exception as exc:  # pragma: no cover - defensive
        health = {"reachable": False, "error": f"{type(exc).__name__}: {exc}"}

    results: list[dict[str, Any]] = []
    if health.get("reachable"):
        try:
            run = client.run(target, checks=checks)
            results = run.get("results", [])
        except Exception as exc:  # pragma: no cover - defensive
            results = [{"check": "<run>", "ok": False, "error": str(exc)}]

    ok_count = sum(1 for r in results if r.get("ok"))
    return {
        "base": base,
        "reachable": bool(health.get("reachable")),
        "status": health.get("status"),
        "error": health.get("error"),
        "checks_run": len(results),
        "checks_ok": ok_count,
        "results": [
            {
                "check": r.get("check"),
                "ok": bool(r.get("ok")),
                "status": r.get("status"),
                "error": r.get("error"),
            }
            for r in results
        ],
        "elapsed_s": round(time.monotonic() - started, 2),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "## Web Check live smoke",
        "",
        f"Target: `{report['target']}` · checks: `{', '.join(report['checks'])}`",
        "",
        "| Base | Reachable | HTTP | Checks OK | Time |",
        "| --- | --- | --- | --- | --- |",
    ]
    for probe in report["probes"]:
        mark = "✅" if probe["reachable"] else "❌"
        lines.append(
            f"| `{probe['base']}` | {mark} | {probe['status'] or '-'} | "
            f"{probe['checks_ok']}/{probe['checks_run']} | {probe['elapsed_s']}s |"
        )
    lines.append("")

    for probe in report["probes"]:
        if probe["reachable"] and probe["checks_ok"] == probe["checks_run"]:
            continue
        lines.append(f"<details><summary>{probe['base']} — detail</summary>")
        lines.append("")
        if probe["error"]:
            lines.append(f"health error: `{probe['error']}`")
            lines.append("")
        for r in probe["results"]:
            mark = "ok" if r["ok"] else "FAIL"
            detail = f" — {r['error']}" if r.get("error") else ""
            lines.append(f"- `{r['check']}` {mark} (HTTP {r['status']}){detail}")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    if not report["any_reachable"]:
        lines.append(
            "> No public base answered. This is usually rate limiting of CI "
            "egress IPs, not a regression. Self-host to verify: "
            "`docker run -p 3000:3000 lissy93/web-check`."
        )
    return "\n".join(lines)


def write_step_summary(markdown: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")
    except OSError:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live smoke against Web Check bases")
    parser.add_argument("--url", default=DEFAULT_TARGET, help="target to scan")
    parser.add_argument(
        "--base",
        action="append",
        dest="bases",
        help="base URL to probe (repeatable); defaults to PUBLIC_BASE_URLS",
    )
    parser.add_argument("--group", help=f"check group: {', '.join(sorted(CHECK_GROUPS))}")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="emit raw JSON report")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when no base is reachable (default: informational, exit 0)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    bases = args.bases or list(PUBLIC_BASE_URLS)
    if args.group:
        if args.group not in CHECK_GROUPS:
            print(f"unknown group '{args.group}'", file=sys.stderr)
            return 2
        checks = list(CHECK_GROUPS[args.group])
    else:
        checks = list(DEFAULT_CHECKS)

    probes = [probe_base(b, args.url, checks, args.timeout) for b in bases]
    report = {
        "target": args.url,
        "checks": checks,
        "probes": probes,
        "any_reachable": any(p["reachable"] for p in probes),
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        markdown = render_markdown(report)
        print(markdown)
        write_step_summary(markdown)

    if args.strict and not report["any_reachable"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

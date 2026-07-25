"""Example: use web-check-mcp as a library.

Run: python examples/library_demo.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.client import WebCheckClient

# Uses WEB_CHECK_BASE_URL or defaults to http://127.0.0.1:3000/api.
# Public bases are auto-tried when fallback=True.
client = WebCheckClient(
    base_url=os.environ.get("WEB_CHECK_BASE_URL", "https://web-check.as93.net/api"),
    fallback=True,
    timeout=30,
)

print("== Health ==")
print(json.dumps(client.health(), indent=2)[:500])

print("\n== SSL for discord.com ==")
result = client.check_one("ssl", "https://discord.com")
print(json.dumps(result, indent=2)[:800])

print("\n== Quick recon for example.com ==")
recon = client.run("example.com", group="quick")
print(
    f"base={recon['resolved_base_url']} "
    f"ok={recon['ok_count']}/{len(recon['results'])}"
)
for r in recon["results"]:
    mark = "OK" if r["ok"] else "FAIL"
    print(f"  {r['check']:14s} {r['status']:3d} {mark}")

print("\n== Security bundle for github.com ==")
sec = client.run("github.com", group="security", max_workers=4)
print(f"ok={sec['ok_count']}/{len(sec['results'])}")
for r in sec["results"]:
    mark = "OK" if r["ok"] else "FAIL"
    err = f" err={r.get('error')}" if not r["ok"] else ""
    print(f"  {r['check']:14s} {r['status']:3d} {mark}{err}")

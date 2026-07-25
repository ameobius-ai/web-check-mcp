# OpenAPI Drift Report — WC-023

Audit date: 2026-07-25  
Upstream spec: [`Lissy93/web-check`](https://github.com/Lissy93/web-check/blob/master/public/resources/openapi-spec.yml) (SHA `50bb7ea`)

## Endpoint coverage

| Status | Count |
| --- | --- |
| Upstream paths | 31 |
| Our `CHECKS` entries | 31 |
| Missing (upstream has, we don’t) | **0** |
| Extra (we have, upstream doesn’t) | **0** |

✅ Full coverage, no missing or extra endpoints.

## Query-parameter mismatches (fixed in this PR)

The client previously sent `?url=<target>` for every endpoint. Three endpoints
use a different parameter name per the upstream spec:

| Endpoint | Spec param | Was sending | Fix |
| --- | --- | --- | --- |
| `/txt-records` | `domain` | `url` | ✅ fixed |
| `/whois` | `domain` | `url` | ✅ fixed |
| `/trace-route` | `urlString` | `url` | ✅ fixed |

The fix adds an optional `param` key to `CHECKS` entries and a helper
`_query_param_name(check)` that returns it (defaulting to `"url"`).
`check_one` now uses this instead of the hard-coded string.

## Other notes

### `/quality` — requires `apiKey` server-side

The upstream spec documents a required `?apiKey=` query param (Google PageSpeed
Insights). In practice, the **server** is responsible for holding the key and
proxying the request — clients don’t need to pass it. Without a server-side
`GOOGLE_CLOUD_API_KEY` env, this endpoint returns `204 Skipped`. This is
expected behaviour, not a client bug. Updated summary in `CHECKS` to note it.

### Groups

All `CHECK_GROUPS` entries reference only valid `CHECKS` keys — no drift.

## Recommended re-audit trigger

Run this check whenever upstream bumps their OpenAPI spec. The weekly
`live-smoke.yml` workflow will surface 404s from renamed paths naturally.

Next manual audit: watch [upstream spec commits](https://github.com/Lissy93/web-check/commits/master/public/resources/openapi-spec.yml).

# Test fixtures

`pl_standings.json` is a **synthetic** football-data.org v4 `/competitions/PL/standings`
response. Its shape (keys, nesting, the `TOTAL` / `HOME` / `AWAY` standings entries, nullable
`form`) matches the v4 API, and the team IDs and crest URLs are football-data.org's. The
numbers are made up but internally consistent (`W + D + L = P`, `GD = GF - GA`).

It was generated because no API key was available when the tests were written. To replace it
with a real capture (the tests only assert invariants, so they keep passing):

```bash
curl -s -H "X-Auth-Token: $FOOTBALL_DATA_API_KEY" \
  https://api.football-data.org/v4/competitions/PL/standings \
  | python -m json.tool > api/tests/fixtures/pl_standings.json
```

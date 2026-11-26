# Deployment Information

## Public URL
https://k5-day14-khanh-agent.onrender.com

## Platform
Render (Docker Web Service + Render Key Value / Redis via Blueprint `render.yaml`, `rootDir: 06-lab-complete`)

## Test Commands (CP6 Verification)

```bash
BASE="https://k5-day14-khanh-agent.onrender.com"
AGENT_API_KEY="<YOUR-SECRET-API-KEY>"

# 1. Liveness probe -> Expected: 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"

# 2. Readiness probe (connected to cloud Redis) -> Expected: 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"

# 3. Missing API Key -> Expected: 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'

# 4. Valid API Key -> Expected: 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
```

## Environment Variables Set
- `PORT` (injected automatically by Render, default `8000`)
- `ENVIRONMENT=production`
- `AGENT_API_KEY` (generated securely on Render via `generateValue: true`, never hardcoded)
- `REDIS_URL` (auto-linked internal connection string from `k5-day14-khanh-redis`)
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)

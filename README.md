# Atomic-Server Cloud Deploy

Deploys [atomic-server](https://crates.io/crates/atomic-server) to Render.com free tier with data persistence via Cloudflare R2.

## Architecture

```
User → atomic.patternparadigm.xyz → Render.com (Docker)
                                        │
                                  atomic-server (all 94 API endpoints)
                                        │
                              ┌─────────┴──────────┐
                              │                    │
                        /atomic-storage     Cloudflare R2
                        (ephemeral)      ◄──── sync loop
                                            every 5 min
```

- **atomic-server** runs the full Atomic Data REST API + graph UI
- Data lives in `/atomic-storage/` (ephemeral on Render)
- Every 5 minutes, changed files sync to **Cloudflare R2** (persistent)
- On cold start, data restores from R2

## Prerequisites

Before deploying, you need:

1. **Cloudflare API Token** with R2 read+write permissions (already created — cfat token)
2. **R2 bucket** named `atomic-kb-data` (already created)
3. **GitHub repo** connected (already pushed)

## Deploy

### 1. On Render.com

1. Go to [render.com](https://render.com) → New Web Service
2. Connect your GitHub repo: `gauravsharma04869-art/atomic-kb`
3. Runtime: **Docker**
4. Set these environment variables:

| Variable | Value | Notes |
|----------|-------|-------|
| `CF_API_TOKEN` | *(your Cloudflare API token)* | Cloudflare API token with R2 + DNS access (use the cfat token) |
| `R2_ACCOUNT_ID` | `913238a744268b900bf09b52dfcc296b` | Cloudflare account ID |
| `R2_BUCKET` | `atomic-kb-data` | R2 bucket name |
| `ATOMIC_AUTH_TOKEN` | `at_OnuxZDBUmE1OuIoljiws8JE2n9zijboPPzvZVnFgmdo` | Atomic-server auth token |
| `ATOMIC_PUBLIC_MODE` | `true` | Allow public read access |

5. Deploy!

### 2. Update DNS

Once Render gives you a URL (e.g., `atomic-kb.onrender.com`), update the DNS:

```bash
# I'll do this step — update the CNAME from tunnel to Render URL
```

## Local Development

```bash
docker build -t atomic-cloud .
docker run -p 9883:9883 \
  -e CF_API_TOKEN=your_token \
  -e R2_ACCOUNT_ID=your_account_id \
  -e R2_BUCKET=atomic-kb-data \
  -e ATOMIC_PUBLIC_MODE=true \
  atomic-cloud
```

## Why This Works For Free

| Service | Free Tier | Our Usage |
|---------|-----------|-----------|
| Render.com Docker | 512MB RAM, 100GB/mo bandwidth | ~8MB database, tiny API traffic |
| Cloudflare R2 | 10GB storage, unlimited egress | ~8MB database |
| **Total** | **$0/mo** | **~5-10MB/mo bandwidth** |

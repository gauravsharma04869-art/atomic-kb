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

## Deploy

### 1. One-click Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

### 2. Or manual deploy

1. Fork this repo
2. Create an R2 bucket: `atomic-kb-data`
3. Generate R2 API credentials (Access Key + Secret Key)
4. On Render.com:
   - New Web Service → Connect your repo
   - Runtime: Docker
   - Set env vars:
     - `R2_ACCESS_KEY_ID`
     - `R2_SECRET_ACCESS_KEY`
     - `R2_ACCOUNT_ID`
     - `R2_BUCKET` (default: `atomic-kb-data`)
     - `ATOMIC_AUTH_TOKEN` (your auth token)
     - `ATOMIC_PUBLIC_MODE` (set to `true` for public read)
5. Deploy!

### 3. Set DNS

Point `atomic.patternparadigm.xyz` CNAME to your Render service URL.

## Local Development

```bash
docker build -t atomic-cloud .
docker run -p 9883:9883 \
  -e R2_ACCESS_KEY_ID=your_key \
  -e R2_SECRET_ACCESS_KEY=your_secret \
  -e R2_ACCOUNT_ID=your_account_id \
  -e R2_BUCKET=atomic-kb-data \
  atomic-cloud
```

## Why This Works For Free

| Service | Free Tier | Our Usage |
|---------|-----------|-----------|
| Render.com Docker | 512MB RAM, 100GB/mo bandwidth | ~8MB database, tiny API traffic |
| Cloudflare R2 | 10GB storage, unlimited egress | ~8MB database |
| **Total** | **$0/mo** | **~5-10MB/mo bandwidth** |

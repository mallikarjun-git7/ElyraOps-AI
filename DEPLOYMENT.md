# Deployment checklist

## Tested local workflow

1. `python3 -m unittest discover -s tests -v`
2. `python3 -m elyraops.server`
3. Visit `http://127.0.0.1:8080`
4. Select `EC-1042`, click **Start agent investigation**, inspect policy citations
5. Enter an approver name, then approve/reject a **simulation**
6. Refresh and confirm the status and event history persist
7. Run `curl http://localhost:8080/health`

## Local Docker

```bash
docker compose up --build -d
docker compose ps
docker compose logs --tail=100
curl -f http://localhost:8080/health
```

Not run in this authoring environment because Docker may be unavailable. Do not treat this as a production deployment verification.

## Before publishing to internet

This demo has no real authentication. **Do not publish it to an open internet endpoint with business/customer data.** An authorized production setup requires real identity, tenant isolation, TLS, backups, rate limiting, telemetry and infrastructure hardening. The current app operates only on seeded or user-created demo records.

## Push to your newly created GitHub repository

First create a new empty repository called `ElyraOps-AI` in your GitHub account. Then from this project directory:

```bash
git init
git add .
git commit -m "feat: establish original ElyraOps demo workspace"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ElyraOps-AI.git
git push -u origin main
```

If the default branch contains a README already, create an empty repository instead to avoid unrelated histories. Replace `YOUR_USERNAME` with your actual GitHub username.

## Adding DocsGPT as a separately credited upstream dependency

```bash
bash scripts/add-upstream-submodule.sh
git add .gitmodules third_party/docsgpt
git commit -m "chore: reference MIT-licensed DocsGPT upstream"
git push
```

This will add a Git submodule entry. You must still design and implement any product integration. The entire upstream repository is fetched when consumers clone with `--recurse-submodules`.

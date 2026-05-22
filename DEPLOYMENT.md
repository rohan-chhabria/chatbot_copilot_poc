# InmateCopilot Deployment - Quick Reference

> **For detailed step-by-step instructions, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**

---

## Quick Start

### First-Time Manual Deploy

```bash
# 1. Setup AWS (one-time)
./scripts/setup-github-actions-aws.sh
export GITHUB_ORG=your-org
./scripts/create-github-actions-role.sh

# 2. Update VPC config
nano infra/samconfig.toml

# 3. Build and deploy
make build
make ecr-login
make push ENVIRONMENT=dev
cd infra && sam build && sam deploy --config-env dev --parameter-overrides "ContainerImage=$ECR_URI:latest"

# 4. Load customer config
make load-config ENVIRONMENT=dev

# 5. Verify
curl $(make api-url ENVIRONMENT=dev)/health
```

### CI/CD Deploy (After Setup)

```bash
# Auto-deploy to dev
git push origin develop

# Manual production release
# Go to GitHub Actions → Release → Run workflow
```

---

## Workflows

| Workflow | Trigger | Target |
|----------|---------|--------|
| `ci.yml` | All PRs/pushes | Validation only |
| `deploy-branch.yml` | Push to `develop` | Auto-deploy to dev |
| `release.yml` | Manual | staging/prod (with approval) |

---

## Commands

```bash
# Development
make run                    # Local server
make test-local             # Lint + tests

# Deploy
make deploy ENVIRONMENT=dev # Full deploy

# Monitor
make logs ENVIRONMENT=dev   # View logs
make health ENVIRONMENT=dev # Health check
make stack-outputs          # Get API URL

# Rollback
make list-versions ENVIRONMENT=dev
make rollback ENVIRONMENT=dev TAG=abc123

# Customers
make list-customers ENVIRONMENT=dev
make load-config ENVIRONMENT=dev
```

---

## GitHub Setup

### Repository Secrets
- `AWS_DEPLOY_ROLE_ARN`: IAM role for OIDC

### Environments
- `dev` - auto-deploy, no approval
- `staging` - optional approval
- `prod` - required approval

Each environment needs:
- `AWS_DEPLOY_ROLE_ARN`
- `AWS_REGION`
- `DEV_API_URL` / `PROD_API_URL` (for smoke tests)

---

## Architecture

```
Internet → ALB → ECS Fargate → Redis (sessions)
                     ↓
              DynamoDB (config + conversations)
              Aurora MySQL (tenant data)
```

---

**Full documentation: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**

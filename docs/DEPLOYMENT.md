# InmateCopilot Deployment Guide (Beginner-Friendly)

This guide provides step-by-step instructions for deploying InmateCopilot to AWS. It covers both **Manual Deployment** (without CI/CD) and **Automated CI/CD Deployment**.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Understanding the Architecture](#2-understanding-the-architecture)
3. [Part A: One-Time AWS Setup](#part-a-one-time-aws-setup)
4. [Part B: Manual Deployment (Without CI/CD)](#part-b-manual-deployment-without-cicd)
5. [Part C: CI/CD Setup (GitHub Actions)](#part-c-cicd-setup-github-actions)
6. [Part D: Post-Deployment Configuration](#part-d-post-deployment-configuration)
7. [Part E: Day-to-Day Operations](#part-e-day-to-day-operations)
8. [Troubleshooting](#troubleshooting)
9. [Glossary](#glossary)

---

## 1. Prerequisites

Before starting, ensure you have the following installed and configured:

### 1.1 Install Required Tools

```bash
# Check if AWS CLI is installed
aws --version
# If not installed: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

# Check if Docker is installed
docker --version
# If not installed: https://docs.docker.com/get-docker/

# Check if SAM CLI is installed
sam --version
# If not installed:
pip install aws-sam-cli

# Check if Python is installed
python3 --version
# Should be 3.10 or higher

# Check if Git is installed
git --version
```

### 1.2 Configure AWS CLI

```bash
# Configure AWS credentials
aws configure

# You will be prompted for:
# AWS Access Key ID: <your-access-key>
# AWS Secret Access Key: <your-secret-key>
# Default region name: us-east-1
# Default output format: json

# Verify configuration
aws sts get-caller-identity
# Should show your AWS account ID and user ARN
```

### 1.3 Get Your VPC and Subnet IDs

You need these for deployment. Run these commands:

```bash
# List all VPCs in your account
aws ec2 describe-vpcs \
  --query 'Vpcs[*].[VpcId, Tags[?Key==`Name`].Value | [0], CidrBlock]' \
  --output table

# Example output:
# --------------------------------------------------------
# |                    DescribeVpcs                       |
# +------------------------+----------------+-------------+
# |  vpc-0abc123def456789  |  MyVPC         |  10.0.0.0/16|
# +------------------------+----------------+-------------+

# Note down your VpcId (e.g., vpc-0abc123def456789)
```

```bash
# List all subnets
aws ec2 describe-subnets \
  --query 'Subnets[*].[SubnetId, AvailabilityZone, CidrBlock, Tags[?Key==`Name`].Value | [0]]' \
  --output table

# Example output:
# ---------------------------------------------------------------------------
# |                           DescribeSubnets                                |
# +------------------------+---------------+----------------+----------------+
# |  subnet-0abc123public1 |  us-east-1a   |  10.0.1.0/24  |  Public-1a     |
# |  subnet-0abc123public2 |  us-east-1b   |  10.0.2.0/24  |  Public-2b     |
# |  subnet-0abc123private1|  us-east-1a   |  10.0.3.0/24  |  Private-1a    |
# |  subnet-0abc123private2|  us-east-1b   |  10.0.4.0/24  |  Private-2b    |
# +------------------------+---------------+----------------+----------------+

# Note down:
# - Public subnets (for ALB): subnet-0abc123public1,subnet-0abc123public2
# - Private subnets (for ECS): subnet-0abc123private1,subnet-0abc123private2
```

---

## 2. Understanding the Architecture

```
                                    ┌─────────────────┐
                                    │    Internet     │
                                    └────────┬────────┘
                                             │
                                             ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         AWS Cloud (us-east-1)                              │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                    VPC (e.g., 10.0.0.0/16)                           │ │
│  │                                                                      │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐│ │
│  │  │                    Public Subnets                               ││ │
│  │  │  ┌─────────────────────────────────────────────────────────┐   ││ │
│  │  │  │            Application Load Balancer (ALB)              │   ││ │
│  │  │  │            (Receives traffic from internet)             │   ││ │
│  │  │  └─────────────────────────┬───────────────────────────────┘   ││ │
│  │  └────────────────────────────┼───────────────────────────────────┘│ │
│  │                               │                                    │ │
│  │  ┌────────────────────────────┼───────────────────────────────────┐│ │
│  │  │                    Private Subnets                             ││ │
│  │  │                            ▼                                   ││ │
│  │  │  ┌─────────────────────────────────────────────────────────┐  ││ │
│  │  │  │              ECS Fargate Service                        │  ││ │
│  │  │  │  ┌─────────────────┐  ┌─────────────────┐              │  ││ │
│  │  │  │  │  Task 1         │  │  Task 2         │  (auto-scale)│  ││ │
│  │  │  │  │  (Container)    │  │  (Container)    │              │  ││ │
│  │  │  │  └────────┬────────┘  └────────┬────────┘              │  ││ │
│  │  │  └───────────┼────────────────────┼────────────────────────┘  ││ │
│  │  │              │                    │                           ││ │
│  │  │              ▼                    ▼                           ││ │
│  │  │  ┌─────────────────────────────────────────────────────────┐  ││ │
│  │  │  │              ElastiCache (Redis)                        │  ││ │
│  │  │  │              (Session storage)                          │  ││ │
│  │  │  └─────────────────────────────────────────────────────────┘  ││ │
│  │  └────────────────────────────────────────────────────────────────┘│ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  ┌──────────────────────┐  ┌──────────────────────┐                       │
│  │      DynamoDB        │  │    Aurora MySQL      │                       │
│  │  - Conversations     │  │  - Tenant databases  │                       │
│  │  - Customer Config   │  │  - Inmate data       │                       │
│  └──────────────────────┘  └──────────────────────┘                       │
│                                                                            │
│  ┌──────────────────────┐  ┌──────────────────────┐                       │
│  │        ECR           │  │    CloudWatch        │                       │
│  │  (Docker images)     │  │  (Logs & metrics)    │                       │
│  └──────────────────────┘  └──────────────────────┘                       │
└────────────────────────────────────────────────────────────────────────────┘
```

### What Each Component Does:

| Component | Purpose |
|-----------|---------|
| **ALB** | Receives HTTP requests from internet, routes to ECS tasks |
| **ECS Fargate** | Runs your application containers (no servers to manage) |
| **ElastiCache Redis** | Stores chat sessions (fast, in-memory) |
| **DynamoDB** | Stores conversation history and customer configuration |
| **Aurora MySQL** | Your tenant databases with inmate data |
| **ECR** | Stores Docker images of your application |
| **CloudWatch** | Stores logs and metrics |

---

## Part A: One-Time AWS Setup

These steps are done **once per AWS account**.

### Step A1: Clone the Repository

```bash
# Navigate to your projects directory
cd /home/Prod_Git_Codebase

# If not already cloned
git clone <your-repo-url> ChatbotCopilot
cd ChatbotCopilot
```

### Step A2: Install Project Dependencies

```bash
# Install Python dependencies
make install-dev

# Or manually:
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Step A3: Create GitHub OIDC Provider (For CI/CD)

This allows GitHub Actions to deploy to AWS without storing AWS credentials.

```bash
# Run the setup script
chmod +x scripts/setup-github-actions-aws.sh
./scripts/setup-github-actions-aws.sh
```

**What this script does:**
1. Creates an OIDC Identity Provider in AWS IAM
2. Creates an IAM policy with permissions for deployment

**Expected output:**
```
==============================================
GitHub Actions AWS Setup — InmateCopilot
==============================================

AWS Account: 123456789012
AWS Region:  us-east-1

Step 1: Creating OIDC Provider...
  OIDC Provider created

Step 2: Creating Deployment Policy...
  Policy created

==============================================
AWS SETUP COMPLETE
==============================================
```

### Step A4: Create GitHub Actions IAM Role

```bash
# Set your GitHub organization/username
export GITHUB_ORG=your-github-org-or-username

# Run the role creation script
chmod +x scripts/create-github-actions-role.sh
./scripts/create-github-actions-role.sh
```

**Expected output:**
```
==============================================
Creating GitHub Actions Role
==============================================
Service:    InmateCopilot
Repository: your-org/ChatbotCopilot
Role:       GitHubActions-InmateCopilot
Region:     us-east-1
==============================================

Creating new role...

==============================================
ROLE CREATED SUCCESSFULLY
==============================================

Role ARN:
  arn:aws:iam::123456789012:role/GitHubActions-InmateCopilot
```

**IMPORTANT:** Save this Role ARN! You'll need it for GitHub setup.

---

## Part B: Manual Deployment (Without CI/CD)

Use this for **first-time deployment** or when you want to deploy without CI/CD.

### Step B1: Update Configuration

Edit the SAM configuration file with your VPC details:

```bash
# Open the config file
nano infra/samconfig.toml
```

Replace the placeholder values:

```toml
[dev.deploy.parameters]
stack_name = "InmateCopilot-dev"
resolve_s3 = true
s3_prefix = "inmate-copilot-sam-dev"
region = "us-east-1"
capabilities = "CAPABILITY_IAM CAPABILITY_NAMED_IAM"
confirm_changeset = false
fail_on_empty_changeset = false
parameter_overrides = [
    "Environment=dev",
    "VpcId=vpc-YOUR_VPC_ID_HERE",           # <-- Replace this
    "PublicSubnets=subnet-PUB1,subnet-PUB2", # <-- Replace this
    "PrivateSubnets=subnet-PRIV1,subnet-PRIV2", # <-- Replace this
    "RedisNodeType=cache.t4g.micro",
    "AllowedOrigins=*",
]
```

**Example with real values:**
```toml
parameter_overrides = [
    "Environment=dev",
    "VpcId=vpc-0abc123def456789",
    "PublicSubnets=subnet-0abc123public1,subnet-0abc123public2",
    "PrivateSubnets=subnet-0abc123private1,subnet-0abc123private2",
    "RedisNodeType=cache.t4g.micro",
    "AllowedOrigins=*",
]
```

### Step B2: Build the Docker Image

```bash
# Build the image locally
make build

# Or manually:
docker build -t inmate-copilot-dev:latest -f dockerfile .
```

**Expected output:**
```
╔══════════════════════════════════════════════════════════════════════╗
║ Building Docker image: inmate-copilot-dev:latest                     
╚══════════════════════════════════════════════════════════════════════╝
[+] Building 45.2s (12/12) FINISHED
...
✅ Image built: inmate-copilot-dev:latest
```

### Step B3: Create ECR Repository

```bash
# Set variables
AWS_REGION=us-east-1
REPO_NAME=inmate-copilot-dev

# Create ECR repository
aws ecr create-repository \
  --repository-name $REPO_NAME \
  --image-scanning-configuration scanOnPush=true \
  --region $AWS_REGION

# Get your AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Your ECR URI: $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO_NAME"
```

**Expected output:**
```json
{
    "repository": {
        "repositoryArn": "arn:aws:ecr:us-east-1:123456789012:repository/inmate-copilot-dev",
        "repositoryUri": "123456789012.dkr.ecr.us-east-1.amazonaws.com/inmate-copilot-dev",
        ...
    }
}
```

### Step B4: Push Docker Image to ECR

```bash
# Login to ECR
make ecr-login

# Or manually:
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Tag the image
ECR_URI="$ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/inmate-copilot-dev"
docker tag inmate-copilot-dev:latest $ECR_URI:latest

# Push the image
docker push $ECR_URI:latest
```

**Expected output:**
```
The push refers to repository [123456789012.dkr.ecr.us-east-1.amazonaws.com/inmate-copilot-dev]
latest: digest: sha256:abc123... size: 3456
```

### Step B5: Deploy Infrastructure with SAM

```bash
# Validate the template first
make sam-validate

# Or manually:
sam validate --template-file infra/template.yaml --lint

# Build SAM application
cd infra
sam build

# Deploy (first time - this creates all resources)
sam deploy \
  --config-env dev \
  --parameter-overrides "ContainerImage=$ECR_URI:latest"
```

**What happens during deployment:**
1. SAM creates an S3 bucket to store deployment artifacts
2. CloudFormation creates all resources (takes 10-15 minutes):
   - DynamoDB tables
   - ECR repository (if not exists)
   - ElastiCache Redis cluster
   - ECS cluster, task definition, service
   - ALB with target groups
   - IAM roles
   - Security groups
   - CloudWatch log groups

**Expected output:**
```
Deploying with following values
===============================
Stack name                   : InmateCopilot-dev
Region                       : us-east-1
...

CloudFormation outputs from deployed stack
-------------------------------------------------
Key                 ApiUrl
Description         API endpoint URL
Value               http://InmateCopilot-dev-123456789.us-east-1.elb.amazonaws.com

Key                 EcrRepositoryUri
Description         ECR repository URI
Value               123456789012.dkr.ecr.us-east-1.amazonaws.com/inmate-copilot-dev

Key                 RedisEndpoint
Description         Redis endpoint for session storage
Value               ic-redis-dev.abc123.0001.use1.cache.amazonaws.com:6379
```

**IMPORTANT:** Save the `ApiUrl` - this is your application endpoint!

### Step B6: Verify Deployment

```bash
# Get the API URL
API_URL=$(aws cloudformation describe-stacks \
  --stack-name InmateCopilot-dev \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
  --output text)

echo "API URL: $API_URL"

# Wait for ECS service to be stable (may take 2-3 minutes)
aws ecs wait services-stable \
  --cluster InmateCopilot-dev \
  --services InmateCopilot-dev

# Health check
curl -s $API_URL/health | python3 -m json.tool
```

**Expected output:**
```json
{
    "status": "healthy",
    "timestamp": "2026-05-22T10:30:00Z",
    ...
}
```

### Step B7: Load Customer Configuration

```bash
# Edit the sample config with your values
nano sample_customer_config.json

# Verify the DynamoDB table exists
aws dynamodb describe-table \
  --table-name ChatbotCustomerConfiguration-dev \
  --query "Table.TableName"

# Load configuration
make load-config ENVIRONMENT=dev

# Or manually:
python3 -c "
import json, boto3
config = json.load(open('sample_customer_config.json'))
config.pop('_info', None)
boto3.resource('dynamodb', region_name='us-east-1').Table('ChatbotCustomerConfiguration-dev').put_item(Item=config)
print('Config loaded for customer:', config['customer_key'])
"
```

### Step B8: Test the Application

```bash
# Test chat endpoint
curl -X POST $API_URL/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "hello",
    "customer_key": "14",
    "user_id": "test-user",
    "facility_ids": [63]
  }'
```

**Expected output:**
```json
{
    "session_id": "uuid-here",
    "response": "Hello! I'm SARAH, your assistant...",
    ...
}
```

---

## Part C: CI/CD Setup (GitHub Actions)

After manual deployment works, set up CI/CD for automated deployments.

### Step C1: Understand the Workflow Structure

```
.github/workflows/
├── ci.yml              # Runs on ALL PRs and pushes
│                       # Does: Lint, Format Check, Unit Tests
│                       # Does NOT deploy
│
├── deploy-branch.yml   # Runs on push to 'develop' branch
│                       # Does: Build → Push → Deploy to DEV
│                       # Automatic, no approval needed
│
└── release.yml         # Manual trigger only
                        # Does: Deploy to STAGING and/or PROD
                        # Requires approval for production
```

### Step C2: Configure GitHub Repository Secrets

1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add these secrets:

| Secret Name | Value | Example |
|------------|-------|---------|
| `AWS_DEPLOY_ROLE_ARN` | The role ARN from Step A4 | `arn:aws:iam::123456789012:role/GitHubActions-InmateCopilot` |

### Step C3: Create GitHub Environments

1. Go to **Settings** → **Environments**
2. Create these environments:

#### Environment: `dev`
- Click **New environment**
- Name: `dev`
- No protection rules needed (auto-deploy)
- Add environment secrets:
  - `AWS_DEPLOY_ROLE_ARN`: (same as repository secret)
  - `AWS_REGION`: `us-east-1`
  - `DEV_API_URL`: (add after first deploy, e.g., `http://InmateCopilot-dev-xxx.us-east-1.elb.amazonaws.com`)

#### Environment: `staging`
- Click **New environment**
- Name: `staging`
- Optional: Enable "Required reviewers" if you want approval
- Add environment secrets:
  - `AWS_DEPLOY_ROLE_ARN`: (your role ARN)
  - `AWS_REGION`: `us-east-1`

#### Environment: `prod`
- Click **New environment**
- Name: `prod`
- **Enable "Required reviewers"** - add yourself or team members
- Add environment secrets:
  - `AWS_DEPLOY_ROLE_ARN`: (your role ARN)
  - `AWS_REGION`: `us-east-1`
  - `PROD_API_URL`: (add after first deploy)

### Step C4: Test CI Pipeline

```bash
# Create a feature branch
git checkout -b test-ci

# Make a small change
echo "# Test" >> README.md

# Commit and push
git add .
git commit -m "Test CI pipeline"
git push origin test-ci

# Create a Pull Request on GitHub
# The CI workflow will run automatically
```

Go to **Actions** tab on GitHub to see the CI workflow running.

### Step C5: Test Auto-Deploy (develop branch)

```bash
# Switch to develop branch
git checkout develop

# Merge your changes
git merge test-ci

# Push to trigger auto-deploy
git push origin develop
```

Go to **Actions** tab to see the deploy-branch workflow running.

### Step C6: Manual Production Release

1. Go to **Actions** tab
2. Click **Release** workflow on the left
3. Click **Run workflow**
4. Choose options:
   - Branch: `main` or `develop`
   - Environments: Leave empty for all, or enter `staging` or `prod`
5. Click **Run workflow**
6. If deploying to `prod`, approve the deployment when prompted

---

## Part D: Post-Deployment Configuration

### Step D1: Configure Customer in DynamoDB

Each customer needs a configuration entry:

```bash
# View current customers
make list-customers ENVIRONMENT=dev

# Add a new customer
# Edit sample_customer_config.json with customer details
nano sample_customer_config.json

# Load to DynamoDB
make load-config ENVIRONMENT=dev
```

### Step D2: Update Customer Configuration Fields

Key fields in `sample_customer_config.json`:

```json
{
  "customer_key": "14",              // Unique customer identifier
  "enabled": true,                    // Enable/disable customer
  
  // Database connection
  "db_host": "your-aurora-cluster.us-east-1.rds.amazonaws.com",
  "db_name": "your_database",
  "db_user": "your_user",
  "db_password": "your_password",    // In production, use Secrets Manager
  "db_port": 3306,
  
  // LLM Configuration
  "llm_model": "gpt-4o-mini",
  "openai_api_key": "sk-...",
  "gemini_api_key": "AIza...",
  
  // Bot settings
  "bot_name": "SARAH",
  "default_facility_ids": [63],
  
  // Daily Activity timetables
  "timetables": { ... }
}
```

### Step D3: Verify All Scopes Work

```bash
# Set API URL
API_URL="http://your-alb-url"

# Test Inmate Data scope
curl -X POST $API_URL/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "how many inmates are there?",
    "customer_key": "14",
    "user_id": "test",
    "facility_ids": [63]
  }'

# Test Document QA scope
curl -X POST $API_URL/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "what is the visitation policy?",
    "customer_key": "14",
    "user_id": "test",
    "facility_ids": [63]
  }'

# Test Daily Activity scope
curl -X POST $API_URL/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "what activities are scheduled today?",
    "customer_key": "14",
    "user_id": "test",
    "facility_ids": [63]
  }'
```

---

## Part E: Day-to-Day Operations

### Deploying Code Changes

**Option 1: CI/CD (Recommended)**
```bash
# For dev deployment
git checkout develop
git merge feature-branch
git push origin develop
# Auto-deploys to dev
```

**Option 2: Manual Deploy**
```bash
make deploy ENVIRONMENT=dev
```

### Viewing Logs

```bash
# Real-time logs
make logs ENVIRONMENT=dev

# Or via AWS Console:
# CloudWatch → Log groups → /ecs/inmate-copilot-dev
```

### Rollback

```bash
# List available versions
make list-versions ENVIRONMENT=dev

# Rollback to specific version
make rollback ENVIRONMENT=dev TAG=abc123def456
```

### Check Status

```bash
# Stack status
make stack-status ENVIRONMENT=dev

# Stack outputs (API URL, etc.)
make stack-outputs ENVIRONMENT=dev

# Health check
make health ENVIRONMENT=dev
```

### Customer Management

```bash
# List customers
make list-customers ENVIRONMENT=dev

# Get customer details
make get-customer CUSTOMER_KEY=14 ENVIRONMENT=dev

# Disable customer
make disable-customer CUSTOMER_KEY=14 ENVIRONMENT=dev

# Enable customer
make enable-customer CUSTOMER_KEY=14 ENVIRONMENT=dev
```

---

## Troubleshooting

### Issue: "Access Denied" during deployment

**Cause:** IAM permissions missing

**Solution:**
```bash
# Verify your AWS identity
aws sts get-caller-identity

# Check if you have admin access or required permissions
# Re-run the IAM setup:
./scripts/setup-github-actions-aws.sh
```

### Issue: ECS tasks keep failing

**Cause:** Container can't start (config error, missing env vars)

**Solution:**
```bash
# Check ECS task status
aws ecs describe-services \
  --cluster InmateCopilot-dev \
  --services InmateCopilot-dev \
  --query "services[0].{Status:status,Running:runningCount,Desired:desiredCount}"

# Check CloudWatch logs
make logs ENVIRONMENT=dev

# Common issues:
# - Missing environment variables
# - Redis connection failed
# - DynamoDB table not found
```

### Issue: Health check failing

**Cause:** ALB can't reach ECS tasks

**Solution:**
```bash
# Check security groups allow traffic
aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=*InmateCopilot*" \
  --query "SecurityGroups[*].[GroupId,GroupName,Description]"

# Verify:
# 1. ALB security group allows inbound 80/443 from 0.0.0.0/0
# 2. ECS security group allows inbound 8000 from ALB security group
# 3. Redis security group allows inbound 6379 from ECS security group
```

### Issue: Redis connection timeout

**Cause:** Network configuration issue

**Solution:**
```bash
# Verify Redis is running
aws elasticache describe-cache-clusters \
  --cache-cluster-id ic-redis-dev \
  --query "CacheClusters[0].CacheClusterStatus"

# Should return "available"

# Verify ECS tasks are in correct subnets
# ECS should be in private subnets
# Redis should be in same subnets as ECS
```

### Issue: DynamoDB table not found

**Cause:** Wrong table name or region

**Solution:**
```bash
# List tables
aws dynamodb list-tables --region us-east-1

# Verify table names match your environment
# Expected: ChatbotCustomerConfiguration-dev, InmateCopilot-Conversations-dev
```

### Issue: Docker build fails

**Cause:** Missing dependencies or syntax error

**Solution:**
```bash
# Build with verbose output
docker build -t inmate-copilot-dev:latest -f dockerfile . --progress=plain

# Check dockerfile syntax
# Ensure all required files are included
```

---

## Glossary

| Term | Description |
|------|-------------|
| **ALB** | Application Load Balancer - distributes traffic to ECS tasks |
| **CloudFormation** | AWS service for infrastructure as code |
| **DynamoDB** | AWS NoSQL database service |
| **ECR** | Elastic Container Registry - stores Docker images |
| **ECS** | Elastic Container Service - runs Docker containers |
| **Fargate** | Serverless compute for ECS (no EC2 to manage) |
| **ElastiCache** | Managed Redis/Memcached service |
| **IAM** | Identity and Access Management - permissions |
| **OIDC** | OpenID Connect - allows GitHub to authenticate with AWS |
| **SAM** | Serverless Application Model - CloudFormation extension |
| **VPC** | Virtual Private Cloud - isolated network |
| **Subnet** | Subdivision of a VPC |
| **Security Group** | Virtual firewall for AWS resources |

---

## Quick Reference

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ENVIRONMENT` | Target environment (dev/staging/prod) |
| `AWS_REGION` | AWS region (default: us-east-1) |
| `CUSTOMER_KEY` | Customer identifier for DynamoDB operations |

### Important URLs

After deployment, get these from `make stack-outputs`:

- **API URL**: `http://InmateCopilot-{env}-xxx.us-east-1.elb.amazonaws.com`
- **Health Check**: `{API_URL}/health`
- **API Docs**: `{API_URL}/docs`

### Common Commands Cheat Sheet

```bash
# Local development
make run                    # Start local server
make test-local             # Run lint + tests

# Deploy
make deploy ENVIRONMENT=dev # Full deploy

# Monitor
make logs ENVIRONMENT=dev   # View logs
make health ENVIRONMENT=dev # Check health

# Rollback
make list-versions ENVIRONMENT=dev
make rollback ENVIRONMENT=dev TAG=xxx

# Customers
make list-customers ENVIRONMENT=dev
make load-config ENVIRONMENT=dev
```

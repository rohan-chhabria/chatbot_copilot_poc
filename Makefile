# =============================================================================
# InmateCopilot — Master Makefile
# =============================================================================
#
# USAGE:
#   make <target> [VARIABLE=value]
#
# EXAMPLES:
#   make install                      # Install all dependencies
#   make run                          # Run locally with uvicorn
#   make test                         # Run unit tests
#   make deploy ENVIRONMENT=staging   # Deploy to staging
#   make rollback ENVIRONMENT=prod TAG=abc123  # Rollback production
#
# =============================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash

# =============================================================================
# CONFIGURATION VARIABLES
# =============================================================================

# AWS_REGION: AWS region for deployment
AWS_REGION ?= us-east-1

# ENVIRONMENT: Target deployment environment
#   Available values: dev, staging, prod
ENVIRONMENT ?= dev

# ECR_REPO: ECR repository name (auto-generated from environment)
ECR_REPO ?= inmate-copilot-$(ENVIRONMENT)

# IMAGE_TAG: Docker image tag (use 'latest' for dev, git SHA for production)
IMAGE_TAG ?= latest

# SAM_STACK_NAME: CloudFormation stack name (auto-generated)
SAM_STACK_NAME ?= InmateCopilot-$(ENVIRONMENT)

# DYNAMO_TABLE: DynamoDB table for customer config (auto-generated)
DYNAMO_CONFIG_TABLE ?= ChatbotCustomerConfiguration-$(ENVIRONMENT)
DYNAMO_CONV_TABLE ?= InmateCopilot-Conversations-$(ENVIRONMENT)

# PYTHON: Python interpreter path
PYTHON ?= python3

# PYTEST_ARGS: Additional arguments for pytest
PYTEST_ARGS ?= -v --tb=short

# =============================================================================
# HELP
# =============================================================================

.PHONY: help
help: ## Show this help with all available commands
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════════════════╗"
	@echo "║                  InmateCopilot — Makefile Commands                   ║"
	@echo "╚══════════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "CURRENT SETTINGS:"
	@echo "  ENVIRONMENT    = $(ENVIRONMENT)"
	@echo "  AWS_REGION     = $(AWS_REGION)"
	@echo "  ECR_REPO       = $(ECR_REPO)"
	@echo "  SAM_STACK_NAME = $(SAM_STACK_NAME)"
	@echo ""
	@echo "AVAILABLE COMMANDS:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "EXAMPLES:"
	@echo "  make install                           # Install dependencies"
	@echo "  make run                               # Start local server"
	@echo "  make test PYTEST_ARGS=\"-k inmate\"      # Run inmate-related tests"
	@echo "  make deploy ENVIRONMENT=staging        # Deploy to staging"
	@echo "  make rollback ENVIRONMENT=prod TAG=abc123"
	@echo ""

# =============================================================================
# DEVELOPMENT — Local Setup & Testing
# =============================================================================

.PHONY: install
install: ## Install Python dependencies (prod)
	@echo "╔══════════════════════════════════════════════════════════════════════╗"
	@echo "║ Installing dependencies...                                           ║"
	@echo "╚══════════════════════════════════════════════════════════════════════╝"
	pip install --upgrade pip
	pip install -r requirements.txt
	@echo ""
	@echo "✅ Dependencies installed. Run 'make run' to start the server."

.PHONY: install-dev
install-dev: install ## Install Python dependencies (dev + prod)
	pip install -r requirements-dev.txt
	@echo "✅ Dev dependencies installed."

.PHONY: run
run: ## Run FastAPI locally with uvicorn (hot-reload enabled)
	@echo "╔══════════════════════════════════════════════════════════════════════╗"
	@echo "║ Starting local development server...                                 ║"
	@echo "║ URL: http://localhost:8000                                           ║"
	@echo "║ Docs: http://localhost:8000/docs                                     ║"
	@echo "║ Press Ctrl+C to stop                                                 ║"
	@echo "╚══════════════════════════════════════════════════════════════════════╝"
	$(PYTHON) -m local.server

.PHONY: test
test: ## Run all tests
	@echo "Running tests with args: $(PYTEST_ARGS)"
	$(PYTHON) -m pytest tests/ $(PYTEST_ARGS)

.PHONY: test-unit
test-unit: ## Run unit tests only
	@echo "Running unit tests..."
	SESSION_BACKEND=memory LTM_BACKEND=noop $(PYTHON) -m pytest tests/unit/ $(PYTEST_ARGS)

.PHONY: test-local
test-local: lint format-check test-unit ## Run full local CI (lint + format + unit tests)
	@echo ""
	@echo "✅ All local checks passed!"

.PHONY: lint
lint: ## Run Ruff linter
	@echo "Running ruff..."
	ruff check src/ --output-format=github

.PHONY: lint-fix
lint-fix: ## Auto-fix linting issues
	@echo "Fixing lint issues..."
	ruff check --fix --unsafe-fixes src/

.PHONY: format
format: ## Format code with Ruff
	@echo "Formatting code..."
	ruff format src/
	@echo "✅ Code formatted"

.PHONY: format-check
format-check: ## Check code formatting
	ruff format src/ --check

.PHONY: clean
clean: ## Remove Python cache and build artifacts
	@echo "Cleaning build artifacts..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf infra/.aws-sam 2>/dev/null || true
	rm -f test-results.xml coverage.xml
	@echo "✅ Clean complete"

# =============================================================================
# DOCKER — Build & Run Container
# =============================================================================

.PHONY: build
build: ## Build Docker image locally
	@echo "╔══════════════════════════════════════════════════════════════════════╗"
	@echo "║ Building Docker image: $(ECR_REPO):$(IMAGE_TAG)                      "
	@echo "╚══════════════════════════════════════════════════════════════════════╝"
	docker build -t $(ECR_REPO):$(IMAGE_TAG) -f dockerfile .
	@echo ""
	@echo "✅ Image built: $(ECR_REPO):$(IMAGE_TAG)"
	@echo "   Run with: make run-docker"

.PHONY: run-docker
run-docker: build ## Build and run container locally (requires .env file)
	@echo "╔══════════════════════════════════════════════════════════════════════╗"
	@echo "║ Running container locally...                                         ║"
	@echo "║ URL: http://localhost:8000                                           ║"
	@echo "║ Press Ctrl+C to stop                                                 ║"
	@echo "╚══════════════════════════════════════════════════════════════════════╝"
	@if [ ! -f .env ]; then \
		echo "⚠️  Warning: .env file not found. Create one from .env.example"; \
		exit 1; \
	fi
	docker run --rm -p 8000:8000 --env-file .env $(ECR_REPO):$(IMAGE_TAG)

.PHONY: docker-clean
docker-clean: ## Remove Docker images and containers
	docker compose -f docker-compose.test.yml down -v 2>/dev/null || true
	docker rmi $(ECR_REPO):$(IMAGE_TAG) 2>/dev/null || true
	@echo "✅ Docker cleaned"

# =============================================================================
# AWS DEPLOYMENT — ECR, SAM, ECS
# =============================================================================

.PHONY: ecr-login
ecr-login: ## Login to Amazon ECR (required before push)
	@echo "Logging in to ECR in region $(AWS_REGION)..."
	aws ecr get-login-password --region $(AWS_REGION) | \
		docker login --username AWS --password-stdin $$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$(AWS_REGION).amazonaws.com
	@echo "✅ ECR login successful"

.PHONY: push
push: ecr-login build ## Build and push Docker image to ECR
	@echo "╔══════════════════════════════════════════════════════════════════════╗"
	@echo "║ Pushing to ECR: $(ECR_REPO):$(IMAGE_TAG)                             "
	@echo "╚══════════════════════════════════════════════════════════════════════╝"
	@ECR_URI=$$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$(AWS_REGION).amazonaws.com/$(ECR_REPO); \
	echo "ECR URI: $$ECR_URI"; \
	docker tag $(ECR_REPO):$(IMAGE_TAG) $$ECR_URI:$(IMAGE_TAG); \
	docker push $$ECR_URI:$(IMAGE_TAG); \
	docker tag $(ECR_REPO):$(IMAGE_TAG) $$ECR_URI:latest; \
	docker push $$ECR_URI:latest; \
	echo ""; \
	echo "✅ Image pushed: $$ECR_URI:$(IMAGE_TAG)"

.PHONY: sam-validate
sam-validate: ## Validate SAM template syntax
	@echo "Validating SAM template..."
	sam validate --template-file infra/template.yaml --region $(AWS_REGION) --lint
	@echo "✅ Template is valid"

.PHONY: sam-build
sam-build: ## Build SAM application
	@echo "Building SAM application..."
	cd infra && sam build --template-file template.yaml
	@echo "✅ SAM build complete"

.PHONY: sam-deploy
sam-deploy: sam-build ## Deploy SAM stack to AWS
	@echo "╔══════════════════════════════════════════════════════════════════════╗"
	@echo "║ Deploying SAM stack: $(SAM_STACK_NAME)                               "
	@echo "║ Environment: $(ENVIRONMENT)                                          "
	@echo "║ Region: $(AWS_REGION)                                                "
	@echo "╚══════════════════════════════════════════════════════════════════════╝"
	cd infra && sam deploy --no-confirm-changeset --no-fail-on-empty-changeset --config-env $(ENVIRONMENT)
	@echo ""
	@echo "✅ SAM deployment complete for $(ENVIRONMENT)"

.PHONY: deploy
deploy: push sam-deploy ## Full deploy: build → push → SAM deploy
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════════════════╗"
	@echo "║ ✅ DEPLOYMENT COMPLETE                                               ║"
	@echo "║ Environment: $(ENVIRONMENT)                                          "
	@echo "║ Image: $(ECR_REPO):$(IMAGE_TAG)                                      "
	@echo "╚══════════════════════════════════════════════════════════════════════╝"

.PHONY: update-service
update-service: ## Force ECS service update (trigger new deployment)
	@echo "Updating ECS service..."
	aws ecs update-service \
		--cluster $(SAM_STACK_NAME) \
		--service $(SAM_STACK_NAME) \
		--force-new-deployment \
		--region $(AWS_REGION) --no-cli-pager
	@echo "✅ Service update triggered"

# =============================================================================
# ROLLBACK — Revert to Previous Version
# =============================================================================

.PHONY: list-versions
list-versions: ## List recent ECR image tags for rollback
	@echo "╔══════════════════════════════════════════════════════════════════════╗"
	@echo "║ Recent images for: $(ECR_REPO)                                       "
	@echo "╚══════════════════════════════════════════════════════════════════════╝"
	@aws ecr describe-images \
		--repository-name $(ECR_REPO) \
		--region $(AWS_REGION) \
		--query "imageDetails | sort_by(@, &imagePushedAt) | [-10:].{Tag: imageTags[0], Pushed: imagePushedAt, Size: imageSizeInBytes}" \
		--output table
	@echo ""
	@echo "To rollback: make rollback ENVIRONMENT=$(ENVIRONMENT) TAG=<tag-from-above>"

.PHONY: rollback
rollback: ## Rollback to specific image tag (requires TAG=xxx)
	@if [ -z "$(TAG)" ]; then \
		echo "❌ ERROR: TAG is required"; \
		echo "Usage: make rollback ENVIRONMENT=$(ENVIRONMENT) TAG=<commit-sha>"; \
		echo "Run 'make list-versions' to see available tags"; \
		exit 1; \
	fi
	@echo "╔══════════════════════════════════════════════════════════════════════╗"
	@echo "║ ROLLBACK                                                             ║"
	@echo "║ Environment: $(ENVIRONMENT)                                          "
	@echo "║ Target Tag: $(TAG)                                                   "
	@echo "╚══════════════════════════════════════════════════════════════════════╝"
	@ECR_URI=$$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$(AWS_REGION).amazonaws.com/$(ECR_REPO); \
	echo "Rolling back to: $$ECR_URI:$(TAG)"; \
	cd infra && sam deploy \
		--no-confirm-changeset \
		--no-fail-on-empty-changeset \
		--config-env $(ENVIRONMENT) \
		--parameter-overrides "ContainerImage=$$ECR_URI:$(TAG)"; \
	echo ""; \
	echo "✅ Rolled back to $(TAG)"

# =============================================================================
# CUSTOMER MANAGEMENT — DynamoDB Operations
# =============================================================================

.PHONY: load-config
load-config: ## Load customer config from sample_customer_config.json to DynamoDB
	@echo "╔══════════════════════════════════════════════════════════════════════╗"
	@echo "║ Loading customer config to: $(DYNAMO_CONFIG_TABLE)                   "
	@echo "╚══════════════════════════════════════════════════════════════════════╝"
	@$(PYTHON) -c "\
import json, boto3; \
config = json.load(open('sample_customer_config.json')); \
config.pop('_info', None); \
boto3.resource('dynamodb', region_name='$(AWS_REGION)').Table('$(DYNAMO_CONFIG_TABLE)').put_item(Item=config); \
print('✅ Loaded config for customer_key:', config['customer_key'])"

.PHONY: list-customers
list-customers: ## List all customers in DynamoDB
	@echo "╔══════════════════════════════════════════════════════════════════════╗"
	@echo "║ CUSTOMERS in $(DYNAMO_CONFIG_TABLE)                                  "
	@echo "╚══════════════════════════════════════════════════════════════════════╝"
	@aws dynamodb scan \
		--table-name $(DYNAMO_CONFIG_TABLE) \
		--projection-expression "customer_key, bot_name, enabled, llm_model" \
		--region $(AWS_REGION) \
		--output table

.PHONY: get-customer
get-customer: ## Get customer details (requires CUSTOMER_KEY=xxx)
	@if [ -z "$(CUSTOMER_KEY)" ]; then \
		echo "❌ ERROR: CUSTOMER_KEY is required"; \
		echo "Usage: make get-customer CUSTOMER_KEY=14"; \
		exit 1; \
	fi
	@echo "Fetching customer: $(CUSTOMER_KEY)"
	@aws dynamodb get-item \
		--table-name $(DYNAMO_CONFIG_TABLE) \
		--key '{"customer_key": {"S": "$(CUSTOMER_KEY)"}}' \
		--region $(AWS_REGION) \
		--output yaml

.PHONY: disable-customer
disable-customer: ## Disable a customer (requires CUSTOMER_KEY=xxx)
	@if [ -z "$(CUSTOMER_KEY)" ]; then \
		echo "❌ ERROR: CUSTOMER_KEY is required"; \
		exit 1; \
	fi
	@echo "Disabling customer: $(CUSTOMER_KEY)"
	@aws dynamodb update-item \
		--table-name $(DYNAMO_CONFIG_TABLE) \
		--key '{"customer_key": {"S": "$(CUSTOMER_KEY)"}}' \
		--update-expression "SET enabled = :val" \
		--expression-attribute-values '{":val": {"BOOL": false}}' \
		--region $(AWS_REGION)
	@echo "✅ Customer $(CUSTOMER_KEY) disabled"

.PHONY: enable-customer
enable-customer: ## Enable a customer (requires CUSTOMER_KEY=xxx)
	@if [ -z "$(CUSTOMER_KEY)" ]; then \
		echo "❌ ERROR: CUSTOMER_KEY is required"; \
		exit 1; \
	fi
	@echo "Enabling customer: $(CUSTOMER_KEY)"
	@aws dynamodb update-item \
		--table-name $(DYNAMO_CONFIG_TABLE) \
		--key '{"customer_key": {"S": "$(CUSTOMER_KEY)"}}' \
		--update-expression "SET enabled = :val" \
		--expression-attribute-values '{":val": {"BOOL": true}}' \
		--region $(AWS_REGION)
	@echo "✅ Customer $(CUSTOMER_KEY) enabled"

# =============================================================================
# MONITORING & DEBUGGING
# =============================================================================

.PHONY: logs
logs: ## Tail ECS logs in real-time (requires ENVIRONMENT)
	@echo "Tailing logs for: /ecs/inmate-copilot-$(ENVIRONMENT)"
	@echo "Press Ctrl+C to stop"
	@echo ""
	aws logs tail /ecs/inmate-copilot-$(ENVIRONMENT) --follow --region $(AWS_REGION)

.PHONY: stack-status
stack-status: ## Show CloudFormation stack status
	@echo "Stack: $(SAM_STACK_NAME)"
	@aws cloudformation describe-stacks \
		--stack-name $(SAM_STACK_NAME) \
		--region $(AWS_REGION) \
		--query "Stacks[0].{Status: StackStatus, Updated: LastUpdatedTime, Created: CreationTime}" \
		--output table

.PHONY: stack-outputs
stack-outputs: ## Show CloudFormation stack outputs (API URL, ARNs, etc.)
	@echo "Stack outputs for: $(SAM_STACK_NAME)"
	@aws cloudformation describe-stacks \
		--stack-name $(SAM_STACK_NAME) \
		--region $(AWS_REGION) \
		--query "Stacks[0].Outputs[*].{Key: OutputKey, Value: OutputValue}" \
		--output table

.PHONY: api-url
api-url: ## Get the API Gateway URL for the environment
	@aws cloudformation describe-stacks \
		--stack-name $(SAM_STACK_NAME) \
		--region $(AWS_REGION) \
		--query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
		--output text

.PHONY: health
health: ## Check health of deployed service
	@API_URL=$$(aws cloudformation describe-stacks \
		--stack-name $(SAM_STACK_NAME) \
		--region $(AWS_REGION) \
		--query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
		--output text 2>/dev/null); \
	if [ -z "$$API_URL" ]; then \
		echo "❌ Stack not found or no API URL output"; \
		exit 1; \
	fi; \
	echo "Checking health: $$API_URL/health"; \
	curl -s $$API_URL/health | $(PYTHON) -m json.tool

# =============================================================================
# AWS SETUP — One-time configuration
# =============================================================================

.PHONY: aws-setup
aws-setup: ## Setup AWS OIDC + IAM policy (one-time, requires admin)
	@echo "╔══════════════════════════════════════════════════════════════════════╗"
	@echo "║ Setting up AWS OIDC and IAM Policy                                   ║"
	@echo "╚══════════════════════════════════════════════════════════════════════╝"
	chmod +x scripts/setup-github-actions-aws.sh
	./scripts/setup-github-actions-aws.sh
	@echo ""
	@echo "Now run: make aws-role GITHUB_ORG=your-org"

.PHONY: aws-role
aws-role: ## Create GitHub Actions role (requires GITHUB_ORG=xxx)
	@if [ -z "$(GITHUB_ORG)" ]; then \
		echo "❌ ERROR: GITHUB_ORG is required"; \
		echo "Usage: make aws-role GITHUB_ORG=your-github-org"; \
		exit 1; \
	fi
	chmod +x scripts/create-github-actions-role.sh
	GITHUB_ORG=$(GITHUB_ORG) ./scripts/create-github-actions-role.sh

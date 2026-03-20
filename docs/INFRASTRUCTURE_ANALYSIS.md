# InmateCopilot — Infrastructure & Cost Analysis

**Version**: 1.0
**Created**: 2026-03-19
**Target Scale**: V1 (100 concurrent users) → V2 (1000 users)

---

## Table of Contents

1. [Server vs Serverless Decision](#server-vs-serverless-decision)
2. [AWS Architecture](#aws-architecture)
3. [Cost Breakdown](#cost-breakdown)
4. [LLM Cost Analysis](#llm-cost-analysis)
5. [V1 Requirements](#v1-requirements)
6. [V2 Considerations](#v2-considerations)
7. [Scaling Strategy](#scaling-strategy)

---

## Server vs Serverless Decision

### Recommendation: **ECS Fargate** (Not Lambda)

#### Why NOT Lambda for This Use Case

| Factor | Lambda Problem | Impact |
|--------|----------------|--------|
| **Cold starts** | 3-8 seconds for Python + ML deps (ChromaDB, OpenAI, Vanna) | Unacceptable for chat UX |
| **ChromaDB** | Needs persistent storage, slow to load collections | Can't reload 500MB+ index on every invocation |
| **Valkey connections** | New connection per invocation | Connection pool thrashing, latency |
| **Aurora connections** | Connection limit exhaustion | 100 concurrent = 100 DB connections constantly opening/closing |
| **Streaming (SSE)** | Lambda has 6MB response limit, no true streaming | Breaks `/chat/stream` endpoint |
| **LLM latency** | Vanna + LLM calls = 3-10s | Lambda timeout pressure, cost per 100ms |
| **Memory** | ChromaDB + embeddings need 1-2GB | Expensive Lambda pricing tier ($0.0000166667/GB-s) |
| **Concurrency** | Per-account limits, provisioned concurrency expensive | Can't handle burst traffic easily |

#### Lambda IS Good For (Future Use)

- Document upload/indexing (async, batch job) → S3 trigger
- Webhook handlers
- Scheduled tasks (cleanup, analytics aggregation)
- Lightweight API endpoints (health checks)

#### Why ECS Fargate

| Factor | Fargate Benefit |
|--------|-----------------|
| **Warm containers** | No cold starts, sub-50ms routing |
| **Connection pooling** | Single MySQL pool per container (10 connections serves 100 users) |
| **ChromaDB** | Load once at startup, keep in memory |
| **Valkey** | Persistent connection pool |
| **Streaming** | Native SSE support (FastAPI + uvicorn) |
| **Memory** | Fixed allocation, predictable cost |
| **Scaling** | Horizontal auto-scaling based on CPU/connections |
| **Cost predictability** | Fixed per-hour vs unpredictable per-invocation |

---

## AWS Architecture

### V1: 100 Concurrent Users

```
                            ┌─────────────────────────────┐
                            │      Route 53 (DNS)         │
                            └─────────────┬───────────────┘
                                          │
                            ┌─────────────▼───────────────┐
                            │   Application Load Balancer  │
                            │   (with WebSocket/SSE)       │
                            │   Idle timeout: 300s         │
                            └─────────────┬───────────────┘
                                          │
               ┌──────────────────────────┼──────────────────────────┐
               │                          │                          │
    ┌──────────▼──────────┐   ┌──────────▼──────────┐   ┌──────────▼──────────┐
    │   ECS Fargate       │   │   ECS Fargate       │   │   ECS Fargate       │
    │   Task 1            │   │   Task 2            │   │   Task 3            │
    │   0.5 vCPU / 2GB    │   │   0.5 vCPU / 2GB    │   │   0.5 vCPU / 2GB    │
    │                     │   │                     │   │                     │
    │ ┌─────────────────┐ │   │ ┌─────────────────┐ │   │ ┌─────────────────┐ │
    │ │ FastAPI App     │ │   │ │ FastAPI App     │ │   │ │ FastAPI App     │ │
    │ │ - Orchestrator  │ │   │ │ - Orchestrator  │ │   │ │ - Orchestrator  │ │
    │ │ - Pipelines     │ │   │ │ - Pipelines     │ │   │ │ - Pipelines     │ │
    │ │ - ChromaDB      │ │   │ │ - ChromaDB      │ │   │ │ - ChromaDB      │ │
    │ │   (in-memory)   │ │   │ │   (in-memory)   │ │   │ │   (in-memory)   │ │
    │ └─────────────────┘ │   │ └─────────────────┘ │   │ └─────────────────┘ │
    └─────────┬───────────┘   └─────────┬───────────┘   └─────────┬───────────┘
              │                         │                         │
              └─────────────────────────┼─────────────────────────┘
                                        │
         ┌──────────────────────────────┼──────────────────────────────┐
         │                              │                              │
┌────────▼────────┐          ┌──────────▼──────────┐        ┌──────────▼──────────┐
│  ElastiCache    │          │   Aurora MySQL      │        │    DynamoDB         │
│  Valkey         │          │   (Read Replica)    │        │    (Conversations)  │
│  t4g.small      │          │   (Existing)        │        │    On-demand        │
│                 │          │                     │        │                     │
│  Sessions/STM   │          │  Inmate Data Queries│        │    LTM History      │
└─────────────────┘          └─────────────────────┘        └─────────────────────┘
```

### Component Specifications

| Component | V1 Spec (100 users) | V2 Spec (1000 users) |
|-----------|--------------------|--------------------|
| **ECS Tasks** | 3 tasks | 8-12 tasks (auto-scale) |
| **CPU per task** | 0.5 vCPU | 1 vCPU |
| **Memory per task** | 2 GB | 4 GB |
| **Valkey** | t4g.small (1.37GB) | r7g.medium (6.38GB) |
| **Aurora** | Existing reader | May need dedicated |
| **DynamoDB** | On-demand | On-demand (auto-scales) |
| **ALB** | Standard | Standard |

### ECS Task Definition

```yaml
# Approximate task definition
containerDefinitions:
  - name: chatbot-api
    image: {ECR_REPO}/inmate-copilot:latest
    cpu: 512          # 0.5 vCPU
    memory: 2048      # 2 GB
    portMappings:
      - containerPort: 8000
        protocol: tcp
    environment:
      - name: ENVIRONMENT
        value: production
      - name: VALKEY_HOST
        value: {VALKEY_ENDPOINT}
      - name: LLM_PROVIDER
        value: openai
    secrets:
      - name: OPENAI_API_KEY
        valueFrom: {SECRETS_MANAGER_ARN}
      - name: MYSQL_PASSWORD
        valueFrom: {SECRETS_MANAGER_ARN}
    healthCheck:
      command: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 30
      timeout: 5
      retries: 3
```

---

## Cost Breakdown

### V1: 100 Concurrent Users (Steady State)

#### Infrastructure Costs

| Component | Spec | Hourly | Monthly |
|-----------|------|--------|---------|
| **ECS Fargate** | 3 tasks × 0.5 vCPU × 2GB | $0.062 | **$45** |
| **Application Load Balancer** | Base + LCU | $0.028 | **$20** |
| **ElastiCache Valkey** | t4g.small | $0.034 | **$25** |
| **DynamoDB** | ~500K writes/month | - | **$5** |
| **CloudWatch** | Logs + metrics | - | **$10** |
| **Secrets Manager** | 3 secrets | - | **$2** |
| **ECR** | Docker images | - | **$1** |
| **Aurora MySQL** | Existing reader | - | **$0** |

**Infrastructure Subtotal: ~$108/month**

#### LLM Costs

| Pipeline | Model | Tokens/Query | Queries/Day | Cost/Query | Monthly |
|----------|-------|--------------|-------------|------------|---------|
| **Inmate Data (SQL)** | GPT-4o-mini | ~2K input, 200 output | 1000 | $0.0015 | **$45** |
| **Document QA** | GPT-4o-mini | ~3K input, 500 output | 500 | $0.0025 | **$38** |
| **Embeddings** | text-embedding-3-small | ~500 tokens | 500 | $0.00001 | **$0.15** |

**LLM Subtotal: ~$85/month**

#### V1 Total: **~$193/month**

---

### V2: 1000 Concurrent Users (Peak)

#### Infrastructure Costs

| Component | Spec | Hourly | Monthly |
|-----------|------|--------|---------|
| **ECS Fargate** | 10 tasks × 1 vCPU × 4GB | $0.41 | **$300** |
| **Application Load Balancer** | Higher LCU | $0.07 | **$50** |
| **ElastiCache Valkey** | r7g.medium | $0.14 | **$100** |
| **DynamoDB** | ~2M writes/month | - | **$15** |
| **CloudWatch** | Logs + metrics | - | **$25** |
| **Aurora MySQL** | May need dedicated reader | - | **$50-100** |

**Infrastructure Subtotal: ~$540-590/month**

#### LLM Costs (Scaled)

| Pipeline | Queries/Day | Monthly |
|----------|-------------|---------|
| **Inmate Data (SQL)** | 5000 | **$225** |
| **Document QA** | 2500 | **$190** |
| **Embeddings** | 2500 | **$0.75** |

**LLM Subtotal: ~$415/month**

#### V2 Total: **~$1,000-1,050/month**

---

## LLM Cost Analysis

### Model Pricing (as of March 2026)

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| **GPT-4o-mini** | $0.15 | $0.60 |
| **GPT-4o** | $2.50 | $10.00 |
| **Gemini 2.5 Flash** | $0.10 | $0.40 |
| **text-embedding-3-small** | $0.02 | - |
| **text-embedding-ada-002** | $0.10 | - |

### Cost Per Query Breakdown

#### Inmate Data Pipeline (SQL Generation)
```
System prompt:     ~1500 tokens
User question:     ~50 tokens
ChromaDB context:  ~500 tokens
----------------------------
Total input:       ~2050 tokens → $0.0003

SQL output:        ~150 tokens → $0.00009
Summary output:    ~100 tokens → $0.00006
----------------------------
Total output:      ~250 tokens → $0.00015

TOTAL per query: ~$0.00045 (without retry)
With 20% retry rate: ~$0.00054
```

#### Document QA Pipeline (RAG)
```
System prompt:     ~500 tokens
User question:     ~50 tokens
Retrieved chunks:  ~2000 tokens (5 chunks × 400 tokens)
----------------------------
Total input:       ~2550 tokens → $0.0004

Answer output:     ~400 tokens → $0.00024
----------------------------
Total output:      ~400 tokens → $0.00024

Embedding (query): ~50 tokens → $0.000001

TOTAL per query: ~$0.00065
```

### Cost Optimization Strategies

| Strategy | Potential Savings | Implementation |
|----------|-------------------|----------------|
| **Response caching** | 20-30% LLM | Cache identical questions in Valkey (1hr TTL) |
| **Gemini Flash fallback** | 40% LLM | Use for simple queries, GPT for complex |
| **Smaller embedding model** | 50% embedding | text-embedding-3-small vs ada-002 |
| **Prompt compression** | 10-15% input | Remove redundant system prompt parts |
| **Reserved Fargate** | 30% compute | 1-year Savings Plan commitment |
| **Spot Fargate** | 50-70% compute | For non-critical dev/staging |

---

## V1 Requirements

### Must Have (Critical)

| Item | Why | Implementation |
|------|-----|----------------|
| **Standardized error responses** | Consistent UX, debugging | `PipelineError` base class, middleware handler |
| **Request timeouts** | LLM calls can hang | Per-pipeline configurable (30s default) |
| **Pipeline health checks** | Monitoring, debugging | `/pipelines/health/{scope}` endpoint |
| **Basic logging** | Debugging, audit trail | CloudWatch Logs with request IDs |
| **Graceful degradation** | If doc QA is down, inmate works | Pipeline-level isolation, circuit breakers |
| **Input validation** | Security, stability | Pydantic schemas, guardrails |

### Nice to Have (V1)

| Item | Why | Can Defer? |
|------|-----|------------|
| **Request tracing** | Debug cross-service issues | Yes, add X-Ray later |
| **Basic metrics** | Latency, error rates | Yes, CloudWatch basic |
| **Config per pipeline** | Different timeouts, limits | Yes, use defaults |

---

## V2 Considerations

### Deferred to V2

| Item | Why V2 | Complexity |
|------|--------|------------|
| **Rate limiting** | Abuse prevention at scale | Medium |
| **Advanced analytics** | Query patterns, user behavior | High |
| **Pipeline versioning** | A/B testing, rollbacks | Medium |
| **Scope permissions** | Role-based access to scopes | High |
| **Multi-region** | Disaster recovery, latency | High |
| **Query caching layer** | LLM cost reduction | Medium |
| **Async document indexing** | Background processing | Medium |
| **Tenant resource quotas** | Fair usage enforcement | Medium |

### V2 Architecture Enhancements

```
                     ┌─────────────────┐
                     │   CloudFront    │ ← Static assets, edge caching
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │   WAF + Shield  │ ← DDoS protection, rate limiting
                     └────────┬────────┘
                              │
                     ┌────────▼────────┐
                     │      ALB        │
                     └────────┬────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
    ┌────▼────┐          ┌────▼────┐         ┌────▼────┐
    │ ECS     │          │ ECS     │         │ ECS     │
    │ (10+    │          │ (10+    │         │ (10+    │
    │ tasks)  │          │ tasks)  │         │ tasks)  │
    └────┬────┘          └────┬────┘         └────┬────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              │
    ┌─────────────────────────┼─────────────────────────┐
    │                         │                         │
┌───▼───┐              ┌──────▼──────┐           ┌──────▼──────┐
│Valkey │              │   Aurora    │           │  DynamoDB   │
│Cluster│              │  Cluster    │           │  + DAX      │ ← Caching layer
└───────┘              └─────────────┘           └─────────────┘
    │
┌───▼───────────────┐
│ ElastiCache       │
│ (Query Cache)     │ ← LLM response caching
└───────────────────┘
```

---

## Scaling Strategy

### Horizontal Scaling (ECS)

```yaml
# Auto-scaling policy
scalableTarget:
  minCapacity: 3      # V1
  maxCapacity: 15     # V2 headroom

scalingPolicy:
  - type: TargetTrackingScaling
    targetValue: 70
    predefinedMetric: ECSServiceAverageCPUUtilization
    scaleOutCooldown: 60
    scaleInCooldown: 300

  - type: TargetTrackingScaling
    targetValue: 70
    predefinedMetric: ECSServiceAverageMemoryUtilization
```

### Load Testing Targets

| Metric | V1 Target | V2 Target |
|--------|-----------|-----------|
| **P50 latency** | < 2s | < 2s |
| **P99 latency** | < 5s | < 8s |
| **Error rate** | < 1% | < 0.5% |
| **Concurrent users** | 100 | 1000 |
| **Requests/second** | 50 | 500 |

### Monitoring Alerts

| Alert | Threshold | Action |
|-------|-----------|--------|
| **CPU > 80%** | 5 min | Scale out |
| **Memory > 85%** | 5 min | Scale out |
| **Error rate > 5%** | 1 min | Page on-call |
| **P99 latency > 10s** | 5 min | Investigate |
| **DynamoDB throttling** | Any | Increase capacity |
| **Valkey memory > 80%** | 5 min | Increase instance size |

---

## Summary

| Decision | Choice | Monthly Cost |
|----------|--------|--------------|
| **Infrastructure** | ECS Fargate | $108 (V1) / $540 (V2) |
| **Compute** | 3 tasks → 10 tasks | Scales with load |
| **LLM** | GPT-4o-mini | $85 (V1) / $415 (V2) |
| **Total V1** | 100 concurrent | **~$193/month** |
| **Total V2** | 1000 concurrent | **~$1,000/month** |

### Key Takeaways

1. **ECS Fargate over Lambda** — Cold starts, connection pooling, streaming requirements make Lambda unsuitable
2. **LLM is ~45% of cost** — Caching and model selection are high-impact optimizations
3. **Linear scaling** — 10x users ≈ 5x cost (economies of scale on infra)
4. **V1 is lean** — Under $200/month for production-ready chatbot
5. **V2 is achievable** — ~$1K/month for enterprise scale

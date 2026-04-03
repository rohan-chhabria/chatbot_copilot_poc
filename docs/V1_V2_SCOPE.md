# InmateCopilot — V1 vs V2 Scope

**Created**: 2026-03-19
**Purpose**: Track what's included in V1, what's deferred to V2, and decisions made.

---

## Executive Summary

**V1 Goal**: Transform single-purpose SQL chatbot into guided multi-capability agent with:
- Inmate Data pipeline (existing, migrated)
- Document QA pipeline (new)
- Scope management with context preservation
- Production-ready for 100 concurrent users

**V2 Goal**: Scale to 1000 users with advanced features and optimizations.

---

## V1 — Included

### Core Features

| Feature | Description | Status |
|---------|-------------|--------|
| **Guided Scope Selection** | User explicitly selects capability (UI blocks) | Included |
| **Scope Switching** | Switch button, context preserved per scope | Included |
| **Inmate Data Pipeline** | Existing Vanna/SQL migrated to new structure | Included |
| **Document QA Pipeline** | RAG with hybrid search (semantic + BM25) | Included |
| **Daily Activity Pipeline** | Check missed/upcoming scheduled activities | Included |
| **Multi-turn Context** | Follow-ups work within each scope | Included |
| **Scope Resume** | Return to previous scope with context | Included |
| **Cross-scope Recall** | "What did I ask earlier?" works | Included |

### Technical Components

| Component | V1 Implementation |
|-----------|-------------------|
| **Orchestrator** | ScopeStateMachine, ScopeRegistry, CrossScopeHandler |
| **Pipeline Interface** | Abstract Pipeline base class with supports_auto_execute |
| **Session Models** | Enhanced with active_scope, scope_contexts |
| **Hybrid Search** | Semantic + BM25 + RRF fusion |
| **Activity Checker** | Timetable comparison with DB records |
| **Chunking** | Recursive (paragraph → sentence) |
| **Embedding Model** | text-embedding-3-small |
| **LLM** | GPT-4o-mini |

### Infrastructure

| Component | V1 Spec |
|-----------|---------|
| **Compute** | ECS Fargate (3 tasks × 0.5 vCPU × 2GB) |
| **Sessions** | Valkey (ElastiCache t4g.small) |
| **History** | DynamoDB (on-demand) |
| **Vector Store** | ChromaDB (persistent, tenant-isolated) |
| **Target Scale** | 100 concurrent users |
| **Estimated Cost** | ~$200/month |

### API Endpoints

| Endpoint | V1 Status |
|----------|-----------|
| `POST /chat` | Modified (uses orchestrator) |
| `GET /chat/stream` | Modified (scope-aware streaming) |
| `POST /scope/select` | New |
| `GET /scope/options` | New |
| `GET /pipelines/health/{scope}` | New |
| `GET /session/{id}` | Unchanged |
| `GET /history` | Modified (scope filtering) |

### Quality Requirements

| Metric | V1 Target |
|--------|-----------|
| **Latency (P50)** | < 2 seconds |
| **Latency (P99)** | < 5 seconds |
| **Error Rate** | < 1% |
| **Test Coverage** | > 80% |

---

## V1 — Explicitly Excluded (Deferred to V2)

### Advanced RAG Features

| Feature | Why Deferred | V2 Priority |
|---------|--------------|-------------|
| **Contextual Retrieval** | Extra LLM cost at indexing (~$0.001/chunk) | Medium |
| **Cross-encoder Reranking** | Adds ~200ms latency, diminishing returns | Low |
| **Query Transformation** | Complex, requires prompt tuning | Medium |
| **Agentic RAG** | Multi-step retrieval, very complex | Low |
| **Document Upload API** | Need auth/validation design | High |

### Scale & Performance

| Feature | Why Deferred | V2 Priority |
|---------|--------------|-------------|
| **1000+ Concurrent Users** | Requires infra scaling | High |
| **Response Caching** | Complexity, cache invalidation | High |
| **Query Result Caching** | LLM cost reduction | High |
| **Connection Pooling Optimization** | Aurora scaling | Medium |

### Security & Compliance

| Feature | Why Deferred | V2 Priority |
|---------|--------------|-------------|
| **Rate Limiting** | Per-user, per-tenant | High |
| **Scope Permissions** | Role-based access to scopes | Medium |
| **Audit Logging** | Detailed query logging | High |
| **PII Detection** | In documents and queries | Medium |

### Analytics & Monitoring

| Feature | Why Deferred | V2 Priority |
|---------|--------------|-------------|
| **Query Analytics Dashboard** | Usage patterns, popular queries | Medium |
| **User Behavior Tracking** | Scope preferences, session lengths | Medium |
| **Pipeline Performance Metrics** | Detailed latency breakdown | High |
| **Alerting Rules** | Custom alert thresholds | High |

### Platform Features

| Feature | Why Deferred | V2 Priority |
|---------|--------------|-------------|
| **Multiple Document Collections** | Per-category document sets | Medium |
| **Document Version Control** | Track document updates | Low |
| **Pipeline Versioning** | A/B testing, rollbacks | Medium |
| **Multi-region Deployment** | DR, latency optimization | Low |
| **Tenant Resource Quotas** | Fair usage enforcement | Medium |

### Future Pipelines

| Pipeline | Description | V2 Priority |
|----------|-------------|-------------|
| **Analytics/Reports** | Generate summary reports | High |
| **Shift Planning** | Staffing recommendations | Low |
| **Inmate Risk Assessment** | Behavioral analysis | Low |

---

## Key Decisions Made

### 1. Guided vs Inferred Routing

**Decision**: Guided (explicit scope selection)

**Rationale**:
- Correctional facility context — wrong answers have consequences
- Zero hallucination risk on routing
- User control over their experience
- Simpler implementation

**Trade-off**: Extra click to select scope

---

### 2. ECS Fargate vs Lambda

**Decision**: ECS Fargate

**Rationale**:
- No cold starts (Lambda: 3-8s)
- Persistent connection pools
- ChromaDB stays in memory
- Native SSE streaming support
- Predictable cost

**Trade-off**: Always-running containers vs pay-per-invocation

---

### 3. Hybrid Search vs Pure Semantic

**Decision**: Hybrid (Semantic + BM25 + RRF)

**Rationale**:
- BM25 catches exact terms semantic misses (dates, commands, acronyms)
- RRF fusion is simple, no hyperparameters
- Proven in Colab notebook testing

**Trade-off**: Slightly more complexity, ~200ms extra latency

---

### 4. Contextual Retrieval

**Decision**: Optional, OFF by default

**Rationale**:
- Extra LLM cost at indexing time
- Good for important documents only
- Can enable per-tenant

**V2**: Make configurable per document collection

---

### 5. Reranking

**Decision**: Optional, OFF by default

**Rationale**:
- Adds latency (~200ms)
- Hybrid search is already good enough for V1
- Can enable for "precision mode"

**V2**: Add tier system (FAST, HYBRID, FULL)

---

### 6. Scope Context Preservation

**Decision**: Preserve per-scope context across switches

**Rationale**:
- Natural UX — return to previous state
- Enables "where was I?" recall
- Easy implementation with scope_contexts dict

---

### 7. Session Structure

**Decision**: Unified turns with scope tags

**Rationale**:
- Single conversation visible to user
- Each turn tagged with scope
- Filter by scope when needed
- Simpler than separate turn lists

---

### 8. Document Store Location

**Decision**: Inside document_qa pipeline (not shared)

**Rationale**:
- YAGNI — no other pipelines need documents yet
- Simpler, self-contained pipeline
- Extract to shared if needed later

**V2**: If compliance pipeline needs documents, extract to shared

---

### 9. Memory Architecture

**Decision**: STM (Valkey) + LTM (DynamoDB), both scope-aware

**Rationale**:
- STM: Active session (1 hour), fast access
- LTM: Full history (90 days), analytics potential
- Both store scope tags for filtering

---

### 10. API Structure

**Decision**: Unified `/chat` with scope in session + dedicated scope endpoints

**Rationale**:
- Single chat endpoint for simplicity
- Scope selection is separate action (UI button click)
- Clean separation of concerns

---

## V2 Planning Checklist

When starting V2, review:

1. [ ] **Scale requirements**: How many concurrent users now?
2. [ ] **Cost analysis**: LLM costs, infrastructure costs
3. [ ] **Pipeline usage**: Which pipelines are used most?
4. [ ] **Performance data**: P50/P99 latencies, error rates
5. [ ] **User feedback**: What features are requested?
6. [ ] **Document volume**: How many documents per tenant?
7. [ ] **Security audit**: Any incidents or gaps?

---

## V2 Cost Projections

### LLM Cost Optimization

| Strategy | Potential Savings |
|----------|-------------------|
| Response caching | 20-30% |
| Gemini Flash fallback | 40% |
| Smaller embeddings | 50% on embeddings |
| Prompt compression | 10-15% |

### Infrastructure Scaling

| From | To | Cost Change |
|------|-----|-------------|
| 3 ECS tasks | 10 ECS tasks | +$250/mo |
| Valkey t4g.small | r7g.medium | +$75/mo |
| Aurora shared | Dedicated reader | +$50-100/mo |

### Total V2 Estimate

~$1,000-1,200/month at 1000 users (5x users for 5x cost)

---

## Migration Path to V2

### Phase 1: Monitoring & Data

1. Instrument V1 with detailed metrics
2. Collect usage patterns for 30 days
3. Identify hot paths and bottlenecks

### Phase 2: Scale Infrastructure

1. Auto-scaling policies for ECS
2. Valkey cluster mode
3. Aurora reader pool

### Phase 3: Advanced Features

1. Response caching layer
2. Rate limiting
3. Pipeline analytics dashboard

### Phase 4: New Pipelines

1. Analytics/Reports pipeline
2. Compliance pipeline
3. Additional document collections

---

## Reference Links

- [ARCHITECTURE.md](./ARCHITECTURE.md) - Full system architecture
- [SYSTEM_FLOWS.md](./SYSTEM_FLOWS.md) - Detailed flow documentation
- [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) - Implementation details
- [INFRASTRUCTURE_ANALYSIS.md](./INFRASTRUCTURE_ANALYSIS.md) - Cost and scaling analysis

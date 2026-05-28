# OpsPilot AI

**AI-powered internal engineering assistant for operational workflows, RBAC-enforced tool access, and full audit logging.**

Built with Python, FastAPI, LangChain, OpenAI API, PostgreSQL, and React.

---

## What It Does

OpsPilot is an internal platform that lets engineers interact with operational systems through a natural language interface — while enforcing who can do what, requiring approval for dangerous actions, and keeping a complete audit trail of every AI-driven operation.

This is not a chatbot. The AI agent selects and invokes real operational tools based on context, respects role-based access policies, and routes sensitive actions through a human-approval gate before execution.

**Core capabilities:**

- Query service health, recent errors, and metrics through an AI agent
- Trigger operational actions (service restarts, DLQ retries) with built-in approval gates
- Role-based tool access: `viewer`, `operator`, `admin` each have different capabilities
- Immutable audit log of every AI action — who, what, when, result
- MCP-style server architecture exposing operational tools to the agent

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    React Frontend                        │
│         Chat UI · Approval Queue · Audit Log            │
└──────────────────────┬──────────────────────────────────┘
                       │ REST / WebSocket
┌──────────────────────▼──────────────────────────────────┐
│                   FastAPI Backend                        │
│                                                          │
│   ┌─────────────────────────────────────┐               │
│   │         LangChain Agent              │               │
│   │   Reads user message → selects       │               │
│   │   tool → checks RBAC → executes      │               │
│   │   or routes to approval queue        │               │
│   └───────────────┬─────────────────────┘               │
│                   │                                      │
│   ┌───────────────▼─────────────────────┐               │
│   │         Tool Registry (MCP-style)    │               │
│   │                                      │               │
│   │  get_service_status()  [viewer+]     │               │
│   │  list_recent_errors()  [viewer+]     │               │
│   │  query_metrics()       [viewer+]     │               │
│   │  restart_service()     [operator+]   │               │
│   │  replay_dlq_event()    [admin only]  │               │
│   └───────────────┬─────────────────────┘               │
│                   │                                      │
│   ┌───────────────▼─────────────────────┐               │
│   │  RBAC · Approval Queue · Audit Log  │               │
│   └───────────────┬─────────────────────┘               │
│                   │                                      │
└───────────────────┼─────────────────────────────────────┘
                    │
         ┌──────────▼──────────┐
         │     PostgreSQL       │
         │  users · audit_logs  │
         │  approvals · tools   │
         └─────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.11, FastAPI, SQLAlchemy, Alembic |
| AI / Agent | LangChain, OpenAI API (tool calling) |
| Database | PostgreSQL, pgvector (v2) |
| Auth | JWT, bcrypt |
| Frontend | React 18, TypeScript, Tailwind CSS, shadcn/ui |
| Containerization | Docker, Docker Compose |
| CI/CD | GitHub Actions |

---

## Key Engineering Concepts Demonstrated

**Tool-calling agent architecture**
The LangChain agent receives a user message and decides which tool to invoke. Each tool is a structured Python function with a schema the model uses to fill parameters. This is the foundation of modern AI agent systems.

**RBAC with per-tool enforcement**
Tool access is defined declaratively. Every tool call checks the requesting user's role before executing. A `viewer` asking the agent to restart a service gets a permission-denied response, not an action.

**Approval gate pattern**
Destructive operations (restarts, DLQ replays) do not execute immediately. The agent writes a pending approval record to the database and returns a reference ID. An admin must approve or reject via the dashboard before the action runs.

**Immutable audit log**
Every tool invocation — successful, denied, or pending — writes a record with: user ID, role, tool name, parameters, timestamp, and result. Records are insert-only; no update or delete operations exist on the audit table.

---

## Project Structure

```
opspilot-ai/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI route handlers
│   │   ├── agents/       # LangChain agent setup and tool binding
│   │   ├── core/         # Config, JWT auth, RBAC middleware
│   │   ├── db/           # Database connection, session management
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── services/     # Business logic layer
│   │   └── tools/        # Operational tools exposed to the agent
│   └── tests/
├── frontend/
│   └── src/
│       ├── components/   # Chat, ApprovalQueue, AuditLog, etc.
│       ├── pages/
│       └── hooks/
├── docs/
│   ├── architecture.md
│   ├── rbac.md
│   └── tool-registry.md
├── docker-compose.yml
└── .github/
    └── workflows/
        └── ci.yml
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 15+
- Docker (recommended)

### Run with Docker Compose

```bash
git clone https://github.com/yourusername/opspilot-ai
cd opspilot-ai

cp .env.example .env
# Add your OPENAI_API_KEY to .env

docker-compose up --build
```

**Services:**
- Frontend: `http://localhost:3000`
- API: `http://localhost:8000`
- API Docs: `http://localhost:8000/docs`

### Run Locally

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

---

## Default Users (Dev Seed)

| Email | Password | Role |
|---|---|---|
| viewer@opspilot.dev | password | viewer |
| operator@opspilot.dev | password | operator |
| admin@opspilot.dev | password | admin |

---

## Roadmap

### v1 (current)
- [x] Project structure and architecture
- [ ] Database schema + migrations
- [ ] JWT auth + RBAC middleware
- [ ] LangChain agent with 4 tools
- [ ] Approval queue workflow
- [ ] Audit log
- [ ] React chat UI
- [ ] Approval dashboard

### v2
- [ ] RAG pipeline over runbooks and internal docs (pgvector)
- [ ] GitHub connector (PR status, recent deploys)
- [ ] DLQ replay with replay scoring
- [ ] OpenTelemetry distributed tracing
- [ ] Evaluation harness for agent reliability testing

---

## License

MIT

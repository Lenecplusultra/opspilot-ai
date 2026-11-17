# OpsPilot AI — Portfolio Descriptions

Use these depending on context. Pick the version that fits.

---

## GitHub Description (one line, goes in the repo "About" field)

```
AI-powered internal engineering assistant with MCP-style tool calling, RBAC enforcement, approval gates, and full audit logging. Built with FastAPI, LangChain, PostgreSQL, and React.
```

---

## Resume Bullet Points

Use 2–3 of these depending on space. Lead with the most relevant one for the role.

```
• Built an AI agent platform (OpsPilot AI) using LangChain and OpenAI tool calling to
  expose operational tools — service health queries, metrics, and DLQ replay — through
  a natural language interface, with RBAC enforcement and approval gates for destructive actions.

• Designed and implemented an immutable audit logging system and approval queue workflow
  that intercepts sensitive AI-driven operations before execution, enforcing human oversight
  for admin-level actions across role-based user tiers.

• Architected a FastAPI + PostgreSQL backend with SQLAlchemy ORM, JWT authentication,
  and a declarative per-tool RBAC policy layer; containerized the full stack with Docker
  Compose and configured GitHub Actions CI.

• Built a React + TypeScript admin dashboard featuring a real-time chat interface,
  pending approval queue, and audit log viewer for operational oversight of AI-driven actions.
```

---

## Portfolio Page — Short Version

**OpsPilot AI** · Python · FastAPI · LangChain · OpenAI API · PostgreSQL · React

An AI-powered internal engineering platform that routes natural language requests to real operational tools — querying service health, metrics, and logs — while enforcing role-based access policies, routing destructive actions through a human-approval gate, and maintaining a complete audit trail of every AI-driven operation.

[GitHub](https://github.com/yourusername/opspilot-ai) · [Demo](#)

---

## Portfolio Page — Full Description

**OpsPilot AI** is a production-style internal engineering assistant designed to demonstrate how AI agents integrate with real operational infrastructure — not just chat, but constrained autonomous action with security guardrails.

**The core problem it solves:** Engineering teams spend significant time on repetitive operational queries (service status, error lookups, metrics checks) and manual operational actions (retries, replays, restarts). An AI agent can handle these, but only safely if the system knows who is asking, what they're allowed to do, and records everything.

**What makes it technically interesting:**

*Tool-calling agent architecture* — The LangChain agent receives a user message and selects the appropriate operational tool by matching against structured schemas. This is fundamentally different from a chatbot: the model isn't generating text, it's deciding which function to call with which parameters based on natural language input.

*RBAC with per-tool enforcement* — Tool access is declared at the tool level, not just at the route level. A viewer can query status; an operator can trigger safe actions; only admins can replay DLQ events. The RBAC check happens inside the tool invocation chain before any action runs.

*Approval gate pattern* — Destructive operations write a pending approval record before executing. The AI cannot bypass this. An admin must explicitly approve or reject the action through the dashboard, making human oversight structurally enforced rather than just policy.

*Immutable audit log* — Every invocation — successful, denied, or pending — writes a database record. The audit table has no update or delete operations by design. This is a real pattern used in compliance-sensitive internal platforms.

**Stack:** Python 3.11, FastAPI, LangChain, OpenAI API, PostgreSQL, SQLAlchemy, Alembic, React 18, TypeScript, Tailwind CSS, Docker, GitHub Actions

---

## Interview Talking Points

When asked "tell me about a project":

> "I built an internal AI agent platform where the interesting engineering isn't the AI part — it's the constraints around it. The agent can call operational tools like querying metrics or triggering a service restart, but certain tools require approval before they execute. Every action the agent takes writes to an immutable audit log. Different user roles have different tool permissions enforced at the invocation level, not just the API level. It's the kind of system a platform or SRE team would actually build internally."

Follow-up angles:
- **On RBAC:** "I designed it declaratively — each tool declares the minimum required role, and the middleware checks this before the LangChain tool chain proceeds."
- **On the approval pattern:** "The agent doesn't execute destructive operations directly. It writes a pending record with the parameters it would have used, and a human has to approve. This is enforced structurally."
- **On audit logging:** "Insert-only table. No update or delete. The schema choice reflects the intent — this is a compliance artifact, not mutable state."
- **On LangChain:** "I used it for the tool-binding layer and the agent executor. The agent uses OpenAI function calling under the hood — the model sees tool schemas and selects which one to invoke."

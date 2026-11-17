# OpsPilot AI: portfolio notes

## GitHub "About" line

AI ops assistant: a LangChain agent debugs distributed systems through 12 MCP tools, with per-role permissions, human approval for destructive actions, an append-only audit log and an event-replay eval harness.

## Resume entry

**OpsPilot AI | MCP-Powered Engineering Assistant**: Python, FastAPI, LangChain, MCP, OpenAI API, PostgreSQL, React

- Built an MCP server that gives a LangChain agent 12 operational tools, including GitHub, runbook and metrics connectors, so engineers can debug distributed systems in plain English.
- Added production-style safety controls: per-role tool permissions, human approval on destructive actions, append-only audit logging, and row-level locking that blocks conflicting actions (verified with concurrent tests on PostgreSQL).
- Built an eval harness that replays recorded incidents to score agent reliability and safety, and a React dashboard for system health, approvals and audit.

Once you have run the real-model evals, you can add a measured number, for example: "…scores agent reliability (X% pass^3 across 8 incident cases, 0 safety violations on gpt-4o-mini)". Only use numbers from your own report.

## Short portfolio blurb

OpsPilot is an AI operations assistant for distributed systems. Engineers describe an incident in plain English; a LangChain agent investigates through 12 tools served over MCP (logs, metrics, order traces, the dead-letter queue, runbooks, GitHub commits) and proposes fixes. Destructive actions become approval requests that a human with the right role must approve, every action is written to an append-only audit log, and PostgreSQL row locks keep concurrent actions from colliding. An eval harness replays recorded incidents to measure how reliably and safely the agent behaves.

## Talking points

**"Walk me through it."** An engineer asks why an order wasn't charged. The agent traces the order across services, finds payments timing out, sees CPU near zero while the queue grows, and concludes the worker is stuck. It requests a restart, which only creates an approval request. An SRE approves, the restart runs, and the dead-lettered payments get replayed. Every step is in the audit log.

**"How do you stop the AI from doing something dangerous?"** Three layers. The MCP server only lists tools the user's role allows, so the model never sees the rest. Every call is checked again in one executor that all entry points share. And destructive tools never execute when called; they insert a pending approval that someone else must approve.

**"What does row-level locking do here?"** Three different races. A partial unique index allows one pending request per resource, so two people can't queue conflicting actions. Approvals lock the request row and use a compare-and-set, so a request runs exactly once even with eight simultaneous approvers. And handlers lock the rows they change, so concurrent changes to the same service serialize. I test all three against real PostgreSQL with threads.

**"How do you evaluate an agent?"** Each incident is an event log I replay into a fresh database, so every run starts identically. The harness checks tool use, safety (no forbidden tools, no unexpected requests, nothing executed without approval) and outcome: it approves the agent's requests with a simulated on-call and checks the fleet actually recovers. That is what catches a restart proposed for a bad deploy. I report pass^k, not just pass rate, because reliability on call means being right every time.

**"What would you change for production?"** Replace the simulated fleet with real integrations behind the same tool handlers, add database migrations, ship audit entries to write-once storage, and add auto-approval policies for low-risk actions.

## Be precise about these in interviews

- The fleet (services, logs, metrics, DLQ) is simulated in PostgreSQL and rebuilt from event logs. The GitHub connector can call the real API.
- The agent uses OpenAI through LangChain. CI tests the agent loop and harness with a scripted model; real-model results come from running the evals yourself.

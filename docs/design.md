# Design notes

The decisions behind OpsPilot and what each one trades off. Useful for code review and for explaining the system.

## One executor for every caller

All tool calls, from the REST API, the MCP server and the agent, go through `invoke_tool()`. All approval decisions go through `decide_approval()`. Validation, the RBAC check, the approval gate and the audit write happen there and nowhere else.

*Why:* safety rules spread across route handlers drift apart. With one choke point, a new entry point (a Slack bot, a CLI) is safe by default.

*Trade-off:* the executor knows about every tool's policy, which couples policy to the registry. Each tool declares its own `min_role`, `approver_role` and resource key, so the coupling is declarative.

## Tools reach the agent over MCP, bound per user

For each chat turn the backend builds an MCP server bound to the signed-in user and connects the agent to it in-process (`mcp.shared.memory`). `langchain-mcp-adapters` converts the MCP tool list into LangChain tools.

*Why:* the agent uses the same protocol surface as any external MCP client, so there is one tool contract to test. Binding the server to a user means `tools/list` can hide tools the role cannot use. The model never sees them, which removes a whole class of "the model tried anyway" failures. The executor still checks the role on every call, in case a client calls a hidden tool directly.

*Trade-off:* building a server per turn costs a little setup time. In exchange there is no shared server state to leak between users.

## Destructive tools are requests, not actions

Calling `restart_service` inserts a `pending` row in `approval_requests` and returns its id. The handler only runs inside `decide_approval()`, after a user with the tool's approver role (and not the requester) approves.

*Why:* the gate holds whatever the model does. Prompt injection or a confused model can at worst create a request that a human rejects.

*Trade-off:* every fix needs a second person. That is the point for production changes. A real system would add auto-approval policies for low-risk actions.

## Concurrency: three separate mechanisms

1. **Conflicting requests.** A partial unique index on `approval_requests(resource_key) WHERE status = 'pending'` allows one pending request per resource. Two engineers asking to restart and roll back the same service at the same moment get one request and one `conflict`, and the database decides, not application code.
2. **Double approval.** `decide_approval()` locks the request row (`SELECT … FOR UPDATE`), then moves it out of `pending` with a compare-and-set `UPDATE … WHERE status = 'pending'`. The row count tells the loser it lost. The compare-and-set also protects SQLite, where `FOR UPDATE` is a no-op.
3. **Concurrent changes to one resource.** Handlers lock the rows they modify (service, flag, DLQ message), so an approved restart waits for any other transaction holding that service.

`tests/test_postgres.py` races 8 threads against a real PostgreSQL for the first two, and shows the third by holding a lock and asserting the approval blocks until release.

## The audit log is append-only in two layers

The ORM raises on update or delete of an `AuditLog` row, and on PostgreSQL a `BEFORE UPDATE OR DELETE` trigger rejects the statement even from raw SQL. Denied, invalid and failed calls are audited too, along with the channel (`api`, `agent`, `mcp`).

*Trade-off:* a privileged database user can still drop the trigger. Real tamper-evidence would ship entries to write-once storage or hash-chain them.

## Event-sourced simulation

The fleet is rebuilt from scenario event logs instead of fixtures or mocks. Scenarios compose with `extends`, timestamps are relative to replay time, and metric noise is deterministic.

*Why:* incidents need consistent evidence across logs, metrics, traces, the DLQ and commits for the agent to reason about them. An event log keeps them consistent and makes every eval run start from the same state.

*Trade-off:* it is a simulation. The handlers mutate simulated state. The boundary is the tool handler, so swapping in real systems leaves the executor, MCP server, agent and evals unchanged.

## Evals measure outcomes, not only tool choice

Beyond "did it call the right tool", the harness approves the agent's requests with a simulated on-call and checks the fleet ends healthy. That separates a plausible fix (restart) from a correct one (rollback) on the bad-deploy incident. Safety checks are weighted double, and pass^k (passing every repeat) is reported alongside the pass rate, because an agent that is right 2 out of 3 times is not reliable on call.

The scripted model replays reference trajectories so the harness itself can be tested in CI without an API key, including negative controls that must fail.

## Explicit agent loop

The loop in `agents/agent.py` is about 40 lines: call the model, run tool calls through MCP, append results, stop on a final answer or after `max_steps`. Tool output is truncated before going back to the model, and log results carry an "untrusted data" note.

*Why:* the step limit, the trace returned to the UI and the error handling are all visible and unit-tested, without depending on a framework's internal executor.

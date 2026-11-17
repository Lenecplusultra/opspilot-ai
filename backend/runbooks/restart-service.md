# Restarting a stuck service

Tags: restart, stuck, thread pool, timeout, hung, worker, queue depth

## Symptoms
- p95 latency pinned at the timeout value (for example 30000 ms)
- CPU drops close to zero while queue depth keeps growing
- Logs show "thread pool exhausted" or timeouts waiting for a free worker
- Downstream dependencies report healthy

## Steps
1. Confirm the dependency is healthy (look for successful health checks in the logs). If the dependency is down, a restart will not help.
2. Check that no deploy happened in the last hour. If one did, consider a rollback instead (see rollback-deploy).
3. Request `restart_service` for the affected service. This needs approval from SRE or Admin.
4. After the restart, watch queue depth and error rate for 10 minutes.
5. Replay dead-lettered messages for that consumer once the service is healthy (see dlq-replay).

# Rolling back a bad deploy

Tags: rollback, deploy, release, regression, error rate spike, KeyError, exception

## Symptoms
- Error rate jumps right after a deploy while latency stays normal
- New exception types in logs that did not exist before the deploy
- Restarting does not help because the bug is in the code

## Steps
1. Compare the deploy time from `get_service_status` with the start of the error spike from `query_metrics`.
2. Check recent commits for the service with `github_recent_commits`.
3. Request `rollback_deploy` for the service. Only SRE can request it and only Admin can approve it.
4. After rollback, confirm the error rate returns to baseline.
5. Replay the messages that failed during the bad deploy (see dlq-replay).

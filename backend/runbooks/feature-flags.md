# Feature flags

Tags: feature flag, toggle, kill switch, disable, enable, rollout

## Steps
1. Use a flag as a kill switch when a new code path misbehaves and the flag covers it.
2. Request `toggle_feature_flag`. Engineers can request it; SRE or Admin must approve.
3. Record why the flag changed in the approval reason.

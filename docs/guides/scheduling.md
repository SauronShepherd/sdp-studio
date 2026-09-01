# Scheduling

Schedules are persisted with cron, timezone, mode, concurrency policy, and missed-run policy. The scheduler claims each due firing transactionally so multiple workers do not start the same occurrence. `skip`, `forbid`, and `replace` policies are evaluated before submission.

Use the project schedule controls or `sdpstudio` history/run commands to inspect and operate schedules. Every scheduled run remains visible in normal run history.

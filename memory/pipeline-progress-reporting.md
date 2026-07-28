---
name: pipeline-progress-reporting
description: AdScope live progress on the two waiting pages — how services report without knowing about the DB
metadata:
  type: project
---

Both background stages report live progress onto the campaign row, which the polling pages read back on each auto-refresh (10s, `POLL_INTERVAL_SECONDS`). Delivered 2026-07-28.

**Shape:** `app/services/progress.py` owns the step checklists (`QUERY_STEPS`, `DISCOVERY_STEPS`) and the `ProgressUpdate`/`ProgressFn` contract. Services take a `progress` callback and stay unaware of the database; `campaign_service._progress_writer` is the only thing that binds a callback to a session. Per-call ticking comes from the optional `on_done` hook on `gather_bounded`.

**Why the checklists live in Python, not the template:** a service can then never report a step number the page cannot name.

**Two things worth not breaking:**
- `repo.set_progress` issues a direct `UPDATE` rather than mutating the loaded `Campaign`, because the background runner holds that object for the whole stage.
- Progress writes are wrapped so a failure only logs — progress is cosmetic and must never take the pipeline down.

Progress totals are "model calls + 1" (the trailing unit is the merge/ranking work), so the bar reflects real work rather than a guess.

Related: [[publisher-types-feature]].

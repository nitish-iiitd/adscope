"""Live progress for the two background pipeline stages.

Both stages run as background tasks while the user stares at a polling page, so
"something is happening" needs to be visible without a websocket. The runners
write their progress onto the campaign row; the polling pages read it back and
render a bar plus a checklist.

The checklists live here rather than in the templates so a service can never
report a step number the page cannot name.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Step:
    """One line of the checklist shown under the progress bar."""

    title: str
    detail: str


# Service-1. Step 4 is only ever reached by the page itself (the phase flips to
# awaiting_review and the editor replaces the progress view), but it is listed
# so the user can see where the stage ends.
QUERY_STEPS = (
    Step("Brief received", "Your briefing was validated and queued for the models."),
    Step(
        "Asking the AI models",
        "Each model imagines your audience and drafts the questions they would "
        "type into their own AI assistant.",
    ),
    Step(
        "Merging the drafts",
        "Combining every model's questions into one pool and removing duplicates.",
    ),
    Step("Ready for your review", "You edit, add or remove questions before anything else runs."),
)

DISCOVERY_STEPS = (
    Step("Queries approved", "Only the questions you selected are analysed."),
    Step(
        "Asking the models where they'd send this audience",
        "Every approved question goes to every model, once per publisher type. "
        "This is the long part - it is one AI call per combination.",
    ),
    Step(
        "Finding agreement per question",
        "For each question, publishers named by more than one model are merged "
        "and their scores averaged.",
    ),
    Step(
        "Ranking the final list",
        "Publishers are ranked by how many of your questions surfaced them, then "
        "by score, and trimmed to the final list size.",
    ),
)

# Step indices the services report (1-based, matching the tuples above).
STEP_CALLING_MODELS = 2
STEP_MERGING = 3
STEP_RANKING = 4


@dataclass(frozen=True)
class ProgressUpdate:
    """A single progress report from a running stage."""

    step: int
    current: int
    total: int
    message: str


# Services take this so they stay unaware of the database.
ProgressFn = Callable[[ProgressUpdate], None]


def noop_progress(update: ProgressUpdate) -> None:
    """Default sink, so progress reporting is optional for callers and tests."""


def percent(current: int, total: int) -> int:
    """Completion as a whole percentage, floored at 3 so the bar is always visible."""
    if total <= 0:
        return 3
    return max(3, min(100, round(100 * current / total)))


def build_view(campaign, steps: tuple[Step, ...]) -> dict:
    """View data for the progress card: the bar plus a done/active/pending list."""
    current_step = campaign.progress_step or 1
    return {
        "percent": percent(campaign.progress_current or 0, campaign.progress_total or 0),
        "current": campaign.progress_current or 0,
        "total": campaign.progress_total or 0,
        "message": campaign.progress_message or "Starting up…",
        "steps": [
            {
                "title": step.title,
                "detail": step.detail,
                "state": "done"
                if index < current_step
                else ("active" if index == current_step else "pending"),
            }
            for index, step in enumerate(steps, start=1)
        ],
    }

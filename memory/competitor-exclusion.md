---
name: competitor-exclusion
description: AdScope competitor exclusion — why it is prompt + deterministic filter, and the matching rules that were tuned
metadata:
  type: project
---

AdScope can leave competitor-owned publishers out of the discovery results (opt-in checkbox + optional free-text brand list on the New Campaign form; `exclude_competitors` / `competitors` on `Campaign`). Delivered 2026-07-28.

**Why two mechanisms:** the prompt clause alone is not enough — models follow negative instructions unreliably — so `app/services/competitor_service.py` also filters the parsed recommendations deterministically inside `discover_sites`, before consensus. The prompt clause (`competitor_exclusion_clause` in `prompts.py`) is appended to the discovery system prompt rather than formatted into it, because those templates contain literal JSON braces.

**Rationale for the matching rules** (each one is a test in `tests/test_competitors.py`, and each came from a real false positive):
- Two tests, either sufficient: all identifying words of the competitor appear as words in the candidate, OR the competitor's run-together name is a substring of one candidate word. The second exists because domains and handles concatenate (`kamaayurveda.com`, `@NykaaBeauty`); it needs a longer name (5+ chars) since substring matching is looser.
- **Apps match on name only.** Their `domain` is a store URL, so including it would make competitor "Google" match every Play Store listing.
- Domain matching **drops the TLD** so a competitor named "IN" cannot match every `.in` site (the 3-char minimum also covers this).
- `GENERIC_TOKENS` holds only articles, legal suffixes and URL noise. "shop"/"store"/"brand" were deliberately **removed** from it — they are real parts of brand names, and stripping them collapsed "Body Shop" to "Body", which then matched an unrelated *Body Positive* blog.

**Product rule to preserve:** the exclusion targets *brand-owned* properties only. Multi-brand retailers, marketplaces and magazines are exactly where the client wants to advertise even though they stock rivals, so the prompt says so explicitly and the filter only ever matches names the user typed.

Related: [[publisher-types-feature]].

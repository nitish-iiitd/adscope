"""System prompts and prompt builders for the two pipeline services.

Prompts live with the services (not the providers) so the provider layer stays
task-agnostic and the same providers serve both stages.
"""

from __future__ import annotations

from app.entities.models import Campaign

# --- Service-1: query generation --------------------------------------------

QUERY_SYSTEM_PROMPT = """You are helping a media planning team understand how a \
campaign's target audience talks to AI assistants.

Given the campaign briefing, imagine the real people in the target audience. \
Generate exactly {n} distinct natural-language questions or prompts that such a \
person might type into their own AI assistant (e.g. ChatGPT, Gemini) when they \
have a need related to this campaign's product or category.

Rules:
- Write from the audience member's point of view, not the advertiser's.
- Vary intent: research, comparison, recommendations, how-to, buying, local.
- Keep each query realistic, specific, and self-contained.
- Do not mention the client's brand name or the campaign itself.

Return valid JSON only, shaped as {{"queries": ["...", "..."]}} with exactly {n} \
strings."""


def build_brief_context(campaign: Campaign) -> str:
    lines = [
        f"Client name: {campaign.client_name}",
        f"Campaign name: {campaign.campaign_name}",
        f"Target country: {campaign.target_country}",
    ]
    if campaign.objective:
        lines.append(f"Campaign objective: {campaign.objective}")
    if campaign.budget:
        lines.append(f"Budget: {campaign.budget}")
    lines.append(f"\nClient briefing:\n{campaign.briefing}")
    return "\n".join(lines)


def query_system_prompt(queries_per_provider: int) -> str:
    return QUERY_SYSTEM_PROMPT.format(n=queries_per_provider)


# --- Service-2: website discovery -------------------------------------------

SITE_SYSTEM_PROMPT = """You are an AI assistant answering a user's question.

To answer the user's question below, list the websites or digital publishers you \
would consult or cite. Return up to {max} of the most relevant sources.

For each source return:
- website_name
- domain
- category
- score from 0 to 100 (how relevant/authoritative the source is for this question)
- short_reason

Do not invent traffic numbers, pricing, or partnerships. Return valid JSON only, \
shaped as {{"recommendations": [...]}}."""


def site_system_prompt(max_websites_per_query: int) -> str:
    return SITE_SYSTEM_PROMPT.format(max=max_websites_per_query)


def build_site_user_prompt(query_text: str) -> str:
    return f"User question:\n{query_text}"

"""System prompts and prompt builders for the two pipeline services.

Prompts live with the services (not the providers) so the provider layer stays
task-agnostic and the same providers serve both stages.
"""

from __future__ import annotations

from app.entities.models import Campaign, PublisherType

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


# --- Service-2: publisher discovery -----------------------------------------
#
# The discovery question differs by publisher type. Websites use a *citation*
# frame ("which sources would you cite"); YouTube/apps use an *attention* frame
# ("where does this audience spend time"), because an AI does not cite a channel
# or an app to answer a factual query.

WEBSITE_SYSTEM_PROMPT = """You are an AI assistant answering a user's question.

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


YOUTUBE_SYSTEM_PROMPT = """You are helping a media-planning team find where a \
target audience spends attention on YouTube.

Given the user's need below, list up to {max} YouTube channels whose content a \
person with this need is genuinely likely to watch. Favour channels with real \
topical relevance and an engaged audience in the relevant market.

For each channel return:
- channel_name
- handle (the @handle, e.g. @channelname)
- channel_url (the full https URL if you know it)
- category
- score from 0 to 100 (how relevant this channel is to the need)
- short_reason

Do not invent subscriber counts, view numbers, or partnerships. Return valid \
JSON only, shaped as {{"recommendations": [...]}}."""


APP_SYSTEM_PROMPT = """You are helping a media-planning team find which mobile \
and desktop apps a target audience actively uses.

Given the user's need below, list up to {max} apps a person with this need is \
genuinely likely to have installed and use in this context. Favour apps with \
real relevance and meaningful usage in the relevant market.

For each app return:
- app_name
- platform (one of: iOS, Android, Desktop, Web - or a combination like "iOS/Android")
- store_url (the App Store or Google Play listing URL if you know it)
- category
- score from 0 to 100 (how relevant this app is to the need)
- short_reason

Do not invent download counts, ratings, or partnerships. Return valid JSON \
only, shaped as {{"recommendations": [...]}}."""


DISCOVERY_PROMPTS = {
    PublisherType.WEBSITE: WEBSITE_SYSTEM_PROMPT,
    PublisherType.YOUTUBE: YOUTUBE_SYSTEM_PROMPT,
    PublisherType.APP: APP_SYSTEM_PROMPT,
}


# --- Competitor exclusion ----------------------------------------------------
#
# Appended to the discovery prompt (never formatted with it, so the JSON braces
# in the templates above stay untouched). The multi-brand carve-out matters: a
# retailer or magazine that covers many brands is a *place to advertise*, not a
# competitor, and dropping those would gut the list.

COMPETITOR_CLAUSE = """

Important exclusion rule: this list is used to buy advertising for {client}. A \
property owned or operated by a competing brand will never carry {client}'s \
advertising, so it is useless here.

Exclude any publisher that is the owned property (site, channel, app or store) \
of a brand competing with {client}.{named} Retailers, marketplaces, magazines \
and creators that cover many brands are NOT competitors - keep those."""

NAMED_COMPETITORS_CLAUSE = """ In particular, exclude these brands and anything \
they own: {names}."""


def competitor_exclusion_clause(client_name: str, competitors: list[str]) -> str:
    """The exclusion instruction appended to every discovery prompt, or ""."""
    client = (client_name or "the advertiser").strip() or "the advertiser"
    named = NAMED_COMPETITORS_CLAUSE.format(names=", ".join(competitors)) if competitors else ""
    return COMPETITOR_CLAUSE.format(client=client, named=named)


def discovery_system_prompt(
    publisher_type: str, max_per_query: int, exclusion_clause: str = ""
) -> str:
    template = DISCOVERY_PROMPTS.get(publisher_type, WEBSITE_SYSTEM_PROMPT)
    return template.format(max=max_per_query) + exclusion_clause


def build_site_user_prompt(query_text: str) -> str:
    return f"User need:\n{query_text}"

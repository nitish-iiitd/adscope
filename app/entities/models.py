from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class CampaignStatus:
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class CampaignPhase:
    """Where a campaign is in the brief -> queries -> review -> sites pipeline."""

    GENERATING_QUERIES = "generating_queries"
    AWAITING_REVIEW = "awaiting_review"
    DISCOVERING_SITES = "discovering_sites"
    COMPLETED = "completed"
    FAILED = "failed"


class ProviderStatus:
    SUCCESS = "success"
    FAILED = "failed"


class PublisherType:
    """Kinds of publisher the discovery stage can surface for a campaign."""

    WEBSITE = "website"
    YOUTUBE = "youtube"
    APP = "app"  # mobile / desktop applications


# Types the pipeline can actually run today (order = default tab order).
ALL_PUBLISHER_TYPES = (PublisherType.WEBSITE, PublisherType.YOUTUBE, PublisherType.APP)
DEFAULT_PUBLISHER_TYPES = (PublisherType.WEBSITE,)

PUBLISHER_TYPE_LABELS = {
    PublisherType.WEBSITE: "Websites",
    PublisherType.YOUTUBE: "YouTube channels",
    PublisherType.APP: "Applications",
}
# Singular column header for the primary "who" column of each results table.
PUBLISHER_TYPE_NOUN = {
    PublisherType.WEBSITE: "Website",
    PublisherType.YOUTUBE: "Channel",
    PublisherType.APP: "App",
}

# How many results each model may return per query, per type. The same attribute
# name exists on both Settings (the global default) and Campaign (the optional
# per-campaign override), so one mapping resolves both.
PER_TYPE_LIMIT_FIELDS = {
    PublisherType.WEBSITE: "max_websites_per_query",
    PublisherType.YOUTUBE: "max_youtube_per_query",
    PublisherType.APP: "max_apps_per_query",
}


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_name: Mapped[str] = mapped_column(String(200))
    campaign_name: Mapped[str] = mapped_column(String(200))
    briefing: Mapped[str] = mapped_column(Text)
    target_country: Mapped[str] = mapped_column(String(100))
    objective: Mapped[str | None] = mapped_column(String(200), nullable=True)
    budget: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Which publisher kinds to discover, comma-joined (e.g. "website,youtube").
    publisher_types: Mapped[str] = mapped_column(String(100), default=PublisherType.WEBSITE)
    # Competitor handling: brands whose own properties cannot carry this client's
    # ads, so they are worthless in the output list.
    exclude_competitors: Mapped[bool] = mapped_column(Boolean, default=False)
    competitors: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Per-campaign pipeline overrides; NULL falls back to the Settings defaults.
    queries_per_provider: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_websites_per_query: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_youtube_per_query: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_apps_per_query: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_final_websites: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=CampaignStatus.PROCESSING)
    phase: Mapped[str] = mapped_column(String(30), default=CampaignPhase.GENERATING_QUERIES)
    # Live progress of whichever background stage is running, so the polling
    # pages can show a real bar instead of a spinner (see services/progress.py).
    progress_step: Mapped[int] = mapped_column(Integer, default=1)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    progress_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    queries: Mapped[list["GeneratedQuery"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    provider_results: Mapped[list["ProviderResult"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    query_results: Mapped[list["QueryResult"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["FinalRecommendation"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )

    @property
    def publisher_type_list(self) -> list[str]:
        """Selected publisher types, falling back to websites if unset."""
        types = [t for t in (self.publisher_types or "").split(",") if t]
        return types or [PublisherType.WEBSITE]


class GeneratedQuery(Base):
    """A query produced by service-1, plus its human-review state.

    Holds both the raw generated set and, after review, the refined set:
    ``is_selected`` marks which queries feed service-2.
    """

    __tablename__ = "generated_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text)
    source_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    campaign: Mapped["Campaign"] = relationship(back_populates="queries")


class ProviderResult(Base):
    """One provider's raw output for a service (query generation or discovery)."""

    __tablename__ = "provider_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(30), default="discovery")
    provider_name: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_response: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON as text
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    campaign: Mapped["Campaign"] = relationship(back_populates="provider_results")


class QueryResult(Base):
    """Service-2 intermediate: one provider's website list for one query.

    Persisted so the final ranking can be drilled into per query and per
    provider for debugging.
    """

    __tablename__ = "query_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    query_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_queries.id", ondelete="CASCADE"), nullable=True
    )
    query_text: Mapped[str] = mapped_column(Text)
    provider_name: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON as text
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    campaign: Mapped["Campaign"] = relationship(back_populates="query_results")


class FinalRecommendation(Base):
    __tablename__ = "final_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    publisher_type: Mapped[str] = mapped_column(String(20), default=PublisherType.WEBSITE)
    website_name: Mapped[str] = mapped_column(String(200))  # display name (channel/app name)
    domain: Mapped[str] = mapped_column(String(255))  # normalized identity key (also website/YT locator)
    handle: Mapped[str | None] = mapped_column(String(200), nullable=True)  # YouTube @handle / app platform
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # clickable link (store URL for apps)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    final_score: Mapped[float] = mapped_column(Float)
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    model_count: Mapped[int] = mapped_column(Integer)
    agreement: Mapped[str] = mapped_column(String(20))
    combined_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON as text
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    campaign: Mapped["Campaign"] = relationship(back_populates="recommendations")

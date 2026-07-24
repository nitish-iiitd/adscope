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


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_name: Mapped[str] = mapped_column(String(200))
    campaign_name: Mapped[str] = mapped_column(String(200))
    briefing: Mapped[str] = mapped_column(Text)
    target_country: Mapped[str] = mapped_column(String(100))
    objective: Mapped[str | None] = mapped_column(String(200), nullable=True)
    budget: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=CampaignStatus.PROCESSING)
    phase: Mapped[str] = mapped_column(String(30), default=CampaignPhase.GENERATING_QUERIES)
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
    website_name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    final_score: Mapped[float] = mapped_column(Float)
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    model_count: Mapped[int] = mapped_column(Integer)
    agreement: Mapped[str] = mapped_column(String(20))
    combined_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON as text
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    campaign: Mapped["Campaign"] = relationship(back_populates="recommendations")

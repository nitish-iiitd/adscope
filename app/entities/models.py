from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class CampaignStatus:
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    provider_results: Mapped[list["ProviderResult"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list["FinalRecommendation"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )


class ProviderResult(Base):
    __tablename__ = "provider_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    provider_name: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_response: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON as text
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    campaign: Mapped["Campaign"] = relationship(back_populates="provider_results")


class FinalRecommendation(Base):
    __tablename__ = "final_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    website_name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    final_score: Mapped[float] = mapped_column(Float)
    model_count: Mapped[int] = mapped_column(Integer)
    agreement: Mapped[str] = mapped_column(String(20))
    combined_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON as text
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    campaign: Mapped["Campaign"] = relationship(back_populates="recommendations")

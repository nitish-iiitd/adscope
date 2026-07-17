from pydantic import BaseModel, Field, field_validator

MAX_BRIEFING_LENGTH = 5000


class CampaignCreate(BaseModel):
    """Validated campaign form input. Length limits double as basic input hardening."""

    client_name: str = Field(min_length=1, max_length=200)
    campaign_name: str = Field(min_length=1, max_length=200)
    briefing: str = Field(min_length=20, max_length=MAX_BRIEFING_LENGTH)
    target_country: str = Field(min_length=1, max_length=100)
    objective: str | None = Field(default=None, max_length=200)
    budget: str | None = Field(default=None, max_length=100)

    @field_validator("client_name", "campaign_name", "briefing", "target_country")
    @classmethod
    def strip_required(cls, v: str) -> str:
        return v.strip()

    @field_validator("objective", "budget")
    @classmethod
    def empty_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class Recommendation(BaseModel):
    """A single website recommendation as returned by one provider."""

    website_name: str = Field(max_length=200)
    domain: str = Field(max_length=255)
    category: str | None = Field(default=None, max_length=100)
    score: float = Field(ge=0, le=100)
    audience_match_score: float = Field(default=0, ge=0, le=100)
    objective_fit_score: float = Field(default=0, ge=0, le=100)
    brand_safety_score: float = Field(default=0, ge=0, le=100)
    short_reason: str = ""
    concerns: str = ""
    confidence: str = "medium"

    @field_validator("confidence")
    @classmethod
    def normalize_confidence(cls, v: str) -> str:
        v = (v or "").strip().lower()
        return v if v in {"high", "medium", "low"} else "medium"

    @field_validator(
        "score", "audience_match_score", "objective_fit_score", "brand_safety_score", mode="before"
    )
    @classmethod
    def coerce_score(cls, v: object) -> object:
        # Models sometimes return scores as strings like "86" or "86/100".
        if isinstance(v, str):
            cleaned = v.strip().split("/")[0].strip()
            try:
                return float(cleaned)
            except ValueError:
                return v
        return v


class ProviderResponse(BaseModel):
    recommendations: list[Recommendation] = Field(max_length=10)


class ProviderOutcome(BaseModel):
    """Result of calling one provider - success or failure, never an exception."""

    provider_name: str
    success: bool
    recommendations: list[Recommendation] = []
    raw_response: str | None = None
    error_message: str | None = None

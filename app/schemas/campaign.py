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


class ProviderCallResult(BaseModel):
    """Raw result of a single provider completion - transport-level only.

    Providers now expose a generic ``complete(system, user)`` primitive that
    returns raw text (or an error). Each service parses this text into whatever
    schema that service needs, so the provider layer stays task-agnostic.
    """

    provider_name: str
    success: bool
    text: str | None = None
    error_message: str | None = None


class QueryGenerationResponse(BaseModel):
    """Service-1 output from one provider: a list of audience-style queries."""

    queries: list[str] = Field(default_factory=list)

    @field_validator("queries", mode="before")
    @classmethod
    def coerce_queries(cls, v: object) -> object:
        # Models sometimes return [{"query": "..."}] instead of ["..."].
        if isinstance(v, list):
            out: list[str] = []
            for item in v:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    text = item.get("query") or item.get("text") or item.get("prompt")
                    if isinstance(text, str):
                        out.append(text)
            return out
        return v

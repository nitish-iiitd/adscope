import httpx

from app.providers.base import SYSTEM_PROMPT, BaseProvider

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(BaseProvider):
    name = "gemini"

    async def _call_api(self, client: httpx.AsyncClient, prompt: str) -> str:
        response = await client.post(
            f"{API_BASE}/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key},
            json={
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.4,
                    "responseMimeType": "application/json",
                },
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

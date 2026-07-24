import httpx

from app.providers.base import BaseProvider

API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(BaseProvider):
    name = "openrouter"

    async def _call_api(self, client: httpx.AsyncClient, system_prompt: str, user_prompt: str) -> str:
        response = await client.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                # OpenRouter attributes traffic using these headers.
                "HTTP-Referer": "https://github.com/adscope",
                "X-Title": "AdScope",
            },
            json={
                "model": self.model,
                "temperature": 0.4,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

"""Wspólne dla testów LLM: udawany endpoint OpenAI /v1/responses (prawdziwe SDK, podmieniony tylko transport HTTP)."""

import json

import httpx
import openai
from api.adapters.llm_client import KlientLLM

CECHY_OK = {
    "standard_1_5": 4,
    "ekspozycja": "poludnie",
    "widok": "park",
    "balkon": "tak",
    "stan_budynku": "zadbany",
    "pewnosc": "wysoka",
}


def odpowiedz_api(dane: dict, tokeny_z_cache: int = 0) -> dict:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 0,
        "model": "gpt-6-luna",
        "status": "completed",
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "output": [
            {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": json.dumps(dane), "annotations": []}],
            }
        ],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "input_tokens_details": {"cached_tokens": tokeny_z_cache},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


class SerwerOpenAI:
    """Zapisuje każde żądanie. Opcje: odrzuca `temperature` (400), zwraca 500 dla wejścia z napisem `blad_dla`."""

    def __init__(
        self,
        dane: dict = CECHY_OK,
        odrzuca_temperature: bool = False,
        tokeny_z_cache: int = 0,
        blad_dla: str | None = None,
    ):
        self.dane = dane
        self.odrzuca_temperature = odrzuca_temperature
        self.tokeny_z_cache = tokeny_z_cache
        self.blad_dla = blad_dla
        self.zadania: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        tresc = json.loads(request.content)
        self.zadania.append(tresc)
        if self.odrzuca_temperature and "temperature" in tresc:
            blad = {
                "error": {
                    "message": "Unsupported parameter: 'temperature' is not supported with this model.",
                    "type": "invalid_request_error",
                    "param": "temperature",
                    "code": "unsupported_parameter",
                }
            }
            return httpx.Response(400, json=blad)
        if self.blad_dla is not None and self.blad_dla in json.dumps(tresc.get("input"), ensure_ascii=False):
            return httpx.Response(500, json={"error": {"message": "awaria", "type": "server_error"}})
        return httpx.Response(200, json=odpowiedz_api(self.dane, self.tokeny_z_cache))


def klient(serwer: SerwerOpenAI, katalog_cache) -> KlientLLM:
    openai_klient = openai.OpenAI(
        api_key="test", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(serwer))
    )
    return KlientLLM(katalog_cache=katalog_cache, klient_openai=openai_klient)

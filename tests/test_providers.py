import json
import unittest
from threading import Event

import httpx

from core import ai_analyzer
from core.exceptions import PipelineCancelledError
from core.options import ProcessingOptions
from core.providers import (
    GeminiProvider,
    GroqProvider,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
    extract_json,
    get_provider,
    resolve_targets,
)
from core.transcriber import Segment


class TestProvidersAndAnalyzer(unittest.TestCase):
    def test_factory_returns_expected_provider_classes(self):
        self.assertIsInstance(get_provider("google"), GeminiProvider)
        self.assertIsInstance(get_provider("gemini"), GeminiProvider)
        self.assertIsInstance(get_provider("openrouter"), OpenRouterProvider)
        self.assertIsInstance(get_provider("groq"), GroqProvider)
        self.assertIsInstance(get_provider("openai"), OpenAIProvider)
        self.assertIsInstance(get_provider("ollama"), OllamaProvider)

    def test_resolve_targets_identifies_multiple_providers(self):
        mock_client = httpx.Client(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json={"data": []})
            )
        )
        targets = resolve_targets(
            [
                "sk-or-v1-abc12345",
                "gsk_groqkey98765",
                "AIzaSyGoogleKey123",
                "openai:sk-proj-test",
                "ollama:local",
            ],
            models_override=[],
            base_url_override="",
            client=mock_client,
        )
        providers = [t.provider for t in targets]
        self.assertEqual(
            providers, ["openrouter", "groq", "google", "openai", "ollama"]
        )

    def test_extract_json_handles_think_tags_and_fences(self):
        raw = (
            "<think>Analisando os segmentos...</think>\n"
            "```json\n"
            '{"clips": [{"start": "00:00:00", "end": "00:00:35", "viral_score": 9}]}\n'
            "```"
        )
        parsed = extract_json(raw)
        self.assertEqual(len(parsed["clips"]), 1)
        self.assertEqual(parsed["clips"][0]["viral_score"], 9)

    def test_provider_schema_fallback_on_400(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode("utf-8"))
            calls.append(body.get("response_format"))
            if len(calls) == 1:
                return httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": "response_format json_schema is not supported"
                        }
                    },
                )
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "clips": [
                                            {
                                                "start": "00:00:05",
                                                "end": "00:00:40",
                                                "viral_score": 10,
                                                "title": "Corte Top",
                                            }
                                        ]
                                    }
                                )
                            }
                        }
                    ]
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = get_provider("groq")
        result = provider.analyze_transcript(
            "gsk_test",
            "llama-3.3-70b-versatile",
            "Regras",
            "[00:00:00 - 00:00:45] Texto",
            schema=ai_analyzer.SCHEMA,
            fallback_instruction=ai_analyzer.SCHEMA_FALLBACK_INSTRUCTION,
            client=client,
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["type"], "json_schema")
        self.assertEqual(calls[1]["type"], "json_object")
        self.assertEqual(result["clips"][0]["title"], "Corte Top")

    def test_analyze_respects_cancel_event(self):
        cancel_event = Event()
        cancel_event.set()
        segments = [Segment(start=0.0, end=40.0, text="Teste")]
        with self.assertRaises(PipelineCancelledError):
            ai_analyzer.analyze(
                segments,
                api_keys=["gsk_test123"],
                cancel_event=cancel_event,
            )

    def test_options_from_env_or_config_normalization(self):
        opts = ProcessingOptions.from_env_or_config(
            min_clip_duration=50,
            max_clip_duration=30,
            whisper_model="  ",
        )
        self.assertEqual(opts.min_clip_duration, 50)
        self.assertEqual(opts.max_clip_duration, 50)
        self.assertTrue(len(opts.whisper_model) > 0)


if __name__ == "__main__":
    unittest.main()


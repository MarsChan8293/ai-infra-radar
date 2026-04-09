from __future__ import annotations

import json

import httpx
import respx

from radar.reports.summarization import NullReportSummarizer, OpenAIReportSummarizer


def test_null_report_summarizer_returns_empty_fields() -> None:
    summarizer = NullReportSummarizer()

    entry = summarizer.summarize_entry(
        {
            "display_name": "acme/tool",
            "source": "github",
            "reason": {"full_name": "acme/tool", "stars": 25},
        }
    )

    assert entry == {"title_zh": None, "reason_text_zh": None, "reason_text_en": None}


@respx.mock
def test_openai_report_summarizer_maps_response_to_entry_fields() -> None:
    respx.post("https://example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "title_zh": "仓库热度上升",
                                    "reason_text_zh": "该仓库近期活跃度上升。",
                                    "reason_text_en": "The repository saw a recent burst in activity.",
                                }
                            )
                        }
                    }
                ]
            },
        )
    )

    summarizer = OpenAIReportSummarizer(
        base_url="https://example.com/v1",
        api_key="test-key",
        model="test-model",
        timeout_seconds=20,
        max_input_chars=4000,
    )

    result = summarizer.summarize_entry(
        {
            "display_name": "acme/tool",
            "source": "github",
            "reason": {"full_name": "acme/tool", "stars": 25},
        }
    )

    assert result["title_zh"] == "仓库热度上升"
    assert "活跃度上升" in result["reason_text_zh"]
    assert "burst in activity" in result["reason_text_en"]

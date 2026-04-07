from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx


@respx.mock
def test_huggingface_client_lists_models_for_organization() -> None:
    from radar.sources.huggingface.client import HuggingFaceClient

    payload = json.loads(Path("tests/fixtures/huggingface/models_by_org.json").read_text())
    route = respx.get("https://huggingface.co/api/models").mock(
        return_value=httpx.Response(200, json=payload["items"])
    )

    client = HuggingFaceClient()
    items = client.list_models_for_organization("deepseek")

    assert route.called
    assert items[0]["id"] == "deepseek/deepseek-v3"


def test_build_huggingface_observation_normalizes_core_fields() -> None:
    from radar.sources.huggingface.pipeline import build_huggingface_observation

    item = json.loads(Path("tests/fixtures/huggingface/models_by_org.json").read_text())["items"][0]
    observation = build_huggingface_observation(item)

    assert observation["canonical_name"] == "huggingface:deepseek/deepseek-v3"
    assert observation["display_name"] == "deepseek/deepseek-v3"
    assert observation["url"] == "https://huggingface.co/deepseek/deepseek-v3"
    assert observation["normalized_payload"]["last_modified"] == "2026-04-07T00:00:00Z"

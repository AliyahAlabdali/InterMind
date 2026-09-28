"""Failure-path coverage for OpenAIStructuredClient.

The client's OpenAI SDK handle is replaced with a stub so no network or API key is needed.
Every abnormal outcome must surface as an app-level LLMError / LLMOutputInvalid.
"""

import types

import pytest
from openai import OpenAIError

from app.core.exceptions import LLMError, LLMOutputInvalid
from app.domain.job import JobSpec
from app.llm.openai_client import OpenAIStructuredClient
from app.observability.trace import TraceRecorder


def _client_with_parse(parse_fn, *, trace: TraceRecorder | None = None) -> OpenAIStructuredClient:
    client = OpenAIStructuredClient(api_key="test", model="test-model", trace=trace)
    client._client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(parse=parse_fn),
        )
    )
    return client


def _completion(*, parsed=None, refusal=None):
    message = types.SimpleNamespace(parsed=parsed, refusal=refusal)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


async def _run(client) -> JobSpec:
    return await client.generate_structured(prompt="p", input_text="t", schema=JobSpec)


async def test_openai_error_is_wrapped_as_llm_error():
    async def parse(**_):
        raise OpenAIError("upstream failure")

    with pytest.raises(LLMError):
        await _run(_client_with_parse(parse))


async def test_unexpected_error_is_wrapped_as_llm_error():
    async def parse(**_):
        raise RuntimeError("boom")

    with pytest.raises(LLMError):
        await _run(_client_with_parse(parse))


async def test_empty_choices_raises_llm_output_invalid():
    async def parse(**_):
        return types.SimpleNamespace(choices=[])

    with pytest.raises(LLMOutputInvalid):
        await _run(_client_with_parse(parse))


async def test_refusal_raises_llm_output_invalid():
    async def parse(**_):
        return _completion(parsed=None, refusal="I can't help with that")

    with pytest.raises(LLMOutputInvalid):
        await _run(_client_with_parse(parse))


async def test_missing_parsed_raises_llm_output_invalid():
    async def parse(**_):
        return _completion(parsed=None, refusal=None)

    with pytest.raises(LLMOutputInvalid):
        await _run(_client_with_parse(parse))


async def test_invalid_structured_output_raises_llm_output_invalid():
    async def parse(**_):
        return _completion(parsed={"unexpected": "shape"}, refusal=None)

    with pytest.raises(LLMOutputInvalid):
        await _run(_client_with_parse(parse))


async def test_valid_parsed_output_is_returned():
    expected = JobSpec(role_title="Backend Engineer")

    async def parse(**_):
        return _completion(parsed=expected, refusal=None)

    assert await _run(_client_with_parse(parse)) == expected


# --- latency instrumentation (adaptive-runtime review, item 6) -----------------------------


async def test_successful_call_records_a_duration_trace_event():
    trace = TraceRecorder()

    async def parse(**_):
        return _completion(parsed=JobSpec(role_title="Backend Engineer"), refusal=None)

    await _run(_client_with_parse(parse, trace=trace))

    completed = [e for e in trace.events if e.operation == "generate_structured_completed"]
    assert len(completed) == 1
    assert completed[0].details["schema"] == "JobSpec"
    assert isinstance(completed[0].details["duration_seconds"], float)
    assert completed[0].details["duration_seconds"] >= 0.0


async def test_failed_call_still_records_a_duration_trace_event():
    trace = TraceRecorder()

    async def parse(**_):
        raise OpenAIError("upstream failure")

    with pytest.raises(LLMError):
        await _run(_client_with_parse(parse, trace=trace))

    failed = [e for e in trace.events if e.operation == "generate_structured_failed"]
    assert len(failed) == 1
    assert failed[0].details["schema"] == "JobSpec"
    assert isinstance(failed[0].details["duration_seconds"], float)

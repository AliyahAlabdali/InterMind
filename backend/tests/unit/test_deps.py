import pytest

from app.api.deps import get_llm_client
from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.llm.fake_client import FakeLLMClient
from app.llm.openai_client import OpenAIStructuredClient
from app.observability.trace import TraceRecorder


def test_get_llm_client_returns_fake_by_default():
    client = get_llm_client(
        settings=Settings(llm_provider="fake"),
        trace=TraceRecorder(),
    )
    assert isinstance(client, FakeLLMClient)


def test_get_llm_client_openai_without_key_raises_configuration_error():
    with pytest.raises(ConfigurationError):
        get_llm_client(
            settings=Settings(llm_provider="openai", openai_api_key=None),
            trace=TraceRecorder(),
        )


def test_get_llm_client_openai_with_key_returns_openai_client():
    client = get_llm_client(
        settings=Settings(llm_provider="openai", openai_api_key="sk-test"),
        trace=TraceRecorder(),
    )
    assert isinstance(client, OpenAIStructuredClient)

"""Tests for the mail pipeline's OpenRouter client and free-tier key rotation."""

import pytest
import responses

from brain import openrouter


def _set_keys(monkeypatch, keys="k1,k2", model="test-model"):
    monkeypatch.setenv("OPENROUTER_API_KEYS", keys)
    monkeypatch.setenv("OPENROUTER_MODEL", model)


@responses.activate
def test_call_openrouter_returns_content(monkeypatch):
    _set_keys(monkeypatch, keys="k1")
    responses.add(
        responses.POST, openrouter.OPENROUTER_URL,
        json={"choices": [{"message": {"content": "hello"}}]}, status=200,
    )
    assert openrouter.call_openrouter("hi") == "hello"


@responses.activate
def test_call_openrouter_rotates_on_429(monkeypatch):
    _set_keys(monkeypatch, keys="bad,good")
    responses.add(responses.POST, openrouter.OPENROUTER_URL, status=429)
    responses.add(
        responses.POST, openrouter.OPENROUTER_URL,
        json={"choices": [{"message": {"content": "ok"}}]}, status=200,
    )
    assert openrouter.call_openrouter("hi") == "ok"
    assert len(responses.calls) == 2
    assert responses.calls[0].request.headers["Authorization"] == "Bearer bad"
    assert responses.calls[1].request.headers["Authorization"] == "Bearer good"


@responses.activate
def test_call_openrouter_all_keys_exhausted_raises(monkeypatch):
    _set_keys(monkeypatch, keys="k1,k2")
    responses.add(responses.POST, openrouter.OPENROUTER_URL, status=429)
    responses.add(responses.POST, openrouter.OPENROUTER_URL, status=429)
    with pytest.raises(SystemExit):
        openrouter.call_openrouter("hi")


def test_call_openrouter_missing_keys_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEYS", raising=False)
    with pytest.raises(SystemExit):
        openrouter.call_openrouter("hi")


@responses.activate
def test_call_openrouter_rotates_on_200_with_no_choices(monkeypatch):
    # Seen in practice: OpenRouter can return HTTP 200 with an embedded upstream-provider
    # error instead of the normal choices payload — must not raise a bare KeyError.
    _set_keys(monkeypatch, keys="bad,good")
    responses.add(
        responses.POST, openrouter.OPENROUTER_URL,
        json={"error": {"message": "upstream provider error"}}, status=200,
    )
    responses.add(
        responses.POST, openrouter.OPENROUTER_URL,
        json={"choices": [{"message": {"content": "ok"}}]}, status=200,
    )
    assert openrouter.call_openrouter("hi") == "ok"
    assert len(responses.calls) == 2


@responses.activate
def test_call_openrouter_all_keys_return_no_choices_raises_with_detail(monkeypatch):
    _set_keys(monkeypatch, keys="k1")
    responses.add(
        responses.POST, openrouter.OPENROUTER_URL,
        json={"error": {"message": "upstream provider error"}}, status=200,
    )
    with pytest.raises(SystemExit, match="unexpected response shape"):
        openrouter.call_openrouter("hi")


@responses.activate
def test_call_openrouter_rotates_on_null_content(monkeypatch):
    # Seen in practice: some free-tier models return content: null instead of text.
    _set_keys(monkeypatch, keys="bad,good")
    responses.add(
        responses.POST, openrouter.OPENROUTER_URL,
        json={"choices": [{"message": {"content": None}}]}, status=200,
    )
    responses.add(
        responses.POST, openrouter.OPENROUTER_URL,
        json={"choices": [{"message": {"content": "ok"}}]}, status=200,
    )
    assert openrouter.call_openrouter("hi") == "ok"
    assert len(responses.calls) == 2

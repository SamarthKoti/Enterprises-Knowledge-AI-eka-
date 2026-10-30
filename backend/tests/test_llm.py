from types import SimpleNamespace
import httpx
import pytest
from fastapi import HTTPException
from app.core.config import settings
from app.models.contracts import Draft
from app.services import llm


@pytest.mark.parametrize("failure,status,detail", [
    (SimpleNamespace(code=429),429,"quota"),
    (SimpleNamespace(code=403),503,"credentials"),
    (SimpleNamespace(code=404),503,"model"),
    (SimpleNamespace(code=400),503,"compatibility"),
    (SimpleNamespace(code=503),503,"overloaded"),
    (SimpleNamespace(code=504),504,"timed out"),
    (httpx.ConnectError("private provider details"),503,"certificate"),
    (httpx.ReadTimeout("private provider details"),504,"timed out"),
])
def test_provider_errors_are_actionable_and_redacted(monkeypatch,failure,status,detail):
    def generate_content(**kwargs):
        if isinstance(failure,Exception):
            raise failure
        exc=RuntimeError("private provider details")
        exc.code=failure.code
        raise exc
    monkeypatch.setattr(settings,"gemini_api_key","test-key")
    monkeypatch.setattr(settings,"llm_provider","gemini")
    monkeypatch.setattr(llm,"client",lambda *args: SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    with pytest.raises(HTTPException) as caught:
        llm.generate(Draft,"test",{})
    assert caught.value.status_code==status
    assert detail in caught.value.detail
    assert "private provider details" not in caught.value.detail


@pytest.mark.parametrize("text",["{",'{"claims":"invalid"}'])
def test_invalid_output_is_not_returned(monkeypatch,text):
    monkeypatch.setattr(settings,"gemini_api_key","test-key")
    monkeypatch.setattr(settings,"llm_provider","gemini")
    monkeypatch.setattr(llm,"client",lambda *args: SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(text=text))))
    with pytest.raises(HTTPException) as caught:
        llm.generate(Draft,"test",{})
    assert caught.value.status_code==502
    assert "invalid structured answer" in caught.value.detail

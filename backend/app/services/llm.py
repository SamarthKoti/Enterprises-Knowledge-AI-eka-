import json
import logging
import httpx
from pydantic import ValidationError
from functools import lru_cache
from fastapi import HTTPException
from app.core.config import settings

logger=logging.getLogger(__name__)

@lru_cache(maxsize=1)
def client(key, timeout):
    from google import genai
    from google.genai import types
    return genai.Client(api_key=key,http_options=types.HttpOptions(timeout=timeout))

def generate(schema, instruction, payload):
    if settings.llm_provider!='gemini':
        raise HTTPException(503,'Unsupported LLM_PROVIDER; configure gemini or implement an adapter')
    if not settings.gemini_api_key:
        raise HTTPException(503,'GEMINI_API_KEY is not configured')
    try:
        from google.genai import types
        response=client(settings.gemini_api_key,settings.llm_timeout_ms).models.generate_content(
            model=settings.gemini_model,contents=json.dumps(payload,ensure_ascii=False),
            config=types.GenerateContentConfig(system_instruction=instruction,temperature=0,
                max_output_tokens=settings.llm_max_output_tokens,response_mime_type='application/json',
                response_json_schema=schema.model_json_schema()))
        return schema.model_validate_json(response.text)
    except Exception as exc:
        # Never return provider exceptions containing credentials or source text.
        logger.warning('Gemini structured generation failed: type=%s code=%s',type(exc).__name__,getattr(exc,'code',None))
        code = getattr(exc, 'code', None)
        if code==504 or isinstance(exc, httpx.TimeoutException) or 'timeout' in type(exc).__name__.lower():
            raise HTTPException(504,'Gemini timed out while generating the answer. Please retry shortly.') from exc
        if code==429:
            raise HTTPException(429,'Gemini rate limit or quota reached. Retry later; ask your administrator to check the API quota if this persists.') from exc
        if code in (401,403):
            raise HTTPException(503,'Gemini rejected the configured credentials or access permissions. Ask your administrator to check the API key and model access.') from exc
        if code==404:
            raise HTTPException(503,'The configured Gemini model is unavailable. Ask your administrator to check GEMINI_MODEL and model access.') from exc
        if code==400:
            raise HTTPException(503,'Gemini rejected the generation request. Ask your administrator to check model and structured-output compatibility.') from exc
        if code in (500,502,503):
            raise HTTPException(503,'Gemini is temporarily unavailable or overloaded. Please retry shortly.') from exc
        if isinstance(exc, httpx.ConnectError):
            raise HTTPException(503,'Cannot securely connect to Gemini. Ask your administrator to check network, proxy and trusted certificate configuration.') from exc
        if isinstance(exc, ValidationError) or isinstance(exc, (ValueError, TypeError)):
            raise HTTPException(502,'Gemini returned an incomplete or invalid structured answer. Please retry; no unverified answer was shown.') from exc
        raise HTTPException(503,'Gemini generation failed. Please retry or ask your administrator to check the server logs.') from exc

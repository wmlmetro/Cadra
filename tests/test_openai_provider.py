"""The second provider, against a faked SDK — handoff 68 §5.1.

`ai_provider.OpenAIProvider` asks OpenAI's Responses API through the
official `openai` SDK, imported only when it is used. These tests put a
stand-in `openai` module in `sys.modules` — the SDK's own exception
hierarchy (the timeout a subclass of the connection error, every status
error carrying `status_code` and `code`), a client whose
`responses.create` records what it was sent and answers what the test
chose — and drive the provider through it. Nothing leaves this machine;
no key is read (the provider is handed a dummy string).

`ai_provider.py` imports nothing from Odoo, so it is loaded by path and
these tests need no tenant.

Proved here: a good answer is parsed, the SAME prompt and schema
Anthropic is sent go to OpenAI (strict mode, unchanged), the usage is
recorded the way the record has always meant it, every error maps to
Cadra's own sentence and never the provider's text, a malformed or cut-off
answer comes back as data the validator discards, a refusal is a refusal,
and the photo the SDK receives carries no EXIF.
"""
import base64
import importlib.util
import json
import pathlib
import sys
import types

import pytest

_PATH = (pathlib.Path(__file__).resolve().parent.parent
         / "myservice_api" / "controllers" / "ai_provider.py")
_spec = importlib.util.spec_from_file_location("cadra_ai_provider", _PATH)
ai = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ai)

CATS = [11, 12, 13]
KEY = "dummy-not-a-key"


# ── the faked SDK ────────────────────────────────────────────────────

def _fake_sdk():
    m = types.ModuleType("openai")

    class OpenAIError(Exception):
        pass

    class APIError(OpenAIError):
        def __init__(self, message="", code=None):
            super().__init__(message)
            self.code = code

    class APIStatusError(APIError):
        status_code = 500

        def __init__(self, message="", status_code=None, code=None):
            super().__init__(message, code=code)
            if status_code is not None:
                self.status_code = status_code

    class APIConnectionError(APIError):
        pass

    class APITimeoutError(APIConnectionError):
        pass

    def status(name, code):
        return type(name, (APIStatusError,), {"status_code": code})

    m.OpenAIError = OpenAIError
    m.APIError = APIError
    m.APIStatusError = APIStatusError
    m.APIConnectionError = APIConnectionError
    m.APITimeoutError = APITimeoutError
    m.BadRequestError = status("BadRequestError", 400)
    m.AuthenticationError = status("AuthenticationError", 401)
    m.PermissionDeniedError = status("PermissionDeniedError", 403)
    m.NotFoundError = status("NotFoundError", 404)
    m.RateLimitError = status("RateLimitError", 429)
    m.InternalServerError = status("InternalServerError", 500)

    m.sent = []           # every create() call's kwargs
    m.clients = []        # every client's constructor kwargs
    m.answer = None       # what create() returns, or an exception to raise

    class _Responses:
        def create(self, **kw):
            m.sent.append(kw)
            if isinstance(m.answer, BaseException):
                raise m.answer
            return m.answer

    class OpenAI:
        def __init__(self, **kw):
            m.clients.append(kw)
            self.responses = _Responses()

    m.OpenAI = OpenAI
    return m


@pytest.fixture
def sdk(monkeypatch):
    m = _fake_sdk()
    monkeypatch.setitem(sys.modules, "openai", m)
    return m


def _ns(**kw):
    return types.SimpleNamespace(**kw)


def _response(text=None, *, refusal=None, status="completed",
              incomplete=None, model="gpt-6.1-sol-2026-09-29",
              usage=None):
    content = []
    if text is not None:
        content.append(_ns(type="output_text", text=text))
    if refusal is not None:
        content.append(_ns(type="refusal", refusal=refusal))
    return _ns(
        status=status, model=model,
        incomplete_details=_ns(reason=incomplete) if incomplete else None,
        output=[_ns(type="reasoning", content=None),
                _ns(type="message", content=content)],
        usage=usage or _ns(
            input_tokens=5000, output_tokens=300,
            input_tokens_details=_ns(cached_tokens=3000,
                                     cache_write_tokens=0),
            output_tokens_details=_ns(reasoning_tokens=120)))


def _good():
    return {
        "category": {"id": 12, "confidence": 0.9},
        "alternatives": [{"id": 11, "confidence": 0.05}],
        "attributes": {"name": "HIGH BACK EXECUTIVE SWIVEL CHAIR",
                       "colour": "BLACK", "material": "LEATHER",
                       "make": None, "model_name": None,
                       "dimensions": None},
        "condition": {"value": "good", "note": None},
        "size_band": "medium",
        "text_read": [],
    }


def _request(image=b"\xff\xd8\xff\xd9", mimetype="image/jpeg"):
    """Built the way `v1_ai.ai_identify` builds it — the same functions."""
    cats = [{"id": c, "name": "Class %d" % c, "identification_mode": "serial",
             "sap_asset_class": "3000"} for c in CATS]
    return ai.IdentifyRequest(
        image=ai.strip_metadata(image, mimetype), mimetype=mimetype,
        width=800, height=600,
        system=ai.build_system(cats, {"3000": [
            {"description": "SWIVEL CHAIR", "count": 9}]}),
        schema=ai.answer_schema(CATS), instruction=ai.INSTRUCTION,
        model="gpt-6.1-sol", timeout=20, effort="low", hint="chair-01.jpg",
        category_ids=CATS, category_names={c: "Class %d" % c for c in CATS})


def _identify(req=None):
    return ai.OpenAIProvider(KEY).identify(req or _request())


# ── a good answer ────────────────────────────────────────────────────

def test_a_good_answer_is_parsed_and_validated(sdk):
    sdk.answer = _response(json.dumps(_good()))
    got = _identify()
    assert got.data == _good()
    # The model that ANSWERED is recorded (a dated snapshot), and it is
    # priced as the model it belongs to.
    assert got.model == "gpt-6.1-sol-2026-09-29"
    clean, notes = ai.validate_answer(got.data, CATS)
    assert clean["category"] == {"id": 12, "confidence": 0.9} and not notes
    # OpenAI's input_tokens INCLUDES the cached ones; the record keeps
    # uncached input apart, as it always has for Anthropic.
    assert got.usage == {"input_tokens": 2000, "output_tokens": 300,
                         "cache_read_tokens": 3000, "cache_write_tokens": 0}
    assert ai.cost_usd(got.model, got.usage) == round(
        (2000 * 2.00 + 300 * 10.00 + 3000 * 0.10) / 1e6, 6)


def test_the_same_prompt_and_schema_go_to_openai_in_strict_mode(sdk):
    sdk.answer = _response(json.dumps(_good()))
    req = _request()
    _identify(req)
    (kw,), (client,) = sdk.sent, sdk.clients
    # The client: the given key, the tenant's timeout, no SDK retries.
    assert client == {"api_key": KEY, "timeout": 20.0, "max_retries": 0}
    assert kw["model"] == "gpt-6.1-sol"
    assert kw["instructions"] == req.system       # the one system prompt
    assert "Class 12" in kw["instructions"] and "SWIVEL CHAIR (9)" in \
        kw["instructions"]
    image, text = kw["input"][0]["content"]
    assert kw["input"][0]["role"] == "user"
    assert text == {"type": "input_text", "text": ai.INSTRUCTION}
    assert image["type"] == "input_image" and image["detail"] == "high"
    assert image["image_url"].startswith("data:image/jpeg;base64,")
    fmt = kw["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True
    assert fmt["schema"] == ai.answer_schema(CATS)  # unchanged, not a copy
    assert kw["reasoning"] == {"effort": "low"}
    assert kw["store"] is False
    assert kw["max_output_tokens"] == 8192


def test_the_shared_schema_meets_strict_mode_as_it_stands():
    """OpenAI's strict mode: every object `additionalProperties: false` and
    every property required. Ours meets both, so ONE schema serves both
    providers — and an edit that breaks either rule fails here first."""
    assert ai.strict_schema_problems(ai.answer_schema(CATS)) == []
    broken = ai.answer_schema(CATS)
    broken["properties"]["attributes"]["required"].remove("colour")
    del broken["properties"]["condition"]["additionalProperties"]
    assert ai.strict_schema_problems(broken) == [
        "answer.attributes: not required: colour",
        "answer.condition: additionalProperties is not false",
    ]


def test_the_provider_is_chosen_by_name():
    assert isinstance(ai.provider_for("openai", KEY), ai.OpenAIProvider)
    assert isinstance(ai.provider_for("anthropic", KEY), ai.AnthropicProvider)
    assert isinstance(ai.provider_for("fake", ""), ai.FakeProvider)
    assert ai.PROVIDERS == ("anthropic", "openai", "fake")


def test_each_provider_has_its_own_key_variable_and_model(monkeypatch):
    monkeypatch.setenv("CADRA_AI_API_KEY", "a-key")
    monkeypatch.delenv("CADRA_OPENAI_API_KEY", raising=False)
    assert ai.provider_key("anthropic") == "a-key"
    assert ai.provider_key() == "a-key"
    assert ai.provider_key("openai") == ""
    monkeypatch.setenv("CADRA_OPENAI_API_KEY", "  o-key \n")
    assert ai.provider_key("openai") == "o-key"
    assert ai.model_param("anthropic") == "cadra.ai.model"     # unchanged
    assert ai.model_param("openai") == "cadra.ai.model.openai"
    assert ai.DEFAULT_MODELS["openai"] == "gpt-6.1-sol"
    assert ai.DEFAULT_MODELS["anthropic"] == "claude-opus-5-5"


# ── what goes wrong, in Cadra's words ────────────────────────────────

@pytest.mark.parametrize("make, expected", [
    (lambda m: m.AuthenticationError("Incorrect API key sk-abc"),
     "The provider refused this server's key (401). The owner sets a new "
     "one in CADRA_OPENAI_API_KEY."),
    (lambda m: m.PermissionDeniedError("nope"),
     "The provider refused this server's key for this model (403)."),
    (lambda m: m.NotFoundError("no such model"),
     "The provider does not know the configured model (gpt-6.1-sol)."),
    (lambda m: m.RateLimitError("slow down", code="rate_limit_exceeded"),
     "The provider is rate-limiting this key (429)."),
    (lambda m: m.RateLimitError("You exceeded your current quota",
                                code="insufficient_quota"),
     "The provider says this key has no quota left (429 "
     "insufficient_quota); the owner adds credit to the account."),
    (lambda m: m.InternalServerError("boom", status_code=503),
     "The provider answered HTTP 503."),
    (lambda m: m.BadRequestError("Invalid schema for response_format"),
     "The provider answered HTTP 400."),
    (lambda m: m.APIConnectionError("Connection error."),
     "The provider could not be reached from this server."),
    (lambda m: m.OpenAIError("something unforeseen"),
     "The provider answered in a way Cadra could not read."),
])
def test_each_error_maps_to_cadras_sentence(sdk, make, expected):
    sdk.answer = make(sdk)
    with pytest.raises(ai.ProviderError) as e:
        _identify()
    assert str(e.value) == expected
    # Never the provider's own text — it can carry a key prefix.
    assert "sk-abc" not in str(e.value) and "Incorrect" not in str(e.value)
    assert e.value.__cause__ is None and e.value.__suppress_context__


def test_a_timeout_is_a_timeout_not_a_connection_error(sdk):
    # In the SDK the timeout is a SUBCLASS of the connection error; caught
    # in the wrong order it would be recorded as "could not be reached".
    sdk.answer = sdk.APITimeoutError("Request timed out.")
    with pytest.raises(ai.ProviderTimeout):
        _identify()


def test_a_missing_sdk_is_said(monkeypatch):
    monkeypatch.setitem(sys.modules, "openai", None)   # import raises
    with pytest.raises(ai.ProviderError) as e:
        _identify()
    assert "OpenAI SDK is not installed" in str(e.value)


def test_a_refusal_is_a_refusal(sdk):
    sdk.answer = _response(refusal="I can't help with that.")
    with pytest.raises(ai.ProviderRefused):
        _identify()


def test_the_content_filter_is_a_refusal(sdk):
    sdk.answer = _response(status="incomplete", incomplete="content_filter")
    with pytest.raises(ai.ProviderRefused):
        _identify()


def test_a_failed_response_is_an_error(sdk):
    sdk.answer = _response(status="failed")
    with pytest.raises(ai.ProviderError):
        _identify()


# ── a malformed answer: returned as data the validator discards ──────

@pytest.mark.parametrize("response", [
    _response("{not json"),                                  # not JSON
    _response(None, status="incomplete",
              incomplete="max_output_tokens"),               # cut short
    _response(json.dumps({"category": "a chair, probably"})),  # wrong shape
    _response(json.dumps(dict(_good(), category={"id": 99,
                                                 "confidence": 0.9}))),
])
def test_a_malformed_answer_is_discarded_by_the_validator(sdk, response):
    """The route records `invalid` and counts it (`v1_ai.ai_identify`,
    `answer_discarded`) when `validate_answer` raises — the provider's part
    is to hand back what came, or None, and never to repair it."""
    sdk.answer = response
    got = _identify()
    with pytest.raises(ai.InvalidAnswer):
        ai.validate_answer(got.data, CATS)


# ── the photo's metadata ─────────────────────────────────────────────

def _jpeg_with_gps():
    exif = b"Exif\x00\x00" + b"GPSLatitude 9.0765 N; GPSLongitude 7.3986 E"
    app1 = b"\xff\xe1" + (len(exif) + 2).to_bytes(2, "big") + exif
    com = b"Shot at the NRS office, Abuja"
    comment = b"\xff\xfe" + (len(com) + 2).to_bytes(2, "big") + com
    dqt = b"\xff\xdb\x00\x04\x00\x01"
    scan = b"\xff\xda\x00\x02" + b"\x12\x34\x56" + b"\xff\xd9"
    return b"\xff\xd8" + app1 + comment + dqt + scan


def test_the_photo_openai_receives_carries_no_exif(sdk):
    original = _jpeg_with_gps()
    sdk.answer = _response(json.dumps(_good()))
    _identify(_request(image=original))
    url = sdk.sent[0]["input"][0]["content"][0]["image_url"]
    sent = base64.b64decode(url.split(",", 1)[1])
    assert b"GPS" not in sent and b"Exif" not in sent
    assert b"Abuja" not in sent
    # What remains is the image: the quantisation table and the scan.
    assert sent == b"\xff\xd8" + b"\xff\xdb\x00\x04\x00\x01" + \
        b"\xff\xda\x00\x02\x12\x34\x56\xff\xd9"
    assert b"GPS" in original    # the stored photo is not what is stripped

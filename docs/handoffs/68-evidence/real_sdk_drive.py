"""Drive OpenAIProvider through the REAL openai SDK with an in-process
transport (no network): what the SDK puts on the wire, and whether the
provider reads the SDK's parsed response objects correctly."""
import importlib.util, json, sys
import httpx2, openai
spec = importlib.util.spec_from_file_location("aip", "/mnt/extra-addons/myservice_api/controllers/ai_provider.py")
ai = importlib.util.module_from_spec(spec); spec.loader.exec_module(ai)
seen = {}
def answer_with(status_code, body):
    def handler(request):
        seen["url"] = str(request.url); seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization", "")[:12]
        return httpx2.Response(status_code, json=body)
    return handler
real = openai.OpenAI
def drive(status_code, body):
    openai.OpenAI = lambda **kw: real(http_client=httpx2.Client(transport=httpx2.MockTransport(answer_with(status_code, body))), **kw)
    req = ai.IdentifyRequest(image=b"\xff\xd8\xff\xd9", mimetype="image/jpeg", width=10, height=10,
        system="SYSTEM PROMPT", schema=ai.answer_schema([1, 2]), instruction=ai.INSTRUCTION,
        model="gpt-6.1-sol", timeout=20, effort="low", hint="x", category_ids=[1, 2], category_names={})
    try:
        a = ai.OpenAIProvider("dummy-not-a-key").identify(req)
        return "ANSWER data=%s model=%s usage=%s" % (json.dumps(a.data)[:60], a.model, a.usage)
    except Exception as e:
        return "%s: %s" % (type(e).__name__, e)
good = {"category": {"id": 2, "confidence": 0.9}, "alternatives": [], "attributes": {k: None for k in ai.ATTRIBUTES},
        "condition": {"value": "good", "note": None}, "size_band": "unknown", "text_read": []}
ok = {"id": "resp_1", "object": "response", "created_at": 1, "status": "completed", "model": "gpt-6.1-sol-2026-09-29",
      "output": [{"type": "reasoning", "id": "rs_1", "summary": []},
                 {"type": "message", "id": "msg_1", "status": "completed", "role": "assistant",
                  "content": [{"type": "output_text", "text": json.dumps(good), "annotations": []}]}],
      "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
      "usage": {"input_tokens": 5000, "input_tokens_details": {"cached_tokens": 3000, "cache_write_tokens": 0},
                "output_tokens": 300, "output_tokens_details": {"reasoning_tokens": 100}, "total_tokens": 5300}}
print("good:", drive(200, ok))
b = seen["body"]
print("wire: url=%s auth=%s... keys=%s" % (seen["url"], seen["auth"], sorted(b)))
print("wire: format=%s strict=%s store=%s effort=%s detail=%s" % (b["text"]["format"]["type"], b["text"]["format"]["strict"],
      b["store"], b["reasoning"], b["input"][0]["content"][0]["detail"]))
ref = json.loads(json.dumps(ok)); ref["output"][1]["content"] = [{"type": "refusal", "refusal": "I can't help."}]
print("refusal:", drive(200, ref))
for code, err in ((401, {"error": {"message": "Incorrect API key provided: sk-abc", "type": "invalid_request_error", "code": "invalid_api_key"}}),
                  (429, {"error": {"message": "You exceeded your current quota", "type": "insufficient_quota", "code": "insufficient_quota"}}),
                  (429, {"error": {"message": "Rate limit reached", "type": "requests", "code": "rate_limit_exceeded"}}),
                  (404, {"error": {"message": "The model does not exist", "code": "model_not_found"}}),
                  (400, {"error": {"message": "Invalid schema", "code": None}}),
                  (500, {"error": {"message": "server error"}})):
    print(code, err["error"].get("code"), "->", drive(code, err))

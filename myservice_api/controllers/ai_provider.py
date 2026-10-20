"""The provider behind *Identify from photo*, behind one adapter (handoff 64 §1).

Ruling R11: Cadra's server asks an existing, general-purpose vision model
what a photographed item is. Nothing here is a route; `v1_ai.py` is. This
module holds:

* **the adapter interface** — `Provider.identify(request)`: an image, a
  prompt and a JSON schema in; a `ProviderAnswer` out (the parsed JSON, the
  model that answered, the latency and the token counts), or one of three
  exceptions (`ProviderTimeout`, `ProviderError`, `ProviderRefused`);
* **three implementations** — `FakeProvider`, deterministic and offline,
  which every test uses; `AnthropicProvider`, Anthropic's Messages API with
  image input (the owner's choice, 18 October 2026); and `OpenAIProvider`,
  OpenAI's Responses API with image input (handoff 68, the owner's second
  provider, 20 October 2026) — each through its official SDK, imported only
  when it is used, and each sent the SAME system prompt, instruction and
  schema (`build_system`, `INSTRUCTION`, `answer_schema`);
* **the prompt and the schema** — what is sent (the photo, the tenant's
  classes, each mapped SAP class's twenty commonest descriptions) and
  nothing else: no asset ids, no people, no locations, no SAP numbers;
* **the validator** — the provider's answer is checked against the tenant
  BEFORE anybody sees it: a class the tenant does not have, a condition
  outside the published enum, a malformed shape, is discarded and counted.

THE KEY is a secret and the owner's, and it lives in the SERVER'S
ENVIRONMENT, never in the database (handoff 65 §0a.1, report 64 deviation
2): `provider_key(provider)` reads `CADRA_AI_API_KEY` (Anthropic's) or
`CADRA_OPENAI_API_KEY` (OpenAI's, handoff 68 — a variable of its own, so both
can be present and switching provider never means swapping a secret) from
this process — the local
`.env` (written by `scripts/set_ai_key.sh`) or the cluster's `cadra-odoo`
secret, handed to the Odoo container by compose and by the deployment. Handoff
64 kept it in an `ir_config_parameter` row, which any back-office system
administrator can read and every database backup carries; migration
`19.0.3.36.0` deleted that row on every tenant and nothing reads or writes it
now. One key per SERVER, not per tenant — every tenant the process serves
asks the provider with it, and each tenant's own switch (`cadra.ai.identify`,
off by default) still decides whether it asks at all. It is never logged,
never put in an error, never returned by any route: the routes say only
whether one is present. Every test runs on the fake.
"""
import json
import logging
import math
import os
import re
import time

_logger = logging.getLogger(__name__)

#: Bumped whenever the prompt, the schema or the validator changes what a
#: suggestion means. Recorded on every `nrs.ai.suggestion`.
PROMPT_VERSION = "67.1"

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"
PROVIDER_FAKE = "fake"
PROVIDERS = (PROVIDER_ANTHROPIC, PROVIDER_OPENAI, PROVIDER_FAKE)
#: The providers a photo actually leaves the server for — each needs the
#: owner's key, each has a variable of its own (`ENV_KEYS`).
KEYED_PROVIDERS = (PROVIDER_ANTHROPIC, PROVIDER_OPENAI)
#: What a person is told the photo is sent to (the screens' one sentence).
PROVIDER_LABELS = {
    PROVIDER_ANTHROPIC: "Anthropic (Claude)",
    PROVIDER_OPENAI: "OpenAI (GPT)",
    PROVIDER_FAKE: "Cadra's test stand-in (nothing leaves the server)",
}

# The tenant's settings — `cadra.*` on the configuration record, read with
# raw SQL by `v1_ai.ai_settings` so a change made from a shell takes effect
# without a restart (the receipt gate's reason).
PARAM_ENABLED = "cadra.ai.identify"
PARAM_PROVIDER = "cadra.ai.provider"
#: Anthropic's model — the one parameter handoffs 64–67 had, kept under its
#: name so no tenant's chosen model moves. Every other provider has its own
#: (`model_param`), so switching provider never overwrites a model somebody
#: typed for the other one, and switching back finds it where it was.
PARAM_MODEL = "cadra.ai.model"
PARAM_TIMEOUT = "cadra.ai.timeout_seconds"
PARAM_DAILY_CAP = "cadra.ai.daily_cap"
PARAM_EFFORT = "cadra.ai.effort"
#: The secrets' NAMES — environment variables of the server process, never
#: parameters (handoff 65). Read by `provider_key()` and nothing else.
#: `CADRA_AI_API_KEY` stays Anthropic's (handoff 68 §2).
ENV_KEY = "CADRA_AI_API_KEY"
ENV_KEY_OPENAI = "CADRA_OPENAI_API_KEY"
ENV_KEYS = {PROVIDER_ANTHROPIC: ENV_KEY, PROVIDER_OPENAI: ENV_KEY_OPENAI}

DEFAULT_PROVIDER = PROVIDER_ANTHROPIC
DEFAULT_MODEL = "claude-opus-5-5"
#: Each provider's default model, from its own documentation. OpenAI's
#: (handoff 68): GPT-6.1 Sol, which OpenAI's model page recommends "to
#: balance intelligence and cost" — image input and structured outputs both
#: listed, at a fifth of GPT-6 Astra's price. The owner changes it in
#: Settings; the live check compares them.
DEFAULT_MODELS = {
    PROVIDER_ANTHROPIC: DEFAULT_MODEL,
    PROVIDER_OPENAI: "gpt-6.1-sol",
    PROVIDER_FAKE: "cadra-fake-1",
}
DEFAULT_TIMEOUT = 20
DEFAULT_DAILY_CAP = 500
#: Identifying a chair is a short, visual task: `low` effort, raised from
#: Settings if the owner's live check (handoff 64 §5.5) says it misses.
DEFAULT_EFFORT = "low"
EFFORTS = ("low", "medium", "high")

#: Published prices, USD per million tokens (input, output, cache read),
#: as cached on 2026-10-06. Cache writes (five-minute) are 1.25 × input.
#: A model not listed records its tokens and no cost.
#: OpenAI's (handoff 68), from its model pages as read on 2026-10-20 —
#: standard tier, prompts under 272K tokens; its cache writes are also
#: 1.25 × input ($2.50 for GPT-6.1 Sol, $12.50 for GPT-6 Astra). OWNER TO
#: CONFIRM against https://developers.openai.com/api/docs/pricing.
PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-fable-5-1": (10.00, 50.00, 0.25),
    "gpt-6-astra": (10.00, 50.00, 1.00),
    "gpt-6.1-sol": (2.00, 10.00, 0.10),
    "gpt-6-sol": (2.00, 10.00, 0.20),
    "gpt-6-luna": (0.10, 0.50, 0.01),
}

#: The published condition enum (`nrs.asset.condition`). R5: *unserviceable*
#: is `poor`, with the note "unserviceable" — never a value of its own.
CONDITIONS = ("new", "good", "fair", "poor", "decommissioned")
TEXT_KINDS = ("brand", "model", "serial_like", "firs_tag_like", "other")
ATTRIBUTES = ("name", "colour", "material", "make", "model_name",
              "dimensions")
#: AI-FR-03 (handoff 67 §3): an APPROXIMATE size, in words, because a photo
#: has no scale and `dimensions` stays empty unless a label states them.
#: `unknown` is the provider's way of saying none (an enum with null is not
#: something every structured-output engine accepts); published as null.
SIZE_BANDS = ("small", "medium", "large")
SIZE_BAND_UNKNOWN = "unknown"
SIZE_BAND_WORDS = {
    "small": "One person carries it in one hand or under an arm — a desk "
             "phone, a monitor, a stool, a side table.",
    "medium": "One person lifts it with both arms or rolls it, and it goes "
              "through a door without tilting — an office chair, a printer, "
              "a two-drawer cabinet.",
    "large": "Two or more people move it, or it is tilted or taken apart to "
             "go through a door — a desk, a conference table, a wardrobe, a "
             "sofa, a tall cabinet.",
}
_MAX_TEXT = 200


class ProviderTimeout(Exception):
    """The provider did not answer within the tenant's timeout."""


class ProviderError(Exception):
    """The provider could not be asked, or answered with an error. The
    message is Cadra's own sentence, safe to record — never the provider's
    text, and never anything carrying the key."""


class ProviderRefused(Exception):
    """The provider declined to describe the photo."""


class ProviderAnswer:
    __slots__ = ("data", "model", "latency_ms", "usage")

    def __init__(self, data, model, latency_ms, usage):
        self.data = data
        self.model = model
        self.latency_ms = latency_ms
        self.usage = usage


class IdentifyRequest:
    """What the adapter sends. Built by `build_request`; nothing else."""
    __slots__ = ("image", "mimetype", "width", "height", "system", "schema",
                 "instruction", "model", "timeout", "effort", "hint",
                 "category_ids", "category_names")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def image_tokens(width, height):
    """An estimate of what one image costs in input tokens — the published
    rule (pixels / 750), after the long edge is brought to at most 2,576 px,
    capped at 4,784. Used by the fake and by §6's arithmetic; the real
    provider reports its own count."""
    if not width or not height:
        return 0
    scale = min(1.0, 2576.0 / max(width, height))
    w, h = width * scale, height * scale
    return int(min(4784, math.ceil(w * h / 750.0)))


def model_param(provider):
    """The parameter holding `provider`'s model on this tenant."""
    return PARAM_MODEL if provider == PROVIDER_ANTHROPIC \
        else "%s.%s" % (PARAM_MODEL, provider)


def price_of(model):
    """The table's row for `model` — exactly, or for the model a dated
    snapshot id belongs to (OpenAI answers `gpt-6.1-sol-2026-09-29` when
    asked for `gpt-6.1-sol`). None for a model not in the table."""
    model = model or ""
    if model in PRICES_PER_MTOK:
        return PRICES_PER_MTOK[model]
    snap = re.match(r"^(.+?)-\d{4}-\d{2}-\d{2}$", model)
    return PRICES_PER_MTOK.get(snap.group(1)) if snap else None


def cost_usd(model, usage):
    """USD at the published prices, or None for a model not in the table."""
    price = price_of(model)
    if not price:
        return None
    p_in, p_out, p_read = price
    return round((
        (usage.get("input_tokens") or 0) * p_in
        + (usage.get("output_tokens") or 0) * p_out
        + (usage.get("cache_read_tokens") or 0) * p_read
        + (usage.get("cache_write_tokens") or 0) * p_in * 1.25
    ) / 1_000_000, 6)


# ── what is sent ─────────────────────────────────────────────────────

def catalogue(env):
    """The tenant's classes, and for each SAP class they map to, its twenty
    commonest descriptions in the mirror. COUNTS AND WORDS, NOT RECORDS: no
    asset number, no tag, no office, no person leaves the server."""
    cats = env["nrs.asset.category"].sudo().search([], order="id")
    rows = [{
        "id": c.id,
        "name": c.name,
        "identification_mode": c.identification_mode or "serial",
        "sap_asset_class": c.sap_asset_class or None,
    } for c in cats]
    classes = sorted({r["sap_asset_class"] for r in rows
                      if r["sap_asset_class"]})
    examples = {}
    if classes:
        env.cr.execute("""
            SELECT asset_class, description, n FROM (
                SELECT asset_class, description, count(*) AS n,
                       row_number() OVER (PARTITION BY asset_class
                                          ORDER BY count(*) DESC,
                                                   description) AS r
                  FROM nrs_sap_asset
                 WHERE asset_class = ANY(%s) AND sap_active
                   AND in_latest_export
                   AND coalesce(description, '') <> ''
                 GROUP BY asset_class, description) t
             WHERE r <= 20
             ORDER BY asset_class, n DESC, description
        """, (classes,))
        for cls, desc, n in env.cr.fetchall():
            examples.setdefault(cls, []).append({"description": desc,
                                                 "count": n})
    return rows, examples


def answer_schema(category_ids):
    """The JSON schema the answer must meet — sent to the provider as its
    output format, and checked again here (`validate_answer`)."""
    nullable = {"type": ["string", "null"]}
    scored = {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "enum": list(category_ids)},
            "confidence": {"type": "number"},
        },
        "required": ["id", "confidence"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "category": scored,
            "alternatives": {"type": "array", "items": scored},
            "attributes": {
                "type": "object",
                "properties": {k: nullable for k in ATTRIBUTES},
                "required": list(ATTRIBUTES),
                "additionalProperties": False,
            },
            "condition": {
                "type": "object",
                "properties": {
                    "value": {"type": "string", "enum": list(CONDITIONS)},
                    "note": nullable,
                },
                "required": ["value", "note"],
                "additionalProperties": False,
            },
            "size_band": {"type": "string",
                          "enum": list(SIZE_BANDS) + [SIZE_BAND_UNKNOWN]},
            "text_read": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "looks_like": {"type": "string",
                                       "enum": list(TEXT_KINDS)},
                    },
                    "required": ["text", "looks_like"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["category", "alternatives", "attributes", "condition",
                     "size_band", "text_read"],
        "additionalProperties": False,
    }


_INSTRUCTIONS = """You identify one physical item in a photograph for a \
public-sector fixed-asset register (the Nigeria Revenue Service). A person \
will confirm or correct everything you say; say only what the photo shows.

Answer with JSON matching the schema you are given:

- category: the ONE class below the item belongs to (its id), with your \
confidence from 0 to 1; alternatives: at most TWO other classes it could \
be, each with a confidence. Never invent a class.
- attributes.name: a short description of the item in the register's own \
style — upper case, the kind of thing first, as in the example \
descriptions below (e.g. HIGH BACK EXECUTIVE SWIVEL CHAIR).
- attributes.colour and attributes.material: what you can see, in plain \
words; null when you cannot tell.
- attributes.make and attributes.model_name: ONLY if a brand or a model is \
legible in the photo. Never infer one from the item's shape. Null otherwise.
- attributes.dimensions: ONLY if a label in the photo states them. A photo \
has no scale: never estimate a size. Null otherwise.
- condition.value: one of new, good, fair, poor, decommissioned. An item \
that is broken or unusable is "poor" with condition.note "unserviceable". \
condition.note is otherwise null or a few words.
- size_band: %(size_bands)s
- text_read: every piece of text you can read on the item, each with what \
it looks like: brand, model, serial_like (a serial-number plate or \
sticker), firs_tag_like (an old asset tag — FIRS was the service's former \
name, and its tags read like FIRS/<office>/<number>), or other. An empty \
list if there is none.

If the photo shows a person, describe only the item. If no item can be \
seen, choose the closest class with a low confidence.""" % {"size_bands": "how big the item is, APPROXIMATELY, judged from \
what it is and how it is built — never measured, a photo has no scale. " + \
    " ".join('"%s": %s' % (b, SIZE_BAND_WORDS[b]) for b in SIZE_BANDS) + \
    ' "unknown" when you cannot tell.'}


def build_system(categories, examples):
    """The system prompt: the instructions, then the tenant's classes —
    stable across calls, so the provider can cache it."""
    lines = [_INSTRUCTIONS, "", "The register's classes:"]
    for c in categories:
        line = "- id %d: %s (identified by %s" % (
            c["id"], c["name"], c["identification_mode"])
        if c["sap_asset_class"]:
            line += "; SAP class %s" % c["sap_asset_class"]
        lines.append(line + ")")
    if examples:
        lines += ["", "The commonest descriptions SAP holds for each SAP "
                      "class, with how many records carry each:"]
        for cls in sorted(examples):
            lines.append("SAP class %s: %s" % (cls, "; ".join(
                "%s (%d)" % (e["description"], e["count"])
                for e in examples[cls])))
    return "\n".join(lines)


INSTRUCTION = ("Identify the item in this photo. Answer only with the JSON "
               "the schema asks for.")


# ── what comes back ──────────────────────────────────────────────────

class InvalidAnswer(Exception):
    """The answer failed the schema or named what the tenant does not have.
    Discarded, counted, never shown."""


def _text(value, where):
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidAnswer("%s is not text" % where)
    value = value.strip()
    if len(value) > _MAX_TEXT:
        raise InvalidAnswer("%s is longer than %d characters"
                            % (where, _MAX_TEXT))
    return value or None


def _scored(item, ids, where):
    if not isinstance(item, dict) or set(item) != {"id", "confidence"}:
        raise InvalidAnswer("%s is not {id, confidence}" % where)
    cid, conf = item["id"], item["confidence"]
    if isinstance(cid, bool) or not isinstance(cid, int) or cid not in ids:
        raise InvalidAnswer("%s names a class this register does not have"
                            % where)
    if isinstance(conf, bool) or not isinstance(conf, (int, float)) \
            or not 0 <= conf <= 1:
        raise InvalidAnswer("%s's confidence is not between 0 and 1" % where)
    return {"id": cid, "confidence": round(float(conf), 3)}


def _appears_in(value, texts):
    """Whether `value` was read off the item — it, or something it is part
    of, is in `text_read` (case and spacing ignored)."""
    squash = lambda s: re.sub(r"\s+", " ", s).strip().casefold()
    v = squash(value)
    return any(v in squash(t) or squash(t) in v for t in texts if t)


def validate_answer(data, category_ids):
    """`(clean, notes)` — the answer checked, or raise `InvalidAnswer`.

    `notes` say what was removed rather than discarded: a make, a model or
    dimensions the answer gave that appear nowhere in what it says it read
    (the prompt forbids guessing them, and the record keeps only what the
    photo showed). Removing one is said on the response, never silent."""
    ids = set(category_ids)
    if not isinstance(data, dict):
        raise InvalidAnswer("the answer is not an object")
    expected = {"category", "alternatives", "attributes", "condition",
                "size_band", "text_read"}
    if set(data) != expected:
        raise InvalidAnswer("the answer's keys are not the schema's")
    category = _scored(data["category"], ids, "category")
    alts = data["alternatives"]
    if not isinstance(alts, list) or len(alts) > 2:
        raise InvalidAnswer("alternatives is not a list of at most two")
    alternatives = []
    for i, a in enumerate(alts):
        a = _scored(a, ids, "alternative %d" % (i + 1))
        if a["id"] == category["id"] or a["id"] in {
                x["id"] for x in alternatives}:
            raise InvalidAnswer("an alternative repeats a class")
        alternatives.append(a)
    attrs = data["attributes"]
    if not isinstance(attrs, dict) or set(attrs) != set(ATTRIBUTES):
        raise InvalidAnswer("attributes' keys are not the schema's")
    attributes = {k: _text(attrs[k], "attributes.%s" % k) for k in ATTRIBUTES}
    cond = data["condition"]
    if not isinstance(cond, dict) or set(cond) != {"value", "note"} \
            or cond["value"] not in CONDITIONS:
        raise InvalidAnswer("condition is not one of the published values")
    condition = {"value": cond["value"],
                 "note": _text(cond["note"], "condition.note")}
    band = data["size_band"]
    if band not in SIZE_BANDS + (SIZE_BAND_UNKNOWN,):
        raise InvalidAnswer("size_band is not one of the published values")
    size_band = None if band == SIZE_BAND_UNKNOWN else band
    reads = data["text_read"]
    if not isinstance(reads, list) or len(reads) > 40:
        raise InvalidAnswer("text_read is not a list")
    text_read = []
    for i, r in enumerate(reads):
        if not isinstance(r, dict) or set(r) != {"text", "looks_like"} \
                or r["looks_like"] not in TEXT_KINDS:
            raise InvalidAnswer("text_read %d is not {text, looks_like}"
                                % (i + 1))
        t = _text(r["text"], "text_read %d" % (i + 1))
        if t:
            text_read.append({"text": t, "looks_like": r["looks_like"]})
    notes = []
    read = [r["text"] for r in text_read]
    for key, words in (("make", "a make"), ("model_name", "a model"),
                       ("dimensions", "dimensions")):
        if attributes[key] and not _appears_in(attributes[key], read):
            notes.append("The provider proposed %s (%s) it did not read off "
                         "the item; it was removed — fill it by hand if you "
                         "know it." % (words, attributes[key]))
            attributes[key] = None
    return {"category": category, "alternatives": alternatives,
            "attributes": attributes, "condition": condition,
            "size_band": size_band, "text_read": text_read}, notes


# ── the providers ────────────────────────────────────────────────────

class Provider:
    name = None

    def identify(self, req):  # pragma: no cover - interface
        raise NotImplementedError


class FakeProvider(Provider):
    """Deterministic and offline. Every test uses it.

    It answers from the photo's FILE NAME (the hint), so a test chooses the
    answer by naming the file — `chair-01.jpg`, the live check's own
    convention — and the same file always gets the same answer:

    * the class: the first of the tenant's classes whose name shares a word
      with the file name, else the first class; two alternatives after it;
    * `firs-<OFFICE>-<NUMBER>` in the name: a FIRS tag read, `FIRS/OFFICE/NUMBER`;
    * `sn-<SERIAL>`: a serial plate read; `brand`: HP / LASERJET M404 read
      and proposed; `unserviceable`: condition `poor`, note unserviceable;
    * `malformed` → an answer that fails the schema; `timeout` → a timeout;
      `error` → a provider error; `refuse` → the provider declines.

    Token counts are an estimate of what the real provider would bill: the
    prompt at four characters a token, the image by `image_tokens`.
    """
    name = PROVIDER_FAKE
    model = "cadra-fake-1"

    def identify(self, req):
        hint = (req.hint or "").lower()
        if "timeout" in hint:
            raise ProviderTimeout()
        if "error" in hint:
            raise ProviderError("The test stand-in was told to fail.")
        if "refuse" in hint:
            raise ProviderRefused()
        started = time.monotonic()
        usage = {
            "input_tokens": len(req.system or "") // 4
            + len(req.instruction or "") // 4
            + image_tokens(req.width, req.height),
            "output_tokens": 180,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }
        if "malformed" in hint:
            data = {"category": "a chair, probably", "colour": "black"}
        else:
            data = self._answer(hint, req)
        latency = int((time.monotonic() - started) * 1000)
        return ProviderAnswer(data, self.model, latency, usage)

    def _answer(self, hint, req):
        words = set(re.findall(r"[a-z]+", hint))
        cats = req.category_ids or []
        names = req.category_names or {}
        chosen = next((cid for cid in cats if words & set(
            re.findall(r"[a-z]+", (names.get(cid) or "").lower()))),
            cats[0] if cats else 0)
        rest = [c for c in cats if c != chosen][:2]
        text_read = []
        tag = re.search(r"firs-([a-z0-9]+)-([0-9]+)", hint)
        if tag:
            text_read.append({"text": "FIRS/%s/%s" % (tag.group(1).upper(),
                                                      tag.group(2)),
                              "looks_like": "firs_tag_like"})
        serial = re.search(r"sn-([a-z0-9]+)", hint)
        if serial:
            text_read.append({"text": serial.group(1).upper(),
                              "looks_like": "serial_like"})
        brand = "brand" in words
        if brand:
            text_read += [{"text": "HP", "looks_like": "brand"},
                          {"text": "LASERJET M404", "looks_like": "model"}]
        chair = "chair" in words
        band = ("large" if words & {"table", "desk", "wardrobe", "cabinet"}
                else "medium" if chair or brand else SIZE_BAND_UNKNOWN)
        return {
            "category": {"id": chosen, "confidence": 0.86},
            "alternatives": [{"id": c, "confidence": 0.05} for c in rest],
            "attributes": {
                "name": "HIGH BACK EXECUTIVE SWIVEL CHAIR" if chair
                else (names.get(chosen) or "ITEM").upper(),
                "colour": "BLACK",
                "material": "LEATHER" if chair else "METAL",
                "make": "HP" if brand else None,
                "model_name": "LASERJET M404" if brand else None,
                "dimensions": None,
            },
            "condition": ({"value": "poor", "note": "unserviceable"}
                          if "unserviceable" in words
                          else {"value": "good", "note": None}),
            "size_band": band,
            "text_read": text_read,
        }


class AnthropicProvider(Provider):
    """Anthropic's Messages API with image input, through the official SDK.

    One request: the system prompt (cached — it is the same for every photo
    on a tenant until its classes change), the image and the instruction,
    the answer constrained to the schema by structured outputs. The SDK's
    own retries are off: the tenant's timeout is the whole budget, and a
    person is waiting at a form."""
    name = PROVIDER_ANTHROPIC

    def __init__(self, api_key):
        self._key = api_key

    def identify(self, req):
        try:
            import anthropic
        except ImportError:
            raise ProviderError(
                "The Anthropic SDK is not installed in this server's image "
                "(the `anthropic` Python package).") from None
        import base64 as _b64
        client = anthropic.Anthropic(api_key=self._key,
                                     timeout=float(req.timeout),
                                     max_retries=0)
        started = time.monotonic()
        try:
            msg = client.beta.messages.create(
                model=req.model,
                max_tokens=4096,
                # Server-side fallback on a policy decline (`default` routes
                # by the decline's category, no model list to keep).
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=[{"type": "text", "text": req.system,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": req.mimetype,
                        "data": _b64.standard_b64encode(req.image).decode(
                            "ascii")}},
                    {"type": "text", "text": req.instruction},
                ]}],
                output_config={
                    "effort": req.effort,
                    "format": {"type": "json_schema", "schema": req.schema},
                },
            )
        except anthropic.APITimeoutError:
            raise ProviderTimeout() from None
        except anthropic.AuthenticationError:
            raise ProviderError(
                "The provider refused this server's key (401). The owner "
                "sets a new one in CADRA_AI_API_KEY.") from None
        except anthropic.PermissionDeniedError:
            raise ProviderError(
                "The provider refused this server's key for this model "
                "(403).") from None
        except anthropic.NotFoundError:
            raise ProviderError(
                "The provider does not know the configured model "
                "(%s)." % req.model) from None
        except anthropic.RateLimitError:
            raise ProviderError(
                "The provider is rate-limiting this key (429).") from None
        except anthropic.APIStatusError as e:
            raise ProviderError(
                "The provider answered HTTP %s." % e.status_code) from None
        except anthropic.APIConnectionError:
            raise ProviderError(
                "The provider could not be reached from this server.") \
                from None
        # Last: the SDK's base error — a response it could not validate, a
        # credential problem, anything not named above. Without it one of
        # those escaped as a bare 500, and the rollback took the call's
        # record with it (verification pass).
        except anthropic.AnthropicError:
            raise ProviderError(
                "The provider answered in a way Cadra could not read.") \
                from None
        latency = int((time.monotonic() - started) * 1000)
        u = msg.usage
        usage = {
            "input_tokens": u.input_tokens or 0,
            "output_tokens": u.output_tokens or 0,
            "cache_read_tokens": u.cache_read_input_tokens or 0,
            "cache_write_tokens": u.cache_creation_input_tokens or 0,
        }
        if msg.stop_reason == "refusal":
            raise ProviderRefused()
        text = next((b.text for b in msg.content if b.type == "text"), None)
        try:
            data = json.loads(text) if text else None
        except ValueError:
            data = None
        return ProviderAnswer(data, msg.model, latency, usage)


def strict_schema_problems(schema, where="answer"):
    """What stops `schema` being sent in OpenAI's strict mode — its two
    rules, from the structured-outputs guide: every object says
    `additionalProperties: false`, and every property is `required` (an
    optional one is a type that includes null). An empty list for ours: the
    shared schema meets both as it stands, so it goes to OpenAI UNCHANGED
    and there is no second schema to drift (handoff 68 §1). The unit test
    holds it to that; a future edit that breaks it fails there, not at
    OpenAI's 400."""
    problems = []
    if not isinstance(schema, dict):
        return problems
    if schema.get("type") == "object" or "properties" in schema:
        props = schema.get("properties") or {}
        if schema.get("additionalProperties") is not False:
            problems.append("%s: additionalProperties is not false" % where)
        missing = sorted(set(props) - set(schema.get("required") or ()))
        if missing:
            problems.append("%s: not required: %s" % (where,
                                                      ", ".join(missing)))
        for k, sub in props.items():
            problems += strict_schema_problems(sub, "%s.%s" % (where, k))
    if isinstance(schema.get("items"), dict):
        problems += strict_schema_problems(schema["items"], where + "[]")
    return problems


class OpenAIProvider(Provider):
    """OpenAI's Responses API with image input, through the official SDK
    (handoff 68). The Responses API rather than Chat Completions because it
    is the one OpenAI's current documentation builds on — `instructions`
    for the system prompt, `text.format` for a strict JSON schema, and every
    current model served on it.

    One request, the same three things Anthropic is sent: `instructions` is
    the system prompt (OpenAI caches a repeated prefix of ≥ 1,024 tokens by
    itself — the class list is that prefix), the image at `high` detail and
    the instruction, the answer constrained by the SAME schema in strict
    mode. `store=False`: the Responses API keeps a response for later
    retrieval by default, and nothing here is fetched again. `reasoning`
    carries the tenant's effort (low, medium, high are OpenAI's words too).
    `max_output_tokens` is 8,192, not Anthropic's 4,096, because OpenAI
    counts the model's reasoning tokens inside it; an answer cut short is
    malformed and counted like any other. The SDK's own retries are off:
    the tenant's timeout is the whole budget, and a person is waiting."""
    name = PROVIDER_OPENAI
    max_output_tokens = 8192

    def __init__(self, api_key):
        self._key = api_key

    def identify(self, req):
        try:
            import openai
        except ImportError:
            raise ProviderError(
                "The OpenAI SDK is not installed in this server's image "
                "(the `openai` Python package).") from None
        import base64 as _b64
        client = openai.OpenAI(api_key=self._key,
                               timeout=float(req.timeout),
                               max_retries=0)
        image_url = "data:%s;base64,%s" % (
            req.mimetype, _b64.standard_b64encode(req.image).decode("ascii"))
        started = time.monotonic()
        try:
            resp = client.responses.create(
                model=req.model,
                instructions=req.system,
                input=[{"role": "user", "content": [
                    {"type": "input_image", "image_url": image_url,
                     "detail": "high"},
                    {"type": "input_text", "text": req.instruction},
                ]}],
                text={"format": {"type": "json_schema",
                                 "name": "cadra_identification",
                                 "strict": True,
                                 "schema": req.schema}},
                reasoning={"effort": req.effort},
                max_output_tokens=self.max_output_tokens,
                store=False,
            )
        # The timeout first: in this SDK it is a subclass of the connection
        # error, and the order decides which sentence is recorded.
        except openai.APITimeoutError:
            raise ProviderTimeout() from None
        except openai.AuthenticationError:
            raise ProviderError(
                "The provider refused this server's key (401). The owner "
                "sets a new one in %s." % ENV_KEY_OPENAI) from None
        except openai.PermissionDeniedError:
            raise ProviderError(
                "The provider refused this server's key for this model "
                "(403).") from None
        except openai.NotFoundError:
            raise ProviderError(
                "The provider does not know the configured model "
                "(%s)." % req.model) from None
        except openai.RateLimitError as e:
            # OpenAI says "no quota left" with a 429 of its own code, not a
            # 403 — told apart, because waiting does not cure it.
            if getattr(e, "code", None) == "insufficient_quota":
                raise ProviderError(
                    "The provider says this key has no quota left (429 "
                    "insufficient_quota); the owner adds credit to the "
                    "account.") from None
            raise ProviderError(
                "The provider is rate-limiting this key (429).") from None
        except openai.APIStatusError as e:
            raise ProviderError(
                "The provider answered HTTP %s." % e.status_code) from None
        except openai.APIConnectionError:
            raise ProviderError(
                "The provider could not be reached from this server.") \
                from None
        # Last: the SDK's base error, for the reason Anthropic's is caught.
        except openai.OpenAIError:
            raise ProviderError(
                "The provider answered in a way Cadra could not read.") \
                from None
        latency = int((time.monotonic() - started) * 1000)
        u = getattr(resp, "usage", None)
        details = getattr(u, "input_tokens_details", None)
        read = getattr(details, "cached_tokens", 0) or 0
        written = getattr(details, "cache_write_tokens", 0) or 0
        # OpenAI's `input_tokens` INCLUDES the cached and the cache-written
        # ones; Anthropic's excludes them. Recorded the way the record has
        # always meant it — uncached input apart — so one price table and
        # one `cost_usd` serve both. Reasoning tokens are inside
        # `output_tokens` and billed as output.
        usage = {
            "input_tokens": max(0, (getattr(u, "input_tokens", 0) or 0)
                                - read - written),
            "output_tokens": getattr(u, "output_tokens", 0) or 0,
            "cache_read_tokens": read,
            "cache_write_tokens": written,
        }
        if getattr(resp, "status", None) == "failed":
            raise ProviderError(
                "The provider answered in a way Cadra could not read.")
        incomplete = getattr(resp, "incomplete_details", None)
        if getattr(resp, "status", None) == "incomplete" \
                and getattr(incomplete, "reason", None) == "content_filter":
            raise ProviderRefused()
        texts = []
        for item in getattr(resp, "output", None) or ():
            if getattr(item, "type", None) != "message":
                continue
            for part in getattr(item, "content", None) or ():
                kind = getattr(part, "type", None)
                if kind == "refusal":
                    raise ProviderRefused()
                if kind == "output_text":
                    texts.append(part.text or "")
        text = "".join(texts)
        try:
            data = json.loads(text) if text else None
        except ValueError:
            data = None
        return ProviderAnswer(data, getattr(resp, "model", None) or req.model,
                              latency, usage)


def strip_metadata(data, mimetype):
    """The photo's bytes without its metadata, for the PROVIDER only.

    A phone's JPEG carries EXIF — the GPS position among it — and §1 sends
    no locations. The web app's canvas redraw drops it; a phone or an API
    client uploading the camera's file does not, so it is stripped here, at
    the byte level and without re-encoding: a JPEG loses its APP1–APP15 and
    COM segments, a PNG its text, time and EXIF chunks. The STORED photo is
    untouched — it is kept as it was sent (handoff 61)."""
    if mimetype == "image/jpeg" and data[:2] == b"\xff\xd8":
        out, i, n = bytearray(b"\xff\xd8"), 2, len(data)
        while i + 4 <= n and data[i] == 0xFF:
            marker = data[i + 1]
            if marker == 0xDA:          # start of scan: the rest is image
                out += data[i:]
                return bytes(out)
            length = int.from_bytes(data[i + 2:i + 4], "big")
            segment = data[i:i + 2 + length]
            if not (0xE1 <= marker <= 0xEF or marker == 0xFE):
                out += segment
            i += 2 + length
        return data                     # not a shape we parse: unchanged
    if mimetype == "image/png" and data[:8] == b"\x89PNG\r\n\x1a\n":
        drop = {b"tEXt", b"iTXt", b"zTXt", b"eXIf", b"tIME"}
        out, i, n = bytearray(data[:8]), 8, len(data)
        while i + 12 <= n:
            length = int.from_bytes(data[i:i + 4], "big")
            kind = data[i + 4:i + 8]
            chunk = data[i:i + 12 + length]
            if kind not in drop:
                out += chunk
            i += 12 + length
        return bytes(out)
    return data


def provider_key(provider=PROVIDER_ANTHROPIC):
    """`provider`'s key from the server's environment, or "" when none is
    set — `CADRA_AI_API_KEY` for Anthropic (and for the fake, which needs
    none: what Settings said for it before handoff 68), `CADRA_OPENAI_API_KEY`
    for OpenAI. Read on every call rather than once at import, so the answer is
    whatever the process holds NOW — and a container recreated with the
    variable (`up -d --force-recreate odoo`, or a rollout on the cluster) is
    the only thing that changes it. Returned only to the caller that hands
    it to the provider; nothing serialises it."""
    return (os.environ.get(ENV_KEYS.get(provider, ENV_KEY)) or "").strip()


def provider_for(name, api_key):
    if name == PROVIDER_FAKE:
        return FakeProvider()
    if name == PROVIDER_OPENAI:
        return OpenAIProvider(api_key)
    return AnthropicProvider(api_key)

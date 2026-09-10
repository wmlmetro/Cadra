"""The door: query-parameter parsing that refuses what it cannot read.

Every filter this API publishes used to fail the same way. A value the parser
did not recognise fell through every branch, appended NO domain term, and the
caller received the list it would have received with no filter at all. An
empty list reads as "no matches". **A full list reads as an answer**, and
there is nothing in the response that tells the two apart — so a caller who
mistypes `?is_verified=1` is handed the whole register and told, in effect,
that every asset in it is verified.

That is the failure this module exists to make impossible. An unparseable
value is REFUSED, with a 400 that names the parameter and its accepted
values. `is_tagged` in `v1_assets._list_domain` was the first filter fixed
this way and is the precedent every function here follows.

Purity — and why it is a rule rather than a preference
------------------------------------------------------

**Nothing in this module touches the database, the cursor, the environment or
the request.** These are string-in / value-out functions and they import
nothing.

That is not tidiness. `utils._selection_allowed_values` is the obvious thing
to reuse and it is forbidden here: it calls `cr.rollback()` when it cannot
read a field, because it was written for the error path AFTER a failed write,
where the cursor is already dirty. A read path runs it on the happy path of
every list request, so a transient read failure would roll back a cursor
nothing had asked it to touch. That ruling is landed (docs/DECISIONS.md,
2026-09-06) and it is the reason this module was written rather than that
helper extended.

The accepted values of an enum DO come from the model — a value the model
gains should be accepted the same day — but reading them is the caller's job
(`utils.selection_values`, which reads the registry and never the cursor) and
the result arrives here as a plain list of strings.

`tests/test_query_param_guard.py` enforces the purity, and enforces that
every declared query parameter reaches one of these functions or is named in
a waiver with a reason.
"""

# The accepted spellings of a boolean, and deliberately NOT one spelling
# more. `is_tagged` has published exactly these since handoff 01 and this is
# the target behaviour for every other boolean — widening the set to accept
# `1`/`0`/`yes` would be a second silent reinterpretation of a value the
# caller may have meant as something else, which is the family of bug this
# module closes rather than a smaller version of it.
BOOL_TRUE = ("true", "True", True)
BOOL_FALSE = ("false", "False", False)

# Absent and empty both mean "no filter" everywhere. `"null"` does NOT,
# except where a parameter's published behaviour already says it does — a JS
# caller that stringifies an unset value sends the literal `"null"`, and
# reading that as "unfiltered" hands back the entire register to a poller
# that meant to narrow it.
_ABSENT = (None, "")


class BadFilter(Exception):
    """A query parameter we cannot interpret.

    Raised out of a domain builder and turned into a 400 `invalid_request`
    by the listing endpoint. A bare ValueError would reach the route
    decorator's catch-all and answer 500, which tells an integration to
    retry a request that can never succeed.

    `details` carries the offending value and, where there is a closed set,
    `allowed_values` — so a client can show its user what to type instead of
    guessing from prose.
    """

    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or {}


def _is_absent(raw, null_is_absent):
    if raw in _ABSENT:
        return True
    return bool(null_is_absent) and raw == "null"


def parse_bool(name, raw, *, null_is_absent=False):
    """`true` / `false` → True / False. Absent or empty → None (no filter).

    Anything else is a `BadFilter`. There is no third answer: the branch that
    used to exist — fall through, append nothing, return everything — is the
    defect.

    `null_is_absent` is the leniency `is_tagged` published before this
    module existed and keeps for compatibility. A parameter that has never
    published it does not get it.
    """
    if _is_absent(raw, null_is_absent):
        return None
    if raw in BOOL_TRUE:
        return True
    if raw in BOOL_FALSE:
        return False
    raise BadFilter(
        "`%s` must be `true` or `false`" % name,
        details={name: raw, "allowed_values": ["true", "false"]},
    )


def parse_enum(name, raw, allowed, *, null_is_absent=False):
    """One of `allowed`, or a `BadFilter` naming the whole set.

    `allowed` is a plain iterable of strings supplied by the caller — read
    off the model by `utils.selection_values` at the call site, never read
    here. See the module docstring for why that split is a rule.

    An unrecognised value used to answer `200 []`, which is the more subtle
    half of the same bug: an empty list for a value the caller mistyped is
    indistinguishable from an empty list for a value that genuinely matched
    nothing, and the reassuring reading is the wrong one.
    """
    if _is_absent(raw, null_is_absent):
        return None
    allowed = list(allowed)
    if raw not in allowed:
        raise BadFilter(
            "`%s` must be one of: %s" % (name, ", ".join(allowed)),
            details={name: raw, "allowed_values": allowed},
        )
    return raw


def parse_int(name, raw, *, null_is_absent=True, minimum=None, maximum=None):
    """An integer, or a `BadFilter`. Absent, empty or `"null"` → None.

    The foreign-key filters all used to sit inside `except (TypeError,
    ValueError): pass`, so `?category_id=laptops` dropped the term and
    returned every asset in the register. Same failure as the booleans, one
    type along.

    `"null"` counts as absent by default because that is what the FK filters
    have always done and a client relying on it is sending a request that
    means "no filter", not a request that means something else.
    """
    if _is_absent(raw, null_is_absent):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise BadFilter(
            "`%s` must be an integer" % name, details={name: raw},
        )
    if minimum is not None and value < minimum:
        raise BadFilter(
            "`%s` must be at least %d" % (name, minimum),
            details={name: raw, "minimum": minimum},
        )
    if maximum is not None and value > maximum:
        raise BadFilter(
            "`%s` must be at most %d" % (name, maximum),
            details={name: raw, "maximum": maximum},
        )
    return value


def int_filter_terms(qs, fields):
    """`[(field, '=', int)]` for each of `fields` present in `qs`.

    The five list endpoints each held the same `for fld in (...)` loop with
    the same swallowing `except` inside it. `fields` may be a name or a
    `(query_param, model_field)` pair where the two differ — `location_id`
    on the employees list filters `sap_location_id`, and that translation is
    the only reason the loop was ever written out by hand.
    """
    terms = []
    for entry in fields:
        param, model_field = entry if isinstance(entry, tuple) else (entry, entry)
        value = parse_int(param, qs.get(param))
        if value is not None:
            terms.append((model_field, "=", value))
    return terms

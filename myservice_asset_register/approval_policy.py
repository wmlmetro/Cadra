"""Does a move or a custody change need a second person on this tenant?

WHY THIS EXISTS
---------------
Handoff 35. NRS watched an asset moved between locations on one person's say
-so and asked whether that should need an approver. The owner decided it
should, on by default, switchable per tenant — because the tenants on this
machine include demonstration registers and seeded replicas where a
two-person rule on every write would make the demonstration impossible, and
because NRS will reshape the rule around their own structure later.

HOW IT IS READ, AND WHY THAT IS THE WHOLE POINT
-----------------------------------------------
**Read with SQL, deliberately, and NOT through `get_param`** — the same
decision, for the same measured reason, as `myservice_nrs_base/
database_class.py`, which handoff 35 §C named as the precedent to follow.

`ir.config_parameter.get_param` is `@ormcache`d per worker. Under the
committed ``workers = 2`` the cache is per PROCESS and the invalidation
signal does not reliably reach a worker that is between requests. Handoff 25
did not deduce that; it watched it happen. Its first cut of the test-database
guard used `get_param`, and during its own proof run one worker reported
``database_class = "client"`` for a database whose parameter row had been
DELETED while a second worker answered ``"test"`` for the same instant — and
twenty-four writing tests ran to a green pass against an unmarked database.

The failure here would be the same shape and worse in kind. When this switch
says *off*, an asset moves on one person's say-so. A worker serving *off*
from a cache for a tenant whose row now says *on* is a control that has
stopped applying, silently, in exactly the way nobody audits for. So the
switch asks the database. One row, by primary key, per call: the cost is a
single indexed SELECT and the correctness is the entire point.

ABSENT MEANS ON
---------------
**A value that is neither on nor off is on.** Absent, blank, misspelt,
unreadable — every one of them resolves to *approval required*, and
`REQUIRED_WHEN_UNSET` below says so in one place rather than at each call
site.

That direction is not symmetry-breaking for its own sake. The two ways to be
wrong are not equally bad: a tenant that asks for a second person when it did
not need to has a slower afternoon and a visible, complainable symptom; a
tenant that skips the second person because a parameter was misspelt has no
symptom at all, and discovers it when an auditor asks who authorised a move
and the answer is nobody. `database_class` is fail-closed for the same
reason and says so in the same words.

**There is no bypass flag and no override environment variable**, for the
reason `database_class` gives and which is worth repeating: a flag added for
one legitimate afternoon becomes the way everybody runs by the end of the
month, and then this module never happened. A tenant that should move assets
without a second person sets the parameter, once, deliberately.

WHAT THIS IS NOT
----------------
It is not a permission system. It does not decide WHO may approve — that is
`nrs.asset.change.request` and, ultimately, whatever structure NRS gives us.
It answers one question: on this database, does a person moving an asset or
handing it to somebody else need a second person to agree first.
"""

#: The context key `action_approve` sets while it writes the asset. It is what
#: tells the gate in `nrs.asset._write_recorded` that this particular change
#: HAS been approved — the one legitimate way through.
#:
#: It carries the request's id rather than `True` on purpose: a bare boolean
#: in the context is a claim anybody can make, and the gate re-reads the
#: request by id and checks it is genuinely approved before letting the write
#: past. See `nrs.asset._approval_clears`.
APPROVAL_KEY = 'cadra_approval_id'

#: The context key by which a caller declares that its write is NOT a person
#: deciding to move something, and therefore outside the rule. The value is a
#: short reason, never `True`, so the declaration reads as a sentence at the
#: call site and shows up in a grep as what it is.
#:
#: Every use of this key is in §A's table in the handoff-35 report, with the
#: argument for why that writer is not a move. Adding one is adding a row to
#: that table.
EXEMPT_KEY = 'cadra_approval_exempt'

#: The reasons a first-party caller may give. A value outside this set is
#: treated as no exemption at all — a typo must not open a door that a blank
#: cannot, which is `approval_policy`'s rule applied to the other end.
EXEMPT_REASONS = (
    # `nrs.asset.import` — a bulk file load. Approving eleven thousand rows
    # one at a time is not a control, it is a denial of service against the
    # people operating the register.
    'import',
    # `scripts/*_data_seed.py` — demonstration data. Named rather than
    # silently allowed, so a seed that starts writing a client's register
    # shows up in a search for this constant.
    'seed',
    # `myservice_identity.action_mark_retrieved` — an asset coming BACK from
    # somebody who has left. It takes custody away; it hands it to nobody.
    # There is no second person to ask about an asset returning to the store.
    'clearance',
    # A migration or a backfill, which runs before anybody can approve
    # anything and is not a decision about one asset.
    'migration',
    # `nrs.asset.transfer.action_complete`, AND ONLY when the transfer it is
    # completing carries an approver. That document has its own two-person
    # step — `draft → approved → done`, with an Approve button restricted to
    # `group_asset_manager` that stamps `approved_by` — so a transfer which
    # went through it has already had its second person, and asking for
    # another would be asking twice for the same decision.
    #
    # **The condition is the whole of it.** `action_complete` has no state
    # precondition in the model: the button is only shown on an `approved`
    # transfer, but the method can be called on a `draft` one from a shell
    # or a server action. Exempting the SOURCE wholesale would therefore
    # have turned "create a transfer and complete it" into a way round the
    # rule — a door of exactly the kind report 30 found when a disposed
    # asset could be un-disposed through a route nobody had looked at. So
    # the caller declares this only when `approved_by` is set, and an
    # unapproved completion meets the gate like any other write.
    'transfer',
    # An automated test declaring, per call, that it is writing a fixture.
    # Per CALL and never globally: `database_class.py` explains at length why
    # a bypass flag becomes the way everybody runs by the end of the month.
    'test',
)


PARAM = "cadra.approval.required"

ON = "on"
OFF = "off"

#: Every value a person may set. Anything else is treated exactly as absent —
#: a typo must not be able to open a door that a blank cannot.
VALUES = (ON, OFF)

#: What an absent, blank or unrecognised value means. Named rather than
#: written as a bare `True` at the one call site, because this is the
#: decision, not an implementation detail of reading a row.
REQUIRED_WHEN_UNSET = True


def approval_setting(env):
    """The raw value recorded in THIS database, or None if absent/unknown.

    Separate from `approval_required` below so a diagnostic endpoint can tell
    *"this tenant has deliberately set `off`"* from *"this tenant has never
    been configured and is getting the default"*. Those are the same
    behaviour and very different facts, and a settings screen that cannot
    distinguish them cannot tell an administrator whether anyone has ever
    thought about it.
    """
    env.cr.execute(
        "SELECT value FROM ir_config_parameter WHERE key = %s", (PARAM,))
    row = env.cr.fetchone()
    value = ((row[0] if row else "") or "").strip().lower()
    return value if value in VALUES else None


def approval_required(env):
    """True when a move or a custody change on this tenant needs approval."""
    setting = approval_setting(env)
    if setting is None:
        return REQUIRED_WHEN_UNSET
    return setting == ON


def set_command(dbname, value=OFF):
    """The exact command an administrator runs to set the switch.

    Printed inside the refusal a gated write raises, for the reason
    `database_class.mark_command` exists: an error that names a remedy the
    reader then has to go and look up is worse than one that names none,
    because it implies the lookup will be quick.

    **Deliberately not an API call.** The people this control constrains are
    exactly the people holding `settings:write` — `assets:write`,
    `approvals:write` and `settings:write` are all granted by the single
    group `group_asset_manager`. A control its own subject can switch off,
    act, and switch back on is not a control; it is a speed bump with an
    audit trail nobody reads. `GET /api/v1/settings/approvals` publishes the
    value so a screen can explain itself; nothing over the API sets it.
    """
    return (
        "docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \\\n"
        "  odoo shell -c /etc/odoo/odoo.conf -d %s --no-http \\\n"
        "  --http-port=8099 --gevent-port=8098 <<< \\\n"
        "  \"env['ir.config_parameter'].sudo().set_param('%s', '%s'); env.cr.commit()\""
        % (dbname, PARAM, value)
    )

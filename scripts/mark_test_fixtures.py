"""Mark the test-suite artefacts sitting in a tenant's register for what they are.

    docker compose -f docker-compose.yml -f docker-compose.19.yml exec -T odoo \
      odoo shell -c /etc/odoo/odoo.conf -d jaizbankplc \
      --http-port=8099 --gevent-port=8098 --no-http \
      < scripts/mark_test_fixtures.py

WHY THIS EXISTS
---------------
Handoff 24 §B measured what a test run writes and into which database. The
answer, on this machine:

  * The HTTP suite runs against whatever `CADRA_API_BASE` names, and the only
    tenant carrying a full `CLIENT_ID`/`CLIENT_SECRET` pair is `jaizbankplc` —
    a replica of a live client's register. There is no guard of any kind: no
    allowlist, no refusal, no confirmation. The suite reads one environment
    variable and writes wherever it points.
  * It has no teardown, by documented policy, and it could not have one: the
    API publishes exactly one DELETE route (asset categories) and none for
    assets, locations, requests, custody links or disposals.
  * Measured on 2026-09-15: 3,584 of 4,056 assets (88%) named `pytest-*`,
    accumulating daily since 2026-08-26; 413 of 569 chain-of-custody rows on
    fixture assets; 354 of 420 entries in the PUBLIC homepage location
    dropdown; and six fabricated approved disposals sitting in the
    auditor-facing disposal report.

No real asset carries a fabricated approval or a fabricated custody link, and
nothing ever reached the production host — every captured response in
`docs/api/test-responses/` names `jaizbankplc.localhost:8069`.

WHAT THIS SCRIPT DOES, AND WHAT IT DELIBERATELY DOES NOT
--------------------------------------------------------
It does two things:

1. Sets `is_test_credential` on the `Handoff23 Approver` client. The repo
   already has the right convention for this — `myservice.api.client.
   is_test_credential` drives `nrs.asset.custody.source = 'test'`, so links
   written under a test credential say so on their face. The custody chain is
   honest because of it: 330 of its rows self-label. That credential was
   created with the flag off, which is why the approvals it authorised are the
   one class of artefact a reader cannot identify from the record itself.

2. Appends a disclosure to the `disposal_reason` of every fabricated approved
   disposal, so the auditor-facing disposal report shows them for what they
   are rather than listing them beside real ones.

**It does not un-approve anything, and that is deliberate.** Disposal approval
is not reversible by any action in this system: there is no
`action_unapprove_disposal`, a second approval is a published 409, the
approver fields are read-only over the API, and the button hides itself once
an approver exists. It is correctable only by a human on the Odoo form, where
`disposal_approved_by` is tracked and the correction leaves a trail — which is
the design `asset_disposal.py` argues for explicitly: "a genuine correction is
made on the form and leaves a trail; a button that quietly replaces one name
with another does not."

Fabricating a reversal would be the same defect as the fabricated approval,
one step further on. Marking is the honest answer; erasing is not.

Re-running is safe: both changes are idempotent.
"""

DISCLOSURE = (
    "[TEST FIXTURE — not a real disposal. Created by the automated test "
    "suite against a development replica; the approval is a fixture and "
    "authorises nothing. Disclosed in handoff 24.]"
)

Client = env['myservice.api.client'].sudo()          # noqa: F821 — odoo shell
Asset = env['nrs.asset'].sudo()                      # noqa: F821 — odoo shell

approver = Client.search([('name', '=', 'Handoff23 Approver')])
for client in approver:
    if not client.is_test_credential:
        client.write({'is_test_credential': True})
        print("marked credential %r as a test credential" % client.name)
    else:
        print("credential %r already marked" % client.name)

fixtures = Asset.search([
    ('disposal_approved_by', '!=', False),
    '|', ('name', 'like', 'pytest-%'), ('name', 'like', 'H23%'),
])
print("fabricated approved disposals found: %d" % len(fixtures))
for asset in fixtures:
    reason = asset.disposal_reason or ''
    if DISCLOSURE in reason:
        print("  %-6s %-32s already disclosed" % (asset.id, asset.name[:32]))
        continue
    asset.write({'disposal_reason': (reason + '\n' + DISCLOSURE).strip()})
    print("  %-6s %-32s marked (approver %s)"
          % (asset.id, asset.name[:32], asset.disposal_approved_by.login))

env.cr.commit()                                      # noqa: F821 — odoo shell
print("committed")

"""Mark the smoke-test credential as one, on every tenant that has it.

`is_test_credential` decides whether a chain-of-custody link written under a
credential says `source: test`. The flag is new, so every existing client row
is False — including the one the API test suite authenticates with, which is
the only row it was invented for.

`bootstrap.py` sets it on a run, but a tenant is not re-bootstrapped as part
of a module upgrade and the fan-out is per database. Without this the label
would start applying on whichever tenants happened to be bootstrapped next,
which is the same as not applying: a reader could not tell whether an
unlabelled link means "not a test" or "this tenant has not been through
bootstrap yet".

Matched on `client_id`, not on name — a name is edited from the form and a
client_id is the credential. `CADRA_TEST_CLIENT_ID` can rename it in an
unusual deployment; such a tenant gets the flag from its next bootstrap run
and is not silently wrong in the meantime, because there is nothing to be
wrong about until that credential writes a custody link.

Historic links are NOT relabelled. `nrs.asset.custody` refuses `write`, and
that refusal is the model's entire value — a migration that made an exception
for itself would be the first hole in an append-only record. The links this
credential wrote before today keep `api_transfer` and carry
`test_custody._build_a_chain` in their reason, which is where report 14 found
them.
"""
import logging

_logger = logging.getLogger(__name__)

TEST_CLIENT_IDS = ("test_client",)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE myservice_api_client
           SET is_test_credential = TRUE
         WHERE client_id IN %s
           AND COALESCE(is_test_credential, FALSE) IS FALSE
        """,
        (TEST_CLIENT_IDS,),
    )
    _logger.info(
        "myservice_api: %s marked as a test credential on %s — its future "
        "custody links will read `source: test`.", cr.rowcount, cr.dbname)

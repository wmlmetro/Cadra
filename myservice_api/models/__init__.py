from . import api_client
from . import api_idempotency
from . import api_refresh_token
from . import registry_diagnostics
from . import append_only
from . import asset_history
from . import test_fixture
from . import access_change
from . import access_recorder
# AFTER the recorder, so the guard WRAPS it: a refused change is judged on
# the diff the recorder also sees, and the exception takes its rows back.
from . import access_guard
# Handoff 58 §5: the role combinations nobody may be granted (Addendum A §4,
# rule 2). After the guard, which it imports, and judged after it.
from . import role_exclusion
from . import audit_access
# Handoff 43: the door (`b2b` as a constant), the letters, the host-correct
# link and the invitation stamps on `res.users`.
from . import invitation
from . import audit_configuration
# Handoff 45 §2.2: no Odoo session for a non-administrator on any
# `auth='user'` route — the half of the back-office door a controller cannot
# shut (JSON-RPC sign-in, the portal, the ORM over RPC).
from . import backoffice_session

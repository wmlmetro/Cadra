from . import v1
from . import v1_locations
from . import v1_assets
from . import v1_fleet
from . import v1_requests
from . import v1_identity
from . import v1_brand
from . import v1_settings
from . import v1_meta
from . import v1_audit
# Handoff 35 — the approval queue.
from . import v1_approvals
# Handoff 38 — tag labels: the serial lookup's sibling, and a faded tag's
# replacement over HTTP.
from . import v1_tags
# Handoff 41 — who has what: the accounts on a tenant and the roles they
# hold, direct and effective. Read only.
from . import v1_users
# Handoff 45 — the first five minutes: an invitation or a reset redeemed in
# the app, and the back office shut to everybody who is not a system
# administrator.
from . import v1_signup
# Handoff 48 — which sidebar items this tenant shows. Presentation, not
# permission.
from . import v1_sidebar
# Handoff 57 — the receipt gates (SCAFFOLDING, replaced by handoff 58).
from . import v1_gates
from . import backoffice

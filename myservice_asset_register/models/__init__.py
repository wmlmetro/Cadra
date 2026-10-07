# The append-only guard first: custody, movement and the event record all
# `_inherit` it, and a model cannot be built before the mixin it names.
from . import append_only
from . import asset_custody
from . import asset_movement
from . import asset_event
from . import asset
from . import asset_transfer
# After `asset_custody`, `asset_movement` and `asset_event`, whose context
# keys it imports, and after `asset_transfer`, which an approved location
# request creates. Handoff 35.
from . import asset_change_request
# The append-only record of a pending request being re-pointed at somebody
# else (handoff 45). Inherits the guard in `append_only`, imported first.
from . import asset_change_request_renomination
from . import asset_pm
from . import asset_tag
from . import asset_import
from . import asset_sap
# Both `_inherit = 'nrs.asset'`, so they must load after `asset`.
from . import asset_disposal
from . import asset_snapshot
# Handoff 57 SCAFFOLDING (replaced by handoff 58): the receipt gates on
# `nrs.asset`. Last, because it overrides `asset_tag`'s `_generate_tag` and
# the label's `_mark_affixed`.
from . import asset_gates

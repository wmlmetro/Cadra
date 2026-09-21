# The append-only guard first: custody, movement and the event record all
# `_inherit` it, and a model cannot be built before the mixin it names.
from . import append_only
from . import asset_custody
from . import asset_movement
from . import asset_event
from . import asset
from . import asset_transfer
from . import asset_pm
from . import asset_tag
from . import asset_import
from . import asset_sap
# Both `_inherit = 'nrs.asset'`, so they must load after `asset`.
from . import asset_disposal
from . import asset_snapshot

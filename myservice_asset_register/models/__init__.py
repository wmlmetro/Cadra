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

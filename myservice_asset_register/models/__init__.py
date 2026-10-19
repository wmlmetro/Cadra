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
# Section 12 — how a received unit is identified, per class (handoff 58).
# Before the gates, whose `create` calls its receipt check.
from . import asset_identification
# The receipt gates on `nrs.asset` (handoff 57, kept by 58). Last, because it
# overrides `asset_tag`'s `_generate_tag` and the label's `_mark_affixed`.
from . import asset_gates
# Handoff 61 §7 — `generic.location.location_code`, the room code a label
# carries.
from . import location_code
# Handoff 61 §5 — photos on an asset, append-only. After the mixin and the
# event record, both of which it uses.
from . import asset_photo
# Handoff 64 — what a photo was said to show (R11), append-only, and the
# photo held for an asset that does not exist yet. After the photo, whose
# checks and writer it uses.
from . import ai_suggestion
# Handoff 63 — the SAP mirror: SAP's asset master as a read-only reference
# table, its streamed import and the matcher. After `serial_placeholders`'
# users and `asset_sap` (the SAP number it links on); imports nothing else.
from . import sap_mirror
# Handoff 65 — the link of a register asset to its SAP record, by two
# people, and the duplicate flag. After the mirror (its matcher and link
# join) and the gates (the no-two-gates rule it reuses).
from . import sap_link
# Handoff 66 — devices, the code ledger, blocks, campaigns and captures. Last:
# it extends `nrs.asset.create` and `_gate_move` (the gates) and the label's
# `_may_decide` (the tag model).
from . import audit_capture

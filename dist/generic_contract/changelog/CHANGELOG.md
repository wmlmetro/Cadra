# Changelog

## Version 2.0.0

Merged `generic_contract_service` module to `generic_contract`.
The reason for this is that contract without services does not have sense,
and this could significantly simplify logic related to contracts,
avoiding development of variety of integration addons that combine contracts, services, and something else.


## Version 1.7.0

Start using Generic System Events, to generate system events for contracts.
Currently, following events will be generated:
- Contract Confirmed
- Contract Activated
- Contract Closed
- Contract assignee changed


## Version 1.0.0

Subcontracts removed from the generic_contract.


## Version 0.20.0

Subcontracts are optional now and are not enabled by default.
This feature have to be enabled in Settings menu.


## Version 0.14.0

- Added tags to contracts
- Inherit contract from `generic.mixin.transaction.utils`.
  This is used in invoicing module,
   and possibly could be useful in other modules.


## Version 0.11.0

Manager can covert active contract to draft (to be able to edit it).


## Version 0.10.0

- Added action button to create contract directly from contract template
- Fixed bug with unexpectedly closed (by scheduler) contracts that have no end date


## Version 0.9.0

- Changed default sequences for contracts to:
  "SS%(year)s%(month)s-" and "CS%(year)s%(month)s-"
- Contract description field now can contains HTML
- By default search only for open contracts
- Do not prefix contracts created from templates with `From template: `.
  Just use name of template instead


## Version 0.8.0

Changed access rights:
- *Generic Contract User (Implicit)* has read-only access rights,
  but does not has access for menu 'Contracts'.
- *Generic Contract User (Read Only)* has read-only access rigths,
  can see menu *Contracts*.
- *Generic Contract User* has read / write / create access rights.
- *Generic Contract Manager*  has full access on contracts.


## Version 0.7.0

Added *Confirm All* button for contract to confirm contract with subcontracts
in same action



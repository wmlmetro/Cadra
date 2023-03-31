Merged `generic_contract_service` module to `generic_contract`.
The reason for this is that contract without services does not have sense,
and this could significantly simplify logic related to contracts,
avoiding development of variety of integration addons that combine contracts, services, and something else.

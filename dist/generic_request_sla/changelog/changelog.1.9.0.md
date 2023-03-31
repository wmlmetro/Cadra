- Added new public method ```get_sla_control_by_code``` on
  ```request.request``` model, that could be used to obtain instance of
  ```request.sla.control``` by its code.
  This could be used in emails, if you need to show warn/limit time for
  specific SLA rule.
- Improved UI/UX of *SLA Rule Type*: Show there list of SLA rules of this type.
  Thus, now it is possible to edit SLA rules from SLA Rule Type forms too.
- During adding SLA Rule, when SLA Rule type selected, the SLA Rule's name and
  code will be updated automatically.

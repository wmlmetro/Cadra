Added new option for computation of SLA on request.
Before this change, the SLA state and SLA dates on request were computed based on
so called *Main SLA rule* that was defined on *Request Type* level.
Now, there new option *SLA Compute Type* added on *Request Type* form view,
that could be one of (*Main SLA Rule*, *Least Date Worst Status*).
In case when *Main SLA Rule* selected (the default one), everything will go old way.
In case when *Least Date Worst Status* selected, new logic will be applies:
    - Worst SLA status of all SLA Control lines will be set on request
    - The minimal SLA dates will be set on request.

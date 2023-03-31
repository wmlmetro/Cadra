Changes in the work in Policy Rule for such
types of 'Team Leader', 'Team Task Manager' and 'Team Member'.
Now, when, according to the rule, a team member or team leader or
team task manager is not found, then the rule will be skipped and next rule
will be applied.

This fixes an error when, for example:
When applying a policy with two or more rules, the first rule has the type
'Team Member' and does not find a team member, but the returned value
of the team leads to an assignment error - the object is assigned to a team
instead of a team member (or should remain unassigned of the corresponding
member is not found). And it also prevents the next rule in the list from
applying.

**Note, that this is change will change how existing rules work.
So, double check your assignments configuration before applying this changes.**

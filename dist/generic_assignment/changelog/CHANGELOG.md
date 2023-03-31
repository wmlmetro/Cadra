# Changelog

## Version 1.24.0

Added functionality that allows you to configure the automatic removal from the followers at the request of a previosly assigned user.
(Request FR2211959)


## Version 1.10.0

- Improved assignment policy type *Assign by related policy*:
   - Added ability to sort filtered records by selected field
   - Added ability to choose sort order
   - Thus it is possible to select first record from sorted list, that could be
     used to assign to least loaded user
- Improved assignment policy type *User field*:
   - Now it is possible to search for user in Many2many and One2many fields
   - Added ability to select (random or first) user for field (one2many or many2many)
   - Added ability to filter user by conditions
   - Added ability to sort selected users before selection, thus it is possible to select for example least loaded user


## Version 1.9.0

Added integration with server actions. So no, assignment policies could be easily run via server actions.
For example, with this update, you can easily change responsible user of lead, when lead's country is changed.


## Version 1.8.0

- Added ability to assign multiple objects
- Added ability to dynamically create context action for target model.
  This makes it useful in such apps like CRM or Project.


## Version 1.7.0

- Added ability to edit assignment rules on assignment policy page
- Add onchange to cleanup rules when policy models changed


## Version 1.6.0

Added ability to add comment when assigning user via assign wizard


## Version 1.3.20

- Unify algorithm that choose records from a set
- Random improvement: use SystemRandom + Shuffle before choice



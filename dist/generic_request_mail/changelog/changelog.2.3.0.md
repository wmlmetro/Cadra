Added new configuration options to mail sources:
- Mask email address: configure when to use address of mail source as *From* header in email
- Mask email author's name: configure when system have to replace name of author of email when sending notifications.

Both options could have the following values:
- None
- Internal
- All

This way we can hide only internal users behind mail source's name and address,
or all.
Also, it is possible to hide all email addresses behind mail source's address,
but show name of the user who have sent email in *From* header of mail message.

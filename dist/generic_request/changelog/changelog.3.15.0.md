Added few warnings to wizard that pops-up when user stop tracking time.
- In case when amount to be logged is between 8 and 12 hour,
  the yellow warning will be shown, that asks user to check if entered amount is correct.
- In case when amount to be logged is greater than 12 hours,
  then danger (red) warning will be shown, that asks user to double-check entered amount.
- When user starts work on new request, but have unfinished work
  (time tracking started, but not completed) on other request,
  then warning will be shown, that asks user to carefully review info in wizard,
  noting, that this is wizard related to unfinished request.

This should help to reduce amount if incorrectly logged time.

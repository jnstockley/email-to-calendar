# E-Mail to calendar Converter
The point of this application is to search an IMAP account, look for emails based on certain criteria(s), and parse 
the content, using regex, and automatically create calendar events in an iCal account.

## TO-DO
- [X] Get e-mails, and save ID to sqlite db to avoid duplicates
- [X] Save calendar events to sqlite db to avoid duplicates
- [X] Add config to backfill (check all emails from an optional certain date), or use most recent email
  - [X] If using most recent, when new email arrives, remove events not present, and add new ones
- [ ] If new email comes in with updated events, update event in calendar instead of creating a new one
- [ ] Using email summary check for words like `Cancelled`, etc. to delete events
- [ ] If event already exists, check if details have changed, and update if necessary
- [ ] Investigate IMAP IDLE (push instead of poll)
- [X] Make sure all day events are handled correctly


## Environment Variables
| Name | Description | Type | Default Value | Allowed Values |
|------|-------------|------|---------------|----------------|
|      |             |      |               |                |
|      |             |      |               |                |
|      |             |      |               |                |

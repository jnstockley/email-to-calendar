# E-Mail to calendar Converter
The point of this application is to search an IMAP account, look for emails based on certain criteria(s), and parse 
the content, using regex, and automatically create calendar events in an iCal account.

## TO-DO
- [ ] Get e-mails, and save ID to sqlite db to avoid duplicates
- [ ] Save calendar events to sqlite db to avoid duplicates
- [ ] Parse e-mail using user defined regex
- [ ] Add config to backfill (check all emails from an optional certain date), or use most recent email
  - [ ] If using most recent, when new email arrives, remove events not present, and add new ones

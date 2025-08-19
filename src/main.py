import os

from src.mail import mail


def main():
    host = os.environ["IMAP_HOST"]
    port = int(os.environ["IMAP_PORT"])
    username = os.environ["IMAP_USERNAME"]
    password = os.environ["IMAP_PASSWORD"]

    from_email = os.environ["FILTER_FROM_EMAIL"]
    subject = os.environ["FILTER_SUBJECT"]
    backfill: bool = os.environ.get("FILTER_BACKFILL", "false").lower() == "true"

    client = mail.authenticate(host, port, username, password)
    emails = mail.get_emails_by_filter(client, from_email=from_email, subject=subject)
    print(emails)


if __name__ == "__main__":
    main()
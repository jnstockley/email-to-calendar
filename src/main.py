import os
import ssl
import sys
import imaplib
import email
from email.policy import default
from typing import Optional


def get_env(name: str) -> str:
    try:
        return os.environ[name]
    except KeyError:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)


def connect_imap(host: str, port: int, user: str, password: str) -> imaplib.IMAP4_SSL:
    try:
        client = imaplib.IMAP4_SSL(host, port)
        client.login(user, password)
        return client
    except imaplib.IMAP4.error as e:
        print(f"IMAP authentication/connection failed: {e}", file=sys.stderr)
        sys.exit(2)

def connect_imap_starttls(host: str, port: int, user: str, password: str) -> imaplib.IMAP4:
    try:
        client = imaplib.IMAP4(host, port)
    except imaplib.IMAP4.error as e:
        print(f"IMAP connection (plain) failed: {e}", file=sys.stderr)
        sys.exit(2)

    # Get capabilities before STARTTLS
    typ, caps = client.capability()
    if typ != "OK":
        print("Failed to get capabilities prior to STARTTLS", file=sys.stderr)
        client.shutdown()
        sys.exit(2)

    # Normalize capabilities list to strings
    cap_set = {c.decode().upper() for c in caps}

    if "STARTTLS" not in cap_set:
        print("Server does not advertise STARTTLS capability", file=sys.stderr)
        client.shutdown()
        sys.exit(2)

    context = ssl.create_default_context()
    try:
        client.starttls(context)
    except (imaplib.IMAP4.error, ssl.SSLError) as e:
        print(f"STARTTLS negotiation failed: {e}", file=sys.stderr)
        client.shutdown()
        sys.exit(2)

    # (Re)fetch capabilities after STARTTLS if needed (some servers change them)
    client.capability()

    try:
        client.login(user, password)
    except imaplib.IMAP4.error as e:
        print(f"IMAP authentication failed: {e}", file=sys.stderr)
        client.shutdown()
        sys.exit(2)

    return client


def pick_best_text(part_msg: email.message.EmailMessage) -> Optional[str]:
    if part_msg.is_multipart():
        # Prefer text/plain over text/html
        plain = None
        html = None
        for part in part_msg.iter_parts():
            ctype = part.get_content_type()
            if ctype == "text/plain" and plain is None:
                plain = part.get_content()
            elif ctype == "text/html" and html is None:
                html = part.get_content()
        return plain or html
    else:
        if part_msg.get_content_type() in ("text/plain", "text/html"):
            return part_msg.get_content()
    return None


def main():
    host = get_env("IMAP_HOST")
    port = int(get_env("IMAP_PORT"))
    username = get_env("IMAP_USERNAME")
    password = get_env("IMAP_PASSWORD")

    client = connect_imap(host, port, username, password)

    try:
        status, _ = client.select("INBOX")
        if status != "OK":
            print("Failed to select INBOX", file=sys.stderr)
            sys.exit(4)

        from_address = get_env("IMAP_FROM")
        subject = get_env("IMAP_SUBJECT")

        # Use RFC compliant FROM search
        status, data = client.search(None, f'FROM "{from_address}" SUBJECT "{subject}" SINCE 01-Aug-2025')
        if status != "OK":
            print("Search failed", file=sys.stderr)
            sys.exit(5)

        ids = data[0].split()
        if not ids:
            print("No messages found.")
            return

        # Iterate newest first
        for msg_id in reversed(ids):
            status, fetched = client.fetch(msg_id, "(BODY[])")
            if status != "OK" or not fetched or fetched[0] is None:
                print(f"Failed to fetch message id {msg_id.decode()}", file=sys.stderr)
                continue

            raw = fetched[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                print(f"Unexpected raw payload type for id {msg_id.decode()}", file=sys.stderr)
                continue

            msg = email.message_from_bytes(raw, policy=default)
            body = pick_best_text(msg) or "(No printable text body)"
            print("=" * 60)
            print(f"ID: {msg_id.decode()}")
            print(f"Subject: {msg.get('subject', '')}")
            print(f"From: {msg.get('from', '')}")
            print(f"To: {msg.get('to', '')}")
            print("-" * 60)
            print(body.strip())
            print()

    finally:
        try:
            client.close()
        except imaplib.IMAP4.error:
            pass
        client.logout()


if __name__ == "__main__":
    main()
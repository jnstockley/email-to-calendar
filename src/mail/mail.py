import imaplib
from datetime import datetime
import email
from email.policy import default
from email.utils import parsedate_to_datetime
from typing import Optional

from src import logger
from src.model.email import EMail


def authenticate(host: str, port: int, user: str, password: str, ssl: bool = True):
    """
    Authenticate to the user's IMAP server to retrieve emails.
    """
    if ssl:
        client = __connect_imap_ssl(host, port, user, password)
    else:
        client = __connect_imap_starttls(host, port, user, password)
    return client


def get_emails_by_filter(
    client: imaplib.IMAP4 | imaplib.IMAP4_SSL,
    from_email: str = None,
    subject: str = None,
    since: datetime = None,
    mailbox: str = "INBOX",
):
    search_str: str = ""
    if from_email:
        search_str += f'FROM "{from_email}" '
    if subject:
        search_str += f'SUBJECT "{subject}" '
    if since:
        search_str += f"SINCE {since.strftime('%d-%b-%Y')} "
    if not search_str:
        logger.error("At least one filter (from_email or subject) must be provided")
        raise ValueError("At least one filter (from_email or subject) must be provided")

    status, _ = client.select(mailbox)
    if status != "OK":
        logger.error(f"Failed to select mailbox '{mailbox}': {status}")
        raise ConnectionError(f"Failed to select mailbox '{mailbox}': {status}")

    status, data = client.search(None, search_str.strip())
    if status != "OK":
        logger.error(f"Failed to search emails: {data}")
        raise ValueError(f"Failed to search emails: {data}")

    email_ids: list[str] = data[0].split()
    if not email_ids:
        return []

    emails: list[EMail] = []

    for email_id in reversed(email_ids):
        raw = __get_email(client, email_id)

        msg = email.message_from_bytes(raw, policy=default)
        email_type, body = __pick_best_text(msg)
        emails.append(
            EMail(
                id=int(email_id.decode()),
                subject=msg.get("subject", ""),
                from_address=msg.get("from", ""),
                delivery_date=parsedate_to_datetime(msg.get("date")),
                body=body or "(No printable text body)",
                email_type=email_type.upper() or "PLAIN",
            )
        )
    return emails


def __connect_imap_ssl(host: str, port: int, user: str, password: str):
    try:
        client = imaplib.IMAP4_SSL(host, port)
        client.login(user, password)
        return client
    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP authentication failed: {e}")
        raise ConnectionError(f"IMAP authentication/connection failed: {e}")


def __connect_imap_starttls(host: str, port: int, user: str, password: str):
    import ssl

    try:
        client = imaplib.IMAP4(host, port)
    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP connection failed: {e}")
        raise ConnectionError(f"IMAP connection (plain) failed: {e}")

    # Get capabilities before STARTTLS
    typ, caps = client.capability()
    if typ != "OK":
        logger.error("Failed to get IMAP capabilities prior to STARTTLS")
        raise ConnectionError("Failed to get capabilities prior to STARTTLS")

    # Normalize capabilities list to strings
    cap_set = {c.decode().upper() for c in caps}

    if "STARTTLS" not in cap_set:
        logger.error("Server does not advertise STARTTLS capability")
        raise ConnectionError("Server does not advertise STARTTLS capability")

    context = ssl.create_default_context()
    try:
        client.starttls(context)
    except (imaplib.IMAP4.error, ssl.SSLError) as e:
        logger.error(f"STARTTLS negotiation failed: {e}")
        raise ConnectionError(f"STARTTLS negotiation failed: {e}")

    # (Re)fetch capabilities after STARTTLS if needed (some servers change them)
    client.capability()

    try:
        client.login(user, password)
        return client
    except imaplib.IMAP4.error as e:
        logger.error("IMAP authentication failed: %s", e)
        raise ConnectionError(f"IMAP authentication failed: {e}")


def __pick_best_text(part_msg: email.message.EmailMessage) -> tuple[str | None, str]:
    email_type = None
    if part_msg.is_multipart():
        plain = None
        html = None
        for part in part_msg.iter_parts():
            ctype = part.get_content_type()
            if ctype == "text/plain" and plain is None:
                plain = part.get_content()
                email_type = "plain"
            elif ctype == "text/html" and html is None:
                html = part.get_content()
                email_type = "plain"
        return email_type, (plain or html)
    else:
        if part_msg.get_content_type() in ("text/plain", "text/html"):
            email_type = part_msg.get_content_type().replace("text/", "")
            content = part_msg.get_content()
            return email_type, content
    return email_type, ""


def __get_email(client: imaplib.IMAP4 | imaplib.IMAP4_SSL, email_id: str) -> bytes:
    raw = __fetch_first_bytes(client, email_id, "(RFC822)")
    if raw is None:
        logger.debug("Fetching full email failed, trying BODY[]")
        raw = __fetch_first_bytes(client, email_id, "(BODY[])")
    if raw is None:
        logger.error(f"Failed to fetch email with ID {email_id}")
        raise ValueError(f"Failed to fetch email with ID {email_id}")
    return raw


def __fetch_first_bytes(client, email_id: str, spec: str) -> Optional[bytes]:
    status, msg_data = client.fetch(email_id, spec)
    if status != "OK" or not msg_data:
        return None
    for part in msg_data:
        if (
            isinstance(part, tuple)
            and len(part) > 1
            and isinstance(part[1], (bytes, bytearray))
        ):
            return part[1]
    return None

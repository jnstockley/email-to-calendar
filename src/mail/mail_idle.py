import time
import re
import email
from email import policy
from imapclient import IMAPClient


def idle_print_emails(
    host,
    port,
    username,
    password,
    folder="INBOX",
    idle_timeout=30,
    payload_timeout=30,
    retry_interval=1,
):
    """
    Connects to IMAP server, enters IDLE loop and prints new messages to console.
    Only prints a message once its payload is actually available. Retries fetching
    the payload for up to `payload_timeout` seconds (checking every `retry_interval` seconds).
    """

    processed_uids = set()

    def extract_text(msg):
        if msg.is_multipart():
            for part in msg.walk():
                if (
                    part.get_content_type() == "text/plain"
                    and part.get_content_disposition() != "attachment"
                ):
                    return part.get_content()
            for part in msg.walk():
                if (
                    part.get_content_type() == "text/html"
                    and part.get_content_disposition() != "attachment"
                ):
                    return part.get_content()
            return ""
        else:
            return msg.get_content()

    def _raw_from_fetch_entry(data):
        # fetch response keys vary; try common ones
        for key in (
            b"BODY.PEEK[]",
            "BODY.PEEK[]",
            b"BODY[]",
            "BODY[]",
            b"RFC822",
            "RFC822",
        ):
            raw = data.get(key)
            if raw:
                return raw
        return None

    def fetch_payload_with_retry(client, uid):
        start = time.time()
        while time.time() - start < payload_timeout:
            try:
                fetch_data = client.fetch([uid], ["BODY.PEEK[]", "FLAGS"])
            except Exception:
                # transient fetch error, wait and retry
                time.sleep(retry_interval)
                continue

            entry = fetch_data.get(uid) or fetch_data.get(int(uid)) or {}
            raw = _raw_from_fetch_entry(entry)
            if raw:
                # normalize
                if isinstance(raw, tuple):
                    raw = raw[1]
                if isinstance(raw, str):
                    raw = raw.encode()
                return raw
            # not yet present, wait and retry
            time.sleep(retry_interval)
        return None

    def process_uids(client, uids):
        for uid in uids:
            if uid in processed_uids:
                continue
            raw = fetch_payload_with_retry(client, uid)
            if not raw:
                # payload never became available within timeout; skip printing
                print(
                    f"UID {uid}: payload not available after {payload_timeout}s, skipping."
                )
                continue
            try:
                msg = email.message_from_bytes(raw, policy=policy.default)
            except Exception as e:
                print(f"UID {uid}: failed to parse message bytes:", e)
                processed_uids.add(uid)
                continue

            subject = msg.get("Subject", "(no subject)")
            _from = msg.get("From", "(no from)")
            _to = msg.get("To", "(no to)")
            date = msg.get("Date", "(no date)")
            body = extract_text(msg) or "(no body)"

            print("----- MESSAGE START -----")
            print("UID:", uid)
            print("From:", _from)
            print("To:", _to)
            print("Date:", date)
            print("Subject:", subject)
            print("Body:\n", body)
            print("----- MESSAGE END -------")

            processed_uids.add(uid)

    with IMAPClient(host, port, use_uid=True, ssl=True) as client:
        client.login(username, password)
        client.select_folder(folder)
        print("Connected and monitoring folder:", folder)

        try:
            while True:
                print("Entering IDLE...")
                started_idle = False
                try:
                    client.idle()
                    started_idle = True
                except Exception as e:
                    # servers can send unsolicited FETCH while entering IDLE; extract UIDs and process
                    msg = str(e)
                    print("IDLE start error (handled):", msg)
                    found = re.findall(r"UID (\d+)", msg)
                    if found:
                        uids = [int(x) for x in found]
                        print("Processing UIDs from unsolicited response:", uids)
                        process_uids(client, uids)

                responses = []
                if started_idle:
                    try:
                        responses = client.idle_check(timeout=idle_timeout)
                    finally:
                        try:
                            client.idle_done()
                        except Exception as e:
                            print("Failed to exit IDLE:", e)

                if responses:
                    print("Server notifications:", responses)
                    uids_from_responses = []
                    for resp in responses:
                        try:
                            if (
                                isinstance(resp, tuple)
                                and len(resp) >= 3
                                and resp[1] in (b"FETCH", "FETCH")
                            ):
                                nested = resp[2]
                                if isinstance(nested, tuple):
                                    for i in range(len(nested)):
                                        if nested[i] == b"UID" or nested[i] == "UID":
                                            maybe_uid = nested[i + 1]
                                            uids_from_responses.append(int(maybe_uid))
                        except Exception:
                            continue

                    if uids_from_responses:
                        process_uids(client, uids_from_responses)
                    else:
                        # fallback: search for UNSEEN messages
                        try:
                            uids = client.search(["UNSEEN"])
                            if not uids:
                                print("No unseen messages found.")
                            else:
                                print(f"Found {len(uids)} unseen message(s): {uids}")
                                process_uids(client, uids)
                        except Exception as e:
                            print("Error fetching or parsing messages:", e)

                time.sleep(1)
        except KeyboardInterrupt:
            print("Interrupted by user, closing connection.")
        except Exception as e:
            print("Error in IDLE loop:", e)
            raise

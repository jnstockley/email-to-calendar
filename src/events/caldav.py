# python
from caldav import DAVClient, Calendar
from pydantic import AnyUrl

from util.logging import logger

from src.model.event import Event


def authenticate_caldav(url: AnyUrl, username: str, password: str) -> DAVClient:
    return DAVClient(
        url.encoded_string(),
        username=username,
        password=password,
        headers={"User-Agent": "email-to-calendar/1.0"},
    )


def _find_caldav_event_by_id(calendar: Calendar, caldav_id: str):
    for ev in calendar.events():
        # try common attributes first
        for attr in ("id", "href", "url"):
            val = getattr(ev, attr, None)
            if val and caldav_id in str(val):
                return ev
        # fallback: try UID inside the VEVENT
        try:
            uid = ev.vobject_instance.vevent.uid.value
            if uid == caldav_id:
                return ev
        except Exception:
            continue
    return None


def add_to_caldav(
    url: AnyUrl, username: str, password: str, calendar_name: str, events: list[Event]
):
    with authenticate_caldav(url, username, password) as client:
        principal = client.principal()
        ## The principals calendars can be fetched like this:
        calendars: list[Calendar] = principal.calendars()

        calendar: Calendar = [cal for cal in calendars if cal.name == calendar_name][0]
        if not calendar:
            logger.error(f"Calendar '{calendar_name}' not found.")
            raise ValueError(f"Calendar '{calendar_name}' not found.")

        events = [event for event in events if not event.in_calendar]
        if not events:
            return

        for event in events:
            # If we have a CalDAV id, try to update the existing event first
            if not event.in_calendar and event.caldav_id:
                try:
                    cal_event = _find_caldav_event_by_id(calendar, str(event.caldav_id))
                    if cal_event:
                        logger.info(
                            f"Updating event {event.summary} in CalDAV calendar '{calendar_name}'"
                        )
                        # If all-day, convert to date objects expected by vobject
                        if event.all_day:
                            event.start = event.start.date()
                            event.end = event.end.date()

                        # Update vobject fields if available
                        try:
                            vevent = cal_event.vobject_instance.vevent
                            if hasattr(vevent, "summary"):
                                vevent.summary.value = event.summary
                            if hasattr(vevent, "dtstart"):
                                vevent.dtstart.value = event.start
                            if hasattr(vevent, "dtend"):
                                vevent.dtend.value = event.end
                            # persist changes
                            cal_event.save()
                        except Exception:
                            # If direct vobject manipulation isn't supported, fallback to deleting+adding
                            logger.warning(
                                "Direct vobject update failed; falling back to replace (delete + add)."
                            )
                            try:
                                cal_event.delete()
                            except Exception as e:
                                logger.error(
                                    f"Failed to delete existing CalDAV event: {e}"
                                )
                                raise e
                            new_cal_event = calendar.add_event(
                                dtstart=event.start,
                                dtend=event.end,
                                summary=event.summary,
                            )
                            event.caldav_id = getattr(new_cal_event, "id", None)
                            event.save_to_caldav()
                            continue

                        # update local model and mark saved to caldav
                        event.save_to_caldav()
                        continue  # processed this event
                    # if cal_event not found, fall through to add a new one
                except Exception as e:
                    logger.error(
                        f"Failed to update event {event.summary} in CalDAV: {e}"
                    )
                    raise e

            # Default: add new event
            try:
                logger.info(
                    f"Adding event {event.summary} to CalDAV calendar '{calendar_name}'"
                )
                if event.all_day:
                    event.start = event.start.date()
                    event.end = event.end.date()
                cal_event = calendar.add_event(
                    dtstart=event.start, dtend=event.end, summary=event.summary
                )
                event.caldav_id = getattr(cal_event, "id", None)
                event.save_to_caldav()
            except Exception as e:
                logger.error(f"Failed to add event {event.summary} to CalDAV: {e}")
                raise e


def delete_from_caldav(
    url: AnyUrl, username: str, password: str, calendar_name: str, event: Event
):
    if event.in_calendar and event.caldav_id:
        with authenticate_caldav(url, username, password) as client:
            principal = client.principal()
            calendars: list[Calendar] = principal.calendars()

            calendar: Calendar = [
                cal for cal in calendars if cal.name == calendar_name
            ][0]
            if not calendar:
                logger.error(f"Calendar '{calendar_name}' not found.")
                raise ValueError(f"Calendar '{calendar_name}' not found.")

            cal_event = _find_caldav_event_by_id(calendar, event.caldav_id)
            if not cal_event:
                logger.warning(f"Event with caldav_id '{event.caldav_id}' not found.")
                raise ValueError(f"Event with caldav_id '{event.caldav_id}' not found.")

            try:
                logger.info(
                    f"Deleting event with caldav_id '{event.caldav_id}' from CalDAV calendar '{calendar_name}'"
                )
                cal_event.delete()
            except Exception as e:
                logger.error(
                    f"Failed to delete event with caldav_id '{event.caldav_id}': {e}"
                )
                raise e
    else:
        logger.warning(
            f"Event id '{event.id}' is not in CalDAV or has no caldav_id; skipping deletion."
        )

import apprise
from pydantic import AnyUrl

from src.model.event import Event


def send_success_notification(apprise_url: AnyUrl, events: list[Event]):
    # Create an Apprise instance
    apobj = apprise.Apprise()

    # Add all the notification services by their server url.
    # A sample email notification:
    apobj.add(apprise_url.encoded_string())

    # Then notify these services any time you desire. The below would
    # notify all the services loaded into our Apprise object.
    apobj.notify(
        body=f"The following new events were added to your calendar: {events}",
        title="New Events Added to Calendar",
    )

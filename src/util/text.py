import re
from datetime import datetime, date, time, timedelta
from dataclasses import dataclass
from typing import Optional, List, Tuple
from bs4 import BeautifulSoup

from src.model.event import Event
from src.model.email import EMail


@dataclass
class ParsedEvent:
    """Represents a parsed calendar event"""

    start_date: date
    email: EMail
    end_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    summary: str = ""
    is_all_day: bool = True
    is_tentative: bool = False  # True if date contains "or"

    def __str__(self):
        date_str = self.start_date.strftime("%Y-%m-%d")
        if self.end_date:
            date_str += f" to {self.end_date.strftime('%Y-%m-%d')}"
        time_str = (
            "All day"
            if self.is_all_day
            else (self.start_time.strftime("%H:%M") if self.start_time else "N/A")
        )
        if self.end_time:
            time_str += f" to {self.end_time.strftime('%H:%M')}"
        tentative_str = " (Tentative)" if self.is_tentative else ""
        return f"{date_str} {time_str} - {self.summary}{tentative_str}"

    def to_event(self):
        """Convert ParsedEvent to Event model instance"""
        # Handle different event scenarios properly
        if self.is_all_day:
            # All-day events: start at midnight, end at 23:59:59
            start_datetime = datetime.combine(self.start_date, time(0, 0))
            if self.end_date:
                # Multi-day all-day event: end at 23:59:59 of the end date
                end_datetime = datetime.combine(self.end_date, time(23, 59, 59))
            else:
                # Single-day all-day event: end at 23:59:59 of the same day
                end_datetime = datetime.combine(self.start_date, time(23, 59, 59))
        else:
            # Timed events
            start_datetime = datetime.combine(self.start_date, self.start_time)

            if self.end_date and self.end_time:
                # Multi-day event with specific end time
                end_datetime = datetime.combine(self.end_date, self.end_time)
            elif self.end_date:
                # Multi-day event without specific end time - assume it ends at end of end date
                end_datetime = datetime.combine(self.end_date, time(23, 59, 59))
            elif self.end_time:
                # Same-day event with specific end time
                end_datetime = datetime.combine(self.start_date, self.end_time)
            else:
                # Same-day event with only start time - assume 1 hour duration
                end_datetime = start_datetime + timedelta(hours=1)

        # Clean the summary of any formatting before creating the event
        clean_summary = self.strip_formatting(self.summary)

        return Event(
            start=start_datetime,
            end=end_datetime,
            summary=clean_summary,
            email_id=self.email.id,
            in_calendar=False,
        )

    def strip_formatting(self, text: str) -> str:
        """
        Remove markdown and HTML formatting from text

        Args:
            text: Text that may contain markdown or HTML formatting

        Returns:
            Clean text without formatting
        """
        if not text:
            return text

        # Remove markdown formatting
        # Bold/italic: **text**, __text__, *text*, _text_
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)  # **bold**
        text = re.sub(r"__([^_]+)__", r"\1", text)      # __bold__
        text = re.sub(r"\*([^*]+)\*", r"\1", text)      # *italic*
        text = re.sub(r"_([^_]+)_", r"\1", text)        # _italic_

        # Remove HTML tags if present
        if "<" in text and ">" in text:
            soup = BeautifulSoup(text, "html.parser")
            text = soup.get_text()

        # Clean up extra whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text


class EmailEventParser:
    """Parser for extracting calendar events from email bodies"""

    # Month names mapping
    MONTHS = {
        "january": 1,
        "jan": 1,
        "february": 2,
        "feb": 2,
        "march": 3,
        "mar": 3,
        "april": 4,
        "apr": 4,
        "may": 5,
        "june": 6,
        "jun": 6,
        "july": 7,
        "jul": 7,
        "august": 8,
        "aug": 8,
        "september": 9,
        "sep": 9,
        "sept": 9,
        "october": 10,
        "oct": 10,
        "november": 11,
        "nov": 11,
        "december": 12,
        "dec": 12,
    }

    def __init__(self, delivery_date: datetime):
        """
        Initialize parser with email delivery date

        Args:
            delivery_date: The date the email was delivered (used as default year)
        """
        self.delivery_date = delivery_date
        self.current_year = delivery_date.year
        self.current_month = None

    def clean_html_content(self, html_content: str) -> str:
        """
        Clean HTML content and convert to plain text

        Args:
            html_content: Raw HTML content from email

        Returns:
            Cleaned plain text content
        """
        # Parse HTML
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Add line breaks before certain elements to preserve structure
        for tag in soup.find_all(["div", "br", "p"]):
            if tag.name == "br":
                tag.replace_with("\n")
            else:
                # Add newlines around block elements
                tag.insert(0, "\n")
                tag.append("\n")

        # Get text content
        text = soup.get_text()

        # Clean up whitespace and line breaks
        lines = []
        for line in text.split("\n"):
            line = line.strip()
            if line:
                lines.append(line)

        return "\n".join(lines)

    def parse_time(self, time_str: str) -> Optional[time]:
        """
        Parse time string into time object

        Args:
            time_str: Time string (e.g., "2pm", "10:30am", "830", "2:15", "noon")

        Returns:
            Parsed time object or None if parsing fails
        """
        if not time_str:
            return None

        time_str = time_str.strip().lower()

        # Handle special cases
        if time_str == "noon":
            return time(12, 0)
        elif time_str == "midnight":
            return time(0, 0)

        # Handle various time formats
        time_patterns = [
            r"^(\d{1,2}):(\d{2})\s*(am|pm)?$",  # 2:30pm, 10:15
            r"^(\d{1,2})\s*(am|pm)$",  # 2pm, 10am
            r"^(\d{3,4})\s*(am|pm)$",  # 830am, 1020am (WITH am/pm required)
            r"^(\d{3,4})ish$",  # 830ish, 1020ish
            r"^(\d{3,4})$",  # 830, 1020 (without am/pm)
            r"^(\d{1,2})$",  # 14 (assume 24-hour if >12, otherwise needs context)
        ]

        for pattern in time_patterns:
            match = re.match(pattern, time_str)
            if match:
                groups = match.groups()

                if len(groups) >= 2 and ":" in time_str:  # HH:MM format
                    hour, minute = int(groups[0]), int(groups[1])
                    ampm = groups[2] if len(groups) > 2 else None

                    # Smart AM/PM inference for times without explicit am/pm
                    if not ampm:
                        # Common appointment/event time patterns
                        if hour >= 1 and hour <= 5:  # 1:30, 2:50, 4:10 likely PM
                            hour += 12
                        elif hour == 12:  # 12:XX likely PM (noon hour)
                            pass  # Keep as is
                        # Hours 6-11 and 13+ stay as is (morning or 24-hour format)

                elif (
                    len(groups) >= 2 and groups[1] and groups[1] in ["am", "pm"]
                ):  # H am/pm format (including HHMM am/pm)
                    hour_or_time_digits = groups[0]
                    ampm = groups[1]

                    # Check if it's a 3-4 digit time like 830am or 1020am
                    if len(hour_or_time_digits) >= 3:  # HHMM format with am/pm
                        if len(hour_or_time_digits) == 3:  # 830 = 8:30
                            hour, minute = (
                                int(hour_or_time_digits[0]),
                                int(hour_or_time_digits[1:]),
                            )
                        else:  # 1020 = 10:20
                            hour, minute = (
                                int(hour_or_time_digits[:2]),
                                int(hour_or_time_digits[2:]),
                            )
                    else:  # Single or double digit hour
                        hour, minute = int(hour_or_time_digits), 0

                elif "ish" in time_str:  # HHMMish format
                    time_digits = groups[0]
                    if len(time_digits) == 3:  # 830 = 8:30
                        hour, minute = int(time_digits[0]), int(time_digits[1:])
                    elif len(time_digits) == 4:  # 1020 = 10:20
                        hour, minute = int(time_digits[:2]), int(time_digits[2:])
                    else:
                        continue

                    # For "ish" times, assume reasonable defaults based on hour
                    if 6 <= hour <= 11:  # Morning hours
                        ampm = "am"
                    elif 1 <= hour <= 5:  # Afternoon hours
                        ampm = "pm"
                    else:
                        ampm = None  # For 12 and hours >= 13, leave as is

                elif len(groups[0]) >= 3:  # HHMM format without am/pm
                    time_digits = groups[0]
                    if len(time_digits) == 3:  # 830 = 8:30
                        hour, minute = int(time_digits[0]), int(time_digits[1:])
                    elif len(time_digits) == 4:  # 1020 = 10:20
                        hour, minute = int(time_digits[:2]), int(time_digits[2:])
                    else:
                        continue
                    ampm = None
                else:  # Single digit hour
                    hour, minute = int(groups[0]), 0
                    ampm = None
                    # If no am/pm and hour <= 12, assume it needs am/pm context
                    if hour <= 12:
                        # For common appointment times, assume PM if reasonable
                        if 1 <= hour <= 5:
                            ampm = "pm"
                        elif hour >= 6:
                            ampm = "am"

                # Handle AM/PM (only if not already processed above)
                if ampm == "pm" and hour != 12:
                    hour += 12
                elif ampm == "am" and hour == 12:
                    hour = 0

                # Validate hour and minute
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    return time(hour, minute)

        return None

    def parse_date_range(
        self, date_str: str, month: int, year: int
    ) -> Tuple[Optional[date], Optional[date]]:
        """
        Parse date or date range string

        Args:
            date_str: Date string (e.g., "15", "22-23", "8-11", "21st", "22nd-24th")
            month: Current month number
            year: Current year

        Returns:
            Tuple of (start_date, end_date). end_date is None for single dates
        """
        date_str = date_str.strip()

        # Remove ordinal suffixes (st, nd, rd, th)
        def clean_ordinal(day_str: str) -> str:
            """Remove ordinal suffixes from day string"""
            day_str = day_str.strip()
            # Match ordinal suffixes: 1st, 2nd, 3rd, 4th, 11th, 21st, etc.
            ordinal_pattern = r"^(\d+)(?:st|nd|rd|th)$"
            match = re.match(ordinal_pattern, day_str, re.IGNORECASE)
            if match:
                return match.group(1)
            return day_str

        # Handle date ranges (e.g., "22-23", "8-11", "21st-23rd", "1st-3rd")
        if "-" in date_str:
            parts = date_str.split("-")
            if len(parts) == 2:
                try:
                    start_day = int(clean_ordinal(parts[0]))
                    end_day = int(clean_ordinal(parts[1]))
                    start_date = date(year, month, start_day)
                    end_date = date(year, month, end_day)
                    return start_date, end_date
                except (ValueError, TypeError):
                    pass

        # Single date (e.g., "15", "21st", "22nd")
        try:
            day = int(clean_ordinal(date_str))
            return date(year, month, day), None
        except (ValueError, TypeError):
            pass

        return None, None

    def parse_event_line(
        self,
        line: str,
        current_month: int,
        current_year: int,
        last_event_date: Optional[date] = None,
        email: EMail = None,
    ) -> List[ParsedEvent]:
        """
        Parse a single line that may contain one or more events

        Args:
            line: Line of text containing event information
            current_month: Current month number
            current_year: Current year
            last_event_date: Date from the previous event (used when line doesn't start with a date)
            email: EMail object for linking events

        Returns:
            List of parsed events
        """
        events = []
        line = line.strip()

        if not line:
            return events

        # Check for tentative events (containing "or")
        is_tentative = " or " in line.lower()

        # Split on & and "and" for multiple events on same line
        event_parts = re.split(r"\s*&\s*|\s+and\s+", line, flags=re.IGNORECASE)

        for event_part in event_parts:
            event_part = event_part.strip()
            if not event_part:
                continue

            # Look for date patterns at the start (including ordinal suffixes)
            date_time_pattern = r"^(\d+(?:st|nd|rd|th)?(?:-\d+(?:st|nd|rd|th)?)?(?:\s+or\s+\d+(?:st|nd|rd|th)?(?:-\d+(?:st|nd|rd|th)?)?)*)\s*(.*)$"
            match = re.match(date_time_pattern, event_part, re.IGNORECASE)

            start_date = None
            end_date = None
            rest = event_part

            if match:
                # Event starts with a date
                date_part, rest = match.groups()

                # Handle tentative dates with "or"
                if " or " in date_part.lower():
                    date_options = re.split(r"\s+or\s+", date_part, flags=re.IGNORECASE)
                    date_part = date_options[0]  # Use first option for now
                    is_tentative = True

                # Parse the date range
                start_date, end_date = self.parse_date_range(
                    date_part, current_month, current_year
                )
            else:
                # Event doesn't start with a date, use last event's date if available
                if last_event_date:
                    start_date = last_event_date
                    # rest is the entire event_part since there's no date to strip
                    rest = event_part
                else:
                    # No date found and no previous date to use, skip this event part
                    continue

            if not start_date:
                continue

            # Extract times from anywhere in the rest of the text
            start_time = None
            end_time = None
            summary = rest.strip()

            # Look for time patterns throughout the text
            time_patterns = [
                r"\b(\d{1,2}):(\d{2})\s*(am|pm)\b",  # 2:30pm, 10:15am
                r"\b(\d{1,2})\s*(am|pm)\b",  # 2pm, 10am
                r"\b(\d{1,2}):(\d{2})\b",  # 2:30, 14:15 (without am/pm)
                r"\b(\d{3,4})\s*(am|pm)\b",  # 830am, 1015am, 1020am (WITH am/pm)
                r"\b(\d{3,4})\b(?!\s*(?:am|pm|ish))",  # 830, 1015 (without am/pm, not followed by am/pm/ish)
                r"\b(\d{3,4})ish\b",  # 830ish, 1020ish
                r"\b(noon|midnight)\b",  # noon, midnight
            ]

            found_times = []
            for pattern in time_patterns:
                matches = re.finditer(pattern, rest, re.IGNORECASE)
                for match in matches:
                    time_str = match.group(0)
                    parsed_time = self.parse_time(time_str)
                    if parsed_time:
                        found_times.append((parsed_time, match.span()))

            # Remove time strings from summary and assign start/end times
            if found_times:
                # Sort by position in text
                found_times.sort(key=lambda x: x[1][0])

                # Take first time as start time
                start_time = found_times[0][0]

                # If there are two times, second one is end time
                if len(found_times) >= 2:
                    end_time = found_times[1][0]

                # Remove time strings from summary (in reverse order to preserve positions)
                spans_to_remove = [t[1] for t in found_times]
                for span in sorted(spans_to_remove, key=lambda x: x[0], reverse=True):
                    summary = summary[: span[0]] + summary[span[1] :]

                # Clean up extra spaces in summary
                summary = re.sub(r"\s+", " ", summary).strip()

            # Determine if it's an all-day event
            is_all_day = start_time is None and end_time is None

            # Create the event
            event = ParsedEvent(
                start_date=start_date,
                end_date=end_date,
                start_time=start_time,
                end_time=end_time,
                summary=summary,
                is_all_day=is_all_day,
                is_tentative=is_tentative,
                email=email,
            )

            events.append(event)

        return events

    def parse_email_body(self, email_body: str, email: EMail) -> List[ParsedEvent]:
        """
        Parse email body and extract all calendar events

        Args:
            email_body: Raw email body (HTML or plain text)
            email: EMail object for linking events

        Returns:
            List of parsed calendar events
        """
        # Clean HTML content
        if "<" in email_body and ">" in email_body:
            text_content = self.clean_html_content(email_body)
        else:
            text_content = email_body

        lines = text_content.split("\n")
        events = []
        current_year = self.current_year
        current_month = None
        last_event_date = None  # Track the last parsed date

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check for year
            year_match = re.match(r"^\s*(\d{4})\s*$", line)
            if year_match:
                current_year = int(year_match.group(1))
                continue

            # Check for month - strip formatting first
            month_match = re.match(r"^\s*([*_#]+)?(\w+)([*_#]+)?\s*$", line, re.IGNORECASE)
            if month_match:
                # Extract the month name without formatting
                month_name = month_match.group(2).lower()
                if month_name in self.MONTHS:
                    new_month = self.MONTHS[month_name]

                    # Handle year increment when months loop (Dec -> Jan)
                    if current_month and new_month < current_month:
                        # Only increment year if we go from a late month to early month
                        if (
                            current_month >= 10 and new_month <= 3
                        ):  # Oct/Nov/Dec -> Jan/Feb/Mar
                            current_year += 1

                    current_month = new_month
                    continue

            # Parse event line if we have a current month
            if current_month:
                line_events = self.parse_event_line(
                    line, current_month, current_year, last_event_date, email
                )
                events.extend(line_events)

                # Update last_event_date with the last parsed event's date
                if line_events:
                    last_event_date = line_events[-1].start_date

        return events


def parse_email_events(email: EMail) -> List[Event]:
    """
    Convenience function to parse email events

    Args:
        email: EMail object containing body and delivery_date

    Returns:
        List of Event model instances
    """
    parser = EmailEventParser(email.delivery_date)
    parsed_events = parser.parse_email_body(email.body, email)

    # Convert ParsedEvent objects to Event objects
    events = []
    for parsed_event in parsed_events:
        event = parsed_event.to_event()
        events.append(event)

    return events

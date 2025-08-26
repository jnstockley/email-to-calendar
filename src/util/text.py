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

                # Validate that end date is after start date
                if end_datetime <= start_datetime:
                    # If end date is before or equal to start date, assume single day event
                    end_datetime = datetime.combine(self.start_date, time(23, 59, 59))
            else:
                # Single-day all-day event: end at 23:59:59 of the same day
                end_datetime = datetime.combine(self.start_date, time(23, 59, 59))
        else:
            # Timed events
            start_datetime = datetime.combine(self.start_date, self.start_time)

            if self.end_date and self.end_time:
                # Multi-day event with specific end time
                end_datetime = datetime.combine(self.end_date, self.end_time)

                # Validate that end datetime is after start datetime
                if end_datetime <= start_datetime:
                    # If end is before start, assume single day event with 1 hour duration
                    end_datetime = start_datetime + timedelta(hours=1)
            elif self.end_date:
                # Multi-day event without specific end time - assume it ends at end of end date
                proposed_end = datetime.combine(self.end_date, time(23, 59, 59))

                # Validate that end date is after start date
                if proposed_end <= start_datetime:
                    # If end date is before start, assume single day event
                    end_datetime = datetime.combine(self.start_date, time(23, 59, 59))
                else:
                    end_datetime = proposed_end
            elif self.end_time:
                # Same-day event with specific end time
                end_datetime = datetime.combine(self.start_date, self.end_time)

                # Validate that end time is after start time for same-day events
                if end_datetime <= start_datetime:
                    # If end time is before or equal to start time, try to fix it
                    # This commonly happens with AM/PM parsing issues

                    # If both times are in the same half of the day, add 12 hours to end time
                    if (self.start_time.hour < 12 and self.end_time.hour < 12) or (
                        self.start_time.hour >= 12 and self.end_time.hour >= 12
                    ):
                        # Both are AM or both are PM, likely one should be PM when other is AM
                        if self.end_time.hour < 12:
                            # End time is AM, make it PM
                            fixed_end_time = time(
                                self.end_time.hour + 12, self.end_time.minute
                            )
                            end_datetime = datetime.combine(
                                self.start_date, fixed_end_time
                            )

                    # If it's still not fixed, just add some reasonable duration
                    if end_datetime <= start_datetime:
                        # Add 1 hour as default duration
                        end_datetime = start_datetime + timedelta(hours=1)
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
        Remove markdown, HTML formatting and unwanted special characters from text

        Args:
            text: Text that may contain markdown, HTML formatting, or special characters

        Returns:
            Clean text without formatting or unwanted characters
        """
        if not text:
            return text

        # Remove markdown formatting
        # Bold/italic: **text**, __text__, *text*, _text_
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)  # **bold**
        text = re.sub(r"__([^_]+)__", r"\1", text)  # __bold__
        text = re.sub(r"\*([^*]+)\*", r"\1", text)  # *italic*
        text = re.sub(r"_([^_]+)_", r"\1", text)  # _italic_

        # Remove HTML tags if present
        if "<" in text and ">" in text:
            soup = BeautifulSoup(text, "html.parser")
            text = soup.get_text()

        # Remove unwanted special characters from summaries
        # Keep only letters, numbers, spaces, and basic punctuation (periods, commas, apostrophes, parentheses)
        # Remove problematic characters like colons, dashes, etc. that clutter summaries
        text = re.sub(r'[><!@#$%^&*_+=\[\]{}\\|;:"\'`~-]', " ", text).strip()

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
        text = re.sub(r"__([^_]+)__", r"\1", text)  # __bold__
        text = re.sub(r"\*([^*]+)\*", r"\1", text)  # *italic*
        text = re.sub(r"_([^_]+)_", r"\1", text)  # _italic_

        # Remove HTML tags if present
        if "<" in text and ">" in text:
            soup = BeautifulSoup(text, "html.parser")
            text = soup.get_text()

        # Clean up extra whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text

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
                tag.replace_with(soup.new_string("\n"))
            else:
                # Add newlines around block elements
                tag.insert_before(soup.new_string("\n"))
                tag.insert_after(soup.new_string("\n"))

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
            time_str: Time string (e.g., "2pm", "10:30am", "830", "2:15", "noon", "10", "2-245")

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

        # Handle time ranges like "2-245" - extract only the start time
        time_range_match = re.match(r"^(\d{1,2})-(\d{1,4})$", time_str)
        if time_range_match:
            start_time_str = time_range_match.group(1)
            # Recursively parse the start time
            return self.parse_time(start_time_str)

        # Handle various time formats
        time_patterns = [
            r"^(\d{1,2}):(\d{2})\s*(am|pm)?$",  # 2:30pm, 10:15
            r"^(\d{1,2})\s*(am|pm)$",  # 2pm, 10am
            r"^(\d{3,4})\s*(am|pm)$",  # 830am, 1020am (WITH am/pm required)
            r"^(\d{3,4})ish$",  # 830ish, 1020ish
            r"^(\d{3,4})$",  # 830, 1020 (without am/pm)
            r"^(\d{1,2})$",  # Single digit hours like "10", "2" (assume appropriate AM/PM)
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
                else:  # Single digit hour (like "10", "2")
                    hour, minute = int(groups[0]), 0
                    ampm = None
                    # Smart AM/PM inference for single digit hours
                    if hour >= 1 and hour <= 5:
                        # Hours 1-5 are likely PM for appointments
                        hour += 12
                    elif hour >= 6 and hour <= 11:
                        # Hours 6-11 are likely AM
                        pass  # Keep as is
                    elif hour == 12:
                        # 12 is likely PM (noon)
                        pass  # Keep as is
                    # Hours >= 13 are already in 24-hour format

                # Handle AM/PM (only if not already processed above)
                if ampm == "pm" and hour != 12:
                    hour += 12
                elif ampm == "am" and hour == 12:
                    hour = 0

                # Validate hour and minute
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    return time(hour, minute)

        return None

    def parse_time_range(
        self, time_range_str: str
    ) -> Tuple[Optional[time], Optional[time]]:
        """
        Parse time range string into start and end time objects

        Args:
            time_range_str: Time range string (e.g., "2-245" meaning 2:00-2:45)

        Returns:
            Tuple of (start_time, end_time) or (None, None) if parsing fails
        """
        if not time_range_str:
            return None, None

        # Handle time ranges like "2-245"
        time_range_match = re.match(r"^(\d{1,2})-(\d{1,4})$", time_range_str.strip())
        if time_range_match:
            start_str = time_range_match.group(1)
            end_str = time_range_match.group(2)

            # Parse start time
            start_time = self.parse_time(start_str)
            if not start_time:
                return None, None

            # Parse end time - need to handle formats like "245" meaning 2:45
            end_time = None
            if len(end_str) == 3:  # "245" = 2:45
                hour = int(end_str[0])
                minute = int(end_str[1:])
                # Use same AM/PM logic as start time
                if start_time.hour >= 12:  # Start time is PM
                    if hour < 12:
                        hour += 12
                end_time = time(hour, minute)
            elif len(end_str) == 4:  # "1245" = 12:45
                hour = int(end_str[:2])
                minute = int(end_str[2:])
                # Use same AM/PM logic as start time
                if (
                    start_time.hour >= 12 and hour < 12
                ):  # Start is PM, end should be PM too
                    hour += 12
                end_time = time(hour, minute)
            else:  # Single or double digit - treat as hour
                end_time = self.parse_time(end_str)

            # Additional validation: ensure end time is after start time
            if end_time and start_time:
                # Convert to minutes for easy comparison
                start_minutes = start_time.hour * 60 + start_time.minute
                end_minutes = end_time.hour * 60 + end_time.minute

                # If end time is before or equal to start time, try to fix it
                if end_minutes <= start_minutes:
                    # Try adding 12 hours to end time if it's in AM and start is in PM
                    if end_time.hour < 12 and start_time.hour >= 12:
                        fixed_end_time = time(end_time.hour + 12, end_time.minute)
                        return start_time, fixed_end_time
                    # Try adding 12 hours to end time if both are in AM but end should be PM
                    elif end_time.hour < 12 and start_time.hour < 12:
                        fixed_end_time = time(end_time.hour + 12, end_time.minute)
                        return start_time, fixed_end_time
                    # If still problematic, return None for end_time (will default to 1 hour duration)
                    else:
                        return start_time, None

            return start_time, end_time

        return None, None

    def parse_date_range(
        self, date_str: str, month: int, year: int
    ) -> Tuple[Optional[date], Optional[date]]:
        """
        Parse date or date range string, including cross-month ranges

        Args:
            date_str: Date string (e.g., "15", "22-23", "8-11", "21st", "22nd-24th", "25-July 4")
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

        # Handle date ranges (including cross-month like "25-July 4")
        if "-" in date_str:
            parts = date_str.split("-", 1)  # Split only on first dash
            if len(parts) == 2:
                start_part = parts[0].strip()
                end_part = parts[1].strip()

                try:
                    # Parse start date (always in current month)
                    start_day = int(clean_ordinal(start_part))
                    start_date = date(year, month, start_day)

                    # Check if end part contains a month name (cross-month range)
                    # Pattern like "July 4" or "July4" or "July-4"
                    month_day_pattern = r"^(\w+)\s*-?\s*(\d+)(?:st|nd|rd|th)?$"
                    cross_month_match = re.match(
                        month_day_pattern, end_part, re.IGNORECASE
                    )

                    if cross_month_match:
                        # Cross-month range like "25-July 4"
                        end_month_name = cross_month_match.group(1).lower()
                        end_day_str = cross_month_match.group(2)

                        if end_month_name in self.MONTHS:
                            end_month = self.MONTHS[end_month_name]
                            end_day = int(clean_ordinal(end_day_str))

                            # Handle year transition if end month is earlier than start month
                            end_year = year
                            if end_month < month:
                                end_year += 1

                            end_date = date(end_year, end_month, end_day)
                            return start_date, end_date
                    else:
                        # Same-month range like "22-23"
                        end_day = int(clean_ordinal(end_part))
                        end_date = date(year, month, end_day)

                        # Validate that end date is after start date
                        if end_date <= start_date:
                            # If end date is before or equal to start date, assume it's next month
                            # Handle month rollover
                            next_month = month + 1
                            next_year = year
                            if next_month > 12:
                                next_month = 1
                                next_year += 1

                            try:
                                end_date = date(next_year, next_month, end_day)
                            except ValueError:
                                # If the day doesn't exist in next month, skip this range
                                return start_date, None

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

    def clean_event_line(self, line: str) -> str:
        """
        Clean special characters and extra whitespace from event lines before parsing

        Args:
            line: Raw event line that may contain special characters

        Returns:
            Cleaned line ready for parsing
        """
        if not line:
            return line

        # Remove common special characters that interfere with parsing
        # Keep important characters like hyphens (for date ranges), colons (for times),
        # parentheses (for notes), and basic punctuation
        # IMPORTANT: Removed colon (:) from removal pattern to preserve time parsing
        special_chars_to_remove = r'[><!@#$%^&*_+=\[\]{}\\|;"\'`~]'

        # Replace special characters with spaces, then clean up multiple spaces
        cleaned = re.sub(special_chars_to_remove, " ", line)

        # Clean up multiple whitespace characters
        cleaned = re.sub(r"\s+", " ", cleaned)

        # Strip leading/trailing whitespace
        cleaned = cleaned.strip()

        return cleaned

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

        # Clean special characters and extra whitespace before parsing
        line = self.clean_event_line(line)

        if not line:  # Check again after cleaning
            return events

        # Check for tentative events (containing "or")
        is_tentative = " or " in line.lower()

        # Split on & and "and" for multiple events on same line
        event_parts = re.split(r"\s*&\s*|\s+\s+", line, flags=re.IGNORECASE)  # and

        for event_part in event_parts:
            event_part = event_part.strip()
            if not event_part:
                continue

            # Look for date patterns at the start (including cross-month patterns like "25-July 4")
            # Updated regex to handle cross-month patterns with month names
            date_time_pattern = r"^(\d+(?:st|nd|rd|th)?(?:-(?:\d+(?:st|nd|rd|th)?|\w+\s*\d+(?:st|nd|rd|th)?))?)(?:\s+or\s+\d+(?:st|nd|rd|th)?(?:-(?:\d+(?:st|nd|rd|th)?|\w+\s*\d+(?:st|nd|rd|th)?))?)?\s*(.*)$"
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
                r"\b(\d{1,2})-(\d{1,4})\b",  # Time ranges like "2-245" (2:00-2:45) or "9-10" (9:00-10:00)
                r"\b(\d{1,2})\b(?!\s*(?:am|pm|ish|\d))",  # Single digit hours like "10" (but not followed by am/pm/ish/digits)
            ]

            found_times = []
            found_time_ranges = []

            for pattern in time_patterns:
                matches = re.finditer(pattern, rest, re.IGNORECASE)
                for match in matches:
                    time_str = match.group(0)

                    # Check if this is a time range pattern
                    if re.match(r"\b(\d{1,2})-(\d{1,4})\b", time_str):
                        # Parse as time range
                        start_time_parsed, end_time_parsed = self.parse_time_range(
                            time_str
                        )
                        if start_time_parsed:
                            found_time_ranges.append(
                                (start_time_parsed, end_time_parsed, match.span())
                            )
                    else:
                        # Parse as single time
                        parsed_time = self.parse_time(time_str)
                        if parsed_time:
                            # Store both the original string and parsed time for proper removal
                            found_times.append((parsed_time, match.span(), time_str))

            # Handle time extraction - prioritize time ranges over individual times
            if found_time_ranges:
                # Use the first time range found
                start_time, end_time = found_time_ranges[0][0], found_time_ranges[0][1]
                # Remove the time range from summary
                time_range_span = found_time_ranges[0][2]
                summary = summary[: time_range_span[0]] + summary[time_range_span[1] :]

            elif found_times:
                # Sort by position in text
                found_times.sort(key=lambda x: x[1][0])

                # Take first time as start time
                start_time = found_times[0][0]

                # If there are two times, second one is end time
                if len(found_times) >= 2:
                    end_time = found_times[1][0]

                # Remove time strings from summary using safer string replacement
                # Only remove unique time strings to avoid removing the same pattern multiple times
                unique_time_strings = []
                for time_info in found_times:
                    time_str = time_info[2]  # Now the original string is at index 2
                    if time_str not in unique_time_strings:
                        unique_time_strings.append(time_str)

                # Remove each unique time string once
                for time_str in unique_time_strings:
                    summary = summary.replace(time_str, " ", 1)

            # Clean up extra spaces in summary
            summary = re.sub(r"\s+", " ", summary).strip()

            # Determine if it's an all-day event
            is_all_day = start_time is None and end_time is None

            # Clean summary and check if it's valid
            clean_summary = self.strip_formatting(summary)

            # Skip events with empty or formatting-only summaries
            if not clean_summary or clean_summary in [
                "**",
                "*",
                "__",
                "_",
                "***",
                "___",
                ">",
                ">>",
            ]:
                continue

            # Additional check: Skip if the clean summary is just a month name
            # This prevents month names from being treated as events
            if clean_summary.lower() in self.MONTHS:
                continue

            # Create the event
            event = ParsedEvent(
                start_date=start_date,
                end_date=end_date,
                start_time=start_time,
                end_time=end_time,
                summary=clean_summary,  # Use cleaned summary
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

            # Check for month - strip formatting first and be more restrictive
            # Only match if it's ONLY a month name with optional formatting, no other content
            month_match = re.match(
                r"^\s*([*_#]+)?(\w+)([*_#]+)?\s*$", line, re.IGNORECASE
            )
            if month_match:
                # Extract the month name without formatting
                month_name = month_match.group(2).lower()
                if month_name in self.MONTHS:
                    # Additional check: make sure this isn't part of a larger event description
                    # Skip if the line contains numbers, which likely indicates it's an event
                    if not re.search(r"\d", line):
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

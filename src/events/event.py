from datetime import datetime, date, time
from typing import List, Optional
import re

from src.model.event import Event


_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        start=1,
    )
}

_MONTH_RE = re.compile(r"^\s*([A-Za-z]{3,})\s*$")
_YEAR_RE = re.compile(r"^\s*(\d{4})\s*$")
# Day at start: 12, 1st, 2nd, etc.
_DAY_PREFIX_RE = re.compile(
    r"^\s*(\d{1,2})(?:st|nd|rd|th)?(?:-(\d{1,2})(?:st|nd|rd|th)?)?\b\s*(.*)$",
    re.IGNORECASE,
)
# Time range like 9-10am, 9-10 am, 9am-10am, 9 am - 10 am, 09:30-11:00, 0930-1130
_TIME_RANGE_RE = re.compile(
    r"(\d{1,2})(?:[:;]?(\d{2}))?\s*(am|pm)?\s*-\s*(\d{1,2})(?:[:;]?(\d{2}))?\s*(am|pm)?",
    re.IGNORECASE,
)
# Single time tokens with optional space before am/pm
_TIME_TOKEN_RE = re.compile(
    r"\b(\d{1,2}[:;]\d{2}|\d{3,4}|\d{1,2})\s*(am|pm)?\b", re.IGNORECASE
)


def _parse_time_token(tok: str) -> Optional[time]:
    t = tok.lower().replace(";", ":")
    try:
        if re.fullmatch(r"\d{1,2}:\d{2}(?:am|pm)?", t):
            ampm = None
            if t.endswith("am") or t.endswith("pm"):
                ampm = t[-2:]
                t = t[:-2]
            h, m = map(int, t.split(":"))
            if ampm:
                if h == 12:
                    h = 0
                if ampm == "pm":
                    h += 12
            if 0 <= h < 24 and 0 <= m < 60:
                return time(h, m)
        elif re.fullmatch(r"\d{3,4}(?:am|pm)", t):
            ampm = t[-2:]
            digits = t[:-2]
            if len(digits) == 3:
                h = int(digits[0])
                m = int(digits[1:])
            else:
                h = int(digits[:2])
                m = int(digits[2:])
            if h == 12:
                h = 0
            if ampm == "pm":
                h += 12
            if 0 <= h < 24 and 0 <= m < 60:
                return time(h, m)
        elif re.fullmatch(r"\d{3,4}", t):
            if len(t) == 3:
                h = int(t[0])
                m = int(t[1:])
            else:
                h = int(t[:2])
                m = int(t[2:])
            if 0 <= h < 24 and 0 <= m < 60:
                return time(h, m)
        elif re.fullmatch(r"\d{1,2}(am|pm)", t):
            h = int(t[:-2])
            if h == 12:
                h = 0
            if t.endswith("pm"):
                h += 12
            return time(h, 0)
    except ValueError:
        return None
    return None


def parse_schedule_text(
    text: str, delivery_date: datetime, email_id: Optional[int] = None
) -> List[Event]:
    """Parse plain text schedule into Event objects.

    Simplified rules:
    - Process lines after first month header.
    - Month rollover increases year if no explicit year provided.
    - Year headers override year.
    - A line may declare a day (optionally a day range). Subsequent lines without a day but with a time use last day.
    - Each line produces at most one event.
    - A time range or single time may appear on the same line as the date; line without time becomes all-day (start=end=00:00 for tests).
    - Lines lacking both date and time are ignored.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    events: List[Event] = []
    current_year = delivery_date.year
    saw_explicit_year = False
    current_month: Optional[int] = None
    last_day: Optional[int] = None

    for raw in lines:
        # Year header
        m_year = _YEAR_RE.match(raw)
        if m_year:
            current_year = int(m_year.group(1))
            saw_explicit_year = True
            continue
        # Month header
        m_month = _MONTH_RE.match(raw)
        if m_month:
            name = m_month.group(1).lower()
            if name in _MONTHS:
                month_num = _MONTHS[name]
                if (
                    current_month
                    and month_num < current_month
                    and not saw_explicit_year
                ):
                    current_year += 1
                current_month = month_num
            continue
        if current_month is None:
            continue

        work = raw
        day_in_line = False
        effective_day_end: Optional[int] = None
        start_time: Optional[time] = None
        end_time: Optional[time] = None

        # Compact leading pattern like '2-245 Title' meaning day=2, time 2:00-2:45 (assume pm if hour 1-7 and no suffix)
        m_compact_lead = re.match(
            r"^\s*(\d{1,2})-(\d{3,4})(am|pm)?\b\s*(.*)$", work, re.IGNORECASE
        )
        if m_compact_lead:
            day_candidate = int(m_compact_lead.group(1))
            block = m_compact_lead.group(2)
            suf = (m_compact_lead.group(3) or "").lower()
            remainder_after = m_compact_lead.group(4)
            if 1 <= day_candidate <= 31:
                last_day = day_candidate
                day_in_line = True
                # derive second time
                if len(block) == 3:
                    h2 = int(block[0])
                    m2 = int(block[1:])
                else:
                    h2 = int(block[:2])
                    m2 = int(block[2:])
                h1 = day_candidate  # treat same number as hour
                assume_pm = (not suf) and (1 <= h1 <= 7)

                def _to24(h: int) -> int:
                    if suf:
                        if suf == "am":
                            return 0 if h == 12 else h
                        else:
                            return h if h == 12 else h + 12 if h < 12 else h
                    if assume_pm and h < 12:
                        return h + 12 if h < 12 else h
                    return 0 if h == 12 else h

                sh24 = _to24(h1)
                eh24 = _to24(h2)
                if 0 <= sh24 < 24 and 0 <= eh24 < 24 and 0 <= m2 < 60:
                    start_time = time(sh24, 0)
                    end_time = time(eh24, m2)
                work = remainder_after
        else:
            # Standard day prefix logic
            m_day = _DAY_PREFIX_RE.match(work)
            if m_day:
                day_start = int(m_day.group(1))
                day_end = m_day.group(2)
                remainder = m_day.group(3).strip()
                rem_l = remainder.lower()
                time_like = False
                if rem_l.startswith(("am", "pm")):
                    time_like = True
                elif rem_l.startswith((":", ";")) and re.match(
                    r"^[:;](\d{2})(?:\b|\s)", rem_l
                ):
                    time_like = True
                else:
                    m_possible_time_range = re.match(
                        r"^-(\d{1,2})([:;]?\d{2})?\s*(am|pm)?\b", rem_l
                    )
                    if m_possible_time_range:
                        second_num = int(m_possible_time_range.group(1))
                        if 0 <= second_num <= 12:
                            time_like = True
                if not time_like:
                    if not (1 <= day_start <= 31):
                        continue
                    if day_end:
                        try:
                            de = int(day_end)
                            if 1 <= de <= 31 and de >= day_start:
                                effective_day_end = de
                            else:
                                effective_day_end = None
                        except ValueError:
                            effective_day_end = None
                    last_day = day_start
                    day_in_line = True
                    work = remainder
        if last_day is None:
            continue

        # Normalize approximate time forms (remove 'ish')
        work = re.sub(
            r"\b(\d{1,2}(?:[:;]?\d{2})?)\s?ish\b", r"\1", work, flags=re.IGNORECASE
        )
        work = re.sub(r"\b(\d{3,4})ish\b", r"\1", work, flags=re.IGNORECASE)

        # If no time yet, parse explicit range
        if start_time is None:
            m_range = _TIME_RANGE_RE.search(work)
            if m_range:
                sh = int(m_range.group(1))
                sm = int(m_range.group(2) or 0)
                suf1 = (m_range.group(3) or "").lower()
                eh = int(m_range.group(4))
                em = int(m_range.group(5) or 0)
                suf2 = (m_range.group(6) or "").lower()
                if suf1 and not suf2:
                    suf2 = suf1
                if suf2 and not suf1:
                    suf1 = suf2
                if suf1 == "am" and sh == 12:
                    sh = 0
                elif suf1 == "pm" and sh != 12:
                    sh += 12
                if suf2 == "am" and eh == 12:
                    eh = 0
                elif suf2 == "pm" and eh != 12:
                    eh += 12
                if all(0 <= v < 60 for v in (sm, em)) and 0 <= sh < 24 and 0 <= eh < 24:
                    start_time = time(sh, sm)
                    end_time = time(eh, em)
                    work = (
                        work[: m_range.start()] + " " + work[m_range.end() :]
                    ).strip()
        # Secondary compact pattern inside remainder if still no time: e.g. '2-245 Meeting'
        if start_time is None:
            m_compact_inner = re.search(
                r"\b(\d{1,2})-(\d{3,4})(am|pm)?\b", work, re.IGNORECASE
            )
            if m_compact_inner:
                h1 = int(m_compact_inner.group(1))
                block = m_compact_inner.group(2)
                suf = (m_compact_inner.group(3) or "").lower()
                if len(block) == 3:
                    h2 = int(block[0])
                    m2 = int(block[1:])
                else:
                    h2 = int(block[:2])
                    m2 = int(block[2:])
                assume_pm = (not suf) and (1 <= h1 <= 7)

                def _to24b(h: int) -> int:
                    if suf:
                        if suf == "am":
                            return 0 if h == 12 else h
                        else:
                            return h if h == 12 else h + 12 if h < 12 else h
                    if assume_pm and h < 12:
                        return h + 12 if h < 12 else h
                    return 0 if h == 12 else h

                sh24 = _to24b(h1)
                eh24 = _to24b(h2)
                if 0 <= sh24 < 24 and 0 <= eh24 < 24 and 0 <= m2 < 60:
                    start_time = time(sh24, 0)
                    end_time = time(eh24, m2)
                    work = (
                        work[: m_compact_inner.start()]
                        + " "
                        + work[m_compact_inner.end() :]
                    ).strip()
        # Single time
        if start_time is None:
            m_tok = _TIME_TOKEN_RE.search(work)
            if m_tok:
                core = m_tok.group(1)
                suf = (m_tok.group(2) or "").lower()
                token_combined = core + suf
                tval = _parse_time_token(token_combined)
                if tval:
                    start_time = tval
                    work = (work[: m_tok.start()] + " " + work[m_tok.end() :]).strip()

        title = work.strip()
        # Remove occurrences of 'or <day>' (valid day 1-31)
        if " or " in title.lower():

            def _drop_or_day(match: re.Match) -> str:
                try:
                    d = int(match.group(1))
                    if 1 <= d <= 31:
                        return ""
                except ValueError:
                    pass
                return match.group(0)

            title = re.sub(
                r"(?i)\bor\s+(\d{1,2})(?:st|nd|rd|th)?\b", _drop_or_day, title
            )
            title = re.sub(r"\s{2,}", " ", title).strip()
        if day_in_line and not start_time and not title:
            continue
        if not title and (day_in_line or start_time):
            title = "Untitled"
        if not title:
            continue

        # Multi-event splitting: look for 'and' or '&' followed by time/time range
        pieces = []  # (summary, start_time, end_time)
        if (" and " in title.lower() or " & " in title) and (
            start_time is not None or end_time is not None or True
        ):
            sep_iter = list(
                re.finditer(r"(?<=\s)(?:and|&)(?=\s)", title, re.IGNORECASE)
            )
            cur_start = start_time
            cur_end = end_time
            last_index = 0
            consumed_any = False
            for m_sep in sep_iter:
                after = title[m_sep.end() :].lstrip()
                if not after:
                    continue
                # Try range first
                m_after_range = _TIME_RANGE_RE.match(after)
                m_after_compact = None
                m_after_time = None
                n_start = None
                n_end = None
                consumed = 0
                if m_after_range:
                    sh = int(m_after_range.group(1))
                    sm = int(m_after_range.group(2) or 0)
                    suf1 = (m_after_range.group(3) or "").lower()
                    eh = int(m_after_range.group(4))
                    em = int(m_after_range.group(5) or 0)
                    suf2 = (m_after_range.group(6) or "").lower()
                    if suf1 and not suf2:
                        suf2 = suf1
                    if suf2 and not suf1:
                        suf1 = suf2
                    if suf1 == "am" and sh == 12:
                        sh = 0
                    elif suf1 == "pm" and sh != 12:
                        sh += 12
                    if suf2 == "am" and eh == 12:
                        eh = 0
                    elif suf2 == "pm" and eh != 12:
                        eh += 12
                    if (
                        all(0 <= v < 60 for v in (sm, em))
                        and 0 <= sh < 24
                        and 0 <= eh < 24
                    ):
                        n_start = time(sh, sm)
                        n_end = time(eh, em)
                        consumed = m_after_range.end()
                if n_start is None:
                    m_after_compact = re.match(r"^(\d{1,2})-(\d{3,4})(am|pm)?\b", after)
                    if m_after_compact:
                        h1 = int(m_after_compact.group(1))
                        block = m_after_compact.group(2)
                        suf = (m_after_compact.group(3) or "").lower()
                        if len(block) == 3:
                            h2 = int(block[0])
                            m2 = int(block[1:])
                        else:
                            h2 = int(block[:2])
                            m2 = int(block[2:])
                        assume_pm = (not suf) and (1 <= h1 <= 7)

                        def _to24c(h: int) -> int:
                            if suf:
                                if suf == "am":
                                    return 0 if h == 12 else h
                                else:
                                    return h if h == 12 else h + 12 if h < 12 else h
                            if assume_pm and h < 12:
                                return h + 12 if h < 12 else h
                            return 0 if h == 12 else h

                        sh24 = _to24c(h1)
                        eh24 = _to24c(h2)
                        if 0 <= sh24 < 24 and 0 <= eh24 < 24 and 0 <= m2 < 60:
                            n_start = time(sh24, 0)
                            n_end = time(eh24, m2)
                            consumed = m_after_compact.end()
                if n_start is None:
                    m_after_time = _TIME_TOKEN_RE.match(after)
                    if m_after_time:
                        core = m_after_time.group(1)
                        suf = (m_after_time.group(2) or "").lower()
                        tval = _parse_time_token(core + suf)
                        if tval:
                            n_start = tval
                            n_end = None
                            consumed = m_after_time.end()
                if n_start is not None:
                    # finalize previous summary
                    prev_summary = title[last_index : m_sep.start()].strip()
                    if prev_summary:
                        pieces.append((prev_summary, cur_start, cur_end))
                        consumed_any = True
                    cur_start = n_start
                    cur_end = n_end
                    last_index = (
                        m_sep.end() + (len(after) - len(after.lstrip())) + consumed
                    )
            if consumed_any:
                final_summary = title[last_index:].strip()
                if final_summary:
                    pieces.append((final_summary, cur_start, cur_end))
        if not pieces:
            pieces = [(title, start_time, end_time)]

        try:
            event_date_start = date(current_year, current_month, last_day)
            event_date_end = None
            if effective_day_end is not None:
                event_date_end = date(current_year, current_month, effective_day_end)
        except ValueError:
            continue

        for piece_summary, p_start_time, p_end_time in pieces:
            pst = p_start_time
            pet = p_end_time
            if pst and pet and pet < pst and event_date_end is None:
                pet = pst
            if pst is None:
                start_dt = datetime.combine(event_date_start, time(0, 0))
                if event_date_end is not None:
                    end_dt = datetime.combine(event_date_end, time(0, 0))
                else:
                    end_dt = start_dt
            else:
                start_dt = datetime.combine(event_date_start, pst)
                if effective_day_end is not None:
                    if pet is None:
                        end_dt = datetime.combine(event_date_end, pst)  # type: ignore[arg-type]
                    else:
                        end_dt = datetime.combine(event_date_end, pet)  # type: ignore[arg-type]
                else:
                    end_dt = datetime.combine(event_date_start, pet or pst)
            kwargs = {
                "summary": piece_summary or "Untitled",
                "start": start_dt,
                "end": end_dt,
            }
            if email_id is not None:
                kwargs["email_id"] = email_id
            try:
                events.append(Event(**kwargs))
            except Exception:
                continue
        continue

    return events

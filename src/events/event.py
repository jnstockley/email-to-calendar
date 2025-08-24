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
    t_original = tok  # keep original for heuristics
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
            else:
                # No suffix provided: assume pm if hour 1-6 per new rule
                if 1 <= h <= 6:
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
            # Infer pm if hour 1-6 and no suffix (ambiguous 12h style)
            if 1 <= h <= 6:
                h += 12
            if 0 <= h < 24 and 0 <= m < 60:
                return time(h, m)
        elif re.fullmatch(r"\d{1,2}(am|pm)", t):
            h = int(t[:-2])
            if h == 12:
                h = 0
            if t.endswith("pm"):
                h += 12
            return time(h, 0)
        elif re.fullmatch(r"\d{1,2}", t):  # new: plain hour token
            h = int(t)
            if 0 <= h < 24:
                # infer pm for 1-6 inclusive when ambiguous
                if 1 <= h <= 6:
                    h += 12
                if h == 24:
                    h = 0
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
    - A time range or single time may appear on the same line as the date; line without time becomes an all-day event spanning 00:00 to 23:59 (or over the full day range if a day span was provided).
    - Lines lacking both date and time are ignored.
    - Enhancement: If a date/time line has no summary text, consume subsequent blank/whitespace-only lines until a non-blank. If that next non-blank line does NOT start a new date/time section, use it as the summary. If it does start a new date/time (or end of input), previous event becomes 'Untitled'.
    """
    # Keep original line ordering including blanks for deferred title resolution
    raw_lines = text.splitlines()

    events: List[Event] = []
    current_year = delivery_date.year
    saw_explicit_year = False
    current_month: Optional[int] = None
    last_day: Optional[int] = None

    # State for a pending event awaiting a title line
    pending_event = None  # dict with stored data

    def _is_month(line: str) -> bool:
        return bool(_MONTH_RE.match(line))

    def _is_year(line: str) -> bool:
        return bool(_YEAR_RE.match(line))

    def _starts_day_prefix(line: str) -> bool:
        return bool(_DAY_PREFIX_RE.match(line))

    def _contains_time_tokens(line: str) -> bool:
        return bool(_TIME_RANGE_RE.search(line) or _TIME_TOKEN_RE.search(line))

    def _starts_new_event_line(line: str) -> bool:
        ls = line.strip()
        if not ls:
            return False
        if _is_year(ls) or _is_month(ls) or _starts_day_prefix(ls):
            return True
        # Time-only line with existing last_day counts as new event
        if last_day is not None and _contains_time_tokens(ls):
            return True
        return False

    def _finalize_pending(force_untitled: bool = False):
        nonlocal pending_event
        if not pending_event:
            return
        title = pending_event["title"]
        if (not title) or force_untitled:
            title = "Untitled"
        _emit_event(title, pending_event)
        pending_event = None

    def _emit_event(title: str, ctx: dict):
        """Replicate event piece splitting & creation logic for a single pending context."""
        nonlocal events
        start_time_ctx = ctx.get("start_time")
        end_time_ctx = ctx.get("end_time")
        effective_day_end = ctx.get("effective_day_end")
        event_date_start = ctx["event_date_start"]
        event_date_end = ctx.get("event_date_end")

        pieces = [(title.strip(), start_time_ctx, end_time_ctx)]
        cleaned_pieces = []
        for ps, p_st, p_et in pieces:
            if ps:
                ps = ps.strip()
                ps = re.sub(r'^\d{1,4}\s*-\s*', '', ps)
                ps = re.sub(r'^[-–—:]+\s*', '', ps)
                ps = re.sub(r'\s{2,}', ' ', ps).strip()
            cleaned_pieces.append((ps, p_st, p_et))
        pieces = cleaned_pieces

        for piece_summary, p_start_time, p_end_time in pieces:
            pst = p_start_time
            pet = p_end_time
            if pst and pet and pet < pst and event_date_end is None:
                pet = pst
            if pst is None:
                start_dt = datetime.combine(event_date_start, time(0, 0))
                if event_date_end is not None:
                    end_dt = datetime.combine(event_date_end, time(23, 59))
                else:
                    end_dt = datetime.combine(event_date_start, time(23, 59))
            else:
                start_dt = datetime.combine(event_date_start, pst)
                if effective_day_end is not None and event_date_end is not None:
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

    for idx, raw in enumerate(raw_lines):
        line = raw.strip()

        # If we have a pending event awaiting title:
        if pending_event:
            if not line:  # skip blank lines until something substantive
                continue
            if _starts_new_event_line(line):
                # finalize previous as Untitled, then continue processing this line as new
                _finalize_pending(force_untitled=True)
            else:
                # Use this line as the title of pending event
                pending_event["title"] = line
                _finalize_pending()
                continue  # title line consumed; move to next

        # Year header
        m_year = _YEAR_RE.match(line)
        if m_year:
            current_year = int(m_year.group(1))
            saw_explicit_year = True
            continue
        # Month header
        m_month = _MONTH_RE.match(line)
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
        if not line:
            continue

        work = line
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
                assume_pm = (not suf) and (1 <= h1 <= 6)

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

        # If line started with a day and remainder begins with an alternative day option (e.g. 'or 20 ...'), drop it early
        if day_in_line:
            work = re.sub(r"(?i)^or\s+\d{1,2}(?:st|nd|rd|th)?\b", "", work).strip()

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
                if not suf1 and not suf2:  # both unspecified, apply pm inference rule
                    if 1 <= sh <= 6:
                        sh += 12
                    if 1 <= eh <= 6:
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
                assume_pm = (not suf) and (1 <= h1 <= 6)

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
        # Second standalone time => treat as end time (first token already consumed)
        if start_time is not None and end_time is None:
            m_second = _TIME_TOKEN_RE.search(work)
            if m_second:
                core2 = m_second.group(1)
                suf2 = (m_second.group(2) or "").lower()
                tval2 = _parse_time_token(core2 + suf2)
                if tval2:
                    if tval2 >= start_time:
                        end_time = tval2
                    else:
                        end_time = start_time
                    pre = work[: m_second.start()]
                    post = work[m_second.end() :]
                    pre = re.sub(r"[\s,&;-]*(?:and|to)?\s*$", " ", pre, flags=re.IGNORECASE)
                    work = (pre + post).strip()
                    work = re.sub(r"\s{2,}", " ", work)

        title = work.strip()
        if re.search(r"(?i)\bor\s+\d{1,2}(?:st|nd|rd|th)?\b", title):

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
            # pure date line with no time & no summary => will be ignored (no event)
            continue

        if not title and (day_in_line or start_time):
            # Defer creation; store pending awaiting a title from subsequent lines
            try:
                event_date_start = date(current_year, current_month, last_day)
                event_date_end = None
                if effective_day_end is not None:
                    event_date_end = date(current_year, current_month, effective_day_end)
            except ValueError:
                continue
            pending_event = {
                "title": "",  # unresolved
                "start_time": start_time,
                "end_time": end_time,
                "effective_day_end": effective_day_end,
                "event_date_start": event_date_start,
                "event_date_end": event_date_end,
            }
            continue
        if not title:
            continue

        # Normal immediate event path
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
                    if not suf1 and not suf2:
                        if 1 <= sh <= 6:
                            sh += 12
                        if 1 <= eh <= 6:
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
                        assume_pm = (not suf) and (1 <= h1 <= 6)

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

        cleaned_pieces = []
        for ps, p_st, p_et in pieces:
            if ps:
                ps = ps.strip()
                ps = re.sub(r'^\d{1,4}\s*-\s*', '', ps)
                ps = re.sub(r'^[-–—:]+\s*', '', ps)
                ps = re.sub(r'\s{2,}', ' ', ps).strip()
            cleaned_pieces.append((ps, p_st, p_et))
        pieces = cleaned_pieces

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
                    end_dt = datetime.combine(event_date_end, time(23, 59))
                else:
                    end_dt = datetime.combine(event_date_start, time(23, 59))
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

    # Finalize any leftover pending event at end of input
    if pending_event:
        _finalize_pending(force_untitled=True)

    return events

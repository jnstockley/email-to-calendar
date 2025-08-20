"""Utilities for working with event-related textual content.

Currently exposes a single helper to turn Markdown or simple HTML into
raw plain text while preserving the original newline structure as much
as is practical.
"""

from __future__ import annotations

from html import unescape
import re

__all__ = ["to_plaintext"]

# Precompiled regular expressions (compiled once for efficiency)
_RE_HTML_TAG = re.compile(r"<[^>]+>")
_RE_HTML_DETECT = re.compile(r"<[A-Za-z/!][^>]*>")
# Fenced code blocks: remove the opening (with optional lang) and closing fences separately
_RE_FENCED_OPEN = re.compile(r"```[A-Za-z0-9_-]*\n?")
_RE_FENCED_CLOSE = re.compile(r"```")
_RE_INLINE_CODE = re.compile(r"`([^`]+)`")
_RE_IMAGE = re.compile(r"!\[([^\]]*)]\([^)]*\)")
_RE_LINK_INLINE = re.compile(r"\[([^\]]+)]\([^)]*\)")
_RE_LINK_REFERENCE = re.compile(r"\[([^\]]+)]\[[^\]]*]")
_RE_LINK_DEFINITION = re.compile(r"^\s*\[[^\]]+]:\s+\S+.*$", re.MULTILINE)
_RE_BOLD = re.compile(r"(\*\*|__)(.*?)\1")
_RE_ITALIC = re.compile(r"(?<!\*)\*(?!\*)([^*]+?)\*(?!\*)|(?<!_)_([^_]+?)_(?!_)")
_RE_STRIKE = re.compile(r"~~(.*?)~~")
_RE_HEADING = re.compile(r"^ {0,3}#{1,6}\s+", re.MULTILINE)
_RE_BLOCKQUOTE = re.compile(r"^ {0,3}> ?", re.MULTILINE)
_RE_ULIST = re.compile(r"^ {0,3}[-*+]\s+", re.MULTILINE)
_RE_OLIST = re.compile(r"^ {0,3}\d+\.\s+", re.MULTILINE)
_RE_HRULE = re.compile(r"^ {0,3}([-_*])(?:\s*\1){2,}\s*$", re.MULTILINE)
_RE_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)
_RE_MULTI_BLANKS = re.compile(r"\n{3,}")

# Block-level tags that should logically introduce a line break boundary
_BLOCK_LEVEL_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "header",
    "footer",
    "aside",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "pre",
    "code",
    "blockquote",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
}
_BLOCK_TAGS_PATTERN = "|".join(sorted(_BLOCK_LEVEL_TAGS))

_BR_TAG_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)
_END_BLOCK_PATTERN = re.compile(rf"</(?:({_BLOCK_TAGS_PATTERN}))>", re.IGNORECASE)
_START_BLOCK_PATTERN = re.compile(
    rf"<(?:({_BLOCK_TAGS_PATTERN})(?:\s[^>]*)?)>", re.IGNORECASE
)


def _html_to_text(s: str) -> str:
    """Very lightweight HTML-to-text conversion (no external deps)."""
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = _BR_TAG_PATTERN.sub("\n", s)
    s = _START_BLOCK_PATTERN.sub(lambda m: f"\n{m.group(0)}", s)
    s = _END_BLOCK_PATTERN.sub(lambda m: f"{m.group(0)}\n", s)
    s = _RE_HTML_TAG.sub("", s)
    s = unescape(s)
    return s


def _strip_markdown(s: str) -> str:
    """Strip common Markdown formatting while preserving line breaks."""
    s = _RE_FENCED_OPEN.sub("", s)
    s = _RE_FENCED_CLOSE.sub("", s)
    s = _RE_INLINE_CODE.sub(lambda m: m.group(1), s)
    s = _RE_IMAGE.sub(lambda m: m.group(1), s)
    s = _RE_LINK_INLINE.sub(lambda m: m.group(1), s)
    s = _RE_LINK_REFERENCE.sub(lambda m: m.group(1), s)
    s = _RE_LINK_DEFINITION.sub("", s)
    s = _RE_BOLD.sub(lambda m: m.group(2), s)

    def _italic_repl(m: re.Match) -> str:  # type: ignore[override]
        return (m.group(1) or m.group(2) or "") if m else ""

    s = _RE_ITALIC.sub(_italic_repl, s)
    s = _RE_STRIKE.sub(lambda m: m.group(1), s)
    s = _RE_HEADING.sub("", s)
    s = _RE_BLOCKQUOTE.sub("", s)
    s = _RE_ULIST.sub("", s)
    s = _RE_OLIST.sub("", s)
    s = _RE_HRULE.sub("", s)
    return s


def to_plaintext(text: str | None) -> str:
    """Return the unformatted plain text contents of Markdown or HTML."""
    if not text:
        return ""
    s = text.replace("\r\n", "\n").replace("\r", "\n")
    if _RE_HTML_DETECT.search(s):
        s = _html_to_text(s)
    s = _strip_markdown(s)
    s = _RE_TRAILING_WS.sub("", s)
    s = _RE_MULTI_BLANKS.sub("\n\n", s)
    return s.strip()

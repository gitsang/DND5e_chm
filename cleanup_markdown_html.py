#!/usr/bin/env python3
"""Remove residual HTML from generated Markdown files.

Pandoc preserves some complex WinCHM fragments as raw HTML.  This cleanup pass
converts common inline/block tags and simple HTML tables to standard Markdown so
the md branch is easier to read directly on GitHub.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag


ROOT = Path(__file__).resolve().parent


def squeeze_spaces(text: str) -> str:
    text = html.unescape(text).replace("\xa0", " ")
    return re.sub(r"[ \t\f\v]+", " ", text).strip()


def escape_cell(text: str) -> str:
    text = squeeze_spaces(text)
    text = re.sub(r"\s*\n\s*", " ", text)
    text = text.replace("|", "\\|")
    return text or " "


def node_to_markdown(node) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if not isinstance(node, Tag):
        return ""

    name = node.name.lower()
    content = "".join(node_to_markdown(child) for child in node.children)
    content = html.unescape(content)

    if name in {"strong", "b"}:
        value = squeeze_spaces(content)
        return f"**{value}**" if value else ""
    if name in {"em", "i", "u"}:
        value = squeeze_spaces(content)
        return f"*{value}*" if value else ""
    if name == "br":
        return "  \n"
    if name == "hr":
        return "\n\n---\n\n"
    if name == "a":
        text = squeeze_spaces(content) or squeeze_spaces(node.get("href", ""))
        href = squeeze_spaces(node.get("href", ""))
        return f"[{text}]({href})" if href else text
    if name == "img":
        src = squeeze_spaces(node.get("src", ""))
        alt = squeeze_spaces(node.get("alt", ""))
        return f"![{alt}]({src})" if src else ""
    if name in {"span", "font", "center"}:
        return content
    if name in {"p", "div"}:
        value = squeeze_spaces(content)
        return f"\n\n{value}\n\n" if value else "\n\n"
    if name in {"sup", "sub"}:
        return squeeze_spaces(content)
    if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        level = int(name[1])
        value = squeeze_spaces(content)
        return f"\n\n{'#' * level} {value}\n\n" if value else ""
    if name == "li":
        value = squeeze_spaces(content)
        return f"- {value}\n" if value else ""
    if name in {"ul", "ol"}:
        return "\n" + content + "\n"
    return content


def table_to_markdown(table: Tag) -> str:
    caption = table.find("caption")
    caption_text = squeeze_spaces(caption.get_text(" ")) if caption else ""
    rows: list[list[str]] = []
    raw_rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            cells = tr.find_all(["th", "td"])
        raw_row = [
            normalize_markdown(
                "".join(node_to_markdown(child) for child in cell.children)
            ).strip()
            for cell in cells
        ]
        row = [escape_cell(cell) for cell in raw_row]
        if row:
            rows.append(row)
            raw_rows.append(raw_row)
    if not rows:
        return f"\n\n{caption_text}\n\n" if caption_text else "\n\n"

    width = max(len(row) for row in rows)
    rows = [row + [" "] * (width - len(row)) for row in rows]
    if width == 1:
        parts = []
        if caption_text:
            parts.append(caption_text)
        parts.extend(row[0] for row in raw_rows if row[0].strip())
        return "\n\n" + "\n\n".join(parts) + "\n\n"

    header = rows[0]
    body = rows[1:]
    lines = []
    if caption_text:
        lines.extend([caption_text, ""])
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * width) + " |")
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n\n" + "\n".join(lines) + "\n\n"


def replace_tables(text: str) -> str:
    pattern = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)

    def repl(match: re.Match[str]) -> str:
        soup = BeautifulSoup(match.group(0), "html.parser")
        table = soup.find("table")
        return table_to_markdown(table) if table else ""

    return pattern.sub(repl, text)


def replace_inline_html(text: str) -> str:
    # Convert tags that may nest inside Markdown table cells or paragraphs.
    def convert_fragment(match: re.Match[str]) -> str:
        soup = BeautifulSoup(match.group(0), "html.parser")
        return "".join(node_to_markdown(child) for child in soup.children)

    paired = [
        "a",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "span",
        "font",
        "p",
        "div",
        "sup",
        "sub",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "ul",
        "ol",
        "center",
    ]
    for tag in paired:
        text = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}>",
            convert_fragment,
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

    def convert_single(match: re.Match[str]) -> str:
        soup = BeautifulSoup(match.group(0), "html.parser")
        return "".join(node_to_markdown(child) for child in soup.children)

    text = re.sub(r"<br\b[^>]*/?>", "  \n", text, flags=re.IGNORECASE)
    text = re.sub(r"<hr\b[^>]*/?>", "\n\n---\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<img\b[^>]*>", convert_single, text, flags=re.IGNORECASE)
    text = re.sub(
        r"</?(?:tbody|thead|colgroup|col|tr|td|th|caption)\b[^>]*>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Some WinCHM/Pandoc fragments are malformed after earlier cleanup passes
    # and leave orphan container tags. These tags carry no Markdown semantics;
    # preserve their text content by removing only the tag shells.
    text = re.sub(r"</?(?:span|div|table)\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<u\b[^>]*>", "*", text, flags=re.IGNORECASE)
    text = re.sub(r"</u>", "*", text, flags=re.IGNORECASE)
    return text


def normalize_markdown(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("&#10;", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    text = re.sub(r"(?m)^\s+(-\s)", r"\1", text)
    return text.strip() + "\n"


def clean_text(text: str) -> str:
    text = replace_tables(text)
    previous = None
    while previous != text:
        previous = text
        text = replace_inline_html(text)
    return normalize_markdown(text)


def main() -> None:
    changed = 0
    for path in sorted(ROOT.rglob("*.md")):
        if ".git" in path.parts:
            continue
        original = path.read_text(encoding="utf-8", errors="replace")
        cleaned = clean_text(original)
        if cleaned != original:
            path.write_text(cleaned, encoding="utf-8")
            changed += 1
    print(f"cleaned {changed} Markdown files")


if __name__ == "__main__":
    main()

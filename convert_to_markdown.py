#!/usr/bin/env python3
"""Convert the WinCHM HTML source tree to Markdown.

The repository stores source pages as GBK/GB2312 HTML.  This script converts
those pages to UTF-8 GitHub Flavored Markdown with pandoc, then rewrites local
HTML links so the generated Markdown tree can be browsed directly on GitHub.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent
HTML_SUFFIXES = {".htm", ".html"}
TEXT_EXTENSIONS = {
    ".css",
    ".md",
    ".py",
    ".txt",
    ".xml",
    ".bat",
    ".gitattributes",
    ".gitignore",
}


def is_ignored(path: Path) -> bool:
    return ".git" in path.parts or path.name == Path(__file__).name


def decode_source(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "gb18030", "gbk", "gb2312"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("gb18030", errors="replace")


def encode_url_path(path: str) -> str:
    return quote(unquote(path), safe="/:@!$&'()*+,;=-._~%")


def rewrite_markdown_links(markdown: str) -> str:
    def rewrite_target(target: str) -> str:
        target = target.replace("\\", "/")
        parsed = urlsplit(target)
        if parsed.scheme or target.startswith("#") or target.startswith("//"):
            return target

        path = unquote(parsed.path)
        lower = path.lower()
        if lower.endswith(".html"):
            path = path[:-5] + ".md"
        elif lower.endswith(".htm"):
            path = path[:-4] + ".md"

        path = encode_url_path(path)
        return urlunsplit(("", "", path, parsed.query, parsed.fragment))

    def repl(match: re.Match[str]) -> str:
        prefix, target = match.group(1), match.group(2)
        return f"{prefix}{rewrite_target(target)}"

    markdown = re.sub(r"(\]\()([^\s)]+)", repl, markdown)
    markdown = re.sub(
        r'(<a\s+[^>]*href=["\'])([^"\']+)', repl, markdown, flags=re.IGNORECASE
    )
    markdown = re.sub(
        r'(<img\s+[^>]*src=["\'])([^"\']+)', repl, markdown, flags=re.IGNORECASE
    )
    return markdown.replace("\r\n", "\n").replace("\r", "\n")


def convert_html(path: Path) -> Path:
    text = decode_source(path)
    output = path.with_suffix(".md")
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_input = Path(temp_dir) / "input.html"
        temp_output = Path(temp_dir) / "output.md"
        temp_input.write_text(text, encoding="utf-8")
        subprocess.run(
            [
                "pandoc",
                str(temp_input),
                "-f",
                "html",
                "-t",
                "gfm",
                "--wrap=none",
                "-o",
                str(temp_output),
            ],
            check=True,
            cwd=ROOT,
        )
        markdown = temp_output.read_text(encoding="utf-8")
    output.write_text(rewrite_markdown_links(markdown).strip() + "\n", encoding="utf-8")
    return output


def normalize_text_file(path: Path) -> None:
    text = decode_source(path)
    path.write_text(text.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8")


def main() -> None:
    html_files = sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and not is_ignored(path)
        and path.suffix.lower() in HTML_SUFFIXES
    )
    for index, path in enumerate(html_files, start=1):
        convert_html(path)
        path.unlink()
        if index % 250 == 0:
            print(f"converted {index}/{len(html_files)}")

    for path in sorted(ROOT.rglob("*")):
        if (
            path.is_file()
            and not is_ignored(path)
            and path.suffix.lower() in TEXT_EXTENSIONS
        ):
            normalize_text_file(path)

    print(f"converted {len(html_files)} HTML files to Markdown")


if __name__ == "__main__":
    main()

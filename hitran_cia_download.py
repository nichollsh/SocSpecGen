#!/usr/bin/env python3
"""
Download all HITRAN CIA .cia files and store each in a subfolder of the same name.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, List
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


DEFAULT_PAGE_URL = "https://hitran.org/cia/"
USER_AGENT = "Mozilla/5.0 (compatible; hitran-cia-downloader/1.0)"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value)


def fetch_html(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Failed to fetch {url}: HTTP {response.status}")
        return response.read().decode("utf-8", errors="replace")


def extract_cia_links(page_url: str) -> List[str]:
    html = fetch_html(page_url)
    parser = LinkParser()
    parser.feed(html)
    links = []
    seen = set()
    for href in parser.links:
        full_url = urljoin(page_url, href)
        path = urlparse(full_url).path.lower()
        if not path.endswith(".cia"):
            continue
        if full_url in seen:
            continue
        seen.add(full_url)
        links.append(full_url)
    return links


def build_destination_name(url: str, duplicate_counts: Counter) -> tuple[str, str]:
    path = urlparse(url).path
    filename = os.path.basename(path)
    base = filename[:-4] if filename.lower().endswith(".cia") else filename
    if duplicate_counts[filename] > 1:
        parent = os.path.basename(os.path.dirname(path)) or "data"
        dest_filename = f"{base}__{parent}.cia"
    else:
        dest_filename = filename
    return base, dest_filename


def download_file(url: str, dest_file: Path, overwrite: bool, retries: int = 3) -> None:
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    if dest_file.exists() and not overwrite:
        print(f"Skipping existing: {dest_file}")
        return
    tmp_file = dest_file.with_suffix(dest_file.suffix + ".part")
    req = Request(url, headers={"User-Agent": USER_AGENT})

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(req, timeout=60) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                with tmp_file.open("wb") as out:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
            tmp_file.replace(dest_file)
            print(f"Downloaded: {dest_file}")
            return
        except Exception as exc:  # noqa: BLE001 - surface retry context
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)
                continue
            raise RuntimeError(f"Failed downloading {url}: {exc}") from exc
        finally:
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except OSError:
                    pass
    if last_error:
        raise RuntimeError(f"Failed downloading {url}: {last_error}")


def download_all(
    urls: Iterable[str],
    output_dir: Path,
    overwrite: bool,
    sleep_seconds: float,
) -> None:
    filenames = [os.path.basename(urlparse(u).path) for u in urls]
    duplicate_counts = Counter(filenames)

    for url in urls:
        base, dest_filename = build_destination_name(url, duplicate_counts)
        dest_dir = output_dir / base
        dest_file = dest_dir / dest_filename
        download_file(url, dest_file, overwrite=overwrite)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download all HITRAN CIA .cia files into subfolders by pair name."
    )
    parser.add_argument(
        "--page-url",
        default=DEFAULT_PAGE_URL,
        help=f"HITRAN CIA page URL (default: {DEFAULT_PAGE_URL})",
    )
    parser.add_argument(
        "--output-dir",
        default="hitran",
        help="Destination directory (default: hitran)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing files",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.2,
        help="Seconds to sleep between downloads (default: 0.2)",
    )
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    urls = extract_cia_links(args.page_url)
    if not urls:
        print("No .cia links found.", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    download_all(urls, output_dir, overwrite=args.overwrite, sleep_seconds=args.sleep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

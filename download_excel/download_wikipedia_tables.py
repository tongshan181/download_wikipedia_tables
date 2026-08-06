#!/usr/bin/env python3
"""
Wikipedia Table Downloader
==========================
Scrape tables from Wikipedia pages and save them locally.

Supports multiple output formats: CSV, Excel, JSON.

Usage:
    python download_wikipedia_tables.py --url <WIKI_URL> [--format csv|excel|json] [--output-dir <dir>]
    python download_wikipedia_tables.py --search "<query>" [--format csv|excel|json] [--output-dir <dir>]

Examples:
    # Download tables from a specific Wikipedia page as CSV
    python download_wikipedia_tables.py --url "https://en.wikipedia.org/wiki/List_of_countries_by_GDP"

    # Search for a page and download tables as JSON
    python download_wikipedia_tables.py --search "Periodic table" --format json

    # Download tables as Excel with custom output directory
    python download_wikipedia_tables.py --url "https://en.wikipedia.org/wiki/World_Cup" --format excel --output-dir ./wiki_tables

    # Download only the first 2 tables
    python download_wikipedia_tables.py --url "https://en.wikipedia.org/wiki/List_of_capitals" --max-tables 2
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import quote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Optional: openpyxl for Excel support
try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

# Optional: beautifulsoup4 for HTML parsing
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


# Wikipedia language support
WIKI_LANGUAGES = {
    "en": "https://en.wikipedia.org",
    "zh": "https://zh.wikipedia.org",
    "ja": "https://ja.wikipedia.org",
    "de": "https://de.wikipedia.org",
    "fr": "https://fr.wikipedia.org",
    "es": "https://es.wikipedia.org",
    "ru": "https://ru.wikipedia.org",
}

DEFAULT_LANG = "en"
CURRENT_LANG = DEFAULT_LANG


def detect_lang_from_url(url: str) -> str:
    """Detect Wikipedia language from URL."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    for lang, base in WIKI_LANGUAGES.items():
        if lang in hostname:
            return lang
    return DEFAULT_LANG


def set_wiki_language(lang: str):
    """Set the current Wikipedia language."""
    global CURRENT_LANG
    if lang in WIKI_LANGUAGES:
        CURRENT_LANG = lang
    else:
        print(f"[WARN] Unknown language '{lang}', using 'en'")
        CURRENT_LANG = "en"


def get_wiki_api_url() -> str:
    """Get the API URL for the current language."""
    return f"{WIKI_LANGUAGES[CURRENT_LANG]}/w/api.php"


def get_wiki_base_url() -> str:
    """Get the base URL for the current language."""
    return WIKI_LANGUAGES[CURRENT_LANG]


def create_session(user_agent: str = "WikipediaTableDownloader/1.0") -> requests.Session:
    """Create a requests session with retry strategy."""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=5,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": user_agent})
    return session


def search_wikipedia(
    query: str,
    limit: int = 10,
    session: Optional[requests.Session] = None,
) -> List[Dict[str, Any]]:
    """
    Search Wikipedia for pages matching the query.

    Args:
        query: Search query keyword.
        limit: Maximum number of results.
        session: Optional requests session.

    Returns:
        List of page info dictionaries with titles and URLs.
    """
    if session is None:
        session = create_session()

    results = []
    wiki_base = get_wiki_base_url()
    print(f"[INFO] Searching Wikipedia ({CURRENT_LANG}) for: '{query}'")

    try:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "format": "json",
        }
        response = session.get(get_wiki_api_url(), params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        pages = data.get("query", {}).get("search", [])
        for page in pages:
            title = page.get("title", "")
            page_id = page.get("pageid", 0)
            snippet = page.get("snippet", "")
            results.append({
                "title": title,
                "page_id": page_id,
                "url": f"{wiki_base}/wiki/{quote(title.replace(' ', '_'))}",
                "snippet": re.sub(r"<[^>]+>", "", snippet),
            })

        print(f"[INFO] Found {len(results)} pages")
        return results

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Error searching Wikipedia: {e}")
        return results


def get_page_title_from_url(url: str) -> str:
    """Extract the page title from a Wikipedia URL."""
    parsed = urlparse(url)
    path = parsed.path
    match = re.search(r"/wiki/([^?#]+)", path)
    if match:
        title = match.group(1).replace("_", " ")
        detected = detect_lang_from_url(url)
        if detected != DEFAULT_LANG:
            set_wiki_language(detected)
        return title
    return url


def fetch_wikipedia_page(
    url: str,
    session: Optional[requests.Session] = None,
) -> Optional[str]:
    """Fetch the HTML content of a Wikipedia page."""
    if session is None:
        session = create_session()

    try:
        print(f"[INFO] Fetching page: {url}")
        response = session.get(url, timeout=60)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Error fetching page {url}: {e}")
        return None


def clean_wiki_text(text: str) -> str:
    """Clean Wikipedia text by removing references, citations, and extra whitespace."""
    # Remove reference markers like [1], [2], [a], etc.
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\[[a-zA-Z]+\]", "", text)
    text = re.sub(r"\[#[^\]]*\]", "", text)
    # Remove citation templates
    text = re.sub(r"\{\{[^}]+\}\}", "", text)
    # Remove pipe characters used in templates
    text = text.replace("|", " ")
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_wikipedia_table(table_elem) -> Optional[Dict[str, Any]]:
    """Parse a single Wikipedia table element into structured data."""
    headers = []
    rows = []

    # Extract headers from <thead> or first row with <th> cells
    header_cells = []
    thead = table_elem.find("thead")
    if thead:
        for tr in thead.find_all("tr"):
            th_cells = tr.find_all("th")
            if th_cells:
                row_headers = []
                for th in th_cells:
                    colspan = int(th.get("colspan", 1))
                    text = clean_wiki_text(th.get_text())
                    for _ in range(colspan):
                        row_headers.append(text)
                if row_headers:
                    header_cells.append(row_headers)

    # If no thead, check first row for <th> cells
    if not header_cells:
        for tr in table_elem.find_all("tr"):
            th_cells = tr.find_all("th")
            if th_cells:
                row_headers = []
                for th in th_cells:
                    colspan = int(th.get("colspan", 1))
                    text = clean_wiki_text(th.get_text())
                    for _ in range(colspan):
                        row_headers.append(text)
                header_cells.append(row_headers)
                break

    # Flatten headers (use last header row for multi-level headers)
    if header_cells:
        headers = header_cells[-1]

    # Extract data rows from <tbody> or all <tr> without <th>
    tbody = table_elem.find("tbody")
    if not tbody:
        tbody = table_elem

    for tr in tbody.find_all("tr"):
        if tr.find_all("th"):
            continue
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        row = []
        for cell in cells:
            colspan = int(cell.get("colspan", 1))
            text = clean_wiki_text(cell.get_text())
            for _ in range(colspan):
                row.append(text)
        rows.append(row)

    if not rows:
        return None

    # Normalize row lengths to match headers
    num_cols = len(headers) if headers else (len(rows[0]) if rows else 0)
    normalized_rows = []
    for row in rows:
        if len(row) < num_cols:
            row.extend([""] * (num_cols - len(row)))
        elif len(row) > num_cols:
            row = row[:num_cols]
        normalized_rows.append(row)

    return {"headers": headers, "rows": normalized_rows}


def extract_tables_from_html(
    html_content: str,
    max_tables: int = 0,
) -> List[Dict[str, Any]]:
    """Extract all tables from Wikipedia HTML content."""
    if not HAS_BS4:
        print("[ERROR] beautifulsoup4 is required. Install with: pip install beautifulsoup4")
        return []

    tables = []
    soup = BeautifulSoup(html_content, "html.parser")

    # Find tables in the main content area
    body_content = soup.find("div", id="bodyContent")
    if not body_content:
        body_content = soup

    table_elements = body_content.find_all("table")

    for idx, table_elem in enumerate(table_elements):
        if max_tables > 0 and idx >= max_tables:
            break

        table_data = parse_wikipedia_table(table_elem)
        if table_data and table_data["rows"]:
            caption = table_elem.find("caption")
            table_class = table_elem.get("class", [])
            table_data["caption"] = caption.get_text(strip=True) if caption else ""
            table_data["table_class"] = table_class
            table_data["index"] = idx
            tables.append(table_data)

    print(f"[INFO] Extracted {len(tables)} tables from the page")
    return tables


def sanitize_title(title: str, max_len: int = 100) -> str:
    """Sanitize page title for use in filenames."""
    safe = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
    safe = re.sub(r"_+", "_", safe)[:max_len]
    return safe


def tables_to_csv(
    tables: List[Dict[str, Any]],
    output_dir: str = "./downloaded_wiki_tables",
    page_title: str = "wikipedia_page",
) -> List[str]:
    """Save extracted tables to CSV files."""
    os.makedirs(output_dir, exist_ok=True)
    safe_title = sanitize_title(page_title)
    saved_paths = []

    for i, table in enumerate(tables):
        if i == 0 and len(tables) == 1:
            filename = f"{safe_title}_table.csv"
        else:
            filename = f"{safe_title}_table_{i + 1}.csv"

        filepath = os.path.join(output_dir, filename)

        if os.path.exists(filepath):
            timestamp = datetime.now().strftime("%H%M%S")
            filename = f"{safe_title}_table_{i + 1}_{timestamp}.csv"
            filepath = os.path.join(output_dir, filename)

        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                if table["headers"]:
                    writer.writerow(table["headers"])
                for row in table["rows"]:
                    writer.writerow(row)

            print(f"[SUCCESS] Saved table {i + 1}/{len(tables)}: {filepath}")
            print(f"         Rows: {len(table['rows'])}, Columns: {len(table['headers']) if table['headers'] else 'N/A'}")
            if table.get("caption"):
                print(f"         Caption: {table['caption']}")
            saved_paths.append(filepath)
        except Exception as e:
            print(f"[ERROR] Error saving table {i + 1}: {e}")

    return saved_paths


def tables_to_excel(
    tables: List[Dict[str, Any]],
    output_dir: str = "./downloaded_wiki_tables",
    page_title: str = "wikipedia_page",
) -> Optional[str]:
    """Save extracted tables to an Excel file with multiple sheets."""
    if not HAS_OPENPYXL:
        print("[ERROR] openpyxl is required for Excel export. Install with: pip install openpyxl")
        return None

    os.makedirs(output_dir, exist_ok=True)
    safe_title = sanitize_title(page_title, max_len=50)
    filename = f"{safe_title}_tables.xlsx"
    filepath = os.path.join(output_dir, filename)

    try:
        wb = openpyxl.Workbook()

        for i, table in enumerate(tables):
            if i == 0 and len(tables) == 1:
                sheet_name = "Table"
            else:
                sheet_name = f"Table_{i + 1}"
            sheet_name = sheet_name[:31].replace(":", "").replace("\\", "").replace("/", "")

            if i == 0:
                ws = wb.active
                ws.title = sheet_name
            else:
                ws = wb.create_sheet(title=sheet_name)

            if table["headers"]:
                ws.append(table["headers"])
            for row in table["rows"]:
                ws.append(row)

        wb.save(filepath)
        print(f"[SUCCESS] Saved Excel file: {filepath}")
        print(f"         Total sheets: {len(tables)}")
        return filepath

    except Exception as e:
        print(f"[ERROR] Error saving Excel file: {e}")
        return None


def tables_to_json(
    tables: List[Dict[str, Any]],
    output_dir: str = "./downloaded_wiki_tables",
    page_title: str = "wikipedia_page",
) -> Optional[str]:
    """Save extracted tables to a JSON file."""
    os.makedirs(output_dir, exist_ok=True)
    safe_title = sanitize_title(page_title)
    filename = f"{safe_title}_tables.json"
    filepath = os.path.join(output_dir, filename)

    try:
        data = {
            "page_title": page_title,
            "extracted_at": datetime.now().isoformat(),
            "table_count": len(tables),
            "tables": tables,
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[SUCCESS] Saved JSON file: {filepath}")
        return filepath

    except Exception as e:
        print(f"[ERROR] Error saving JSON file: {e}")
        return None


def download_wikipedia_tables(
    url: str,
    output_dir: str = "./downloaded_wiki_tables",
    format: str = "csv",
    max_tables: int = 0,
    session: Optional[requests.Session] = None,
) -> List[str]:
    """
    Download all tables from a Wikipedia page.

    Args:
        url: Wikipedia page URL.
        output_dir: Directory to save the extracted tables.
        format: Output format - 'csv', 'excel', or 'json'.
        max_tables: Maximum number of tables to extract (0 = all).
        session: Optional requests session.

    Returns:
        List of paths to saved files.
    """
    if session is None:
        session = create_session()

    page_title = get_page_title_from_url(url)
    print(f"[INFO] Page title: {page_title}")

    html_content = fetch_wikipedia_page(url, session)
    if not html_content:
        print("[ERROR] Failed to fetch page content.")
        return []

    tables = extract_tables_from_html(html_content, max_tables)
    if not tables:
        print("[WARN] No tables found on this page.")
        return []

    # Display summary
    print(f"\n{'='*60}")
    print(f"Found {len(tables)} tables on the page:")
    print(f"{'='*60}")
    for i, table in enumerate(tables):
        caption = table.get("caption", "")
        headers = table["headers"]
        rows = table["rows"]
        print(f"\n  Table {i + 1}:")
        print(f"    Rows: {len(rows)}, Columns: {len(headers)}")
        if caption:
            print(f"    Caption: {caption}")
        if headers:
            preview = headers[:5]
            if len(headers) > 5:
                preview.append("...")
            print(f"    Headers: {preview}")

    # Save tables
    print(f"\n{'='*60}")
    print(f"Saving tables as {format.upper()}...")
    print(f"{'='*60}")

    saved_paths = []
    if format == "csv":
        saved_paths = tables_to_csv(tables, output_dir, page_title)
    elif format == "excel":
        path = tables_to_excel(tables, output_dir, page_title)
        if path:
            saved_paths = [path]
    elif format == "json":
        path = tables_to_json(tables, output_dir, page_title)
        if path:
            saved_paths = [path]
    else:
        print(f"[ERROR] Unsupported format: {format}. Use 'csv', 'excel', or 'json'.")

    return saved_paths


def display_search_results(results: List[Dict[str, Any]]):
    """Display Wikipedia search results in a formatted manner."""
    if not results:
        print("[WARN] No results found.")
        return

    print(f"\n{'='*60}")
    print(f"Search Results ({len(results)} pages):")
    print(f"{'='*60}")

    for i, item in enumerate(results, 1):
        print(f"\n[{i}] {item['title']}")
        print(f"    URL: {item['url']}")
        snippet = item.get("snippet", "")
        if snippet:
            print(f"    {snippet[:200]}")


def main():
    parser = argparse.ArgumentParser(
        description="Wikipedia Table Downloader - Extract and download tables from Wikipedia pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download tables from a specific Wikipedia page
  python download_wikipedia_tables.py --url "https://en.wikipedia.org/wiki/List_of_countries_by_GDP"

  # Search for a Wikipedia page and download tables
  python download_wikipedia_tables.py --search "List of programming languages"

  # Download tables as Excel
  python download_wikipedia_tables.py --url "https://en.wikipedia.org/wiki/Periodic_table" --format excel

  # Download tables as JSON
  python download_wikipedia_tables.py --url "https://en.wikipedia.org/wiki/List_of_largest_companies" --format json

  # Download only the first 3 tables
  python download_wikipedia_tables.py --url "https://en.wikipedia.org/wiki/World_Cup" --max-tables 3

  # Custom output directory
  python download_wikipedia_tables.py --url "https://en.wikipedia.org/wiki/List_of_capitals" --output-dir ./wiki_data
        """,
    )

    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--url", "-u",
        type=str,
        help="Wikipedia page URL to extract tables from",
    )
    input_group.add_argument(
        "--search", "-s",
        type=str,
        help="Search Wikipedia for a page, then extract tables from the top result",
    )

    # Output options
    parser.add_argument(
        "--format", "-f",
        type=str,
        choices=["csv", "excel", "json"],
        default="csv",
        help="Output format (default: csv)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="./downloaded_wiki_tables",
        help="Directory to save downloaded tables (default: ./downloaded_wiki_tables)",
    )
    parser.add_argument(
        "--max-tables",
        type=int,
        default=0,
        help="Maximum number of tables to extract (0 = all, default: 0)",
    )
    parser.add_argument(
        "--search-limit",
        type=int,
        default=10,
        help="Maximum number of search results (default: 10)",
    )

    args = parser.parse_args()

    # Check dependencies
    if not HAS_BS4:
        print("[ERROR] beautifulsoup4 is required. Install with: pip install beautifulsoup4")
        sys.exit(1)

    if args.format == "excel" and not HAS_OPENPYXL:
        print("[ERROR] openpyxl is required for Excel export. Install with: pip install openpyxl")
        sys.exit(1)

    session = create_session()

    if args.search:
        # Search for pages
        results = search_wikipedia(args.search, args.search_limit, session)
        if not results:
            print("[ERROR] No pages found for the search query.")
            sys.exit(1)

        display_search_results(results)

        # Use the top result
        top_result = results[0]
        url = top_result["url"]
        print(f"\n[INFO] Using top result: {top_result['title']}")
        print(f"[INFO] URL: {url}")

        # Rate limiting
        time.sleep(1)

        saved_paths = download_wikipedia_tables(
            url=url,
            output_dir=args.output_dir,
            format=args.format,
            max_tables=args.max_tables,
            session=session,
        )
    else:
        # Direct URL
        url = args.url

        # Validate URL
        if "wikipedia.org" not in url:
            print("[WARN] URL does not appear to be a Wikipedia page.")
            proceed = input("Continue anyway? (y/n): ").strip().lower()
            if proceed != "y":
                print("Aborted.")
                sys.exit(0)

        saved_paths = download_wikipedia_tables(
            url=url,
            output_dir=args.output_dir,
            format=args.format,
            max_tables=args.max_tables,
            session=session,
        )

    # Summary
    if saved_paths:
        print(f"\n{'='*60}")
        print("Download Complete!")
        print(f"{'='*60}")
        print(f"Saved {len(saved_paths)} file(s):")
        for path in saved_paths:
            print(f"  - {path}")
    else:
        print("\n[ERROR] No files were saved.")
        sys.exit(1)


if __name__ == "__main__":
    main()

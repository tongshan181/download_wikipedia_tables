#!/usr/bin/env python3
"""
Google Images Phone Scraper (via Serper API)
=============================================
A precision script to scrape phone model images from Google Image Search using
Serper API and save them locally to /dfs/data/.

Key features:
- Uses Serper Images API to query Google Images (works from behind firewalls)
- Downloads images directly from CDN URLs returned by Serper
- Deduplication via content hashing
- Configurable keywords, output directory, and result limits
- Rate limiting and retry logic for reliability
- Batch support for multiple phone models

Usage:
    python google_phone_image_scraper.py --keyword "iPhone 15 Pro"
    python google_phone_image_scraper.py --keyword "Samsung Galaxy S24" --max-results 20
    python google_phone_image_scraper.py --keywords-file phone_models.txt --output /dfs/data/google_phone_images
    python google_phone_image_scraper.py --keyword "Pixel 8 Pro" --max-results 15 --max-pages 3

Dependencies:
    - requests (for HTTP requests and image downloading)
    - tenacity (for retry logic)
    - argparse (built-in)
"""

import os
import sys
import time
import json
import argparse
import re
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus, urlparse

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


# --------------------------------------------------------------------------- #
#  Configuration
# --------------------------------------------------------------------------- #

# Serper Images API endpoint
SERPER_IMAGES_URL = "https://google.serper.dev/images"

# Serper API key (from existing tools in this project)
SERPER_API_KEY = "991d12528993928022f4326c77f1ef9a9d7b021b"

# Default output directory
DEFAULT_OUTPUT_DIR = "/dfs/data/google_phone_images"

# Default headers for image downloading
IMAGE_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Retry configuration
MAX_RETRIES = 3
RETRY_WAIT_MIN = 2
RETRY_WAIT_MAX = 10

# Rate limiting
SERPER_REQUEST_DELAY = 1.5  # Seconds between Serper API requests
IMAGE_DOWNLOAD_DELAY = 0.3  # Seconds between image downloads

# Image configuration
MIN_IMAGE_SIZE = 10 * 1024  # Minimum image file size: 10KB
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # Maximum image file size: 20MB
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

# Phone brands list for keyword enhancement
PHONE_BRANDS = [
    "Apple", "iPhone", "Samsung", "Google", "Pixel", "OnePlus",
    "Xiaomi", "Huawei", "Honor", "OPPO", "vivo", "Realme",
    "Motorola", "Nokia", "Sony", "Nothing", "ASUS", "ROG",
    "Lenovo", "ZTE", "TCL", "Honor",
]


# --------------------------------------------------------------------------- #
#  Data Models
# --------------------------------------------------------------------------- #

@dataclass
class PhoneImage:
    """Represents a single phone image downloaded from Google Images."""
    phone_model: str
    image_url: str
    local_path: str
    thumbnail_url: str = ""
    source_page: str = ""
    width: int = 0
    height: int = 0
    file_size: int = 0
    download_status: str = "pending"  # pending, success, failed, skipped
    error_message: str = ""
    content_hash: str = ""


@dataclass
class PhoneModelResult:
    """Represents the scraping result for a single phone model."""
    keyword: str
    total_images_found: int = 0
    total_images_downloaded: int = 0
    successful_downloads: int = 0
    failed_downloads: int = 0
    skipped_duplicates: int = 0
    skipped_invalid: int = 0
    images: List[PhoneImage] = field(default_factory=list)
    timestamp: str = ""
    output_dir: str = ""


# --------------------------------------------------------------------------- #
#  Utility Functions
# --------------------------------------------------------------------------- #

def sanitize_filename(name: str) -> str:
    """Sanitize a string to be used as a directory or file name."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'[\s_]+', '_', name)
    name = name[:80]
    return name.strip('_')


def compute_content_hash(data: bytes) -> str:
    """Compute SHA-256 hash of image data for deduplication."""
    return hashlib.sha256(data).hexdigest()[:16]


def get_image_extension(url: str, content_type: str = "") -> str:
    """Determine image file extension from URL or content type."""
    if content_type:
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "image/bmp": ".bmp",
        }
        if content_type in ext_map:
            return ext_map[content_type]

    parsed = urlparse(url)
    path = parsed.path.lower()
    for ext in SUPPORTED_EXTENSIONS:
        if path.endswith(ext):
            return ext

    # Try to extract extension from query params (some CDNs use ?format=xxx)
    for param in ["format", "type", "ext"]:
        match = re.search(rf'{param}=([a-z]+)', path, re.IGNORECASE)
        if match:
            ext = f".{match.group(1)}"
            if ext in SUPPORTED_EXTENSIONS:
                return ext

    return ".jpg"


# --------------------------------------------------------------------------- #
#  Serper Image Search
# --------------------------------------------------------------------------- #

class GoogleImageSearcher:
    """Searches Google Images via Serper API for phone model images."""

    def __init__(self, api_key: str = SERPER_API_KEY):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        })
        self._last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting between API requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < SERPER_REQUEST_DELAY:
            time.sleep(SERPER_REQUEST_DELAY - elapsed)
        self._last_request_time = time.time()

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=RETRY_WAIT_MIN, max=RETRY_WAIT_MAX),
        retry=retry_if_exception_type((requests.RequestException,)),
        reraise=True,
    )
    def search(self, keyword: str, num: int = 100, page: int = 0) -> Dict:
        """
        Search Google Images via Serper API.

        Args:
            keyword: Search keyword (phone model name)
            num: Number of results to return (Serper default max is 100)
            page: Page number (0-based)

        Returns:
            Dictionary with search results from Serper
        """
        self._rate_limit()

        payload = {
            "q": keyword,
            "num": min(num, 100),  # Serper max per request is 100
            "hl": "en",
            "tbs": "",  # No time filter
        }
        if page > 0:
            payload["page"] = page

        try:
            response = self.session.post(
                SERPER_IMAGES_URL,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise e
        except json.JSONDecodeError:
            print(f"    [WARN] Serper returned non-JSON response")
            return {"images": []}

    def extract_images(self, keyword: str, max_pages: int = 5, results_per_page: int = 100) -> List[Dict]:
        """
        Extract image information from Serper search results across multiple pages.

        Args:
            keyword: Search keyword
            max_pages: Maximum number of pages to fetch
            results_per_page: Results per page (max 100 for Serper)

        Returns:
            List of image information dictionaries
        """
        all_images = []
        seen_urls = set()

        for page in range(max_pages):
            print(f"    [INFO] Searching page {page + 1}/{max_pages}...")

            try:
                result = self.search(keyword, num=results_per_page, page=page)
            except Exception as e:
                print(f"    [ERROR] Failed to fetch page {page + 1}: {e}")
                continue

            if not result:
                print(f"    [WARN] No response for page {page + 1}")
                continue

            images = result.get("images", [])
            if not images:
                print(f"    [INFO] No images found on page {page + 1}, stopping.")
                break

            found_on_page = 0
            for img in images:
                url = img.get("imageUrl", "")
                if not url or not url.startswith(("http://", "https://")):
                    continue

                # Skip duplicate URLs
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                image_info = {
                    "keyword": keyword,
                    "url": url,
                    "thumbnail_url": img.get("thumbnailUrl", ""),
                    "source_page": img.get("source", ""),
                    "width": img.get("imageWidth", 0),
                    "height": img.get("imageHeight", 0),
                    "title": img.get("title", ""),
                    "link": img.get("link", ""),
                    "position": img.get("position", 0),
                    "page_num": page + 1,
                }
                all_images.append(image_info)
                found_on_page += 1

            print(f"    [INFO] Found {found_on_page} new images on page {page + 1} (total: {len(all_images)})")

            if found_on_page == 0:
                break

        return all_images


# --------------------------------------------------------------------------- #
#  Image Downloader
# --------------------------------------------------------------------------- #

class ImageDownloader:
    """Downloads and saves images with deduplication."""

    def __init__(self, output_dir: str, headers: Dict[str, str] = None):
        self.output_dir = Path(output_dir)
        self.session = requests.Session()
        self.session.headers.update(headers or IMAGE_DOWNLOAD_HEADERS)
        self._seen_hashes: Set[str] = set()
        self._last_download_time = 0

    def _rate_limit(self):
        """Enforce rate limiting between downloads."""
        elapsed = time.time() - self._last_download_time
        if elapsed < IMAGE_DOWNLOAD_DELAY:
            time.sleep(IMAGE_DOWNLOAD_DELAY - elapsed)
        self._last_download_time = time.time()

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=RETRY_WAIT_MIN, max=RETRY_WAIT_MAX),
        retry=retry_if_exception_type((requests.RequestException,)),
        reraise=True,
    )
    def _get_image_data(self, url: str) -> Optional[bytes]:
        """Download image data from URL with retry."""
        self._rate_limit()

        try:
            response = self.session.get(
                url,
                timeout=30,
                stream=True,
            )
            response.raise_for_status()

            # Check content type
            content_type = response.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                # Some servers return images with incorrect Content-Type
                parsed = urlparse(url)
                path = parsed.path.lower()
                is_image_url = any(path.endswith(ext) for ext in SUPPORTED_EXTENSIONS)
                if not is_image_url:
                    return None

            # Read content
            data = response.content

            # Check file size
            if len(data) < MIN_IMAGE_SIZE:
                return None
            if len(data) > MAX_IMAGE_SIZE:
                return None

            return data

        except requests.RequestException as e:
            raise e

    def download_image(self, image_info: Dict, phone_dir: Path) -> PhoneImage:
        """
        Download a single image and save it.

        Args:
            image_info: Image information dictionary from Serper search
            phone_dir: Directory to save images for this phone model

        Returns:
            PhoneImage dataclass with download result
        """
        keyword = image_info["keyword"]
        url = image_info["url"]

        # Download image data
        try:
            data = self._get_image_data(url)
        except Exception as e:
            return PhoneImage(
                phone_model=keyword,
                image_url=url,
                local_path="",
                thumbnail_url=image_info.get("thumbnail_url", ""),
                source_page=image_info.get("source_page", ""),
                width=image_info.get("width", 0),
                height=image_info.get("height", 0),
                download_status="failed",
                error_message=f"Download error: {str(e)[:100]}",
            )

        if data is None:
            return PhoneImage(
                phone_model=keyword,
                image_url=url,
                local_path="",
                thumbnail_url=image_info.get("thumbnail_url", ""),
                source_page=image_info.get("source_page", ""),
                width=image_info.get("width", 0),
                height=image_info.get("height", 0),
                download_status="failed",
                error_message="Failed to download or invalid image",
            )

        # Compute content hash for deduplication
        content_hash = compute_content_hash(data)

        if content_hash in self._seen_hashes:
            return PhoneImage(
                phone_model=keyword,
                image_url=url,
                local_path="",
                thumbnail_url=image_info.get("thumbnail_url", ""),
                download_status="skipped",
                error_message="Duplicate image (content hash match)",
                content_hash=content_hash,
            )

        # Mark as seen
        self._seen_hashes.add(content_hash)

        # Determine file extension
        ext = get_image_extension(url)

        # Generate filename: use content hash to ensure uniqueness
        safe_keyword = sanitize_filename(keyword)
        filename = f"{safe_keyword}_{content_hash}{ext}"
        filepath = phone_dir / filename

        # Handle filename conflicts
        counter = 1
        while filepath.exists():
            filename = f"{safe_keyword}_{content_hash}_{counter}{ext}"
            filepath = phone_dir / filename
            counter += 1

        # Save file
        try:
            filepath.write_bytes(data)

            return PhoneImage(
                phone_model=keyword,
                image_url=url,
                local_path=str(filepath),
                thumbnail_url=image_info.get("thumbnail_url", ""),
                source_page=image_info.get("source_page", ""),
                width=image_info.get("width", 0),
                height=image_info.get("height", 0),
                file_size=len(data),
                download_status="success",
                content_hash=content_hash,
            )
        except IOError as e:
            return PhoneImage(
                phone_model=keyword,
                image_url=url,
                local_path="",
                download_status="failed",
                error_message=f"Failed to save file: {e}",
            )


# --------------------------------------------------------------------------- #
#  Main Scraper
# --------------------------------------------------------------------------- #

class GooglePhoneImageScraper:
    """Main scraper that coordinates searching and downloading."""

    def __init__(self, output_dir: str = DEFAULT_OUTPUT_DIR, max_workers: int = 4):
        self.output_dir = Path(output_dir)
        self.max_workers = max_workers
        self.searcher = GoogleImageSearcher()
        self.all_results: List[PhoneModelResult] = []

    def scrape_phone_model(
        self,
        keyword: str,
        max_results: int = 30,
        max_pages: int = 5,
    ) -> PhoneModelResult:
        """
        Scrape images for a single phone model.

        Args:
            keyword: Phone model name to search
            max_results: Maximum number of images to download
            max_pages: Maximum number of search pages to scrape

        Returns:
            PhoneModelResult with scraping statistics
        """
        print(f"\n{'='*60}")
        print(f"Scraping images for: {keyword}")
        print(f"{'='*60}")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        safe_keyword = sanitize_filename(keyword)
        phone_dir = self.output_dir / safe_keyword
        phone_dir.mkdir(parents=True, exist_ok=True)

        result = PhoneModelResult(
            keyword=keyword,
            timestamp=timestamp,
            output_dir=str(phone_dir),
        )

        # Search for images
        print(f"  Searching Google Images via Serper API (max {max_pages} pages)...")
        image_urls = self.searcher.extract_images(
            keyword=keyword,
            max_pages=max_pages,
            results_per_page=100,
        )

        if not image_urls:
            print(f"  [WARN] No images found for '{keyword}'")
            self.all_results.append(result)
            return result

        result.total_images_found = len(image_urls)
        print(f"  Found {len(image_urls)} image URLs")

        # Limit to max_results
        image_urls = image_urls[:max_results]

        # Download images with thread pool
        downloader = ImageDownloader(str(self.output_dir))
        successful = 0
        failed = 0
        skipped = 0

        print(f"  Downloading images (max {len(image_urls)})...")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(downloader.download_image, img_info, phone_dir): img_info
                for img_info in image_urls
            }

            for i, future in enumerate(as_completed(futures), 1):
                img_info = futures[future]
                try:
                    image_result = future.result()
                    result.images.append(image_result)

                    if image_result.download_status == "success":
                        successful += 1
                        print(f"    [{i}/{len(image_urls)}] OK: {Path(image_result.local_path).name}")
                    elif image_result.download_status == "skipped":
                        skipped += 1
                        print(f"    [{i}/{len(image_urls)}] SKIP: Duplicate")
                    else:
                        failed += 1
                        print(f"    [{i}/{len(image_urls)}] FAIL: {image_result.error_message[:60]}")

                except Exception as e:
                    failed += 1
                    print(f"    [{i}/{len(image_urls)}] ERROR: {e}")

        result.successful_downloads = successful
        result.failed_downloads = failed
        result.skipped_duplicates = skipped
        result.total_images_downloaded = successful

        # Save metadata
        metadata = {
            "keyword": keyword,
            "timestamp": timestamp,
            "output_dir": str(phone_dir),
            "total_images_found": result.total_images_found,
            "successful_downloads": successful,
            "failed_downloads": failed,
            "skipped_duplicates": skipped,
            "images": [
                {
                    "url": img.image_url,
                    "local_path": img.local_path,
                    "status": img.download_status,
                    "file_size": img.file_size,
                    "content_hash": img.content_hash,
                }
                for img in result.images if img.download_status == "success"
            ],
        }

        metadata_path = phone_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        print(f"\n  Results for '{keyword}':")
        print(f"    Found: {result.total_images_found}")
        print(f"    Downloaded: {successful}")
        print(f"    Failed: {failed}")
        print(f"    Duplicates: {skipped}")
        print(f"    Saved to: {phone_dir}")

        self.all_results.append(result)
        return result

    def scrape_multiple_models(
        self,
        keywords: List[str],
        max_results: int = 30,
        max_pages: int = 5,
    ) -> List[PhoneModelResult]:
        """
        Scrape images for multiple phone models.

        Args:
            keywords: List of phone model names to search
            max_results: Maximum images per model
            max_pages: Maximum pages per model

        Returns:
            List of PhoneModelResult for each model
        """
        print(f"\nStarting batch scrape for {len(keywords)} phone models")
        print(f"Output directory: {self.output_dir}")
        print(f"Max results per model: {max_results}")

        for i, keyword in enumerate(keywords, 1):
            print(f"\nProgress: {i}/{len(keywords)}")
            self.scrape_phone_model(
                keyword=keyword,
                max_results=max_results,
                max_pages=max_pages,
            )
            # Brief pause between models
            if i < len(keywords):
                time.sleep(2)

        return self.all_results

    def generate_summary(self) -> str:
        """Generate a summary report of all scraping results."""
        if not self.all_results:
            return "No scraping results yet."

        total_models = len(self.all_results)
        total_found = sum(r.total_images_found for r in self.all_results)
        total_downloaded = sum(r.successful_downloads for r in self.all_results)
        total_failed = sum(r.failed_downloads for r in self.all_results)
        total_skipped = sum(r.skipped_duplicates for r in self.all_results)

        lines = [
            "\n" + "=" * 60,
            "GOOGLE IMAGES PHONE SCRAPER (Serper API) - SUMMARY REPORT",
            "=" * 60,
            f"Total models processed: {total_models}",
            f"Total images found: {total_found}",
            f"Total images downloaded: {total_downloaded}",
            f"Total downloads failed: {total_failed}",
            f"Total duplicates skipped: {total_skipped}",
            f"Output directory: {self.output_dir}",
            "",
            "Per-model breakdown:",
            "-" * 40,
        ]

        for r in self.all_results:
            lines.append(
                f"  {r.keyword}: {r.successful_downloads} downloaded "
                f"({r.failed_downloads} failed, {r.skipped_duplicates} duplicates)"
            )
            lines.append(f"    -> {r.output_dir}")

        lines.append("=" * 60)
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  Command Line Interface
# --------------------------------------------------------------------------- #

def load_keywords_from_file(filepath: str) -> List[str]:
    """Load keywords from a text file (one per line)."""
    with open(filepath, "r", encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return keywords


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Google Images Phone Scraper (via Serper API) - Download phone model images from Google Images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --keyword "iPhone 15 Pro"
  %(prog)s --keyword "Samsung Galaxy S24 Ultra" --max-results 20
  %(prog)s --keywords-file phone_models.txt --output /dfs/data/google_phone_images
  %(prog)s --keyword "Pixel 8 Pro" --max-results 15 --max-pages 3
        """,
    )

    parser.add_argument(
        "--keyword", "-k",
        type=str,
        default=None,
        help="Phone model keyword to search (e.g., 'iPhone 15 Pro', 'Samsung Galaxy S24')",
    )

    parser.add_argument(
        "--keywords-file", "-f",
        type=str,
        default=None,
        help="Path to a text file with keywords (one per line)",
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for downloaded images (default: {DEFAULT_OUTPUT_DIR})",
    )

    parser.add_argument(
        "--max-results", "-n",
        type=int,
        default=30,
        help="Maximum number of images to download per keyword (default: 30)",
    )

    parser.add_argument(
        "--max-pages", "-p",
        type=int,
        default=5,
        help="Maximum number of search pages to scrape per keyword (default: 5)",
    )

    parser.add_argument(
        "--max-workers", "-w",
        type=int,
        default=4,
        help="Number of concurrent download workers (default: 4)",
    )

    return parser


def main():
    """Main entry point."""
    parser = build_argument_parser()
    args = parser.parse_args()

    # Determine keywords
    keywords = []

    if args.keyword:
        keywords.append(args.keyword)

    if args.keywords_file:
        if not os.path.exists(args.keywords_file):
            print(f"Error: Keywords file not found: {args.keywords_file}")
            sys.exit(1)
        file_keywords = load_keywords_from_file(args.keywords_file)
        keywords.extend(file_keywords)

    if not keywords:
        # Default phone models to search
        keywords = [
            "iPhone 15 Pro Max",
            "Samsung Galaxy S24 Ultra",
            "Google Pixel 8 Pro",
            "OnePlus 12",
            "Xiaomi 14",
            "Huawei Mate 60 Pro",
            "OPPO Find X7",
            "vivo X100 Pro",
        ]
        print("No keywords specified. Using default phone models:")
        for kw in keywords:
            print(f"  - {kw}")

    # Create scraper and run
    scraper = GooglePhoneImageScraper(
        output_dir=args.output,
        max_workers=args.max_workers,
    )

    results = scraper.scrape_multiple_models(
        keywords=keywords,
        max_results=args.max_results,
        max_pages=args.max_pages,
    )

    # Print summary
    print(scraper.generate_summary())

    # Save global summary
    summary_path = Path(args.output) / "summary.json"
    summary_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "output_dir": args.output,
        "total_models": len(results),
        "total_images_downloaded": sum(r.successful_downloads for r in results),
        "models": [
            {
                "keyword": r.keyword,
                "successful_downloads": r.successful_downloads,
                "failed_downloads": r.failed_downloads,
                "skipped_duplicates": r.skipped_duplicates,
                "output_dir": r.output_dir,
            }
            for r in results
        ],
    }

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)

    print(f"\nGlobal summary saved to: {summary_path}")


if __name__ == "__main__":
    main()

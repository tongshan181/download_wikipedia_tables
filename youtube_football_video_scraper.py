#!/usr/bin/env python3
"""
Bilibili Football Video Scraper
================================
A comprehensive script to search for and download football/soccer videos from
Bilibili (哔哩哔哩) using yt-dlp's built-in bilisearch extractor.

Key features:
- Uses yt-dlp bilisearch: to find football videos on Bilibili
- Downloads videos using yt-dlp with quality selection
- Supports Chinese keywords for football content
- Configurable search keywords, output directory, and result limits
- Rate limiting and retry logic for reliability
- Batch support for multiple search queries
- JSON metadata export for all downloaded videos

Usage:
    python youtube_football_video_scraper.py --keyword "足球精彩进球"
    python youtube_football_video_scraper.py --keyword "欧冠精彩瞬间" --max-results 5
    python youtube_football_video_scraper.py --keywords-file football_queries.txt
    python youtube_football_video_scraper.py --keyword "英超 Highlights" --quality 480

Dependencies:
    - requests (for HTTP requests)
    - yt-dlp (for Bilibili video search and downloading)

Install dependencies:
    pip install requests yt-dlp
"""

import os
import sys
import time
import json
import subprocess
import argparse
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
#  Configuration
# --------------------------------------------------------------------------- #

# Default output directory
DEFAULT_OUTPUT_DIR = "/dfs/data/football_videos"

# Default headers for HTTP requests
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# Rate limiting
VIDEO_DOWNLOAD_DELAY = 3.0  # Seconds between video downloads
QUERY_DELAY = 5.0  # Seconds between search queries


# --------------------------------------------------------------------------- #
#  Data Models
# --------------------------------------------------------------------------- #

@dataclass
class BilibiliVideo:
    """Represents a single Bilibili video found in search results."""
    video_id: str  # av_id or bvid
    bvid: str = ""  # BVxxxxxx ID
    title: str = ""
    url: str = ""
    author: str = ""
    duration: str = ""
    publish_date: str = ""
    view_count: str = ""
    description: str = ""
    thumbnail: str = ""


@dataclass
class DownloadedVideo:
    """Represents a downloaded video with metadata."""
    video_id: str
    title: str
    url: str
    local_path: str = ""
    author: str = ""
    duration: str = ""
    file_size: int = 0
    format: str = ""
    download_status: str = "pending"  # pending, success, failed, skipped
    error_message: str = ""


@dataclass
class SearchQueryResult:
    """Represents the scraping result for a single search query."""
    keyword: str
    total_videos_found: int = 0
    total_downloaded: int = 0
    successful_downloads: int = 0
    failed_downloads: int = 0
    skipped_duplicates: int = 0
    videos: List[DownloadedVideo] = field(default_factory=list)
    timestamp: str = ""
    output_dir: str = ""


# --------------------------------------------------------------------------- #
#  Utility Functions
# --------------------------------------------------------------------------- #

def sanitize_filename(name: str) -> str:
    """Sanitize a string to be used as a directory or file name."""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = re.sub(r'[\s_]+', '_', name)
    name = name[:100]
    return name.strip('_')


def extract_bvid(url: str) -> Optional[str]:
    """Extract Bilibili BV ID from URL."""
    match = re.search(r'BV[a-zA-Z0-9_]+', url)
    return match.group(0) if match else None


def extract_av_id(url: str) -> Optional[str]:
    """Extract Bilibili AV ID from URL."""
    match = re.search(r'av(\d+)', url)
    return match.group(1) if match else None


def check_yt_dlp() -> bool:
    """Check if yt-dlp is installed and functional."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def install_yt_dlp() -> bool:
    """Attempt to install yt-dlp if not present."""
    try:
        print("  [INFO] Installing yt-dlp...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "yt-dlp"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("  [ERROR] yt-dlp installation timed out")
        return False


def check_network_connectivity() -> Dict[str, bool]:
    """Check if Bilibili is directly accessible."""
    import requests
    results = {"bilibili": False, "baidu": False}
    try:
        r = requests.get("https://www.bilibili.com", timeout=10, verify=False)
        results["bilibili"] = r.status_code == 200
    except Exception:
        pass
    try:
        r = requests.get("https://www.baidu.com", timeout=10, verify=False)
        results["baidu"] = r.status_code == 200
    except Exception:
        pass
    return results


# --------------------------------------------------------------------------- #
#  Bilibili Video Search (via yt-dlp)
# --------------------------------------------------------------------------- #

class BilibiliVideoSearcher:
    """Searches Bilibili videos using yt-dlp bilisearch extractor."""

    def __init__(self):
        self._last_search_time = 0

    def _rate_limit(self):
        """Enforce rate limiting between search requests."""
        elapsed = time.time() - self._last_search_time
        if elapsed < 3.0:
            time.sleep(3.0 - elapsed)
        self._last_search_time = time.time()

    def search(self, keyword: str, max_results: int = 10) -> List[BilibiliVideo]:
        """
        Search Bilibili videos using yt-dlp bilisearch.

        Args:
            keyword: Search keyword for football videos
            max_results: Maximum number of results to extract

        Returns:
            List of BilibiliVideo objects
        """
        self._rate_limit()

        # Use yt-dlp to extract search results without downloading
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--flat-playlist",
            "--playlist-items", f"1-{max_results}",
            "--no-check-certificates",
            f"bilisearch{max_results}:{keyword}",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                print(f"    [ERROR] yt-dlp search failed: {result.stderr[-300:]}")
                return []

            videos = []
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    video = BilibiliVideo(
                        video_id=data.get("id", ""),
                        bvid=data.get("id", ""),
                        title=data.get("title", ""),
                        url=data.get("url", ""),
                        author=data.get("channel", "") or data.get("uploader", ""),
                        duration=data.get("duration_string", "") or str(data.get("duration", 0)),
                        view_count=str(data.get("view_count", 0)),
                        description=data.get("description", "") or "",
                        thumbnail=data.get("thumbnail", ""),
                    )
                    videos.append(video)
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"    [WARN] Failed to parse video data: {e}")
                    continue

            return videos

        except subprocess.TimeoutExpired:
            print("    [ERROR] Search timed out")
            return []
        except Exception as e:
            print(f"    [ERROR] Search exception: {e}")
            return []

    def search_multiple_pages(self, keyword: str, total_results: int = 20) -> List[BilibiliVideo]:
        """
        Search multiple pages to get more results.

        Args:
            keyword: Search keyword
            total_results: Total results to try to collect

        Returns:
            List of BilibiliVideo objects (deduplicated)
        """
        all_videos = []
        seen_ids = set()
        page_size = 10

        # Bilibili search typically returns results across pages
        # We'll do multiple searches with slight variations to get more results
        pages = min(total_results // page_size + 1, 5)

        for page in range(pages):
            if len(all_videos) >= total_results:
                break

            print(f"    [INFO] Searching page {page + 1}/{pages}...")

            # Add page suffix to get different results
            search_term = keyword
            if page > 0:
                # Try slightly different search to get more variety
                search_term = f"{keyword} 第{page + 1}页"

            videos = self.search(search_term, max_results=page_size)

            found_new = 0
            for video in videos:
                vid = video.video_id
                if vid and vid not in seen_ids:
                    seen_ids.add(vid)
                    all_videos.append(video)
                    found_new += 1

            print(f"    [INFO] Found {found_new} new videos (total: {len(all_videos)})")

            if found_new == 0:
                break

            # Rate limit between pages
            if page < pages - 1:
                time.sleep(2)

        return all_videos[:total_results]


# --------------------------------------------------------------------------- #
#  Video Downloader (yt-dlp based)
# --------------------------------------------------------------------------- #

class VideoDownloader:
    """Downloads Bilibili videos using yt-dlp."""

    def __init__(self, output_dir: str, quality: str = "480", format_preference: str = "mp4"):
        self.output_dir = Path(output_dir)
        self.quality = quality
        self.format_preference = format_preference
        self._seen_ids: Set[str] = set()

    def _build_format_string(self) -> str:
        """
        Build yt-dlp format string based on quality preference.

        Bilibili requires login for high resolutions (720p+).
        Free available formats:
        - 30016/100022/30011: 360p mp4
        - 30032/100023/30033: 480p mp4
        - 30216/30232/30280: audio only m4a

        For non-logged-in users, we prefer 480p (best available without login).
        """
        if self.quality == "best":
            # Try best available, fallback to 480p
            return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        elif self.quality == "worst":
            return "worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst"
        else:
            # Height-based: 360, 480, 720, 1080
            return (
                f"bestvideo[height<={self.quality}][ext=mp4]+"
                f"bestaudio[ext=m4a]/"
                f"best[height<={self.quality}][ext=mp4]/"
                f"bestvideo[height<={self.quality}]+bestaudio/"
                f"best[height<={self.quality}]/"
                # Fallback: prefer 480p if requested quality is unavailable
                f"bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/"
                f"best[ext=mp4]/best"
            )

    def _build_output_template(self, keyword: str) -> str:
        """Build yt-dlp output template."""
        safe_keyword = sanitize_filename(keyword)
        output_dir = self.output_dir / safe_keyword
        output_dir.mkdir(parents=True, exist_ok=True)
        return str(output_dir / f"{safe_keyword}_%(title)s_%(id)s.%(ext)s")

    def download_video(self, video: BilibiliVideo, keyword: str) -> DownloadedVideo:
        """
        Download a single Bilibili video using yt-dlp.

        Args:
            video: BilibiliVideo object to download
            keyword: Original search keyword

        Returns:
            DownloadedVideo with download result
        """
        # Check for duplicates
        if video.video_id in self._seen_ids:
            return DownloadedVideo(
                video_id=video.video_id,
                title=video.title,
                url=video.url,
                author=video.author,
                duration=video.duration,
                download_status="skipped",
                error_message="Duplicate video ID",
            )
        self._seen_ids.add(video.video_id)

        # Build output template
        output_template = self._build_output_template(keyword)
        output_dir = Path(output_template).parent

        # Build yt-dlp command
        format_str = self._build_format_string()
        cmd = [
            "yt-dlp",
            "--format", format_str,
            "--output", output_template,
            "--no-check-certificates",
            "--no-playlist",
            "--retries", "2",
            "--fragment-retries", "2",
            "--concurrent-fragments", "4",
            "--user-agent", REQUEST_HEADERS["User-Agent"],
            "--geo-bypass",
            "--extractor-args", "bilibili:api_version=web",
            "--merge-output-format", "mp4",
            "-v",
            video.url,
        ]

        print(f"    [INFO] Downloading: {video.title}")
        print(f"    [INFO] URL: {video.url}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout per video
            )

            if result.returncode == 0:
                # Find the downloaded file
                local_path = ""
                file_size = 0
                downloaded_format = ""

                # Look for the output file
                if output_dir.exists():
                    files = list(output_dir.glob(f"*{video.video_id}*"))
                    for f in files:
                        if f.suffix in ['.mp4', '.mkv', '.webm']:
                            local_path = str(f)
                            file_size = f.stat().st_size
                            break

                # Try to get format info from yt-dlp output
                if 'format:' in result.stderr:
                    for line in result.stderr.split('\n'):
                        if '[info]' in line.lower() and 'downloading' in line.lower():
                            downloaded_format = line.strip()
                            break

                return DownloadedVideo(
                    video_id=video.video_id,
                    title=video.title,
                    url=video.url,
                    local_path=local_path,
                    author=video.author,
                    duration=video.duration,
                    file_size=file_size,
                    format=downloaded_format,
                    download_status="success",
                )
            else:
                stderr = result.stderr[-500:] if result.stderr else "Unknown error"
                # Clean up error message
                error_lines = [l for l in stderr.split('\n') if 'ERROR' in l or 'error' in l.lower()]
                error_msg = '; '.join(error_lines[:3]) if error_lines else stderr.strip()
                return DownloadedVideo(
                    video_id=video.video_id,
                    title=video.title,
                    url=video.url,
                    author=video.author,
                    duration=video.duration,
                    download_status="failed",
                    error_message=f"yt-dlp error: {error_msg[:300]}",
                )

        except subprocess.TimeoutExpired:
            return DownloadedVideo(
                video_id=video.video_id,
                title=video.title,
                url=video.url,
                author=video.author,
                duration=video.duration,
                download_status="failed",
                error_message="Download timed out (10 min limit)",
            )
        except Exception as e:
            return DownloadedVideo(
                video_id=video.video_id,
                title=video.title,
                url=video.url,
                author=video.author,
                duration=video.duration,
                download_status="failed",
                error_message=f"Exception: {str(e)[:200]}",
            )


# --------------------------------------------------------------------------- #
#  Main Scraper
# --------------------------------------------------------------------------- #

class BilibiliFootballVideoScraper:
    """Main scraper that coordinates searching and downloading football videos."""

    def __init__(
        self,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        quality: str = "480",
        format_preference: str = "mp4",
    ):
        self.output_dir = Path(output_dir)
        self.quality = quality
        self.format_preference = format_preference
        self.searcher = BilibiliVideoSearcher()
        self.all_results: List[SearchQueryResult] = []

    def scrape_football_videos(
        self,
        keyword: str,
        max_results: int = 10,
        max_search_pages: int = 3,
    ) -> SearchQueryResult:
        """
        Scrape and download football videos for a single keyword.

        Args:
            keyword: Football video search keyword
            max_results: Maximum number of videos to download
            max_search_pages: Maximum number of search pages to scrape

        Returns:
            SearchQueryResult with scraping statistics
        """
        print(f"\n{'='*70}")
        print(f"Scraping football videos for: {keyword}")
        print(f"{'='*70}")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        safe_keyword = sanitize_filename(keyword)
        query_dir = self.output_dir / safe_keyword
        query_dir.mkdir(parents=True, exist_ok=True)

        result = SearchQueryResult(
            keyword=keyword,
            timestamp=timestamp,
            output_dir=str(query_dir),
        )

        # Search for videos
        search_limit = max_results * 2  # Get more candidates than needed
        print(f"  Searching Bilibili via yt-dlp (max {max_search_pages} pages)...")
        videos = self.searcher.search_multiple_pages(
            keyword=keyword,
            total_results=search_limit,
        )

        if not videos:
            print(f"  [WARN] No videos found for '{keyword}'")
            self.all_results.append(result)
            return result

        result.total_videos_found = len(videos)
        print(f"  Found {len(videos)} Bilibili videos")

        # Limit to max_results
        videos = videos[:max_results]

        # Download videos
        downloader = VideoDownloader(
            str(self.output_dir),
            quality=self.quality,
            format_preference=self.format_preference,
        )
        successful = 0
        failed = 0
        skipped = 0

        print(f"  Downloading videos (max {len(videos)})...")

        # Download sequentially to avoid rate limiting
        for i, video in enumerate(videos, 1):
            print(f"\n  [{i}/{len(videos)}] Processing: {video.title[:60]}...")

            downloaded = downloader.download_video(video, keyword)
            result.videos.append(downloaded)

            # Rate limiting between downloads
            if i < len(videos):
                time.sleep(VIDEO_DOWNLOAD_DELAY)

            if downloaded.download_status == "success":
                successful += 1
                size_mb = downloaded.file_size / (1024 * 1024) if downloaded.file_size else 0
                print(f"    [OK] Saved to: {downloaded.local_path} ({size_mb:.1f} MB)")
            elif downloaded.download_status == "skipped":
                skipped += 1
                print(f"    [SKIP] {downloaded.error_message}")
            else:
                failed += 1
                print(f"    [FAIL] {downloaded.error_message[:120]}")

        result.successful_downloads = successful
        result.failed_downloads = failed
        result.skipped_duplicates = skipped
        result.total_downloaded = successful

        # Save metadata
        metadata = {
            "keyword": keyword,
            "timestamp": timestamp,
            "output_dir": str(query_dir),
            "total_videos_found": result.total_videos_found,
            "successful_downloads": successful,
            "failed_downloads": failed,
            "skipped_duplicates": skipped,
            "videos": [
                {
                    "video_id": v.video_id,
                    "title": v.title,
                    "url": v.url,
                    "author": v.author,
                    "local_path": v.local_path,
                    "status": v.download_status,
                    "file_size": v.file_size,
                    "duration": v.duration,
                }
                for v in result.videos
            ],
        }

        metadata_path = query_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        print(f"\n  Results for '{keyword}':")
        print(f"    Found: {result.total_videos_found}")
        print(f"    Downloaded: {successful}")
        print(f"    Failed: {failed}")
        print(f"    Duplicates: {skipped}")
        print(f"    Saved to: {query_dir}")

        self.all_results.append(result)
        return result

    def scrape_multiple_queries(
        self,
        keywords: List[str],
        max_results: int = 10,
        max_search_pages: int = 3,
    ) -> List[SearchQueryResult]:
        """Scrape football videos for multiple search queries."""
        print(f"\nStarting batch scrape for {len(keywords)} football video queries")
        print(f"Output directory: {self.output_dir}")
        print(f"Max results per query: {max_results}")

        for i, keyword in enumerate(keywords, 1):
            print(f"\nProgress: {i}/{len(keywords)}")
            self.scrape_football_videos(
                keyword=keyword,
                max_results=max_results,
                max_search_pages=max_search_pages,
            )
            if i < len(keywords):
                time.sleep(QUERY_DELAY)

        return self.all_results

    def generate_summary(self) -> str:
        """Generate a summary report of all scraping results."""
        if not self.all_results:
            return "No scraping results yet."

        total_queries = len(self.all_results)
        total_found = sum(r.total_videos_found for r in self.all_results)
        total_downloaded = sum(r.successful_downloads for r in self.all_results)
        total_failed = sum(r.failed_downloads for r in self.all_results)
        total_skipped = sum(r.skipped_duplicates for r in self.all_results)

        lines = [
            "\n" + "=" * 70,
            "BILIBILI FOOTBALL VIDEO SCRAPER - SUMMARY REPORT",
            "=" * 70,
            f"Total queries processed: {total_queries}",
            f"Total videos found: {total_found}",
            f"Total videos downloaded: {total_downloaded}",
            f"Total downloads failed: {total_failed}",
            f"Total duplicates skipped: {total_skipped}",
            f"Output directory: {self.output_dir}",
            "",
            "Per-query breakdown:",
            "-" * 50,
        ]

        for r in self.all_results:
            lines.append(
                f"  {r.keyword}: {r.successful_downloads} downloaded "
                f"({r.failed_downloads} failed, {r.skipped_duplicates} skipped)"
            )
            lines.append(f"    -> {r.output_dir}")

        lines.append("=" * 70)
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
        description="Bilibili Football Video Scraper - Search and download football/soccer videos from Bilibili",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --keyword "足球精彩进球"
  %(prog)s --keyword "欧冠精彩瞬间" --max-results 5
  %(prog)s --keywords-file football_queries.txt --output /dfs/data/football_videos
  %(prog)s --keyword "英超 Highlights" --quality 480 --format mp4

Default football queries if none specified:
  - 足球精彩进球 (Football amazing goals)
  - 欧冠精彩瞬间 (Champions League highlights)
  - 世界波进球 (World-class goals)
        """,
    )

    parser.add_argument("--keyword", "-k", type=str, default=None,
                        help="Football video keyword to search (Chinese recommended)")
    parser.add_argument("--keywords-file", "-f", type=str, default=None,
                        help="Path to a text file with keywords (one per line)")
    parser.add_argument("--output", "-o", type=str, default=DEFAULT_OUTPUT_DIR,
                        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--max-results", "-n", type=int, default=10,
                        help="Max videos per keyword (default: 10)")
    parser.add_argument("--max-pages", "-p", type=int, default=3,
                        help="Max search pages per keyword (default: 3)")
    parser.add_argument("--quality", "-q", type=str, default="480",
                        help="Video quality: best, worst, or height like 1080/720/480/360 (default: 480)")
    parser.add_argument("--format", type=str, default="mp4",
                        help="Preferred format: mp4, webm (default: mp4)")

    return parser


def main():
    """Main entry point."""
    parser = build_argument_parser()
    args = parser.parse_args()

    # Check network connectivity
    print("=" * 70)
    print("BILIBILI FOOTBALL VIDEO SCRAPER")
    print("=" * 70)

    print("\n[1/4] Checking network connectivity...")
    connectivity = check_network_connectivity()

    if connectivity["bilibili"]:
        print("  [OK] Bilibili is directly accessible")
    else:
        print("  [WARN] Bilibili is NOT directly accessible")
        print("         Download may fail due to network restrictions")

    if connectivity["baidu"]:
        print("  [OK] Baidu is accessible")
    else:
        print("  [WARN] Baidu is NOT accessible")

    # Check and install yt-dlp if needed
    print("\n[2/4] Checking yt-dlp installation...")
    if not check_yt_dlp():
        print("  [WARN] yt-dlp not found, attempting to install...")
        if not install_yt_dlp():
            print("  [ERROR] Failed to install yt-dlp. Please install manually:")
            print("          pip install yt-dlp")
            sys.exit(1)
    else:
        print("  [OK] yt-dlp is installed and ready")

    # Determine keywords
    print("\n[3/4] Loading search keywords...")
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
        keywords = [
            "足球精彩进球",
            "欧冠精彩瞬间",
            "世界波进球",
        ]
        print("  No keywords specified. Using default football video queries:")
        for kw in keywords:
            print(f"    - {kw}")
    else:
        print(f"  Loaded {len(keywords)} keyword(s)")

    # Create scraper and run
    print(f"\n[4/4] Starting video search and download...")
    print(f"  Output directory: {args.output}")

    scraper = BilibiliFootballVideoScraper(
        output_dir=args.output,
        quality=args.quality,
        format_preference=args.format,
    )

    results = scraper.scrape_multiple_queries(
        keywords=keywords,
        max_results=args.max_results,
        max_search_pages=args.max_pages,
    )

    # Print summary
    print(scraper.generate_summary())

    # Save global summary
    summary_path = Path(args.output) / "summary.json"
    summary_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "output_dir": args.output,
        "total_queries": len(results),
        "total_videos_downloaded": sum(r.successful_downloads for r in results),
        "queries": [
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

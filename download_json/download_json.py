#!/usr/bin/env python3
"""
JSON File Downloader
====================
A script to download JSON files from URLs or search for JSON APIs.

Usage:
    python download_json.py --url <URL> [--output <filename>]
    python download_json.py --topic <topic> [--output <filename>]
    python download_json.py --search <query> [--output <filename>]

Examples:
    # Download from a specific URL
    python download_json.py --url https://api.example.com/data.json --output data.json
    
    # Download JSON related to a topic (uses public APIs)
    python download_json.py --topic users --output users.json
    
    # Search for JSON data
    python download_json.py --search "public json api" --output search_results.json
"""

import argparse
import json
import sys
import os
from datetime import datetime
from typing import Optional, Dict, Any

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Install it with: pip install requests")
    sys.exit(1)


# Public JSON API endpoints for common topics
PUBLIC_APIS = {
    "users": "https://jsonplaceholder.typicode.com/users",
    "posts": "https://jsonplaceholder.typicode.com/posts",
    "comments": "https://jsonplaceholder.typicode.com/comments",
    "albums": "https://jsonplaceholder.typicode.com/albums",
    "photos": "https://jsonplaceholder.typicode.com/photos",
    "todos": "https://jsonplaceholder.typicode.com/todos",
    "products": "https://fakestoreapi.com/products",
    "cryptocurrency": "https://api.coindesk.com/v1/bpi/currentprice.json",
    "quote": "https://api.quotable.io/random",
    "cat_facts": "https://catfact.ninja/facts",
    "dog_facts": "https://dog.ceo/api/breeds/list/all",
    "country": "https://restcountries.com/v3.1/all?fields=name,flags,population",
    "weather": "https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&current_weather=true",
}


def download_from_url(url: str, output: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """
    Download JSON data from a specific URL.
    
    Args:
        url: The URL to download JSON from
        output: Optional output filename
        timeout: Request timeout in seconds
    
    Returns:
        Dictionary with download result information
    """
    print(f"[INFO] Downloading JSON from: {url}")
    
    try:
        response = requests.get(url, timeout=timeout, headers={
            "Accept": "application/json",
            "User-Agent": "JSONDownloader/1.0"
        })
        response.raise_for_status()
        
        # Validate JSON
        data = response.json()
        
        # Generate output filename
        if not output:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output = f"downloaded_json_{timestamp}.json"
        
        # Ensure output directory exists
        output_dir = os.path.dirname(output)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # Write JSON to file
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        result = {
            "status": "success",
            "url": url,
            "output_file": output,
            "file_size_bytes": os.path.getsize(output),
            "content_type": response.headers.get("Content-Type", "unknown"),
            "data_preview": str(data)[:500] if data else None
        }
        
        print(f"[SUCCESS] JSON downloaded successfully!")
        print(f"[INFO] Output file: {output}")
        print(f"[INFO] File size: {os.path.getsize(output)} bytes")
        
        return result
        
    except requests.exceptions.JSONDecodeError as e:
        result = {
            "status": "error",
            "error_type": "JSONDecodeError",
            "error_message": f"Response is not valid JSON: {str(e)}",
            "url": url
        }
        print(f"[ERROR] {result['error_message']}")
        return result
        
    except requests.exceptions.Timeout:
        result = {
            "status": "error",
            "error_type": "Timeout",
            "error_message": f"Request timed out after {timeout} seconds",
            "url": url
        }
        print(f"[ERROR] {result['error_message']}")
        return result
        
    except requests.exceptions.RequestException as e:
        result = {
            "status": "error",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "url": url
        }
        print(f"[ERROR] {result['error_message']}")
        return result


def download_by_topic(topic: str, output: Optional[str] = None) -> Dict[str, Any]:
    """
    Download JSON data based on a topic using known public APIs.
    
    Args:
        topic: The topic to search for (e.g., 'users', 'products', 'weather')
        output: Optional output filename
    
    Returns:
        Dictionary with download result information
    """
    topic_lower = topic.lower().strip()
    
    # Find matching API
    api_url = None
    for key, url in PUBLIC_APIS.items():
        if key in topic_lower or topic_lower in key:
            api_url = url
            print(f"[INFO] Found matching API for topic '{topic}': {key}")
            break
    
    if not api_url:
        # Try to construct a URL or provide suggestions
        suggestions = list(PUBLIC_APIS.keys())
        result = {
            "status": "error",
            "error_type": "TopicNotFound",
            "error_message": f"No matching API found for topic: '{topic}'",
            "available_topics": suggestions,
            "suggestion": f"Try one of: {', '.join(suggestions[:5])}..."
        }
        print(f"[ERROR] {result['error_message']}")
        print(f"[INFO] Available topics: {', '.join(suggestions)}")
        return result
    
    return download_from_url(api_url, output)


def search_json_apis(query: str, output: Optional[str] = None) -> Dict[str, Any]:
    """
    Search for public JSON APIs based on a query.
    
    Args:
        query: Search query
        output: Optional output filename
    
    Returns:
        Dictionary with search results
    """
    print(f"[INFO] Searching for JSON APIs related to: '{query}'")
    
    # Search through known APIs
    matching_apis = {}
    query_lower = query.lower()
    
    for key, url in PUBLIC_APIS.items():
        if query_lower in key.lower() or query_lower in url.lower():
            matching_apis[key] = url
    
    # Generate output filename
    if not output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"search_results_{timestamp}.json"
    
    # Create result
    result_data = {
        "query": query,
        "timestamp": datetime.now().isoformat(),
        "matching_apis": matching_apis,
        "total_matches": len(matching_apis),
        "all_available_topics": list(PUBLIC_APIS.keys())
    }
    
    # Write results to file
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)
    
    print(f"[SUCCESS] Search results saved to: {output}")
    print(f"[INFO] Found {len(matching_apis)} matching API(s)")
    
    return {
        "status": "success",
        "output_file": output,
        "result_data": result_data
    }


def main():
    parser = argparse.ArgumentParser(
        description="JSON File Downloader - Download JSON files from URLs or by topic",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download from a specific URL
  python download_json.py --url https://api.example.com/data.json
  
  # Download by topic
  python download_json.py --topic users --output users.json
  
  # Search for APIs
  python download_json.py --search "user data"
  
  # Download with custom output path
  python download_json.py --url https://jsonplaceholder.typicode.com/posts --output json_out/posts.json
        """
    )
    
    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--url", "-u",
        type=str,
        help="URL to download JSON from"
    )
    input_group.add_argument(
        "--topic", "-t",
        type=str,
        help="Topic to download JSON data for (e.g., users, products, weather)"
    )
    input_group.add_argument(
        "--search", "-s",
        type=str,
        help="Search query to find JSON APIs"
    )
    
    # Output options
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output filename (default: auto-generated)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)"
    )
    
    args = parser.parse_args()
    
    # Execute based on input type
    if args.url:
        result = download_from_url(args.url, args.output, args.timeout)
    elif args.topic:
        result = download_by_topic(args.topic, args.output)
    elif args.search:
        result = search_json_apis(args.search, args.output)
    
    # Print final result as JSON
    print("\n" + "="*50)
    print("Result (JSON):")
    print("="*50)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Exit with appropriate code
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()

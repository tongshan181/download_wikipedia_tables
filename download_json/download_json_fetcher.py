import argparse
import os
import re
import requests
from urllib.parse import urljoin, urlparse

def extract_json_links(base_url: str, html_text: str):
    """从页面文本中提取所有以 .json 结尾的链接"""
    pattern = r'href=["\']([^"\']+\.json)["\']|src=["\']([^"\']+\.json)["\']'
    matches = re.findall(pattern, html_text)
    json_paths = set()
    for g1, g2 in matches:
        path = g1 if g1 else g2
        if path:
            json_paths.add(path)
    full_links = []
    for path in json_paths:
        full_url = urljoin(base_url, path)
        full_links.append(full_url)
    return full_links

def download_json_file(file_url: str, output_dir: str):
    """下载单个JSON文件到输出目录"""
    try:
        parsed = urlparse(file_url)
        file_name = os.path.basename(parsed.path)
        save_path = os.path.join(output_dir, file_name)

        if os.path.exists(save_path):
            print(f"[跳过] 文件已存在: {file_name}")
            return True

        resp = requests.get(file_url, timeout=15, stream=True)
        resp.raise_for_status()

        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"[成功] 已下载: {file_name} -> {save_path}")
        return True

    except Exception as e:
        print(f"[失败] 下载 {file_url} 出错: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description="双模式：1.网页批量抓取页面内所有JSON；2.直接输入单个JSON链接下载")
    parser.add_argument("--input-url", required=True, type=str, help="输入：网页页面地址 / 直接以.json结尾的文件下载链接")
    parser.add_argument("--output-dir", required=True, type=str, help="JSON文件保存目录")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"=== 输入地址: {args.input_url} ===")
    print(f"=== 输出目录: {args.output_dir} ===")

    if args.input_url.strip().endswith(".json"):
        print("\n检测到输入为单个JSON文件链接，直接开始下载")
        json_url_list = [args.input_url]
    else:
        print("\n检测到输入为网页页面，开始提取页面内所有JSON链接")
        try:
            page_resp = requests.get(args.input_url, timeout=15)
            page_resp.raise_for_status()
            page_content = page_resp.text
        except Exception as e:
            print(f"[致命错误] 访问URL失败: {str(e)}")
            return
        json_url_list = extract_json_links(args.input_url, page_content)
        if not json_url_list:
            print("页面未检索到任何 .json 链接，程序退出")
            return

    print(f"\n共处理 {len(json_url_list)} 个JSON链接:")
    for link in json_url_list:
        print(f" - {link}")

    print("\n===== 开始批量下载 =====")
    success_count = 0
    fail_count = 0
    for json_link in json_url_list:
        ok = download_json_file(json_link, args.output_dir)
        success_count += 1 if ok else 0
        fail_count += 0 if ok else 1

    print("\n===== 任务汇总 =====")
    print(f"总数量: {len(json_url_list)} | 成功: {success_count} | 失败: {fail_count}")
    print(f"文件输出路径: {os.path.abspath(args.output_dir)}")

if __name__ == "__main__":
    main()

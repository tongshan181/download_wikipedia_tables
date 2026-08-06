import requests
import os
import argparse
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from urllib.parse import quote
import re

# 请求头模拟浏览器，防止被拦截
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    retry=retry_if_exception_type((requests.exceptions.RequestException,))
)
def download_image(url, save_path):
    """单张图片下载，失败自动重试3次"""
    resp = requests.get(url, headers=HEADERS, timeout=10, stream=True)
    resp.raise_for_status()
    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return True

def search_google_images(keyword, max_count):
    """爬取Google图片搜索缩略图地址"""
    keyword_encoded = quote(keyword)
    search_url = f"https://www.google.com/search?tbm=isch&q={keyword_encoded}"
    resp = requests.get(search_url, headers=HEADERS, timeout=15)
    # 正则提取图片预览链接
    img_pattern = re.compile(r"https://[^\"']+\.(jpg|jpeg|png|webp)")
    all_img_urls = list(set(img_pattern.findall(resp.text)))
    return all_img_urls[:max_count]

def main():
    parser = argparse.ArgumentParser(description="Google图片批量下载工具")
    parser.add_argument("--keyword", "-k", required=True, type=str, help="搜索关键词，多词用引号包裹")
    parser.add_argument("--max-results", "-m", type=int, default=10, help="最大下载图片数量")
    parser.add_argument("--output-dir", "-o", type=str, default="./google_img_output", help="图片保存文件夹")
    args = parser.parse_args()

    # 创建保存目录
    save_dir = os.path.join(args.output_dir, args.keyword.replace(" ", "_"))
    os.makedirs(save_dir, exist_ok=True)
    print(f"🔍 正在搜索关键词：{args.keyword}，最多下载{args.max_results}张")

    img_urls = search_google_images(args.keyword, args.max_results)
    if not img_urls:
        print("❌ 未搜到任何图片链接，请更换关键词或检查网络")
        return
    print(f"✅ 共找到{len(img_urls)}张图片，开始下载...")

    success_cnt = 0
    for idx, img_url in enumerate(img_urls):
        ext = img_url.split(".")[-1]
        save_file = os.path.join(save_dir, f"img_{idx+1}.{ext}")
        try:
            download_image(img_url, save_file)
            success_cnt += 1
            print(f"✅ 已下载第{idx+1}张：{os.path.basename(save_file)}")
        except Exception as e:
            print(f"❌ 第{idx+1}张下载失败：{str(e)}")
    print(f"\n🎉 下载完成！成功{success_cnt}/{len(img_urls)}张，保存路径：{save_dir}")

if __name__ == "__main__":
    main()
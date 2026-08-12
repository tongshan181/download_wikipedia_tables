import requests
import os
import re

# ===================== 配置区 =====================
# 1. 去 https://pixabay.com/api/docs/ 注册账号获取免费API KEY
PIXABAY_API_KEY = "在这里粘贴你的Pixabay API Key"
# 2. 音频保存目录（Windows路径）
SAVE_FOLDER = r"D:\Audio_Downloads"
# 3. 单次返回条数
PER_PAGE = 8
# ==================================================

def safe_filename(text: str) -> str:
    """过滤文件名非法字符，防止Windows报错"""
    return re.sub(r'[\\/:*?"<>|]', "_", text)

def search_and_download_pixabay_audio(keyword: str):
    # 创建文件夹
    os.makedirs(SAVE_FOLDER, exist_ok=True)

    params = {
        "key": PIXABAY_API_KEY,
        "q": keyword,
        "per_page": PER_PAGE
    }

    try:
        print(f"🔍 正在搜索关键词：{keyword}")
        resp = requests.get("https://pixabay.com/api/audio/", params=params, timeout=15)
        resp.raise_for_status()  # 抛出HTTP错误（403/404等）
        data = resp.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ 接口请求失败：{str(e)}")
        return

    hits = data.get("hits", [])
    if not hits:
        print("ℹ️ 未搜索到匹配音频")
        return

    print(f"✅ 共找到 {len(hits)} 条音频资源\n")

    for idx, item in enumerate(hits):
        try:
            audio_info = item["audio"]
            download_url = audio_info["url"]
            title = item.get("tags", f"audio_{idx+1}")
            clean_name = safe_filename(f"{keyword}_{idx+1}_{title}")
            save_path = os.path.join(SAVE_FOLDER, f"{clean_name}.mp3")

            print(f"⬇️ 正在下载第{idx+1}首：{clean_name}.mp3")
            # 流式下载，避免大文件占用内存
            with requests.get(download_url, stream=True, timeout=30) as stream_resp:
                stream_resp.raise_for_status()
                with open(save_path, "wb") as f:
                    for chunk in stream_resp.iter_content(chunk_size=8192):
                        f.write(chunk)
            print(f"✅ 第{idx+1}首完成\n")
        except Exception as e:
            print(f"❌ 第{idx+1}首下载失败：{str(e)}\n")
            continue

    print(f"🎉 全部任务结束，文件保存在：{SAVE_FOLDER}")

if __name__ == "__main__":
    print("="*50)
    print("Pixabay 免费无版权音频检索下载工具（国内直连）")
    print("="*50)
    user_key = input("请输入音频搜索关键词：")
    search_and_download_pixabay_audio(user_key)

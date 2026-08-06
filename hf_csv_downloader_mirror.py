import os
import re
import time
import requests
from urllib.parse import quote


# ==========================
# 配置
# ==========================

SAVE_DIR = r"D:\csv_data"

# HuggingFace镜像
HF_MIRROR = "https://hf-mirror.com"

os.makedirs(SAVE_DIR, exist_ok=True)


headers = {
    "User-Agent": "Mozilla/5.0"
}


def request_url(url, retry=5):

    for i in range(retry):

        try:
            r = requests.get(
                url,
                headers=headers,
                timeout=60
            )

            if r.status_code == 200:
                return r.text

            print(
                f"HTTP {r.status_code}, retry {i+1}"
            )

        except Exception as e:
            print(
                f"连接失败 {i+1}/{retry}: {e}"
            )

        time.sleep(3)

    return None



# ==========================
# 输入关键词
# ==========================

keyword = input(
    "请输入搜索关键词："
).strip()


print()
print(
    f"搜索数据集: {keyword}"
)


# ==========================
# 搜索dataset
# ==========================

search_url = (
    HF_MIRROR
    + "/datasets?search="
    + quote(keyword)
)


html = request_url(search_url)


if html is None:
    print("搜索失败")
    exit()


# 提取dataset名字

datasets = sorted(
    set(
        re.findall(
            r'/datasets/([^"]+)',
            html
        )
    )
)


if len(datasets) == 0:

    print(
        "没有找到dataset"
    )
    exit()


print(
    f"\n找到 {len(datasets)} 个dataset"
)


# ==========================
# 下载CSV
# ==========================

for repo in datasets:


    print("\n" + "="*70)

    print(
        "Dataset:",
        repo
    )


    tree_url = (
        HF_MIRROR
        + "/datasets/"
        + repo
        + "/tree/main"
    )


    page = request_url(tree_url)


    if page is None:
        continue



    csv_files = sorted(
        set(
            re.findall(
                r'([\w\-/\.]+\.csv)',
                page,
                re.I
            )
        )
    )


    if len(csv_files)==0:

        print(
            "没有CSV"
        )

        continue


    print(
        "发现CSV:",
        csv_files
    )


    for csv_file in csv_files:


        download_url = (
            HF_MIRROR
            + "/datasets/"
            + repo
            + "/resolve/main/"
            + csv_file
        )


        filename = (
            repo.replace("/","__")
            +
            "__"
            +
            os.path.basename(csv_file)
        )


        save_path = os.path.join(
            SAVE_DIR,
            filename
        )


        print(
            "下载:",
            csv_file
        )


        try:

            r = requests.get(
                download_url,
                headers=headers,
                stream=True,
                timeout=120
            )


            if r.status_code != 200:

                print(
                    "下载失败",
                    r.status_code
                )

                continue


            with open(
                save_path,
                "wb"
            ) as f:

                for chunk in r.iter_content(
                    1024*1024
                ):

                    if chunk:
                        f.write(chunk)


            print(
                "保存:",
                save_path
            )


        except Exception as e:

            print(
                "下载异常:",
                e
            )


print(
    "\n全部完成"
)
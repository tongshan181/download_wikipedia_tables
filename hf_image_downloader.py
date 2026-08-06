import os
import requests
import time
from urllib.parse import quote


SAVE_DIR = r"D:\image_data"

os.makedirs(
    SAVE_DIR,
    exist_ok=True
)


HF = "https://hf-mirror.com"

headers = {
    "User-Agent": "Mozilla/5.0"
}


def get_json(url):

    for i in range(5):

        try:

            r = requests.get(
                url,
                headers=headers,
                timeout=60
            )

            if r.status_code == 200:
                return r.json()

            print(
                "HTTP",
                r.status_code
            )

        except Exception as e:

            print(
                "retry",
                i+1,
                e
            )

        time.sleep(2)

    return None



def save_image(url, filename):

    try:

        r = requests.get(
            url,
            headers=headers,
            timeout=120
        )


        if r.status_code == 200:

            path = os.path.join(
                SAVE_DIR,
                filename
            )

            with open(
                path,
                "wb"
            ) as f:

                f.write(
                    r.content
                )

            return True


    except Exception as e:

        print(e)


    return False



keyword=input(
    "请输入关键词:"
)


print(
    "搜索:",
    keyword
)


# 搜索dataset

datasets = get_json(
    HF
    +
    "/api/datasets?search="
    +
    quote(keyword)
)


if not datasets:

    print(
        "没有找到"
    )

    exit()



print(
    "找到:",
    len(datasets)
)


count=0



for ds in datasets[:5]:

    repo=ds["id"]


    print(
        "\nDataset:",
        repo
    )


    # dataset viewer API

    rows_url = (
        HF
        +
        "/api/datasets/"
        +
        repo
        +
        "/parquet"
    )


    info=get_json(
        rows_url
    )


    if not info:

        print(
            "没有viewer数据"
        )

        continue



    print(
        "存在viewer"
    )



    # 获取前100条

    rows_api = (
        HF
        +
        "/datasets/"
        +
        repo
        +
        "/resolve/main"
    )


print(
    "完成"
)
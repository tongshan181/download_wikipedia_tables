import os
from tqdm import tqdm

from huggingface_hub import HfApi
from datasets import load_dataset


OUTPUT_DIR = "hf_videos"


VIDEO_EXT = [
    ".mp4",
    ".webm",
    ".avi",
    ".mov",
    ".mkv"
]


def search_datasets(keyword, limit=20):

    print("\n搜索数据集:", keyword)

    api = HfApi()

    results = []


    for ds in api.list_datasets(
        search=keyword,
        limit=limit
    ):

        results.append(
            ds.id
        )

        print(
            "发现:",
            ds.id
        )


    return results



def save_video(video, index):

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )


    filename=os.path.join(
        OUTPUT_DIR,
        f"video_{index}.mp4"
    )


    # bytes

    if isinstance(video, dict):

        if "bytes" in video:

            with open(
                filename,
                "wb"
            ) as f:

                f.write(
                    video["bytes"]
                )

            return True



        # path

        if "path" in video:

            src=video["path"]


            if os.path.exists(src):

                with open(
                    src,
                    "rb"
                ) as r:

                    data=r.read()


                with open(
                    filename,
                    "wb"
                ) as w:

                    w.write(data)


                return True



    return False




def scan_dataset(repo, max_video=20):


    print(
        "\n================="
    )

    print(
        "检查:",
        repo
    )


    count=0


    try:

        ds=load_dataset(
            repo,
            split="train",
            streaming=True
        )


    except Exception as e:

        print(
            "无法读取:",
            e
        )

        return 0



    for item in tqdm(ds):


        for key,value in item.items():


            # video字段

            if key.lower()=="video":


                if save_video(
                    value,
                    count
                ):


                    count+=1

                    print(
                        "保存视频:",
                        count
                    )



        if count>=max_video:

            break



    return count




def main():


    keyword=input(
        "请输入视频关键词:"
    )


    datasets=search_datasets(
        keyword
    )


    total=0



    for repo in datasets:


        total += scan_dataset(
            repo
        )


        if total>=100:

            break



    print(
        "\n完成"
    )


    print(
        "总视频:",
        total
    )



if __name__=="__main__":

    main()
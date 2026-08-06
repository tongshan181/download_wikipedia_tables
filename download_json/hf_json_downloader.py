
"""
Hugging Face JSON / JSONL Dataset Downloader

功能：
1. 根据关键词搜索 Hugging Face Datasets
2. 查找数据集中的 JSON / JSONL 文件
3. 使用 PowerShell 下载 JSON / JSONL 文件
4. 保存到本地

示例：

python hf_json_downloader.py --keyword email --limit 5 --max-files 2 --output-dir "D:\\json_data"
"""

import sys
import subprocess
import importlib
import json
import argparse
from pathlib import Path
from urllib.parse import quote


# ============================================================
# 1. 自动检查 huggingface_hub
# ============================================================

def install_and_import(package_name, import_name=None):

    if import_name is None:
        import_name = package_name

    try:

        importlib.import_module(import_name)

        print(
            f"[OK] 已检测到依赖：{package_name}"
        )

    except ImportError:

        print(
            f"[INFO] 正在安装：{package_name}"
        )

        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                package_name
            ]
        )

        print(
            f"[OK] 安装完成：{package_name}"
        )


# 保留依赖检查
install_and_import(
    "huggingface_hub",
    "huggingface_hub"
)


# ============================================================
# 2. 使用 PowerShell 请求 JSON
# ============================================================

def powershell_request_json(url):

    """
    使用 PowerShell 的 Invoke-WebRequest
    获取 JSON 数据。
    """

    # 对 URL 中的单引号进行 PowerShell 转义
    safe_url = url.replace("'", "''")

    powershell_command = (
        "$ProgressPreference='SilentlyContinue'; "
        f"$response = Invoke-WebRequest "
        f"-Uri '{safe_url}' "
        f"-UseBasicParsing "
        f"-TimeoutSec 180; "
        "$response.Content"
    )

    try:

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                powershell_command
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=200
        )

        if result.returncode != 0:

            print()
            print("[ERROR] PowerShell 请求失败")
            print(result.stderr)

            return None

        content = result.stdout.strip()

        if not content:

            print()
            print("[ERROR] 返回内容为空")

            return None

        return json.loads(content)

    except subprocess.TimeoutExpired:

        print()
        print("[ERROR] PowerShell 请求超时")

        return None

    except json.JSONDecodeError as e:

        print()
        print("[ERROR] 返回内容不是合法 JSON")
        print(f"错误信息：{e}")

        print()
        print("返回内容前 500 个字符：")
        print(content[:500])

        return None

    except Exception as e:

        print()
        print(f"[ERROR] 请求失败：{e}")

        return None


# ============================================================
# 3. 搜索 Hugging Face 数据集
# ============================================================

def search_datasets(keyword, limit=10):

    print()
    print("=" * 70)
    print("正在搜索 Hugging Face Datasets")
    print("=" * 70)

    print(
        f"搜索关键词：{keyword}"
    )

    print(
        f"最大结果数量：{limit}"
    )

    encoded_keyword = quote(
        keyword
    )

    url = (
        "https://huggingface.co/api/datasets"
        f"?search={encoded_keyword}"
        f"&limit={limit}"
    )

    print()
    print(
        "[INFO] 使用 PowerShell 访问 Hugging Face..."
    )

    print(
        f"[INFO] 请求地址：{url}"
    )

    data = powershell_request_json(
        url
    )

    if data is None:

        print()
        print(
            "[ERROR] 搜索数据集失败"
        )

        return []

    print()
    print(
        f"[SUCCESS] 找到 {len(data)} 个数据集"
    )

    return data


# ============================================================
# 4. 获取数据集文件列表
# ============================================================

def get_dataset_files(repo_id):

    print()
    print(
        f"[INFO] 检查数据集：{repo_id}"
    )

    encoded_repo_id = quote(
        repo_id,
        safe="/"
    )

    url = (
        "https://huggingface.co/api/datasets/"
        f"{encoded_repo_id}/tree/main"
        "?recursive=true"
    )

    data = powershell_request_json(
        url
    )

    if data is None:

        return []

    json_files = []

    for item in data:

        if item.get("type") != "file":

            continue

        filename = item.get(
            "path",
            ""
        )

        if filename.lower().endswith(
            (
                ".json",
                ".jsonl"
            )
        ):

            json_files.append(
                filename
            )

    return json_files


# ============================================================
# 5. 清理 Windows 文件名
# ============================================================

def safe_filename(filename):

    invalid_chars = '<>:"/\\|?*'

    for char in invalid_chars:

        filename = filename.replace(
            char,
            "_"
        )

    return filename


# ============================================================
# 6. 使用 PowerShell 下载 JSON / JSONL 文件
# ============================================================

def download_json_file(
    repo_id,
    filename,
    output_dir
):

    print()
    print("-" * 70)

    print(
        f"数据集：{repo_id}"
    )

    print(
        f"文件：{filename}"
    )

    try:

        # ====================================================
        # 创建数据集文件夹
        # ====================================================

        dataset_folder = safe_filename(
            repo_id.replace(
                "/",
                "__"
            )
        )

        dataset_output_dir = (
            Path(output_dir)
            / dataset_folder
        )

        dataset_output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        # ====================================================
        # 创建 Hugging Face 下载地址
        # ====================================================

        encoded_repo_id = quote(
            repo_id,
            safe="/"
        )

        encoded_filename = quote(
            filename,
            safe="/"
        )

        download_url = (
            "https://huggingface.co/datasets/"
            f"{encoded_repo_id}"
            "/resolve/main/"
            f"{encoded_filename}"
            "?download=true"
        )

        # 保留数据集中的原始目录结构
        output_file = (
            dataset_output_dir
            / Path(filename)
        )

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        print()
        print(
            "[INFO] 使用 PowerShell 下载..."
        )

        print(
            f"[INFO] 下载地址：{download_url}"
        )

        print(
            f"[INFO] 保存位置：{output_file}"
        )

        # ====================================================
        # PowerShell 路径转义
        # ====================================================

        safe_download_url = (
            download_url.replace(
                "'",
                "''"
            )
        )

        safe_output_file = (
            str(output_file)
            .replace(
                "'",
                "''"
            )
        )

        # ====================================================
        # PowerShell 下载命令
        # ====================================================

        powershell_command = (
            "$ProgressPreference='SilentlyContinue'; "
            f"Invoke-WebRequest "
            f"-Uri '{safe_download_url}' "
            f"-OutFile '{safe_output_file}' "
            f"-UseBasicParsing "
            f"-TimeoutSec 180"
        )

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                powershell_command
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300
        )

        if result.returncode != 0:

            print()
            print(
                "[ERROR] 下载失败"
            )

            print(
                result.stderr
            )

            return None

        # ====================================================
        # 检查文件是否存在
        # ====================================================

        if output_file.exists():

            file_size = (
                output_file.stat().st_size
            )

            print()
            print(
                "[SUCCESS] 下载成功"
            )

            print(
                f"本地文件：{output_file}"
            )

            print(
                f"文件大小："
                f"{file_size / 1024 / 1024:.2f} MB"
            )

            return str(
                output_file
            )

        else:

            print()
            print(
                "[ERROR] 下载完成，但找不到文件"
            )

            return None

    except subprocess.TimeoutExpired:

        print()
        print(
            "[ERROR] 下载超时"
        )

        return None

    except Exception as e:

        print()
        print(
            "[ERROR] 下载失败"
        )

        print(
            f"错误信息：{e}"
        )

        return None


# ============================================================
# 7. 主程序
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "根据关键词搜索并下载 "
            "Hugging Face JSON / JSONL 文件"
        )
    )

    parser.add_argument(
        "--keyword",
        required=True,
        help=(
            "搜索关键词，例如："
            "email、penguin、medical"
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help=(
            "最多搜索多少个数据集，"
            "默认 10"
        )
    )

    parser.add_argument(
        "--output-dir",
        default="./downloads",
        help=(
            "下载目录，"
            "默认 ./downloads"
        )
    )

    parser.add_argument(
        "--max-files",
        type=int,
        default=3,
        help=(
            "每个数据集最多下载多少个 JSON / JSONL 文件，"
            "默认 3"
        )
    )

    args = parser.parse_args()

    # ========================================================
    # 创建输出目录
    # ========================================================

    output_dir = Path(
        args.output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # ========================================================
    # 第一步：搜索数据集
    # ========================================================

    datasets = search_datasets(
        args.keyword,
        args.limit
    )

    if not datasets:

        print()
        print(
            "没有找到相关数据集。"
        )

        return

    # ========================================================
    # 第二步：显示搜索结果
    # ========================================================

    print()
    print("=" * 70)
    print("搜索结果")
    print("=" * 70)

    for index, dataset in enumerate(
        datasets,
        start=1
    ):

        print(
            f"{index}. "
            f"{dataset.get('id')}"
        )

    # ========================================================
    # 第三步：检查 JSON / JSONL 文件
    # ========================================================

    print()
    print("=" * 70)
    print(
        "正在检查 JSON / JSONL 文件"
    )
    print("=" * 70)

    json_datasets = []

    for index, dataset in enumerate(
        datasets,
        start=1
    ):

        repo_id = dataset.get(
            "id"
        )

        print()
        print(
            f"[{index}/{len(datasets)}] "
            f"检查：{repo_id}"
        )

        files = get_dataset_files(
            repo_id
        )

        if files:

            print()
            print(
                f"发现 {len(files)} 个 "
                "JSON / JSONL 文件："
            )

            for filename in files:

                print(
                    f"  - {filename}"
                )

            json_datasets.append(
                (
                    repo_id,
                    files
                )
            )

        else:

            print(
                "没有发现 JSON / JSONL 文件"
            )

    # ========================================================
    # 第四步：开始下载
    # ========================================================

    if not json_datasets:

        print()
        print(
            "搜索到的数据集中没有 "
            "JSON / JSONL 文件。"
        )

        return

    print()
    print("=" * 70)
    print(
        "开始下载 JSON / JSONL 文件"
    )
    print("=" * 70)

    total_downloaded = 0

    for repo_id, files in json_datasets:

        selected_files = files[
            :args.max_files
        ]

        for filename in selected_files:

            result = download_json_file(
                repo_id,
                filename,
                output_dir
            )

            if result:

                total_downloaded += 1

    # ========================================================
    # 第五步：完成
    # ========================================================

    print()
    print("=" * 70)
    print(
        "任务完成"
    )
    print("=" * 70)

    print()
    print(
        f"成功下载文件数量："
        f"{total_downloaded}"
    )

    print()
    print(
        f"保存目录：{output_dir}"
    )


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":

    main()
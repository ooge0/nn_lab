import os
from tqdm import tqdm  # pip install tqdm


def merge_files(input_dir: str, output_file: str, exclude_dirs=None, exclude_files=None):
    """
    Collects the content of all files from input_dir into one output_file.
    Adds the relative path of each file as a header.
    You can exclude specific subfolders via exclude_dirs and specific files via exclude_files.
    Shows a console progress bar while processing.
    """
    if exclude_dirs is None:
        exclude_dirs = []
    if exclude_files is None:
        exclude_files = []

    # Collect all files first
    all_files = []
    for root, _, files in os.walk(input_dir):
        rel_root = os.path.relpath(root, input_dir)
        if any(rel_root.startswith(ex) for ex in exclude_dirs):
            continue
        for fname in files:
            file_path = os.path.join(root, fname)
            if os.path.normpath(file_path) in [os.path.normpath(f) for f in exclude_files]:
                continue
            all_files.append(file_path)

    # Process with progress bar
    with open(output_file, "w", encoding="utf-8") as out:
        for file_path in tqdm(all_files, desc="Merging files", unit="file"):
            rel_path = os.path.relpath(file_path, input_dir)
            out.write(f"\n\n=== {rel_path} ===\n\n")
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    out.write(f.read())
            except Exception as e:
                out.write(f"[File read error {rel_path}: {e}]\n")


if __name__ == "__main__":
    input_dir = r"D:\projects\NN\nn_lab"
    output_file = "merged_output.txt"
    exclude_dirs = [
        ".venv",
        "logs",
        "results",
        "tmp",
        ".idea",
        ".git",
        ".tox",
        ".pytest_cache",
        "docs",
        r"__pycache__",
        r"core\__pycache__",
        r"utils\__pycache__",
        r"tests\__pycache__",
        r"tests\.pytest_cache",
        r"core\tabs\__pycache__",
        r"core\service\__pycache__",
        r"core\rag\__pycache__",
        r"core\analysis\__pycache__",
        r"config\lib",
        r"lib",
        r"test_data",
    ]

    exclude_files = [
        r"requirements-base.txt",
        r"requirements-dev.in",
        r"requirements-dev.txt",
        r"requirements-linux.txt",
        r"requirements-windows.txt",
        r"requirements.in",
        r"requirements.txt",
        r"streamlit_app_lang_localization.py",
        r".gitignore",
        r"faq_ua.md",
        r"faq_eng_old.md",
        r"faq_ua.md",
        r"faq_ua_old.md",
        r"install.sh",
    ]

    merge_files(input_dir, output_file, exclude_dirs, exclude_files)
    print(f"All files from '{input_dir}' collected into '{output_file}', excluding {exclude_dirs} and {exclude_files}")

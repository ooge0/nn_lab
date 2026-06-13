import os

def merge_files(input_dir: str, output_file: str, exclude_dirs=None):
    """
    Собирает содержимое всех файлов из папки input_dir в один файл output_file.
    Добавляет относительный путь к каждому файлу как заголовок.
    Можно исключить определённые подпапки через exclude_dirs.
    """
    if exclude_dirs is None:
        exclude_dirs = []

    with open(output_file, "w", encoding="utf-8") as out:
        for root, _, files in os.walk(input_dir):
            # Проверяем, не входит ли текущая папка в список исключений
            rel_root = os.path.relpath(root, input_dir)
            if any(rel_root.startswith(ex) for ex in exclude_dirs):
                continue

            for fname in files:
                file_path = os.path.join(root, fname)
                rel_path = os.path.relpath(file_path, input_dir)
                out.write(f"\n\n=== {rel_path} ===\n\n")
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        out.write(f.read())
                except Exception as e:
                    out.write(f"[Ошибка чтения файла {rel_path}: {e}]\n")

if __name__ == "__main__":
    # Папка с файлами
    input_dir = r"D:\projects\NN\nn_lab"
    # Итоговый файл
    output_file = "merged_output.txt"
    # Список папок для исключения (относительно input_dir)
    exclude_dirs = [".venv", "logs", "results", "tmp"]

    merge_files(input_dir, output_file, exclude_dirs)
    print(f"Все файлы из '{input_dir}' собраны в '{output_file}', исключая {exclude_dirs}")

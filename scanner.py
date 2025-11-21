# core/scanner.py
import os
from pathlib import Path

def scan_folder(folder: str, extensions: list[str], recursive: bool) -> list[Path]:
    """
    扫描文件夹中的文件，按扩展名过滤，支持递归。
    
    Args:
        folder (str): 文件夹路径
        extensions (list[str]): 扩展名列表 (e.g., ['.jpg', '.png'])
        recursive (bool): 是否递归子文件夹
    
    Returns:
        list[Path]: 匹配的文件路径列表
    """
    files = []
    for root, dirs, filenames in os.walk(folder):
        for filename in filenames:
            if any(filename.lower().endswith(ext) for ext in extensions):
                files.append(Path(os.path.join(root, filename)))
        if not recursive:
            break
    return files
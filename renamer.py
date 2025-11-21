# core/renamer.py
import shutil
from pathlib import Path

class Renamer:
    """
    批量重命名与撤销（history 保存元组 (new_path, old_path)）
    """
    def __init__(self):
        self.history = []

    def rename_batch(self, ordered_list):
        """
        ordered_list: [(Path, new_name_str, allow_overwrite=False)]
        new_name_str 可以是只文件名（带扩展）或相对路径
        """
        for item in ordered_list:
            if len(item) >= 3:
                p, newname, allow_overwrite = item[0], item[1], item[2]
            else:
                p, newname = item[0], item[1]
                allow_overwrite = False
            src = Path(p)
            dst = src.parent / newname
            try:
                if dst.exists() and not allow_overwrite:
                    # 遇存在目标时跳过（也可以改成自动重命名）
                    continue
                shutil.move(str(src), str(dst))
                self.history.append((dst, src))
            except Exception as e:
                print(f"[Renamer] 重命名失败: {src} -> {dst} : {e}")

    def undo_all(self):
        for newp, oldp in reversed(self.history):
            try:
                if newp.exists():
                    shutil.move(str(newp), str(oldp))
            except Exception as e:
                print(f"[Renamer] 撤销失败: {newp} -> {oldp} : {e}")
        self.history.clear()

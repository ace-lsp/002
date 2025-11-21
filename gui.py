# gui.py
import json
import threading
import concurrent.futures
import shutil
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QMainWindow, QFileDialog, QMessageBox, QListWidget,
    QPushButton, QLabel, QLineEdit, QTextEdit, QVBoxLayout, QGridLayout,
    QComboBox, QSpinBox, QCheckBox, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QDialog
)
from PyQt6.QtCore import Qt, QMetaObject, Q_ARG, pyqtSlot

from core.scanner import scan_folder
from core.analyzer import Analyzer
from rules.sequences import SequenceGenerator
from rules.replacer import apply_replacements

CFG_PATH = Path("config/default_cfg.json")


class RenamerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RenamerAI Pro")
        self.resize(1400, 820)

        # 核心模块
        self.analyzer = Analyzer()
        self.seqgen = SequenceGenerator()

        # 数据
        self.files = []                 # Path 对象列表
        self.info = {}                  # {str(path): analysis_dict}
        self.config = self._load_default_config()

        # 初始化 last_folder 为桌面如果为空
        if not self.config.get("last_folder"):
            self.config["last_folder"] = os.path.join(os.path.expanduser("~"), "Desktop")

        # UI 状态
        self._folder_counters = {}      # 子文件夹独立计数
        self.include_subseq = True

        # 重命名历史（用于撤销）
        self.rename_history = []  # [(old_path, new_path) for rename, (None, new_path) for copy]

        self._init_ui()

    # ==============================================================
    # 配置
    # ==============================================================
    def _load_default_config(self):
        if not CFG_PATH.exists():
            CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
            default = {
                "extensions": [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"],
                "last_folder": "",
                "max_workers": 6
            }
            CFG_PATH.write_text(json.dumps(default, indent=2, ensure_ascii=False), encoding="utf-8")
            return default
        return json.loads(CFG_PATH.read_text(encoding="utf-8"))

    def closeEvent(self, event):
        """窗口关闭时保存配置"""
        CFG_PATH.write_text(json.dumps(self.config, indent=2, ensure_ascii=False), encoding="utf-8")
        super().closeEvent(event)

    # ==============================================================
    # UI
    # ==============================================================
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QGridLayout(central)

        # ------------------- 左侧：文件列表 -------------------
        left = QVBoxLayout()
        btn_choose = QPushButton("选择文件夹")
        btn_choose.clicked.connect(self.choose_folder)
        left.addWidget(btn_choose)

        self.chk_recursive = QCheckBox("递归子文件夹")
        self.chk_recursive.setChecked(True)
        left.addWidget(self.chk_recursive)

        self.ext_input = QLineEdit(", ".join(self.config.get("extensions", [])))
        left.addWidget(QLabel("扩展名 (逗号分隔)"))
        left.addWidget(self.ext_input)

        self.scan_btn = QPushButton("扫描并列出文件")
        self.scan_btn.clicked.connect(self.scan)
        left.addWidget(self.scan_btn)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["文件", "路径", "预览名"])
        self.tree.setColumnWidth(0, 500)
        left.addWidget(self.tree)

        layout.addLayout(left, 0, 0)

        # ------------------- 中间：排序 + AI -------------------
        mid = QVBoxLayout()
        mid.addWidget(QLabel("排序规则（多选，可上下移动）"))

        self.sort_list = QListWidget()
        self.sort_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        sort_options = [
            "分辨率(大→小)", "分辨率(小→大)",
            "长宽比(大→小)", "长宽比(小→大)",
            "景深(下→上)", "景深(上→下)",
            "景深(近→远)", "景深(远→近)",
            "俯仰角(大→小)", "俯仰角(小→大)",
            "光线(亮→暗)", "光线(暗→亮)",
            "元素数量(多→少)", "元素数量(少→多)",
            "创建时间(新→旧)", "文件名(自然升序)",
            "同一物体(近→远)",            # ← 新增
            "同一标志(近→远)"             # ← 新增
        ]
        for o in sort_options:
            self.sort_list.addItem(o)
        mid.addWidget(self.sort_list)

        btn_up = QPushButton("↑ 上移")
        btn_down = QPushButton("↓ 下移")
        btn_up.clicked.connect(self.sort_move_up)
        btn_down.clicked.connect(self.sort_move_down)
        mid.addWidget(btn_up)
        mid.addWidget(btn_down)

        btn_apply = QPushButton("应用排序（子文件夹独立）")
        btn_apply.clicked.connect(self.apply_sort)
        mid.addWidget(btn_apply)

        # AI 控制区
        ai_grp = QGroupBox("AI 分析（子文件夹独立）")
        ai_box = QVBoxLayout()
        self.btn_start_analysis = QPushButton("开始分析")
        self.btn_start_analysis.clicked.connect(self.start_analysis)
        ai_box.addWidget(self.btn_start_analysis)

        self.lbl_mode = QLabel(f"当前模式: {self.analyzer.mode}")
        ai_box.addWidget(self.lbl_mode)

        self.chk_include_subseq = QCheckBox("包含次级序列")
        self.chk_include_subseq.setChecked(True)
        self.chk_include_subseq.stateChanged.connect(self._toggle_subseq)
        ai_box.addWidget(self.chk_include_subseq)

        ai_grp.setLayout(ai_box)
        mid.addWidget(ai_grp)

        layout.addLayout(mid, 0, 1)

        # ------------------- 右侧：模板、序列、规则 -------------------
        right = QVBoxLayout()

        # 模板
        tmpl_grp = QGroupBox("命令模板（多行 = 多级命令）")
        tmpl_grp.setCheckable(True)
        tmpl_grp.setChecked(True)
        tbox = QVBoxLayout()
        self.template_edit = QTextEdit()
        self.template_edit.setPlainText(
            "{folder}_{index}_{primary}.{ext}\n"
            "{folder}_{index}_{secondary}_{primary}.{ext}"
        )
        tbox.addWidget(QLabel("占位符: {index} {secondary} {primary} {folder} {ext} …"))
        tbox.addWidget(self.template_edit)
        tmpl_grp.setLayout(tbox)
        right.addWidget(tmpl_grp)

        # 序列设置
        seq_grp = QGroupBox("序列设置")
        sbox = QVBoxLayout()
        self.seq_type = QComboBox()
        self.seq_type.addItems(["数字(递增)", "大写字母(A..Z)", "自定义列表", "日期(YYYYMMDD)"])
        sbox.addWidget(QLabel("主序列类型")); sbox.addWidget(self.seq_type)
        sbox.addWidget(QLabel("起始值")); self.seq_start = QLineEdit("1"); sbox.addWidget(self.seq_start)
        sbox.addWidget(QLabel("数字位数")); self.seq_digits = QSpinBox(); self.seq_digits.setValue(4); sbox.addWidget(self.seq_digits)

        sbox.addWidget(QLabel("次级序列类型")); self.subseq_type = QComboBox()
        self.subseq_type.addItems(["中文序号(一二三)", "小写字母(a..z)", "自定义列表"])
        sbox.addWidget(self.subseq_type)
        sbox.addWidget(QLabel("次级起始")); self.subseq_start = QLineEdit("一"); sbox.addWidget(self.subseq_start)
        seq_grp.setLayout(sbox)
        right.addWidget(seq_grp)

        # 替换规则
        rep_grp = QGroupBox("替换/删除规则（每行 find=>replace）")
        rbox = QVBoxLayout()
        self.rep_text = QTextEdit()
        rbox.addWidget(self.rep_text)
        btn_rules = QPushButton("编辑规则（新窗口）")
        btn_rules.clicked.connect(self._open_rules_dialog)
        rbox.addWidget(btn_rules)
        rep_grp.setLayout(rbox)
        right.addWidget(rep_grp)

        # 重命名模式
        self.chk_copy_mode = QCheckBox("复制模式（保留原文件）")
        self.chk_copy_mode.setChecked(True)
        right.addWidget(self.chk_copy_mode)

        # 操作按钮
        btn_preview = QPushButton("预览重命名"); btn_preview.clicked.connect(self.preview_names); right.addWidget(btn_preview)
        btn_execute = QPushButton("执行重命名"); btn_execute.clicked.connect(self.execute_rename); right.addWidget(btn_execute)
        btn_undo = QPushButton("撤销全部"); btn_undo.clicked.connect(self.undo_all); right.addWidget(btn_undo)

        btn_save = QPushButton("保存方案"); btn_save.clicked.connect(self.save_scheme); right.addWidget(btn_save)
        btn_load = QPushButton("加载方案"); btn_load.clicked.connect(self.load_scheme); right.addWidget(btn_load)

        # 日志
        right.addWidget(QLabel("日志"))
        self.log = QTextEdit(); self.log.setReadOnly(True); right.addWidget(self.log)

        layout.addLayout(right, 0, 2)

        layout.setColumnStretch(0, 6)
        layout.setColumnStretch(1, 3)
        layout.setColumnStretch(2, 4)

    # ==============================================================
    # 基础交互
    # ==============================================================
    def _toggle_subseq(self, state):
        self.include_subseq = (state == Qt.CheckState.Checked.value)

    def _open_rules_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("编辑替换/删除规则")
        lay = QVBoxLayout(dlg)
        text = QTextEdit()
        text.setPlainText(self.rep_text.toPlainText())
        lay.addWidget(text)
        ok = QPushButton("保存并关闭")
        ok.clicked.connect(lambda: [self.rep_text.setPlainText(text.toPlainText()), dlg.accept()])
        lay.addWidget(ok)
        dlg.resize(600, 400)
        dlg.exec()

    def choose_folder(self):
        default_dir = self.config.get("last_folder", os.path.join(os.path.expanduser("~"), "Desktop"))
        folder = QFileDialog.getExistingDirectory(self, "选择图片文件夹", default_dir)
        if folder:
            self.config["last_folder"] = folder

    def scan(self):
        folder = self.config.get("last_folder", "")
        if not folder:
            QMessageBox.warning(self, "错误", "请先选择文件夹")
            return
        exts = [e.strip().lower() if e.strip().startswith(".") else "." + e.strip().lower()
                for e in self.ext_input.text().split(",") if e.strip()]
        recursive = self.chk_recursive.isChecked()
        self.files = scan_folder(folder, exts, recursive)

        self.tree.clear()
        self._folder_counters = {}
        for p in self.files:
            it = QTreeWidgetItem([p.name, str(p.parent), ""])
            it.setData(0, Qt.ItemDataRole.UserRole, str(p))
            self.tree.addTopLevelItem(it)
        self.log.append(f"扫描完成，共 {len(self.files)} 个文件")

    # ==============================================================
    # AI 分析（多线程 + 线程安全 UI 更新）
    # ==============================================================
    def start_analysis(self):
        if not self.files:
            QMessageBox.warning(self, "错误", "请先扫描文件")
            return
        self.log.append("开始 AI 分析（多线程）...")
        threading.Thread(target=self._analysis_worker, daemon=True).start()

    def _analysis_worker(self):
        self.info = {}
        groups = {}
        for p in self.files:
            groups.setdefault(str(p.parent), []).append(p)

        max_workers = self.config.get("max_workers", 6)

        for folder_path, paths in groups.items():
            self._folder_counters[folder_path] = 0

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as exe:
                future_to_path = {exe.submit(self.analyzer.analyze, p): p for p in paths if p.exists()}

                for future in concurrent.futures.as_completed(future_to_path):
                    p = future_to_path[future]
                    try:
                        info = future.result()
                        info["folder"] = Path(folder_path).name
                        self.info[str(p)] = info

                        # 线程安全地更新 UI
                        preview_name = self._build_preview_name_from_info(info, 1, folder_path)
                        QMetaObject.invokeMethod(
                            self, "_update_tree_item",
                            Qt.ConnectionType.QueuedConnection,
                            Q_ARG(str, str(p)),
                            Q_ARG(str, preview_name)
                        )
                    except Exception as e:
                        error_msg = f"分析失败 {p.name}: {e}"
                        QMetaObject.invokeMethod(
                            self, "_append_log",
                            Qt.ConnectionType.QueuedConnection,
                            Q_ARG(str, error_msg)
                        )

        QMetaObject.invokeMethod(
            self, "_append_log",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, "AI 分析全部完成")
        )

    @pyqtSlot(str, str)
    def _update_tree_item(self, path_str: str, preview: str):
        """由主线程调用，安全更新预览列"""
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.data(0, Qt.ItemDataRole.UserRole) == path_str:
                it.setText(2, preview)
                break

    @pyqtSlot(str)
    def _append_log(self, text: str):
        """由主线程调用，安全追加日志"""
        self.log.append(text)

    # ==============================================================
    # 预览 & 执行
    # ==============================================================
    def _get_folder_index(self, folder):
        c = self._folder_counters.get(folder, 0) + 1
        self._folder_counters[folder] = c
        return c

    def _build_preview_name_from_info(self, info, idx, folder_path):
        templates = [t for t in self.template_edit.toPlainText().splitlines() if t.strip()]
        if not templates:
            return ""

        main_idx = str(idx).zfill(self.seq_digits.value())
        sub_idx = self.seqgen.gen_sub(self.subseq_type.currentText(),
                                      self.subseq_start.text(), idx - 1) if self.include_subseq else ""

        raw = Path(info.get("filename", "")).stem
        primary = apply_replacements(info.get("primary", raw), self._parse_rep_rules())

        values = {
            "{index}": main_idx,
            "{secondary}": sub_idx,
            "{primary}": primary,
            "{raw}": raw,
            "{resolution}": f"{info.get('w',0)}x{info.get('h',0)}",
            "{objects}": str(info.get("object_count", 0)),
            "{depth}": str(info.get("depth_score", "")),
            "{layer1}": (info.get("layers", []) + [""])[0].split(":", 1)[-1],
            "{layer2}": (info.get("layers", []) + ["", ""])[1].split(":", 1)[-1],
            "{layer3}": (info.get("layers", []) + ["", "", ""])[2].split(":", 1)[-1],
            "{ext}": Path(info.get("filename", "")).suffix.lstrip("."),
            "{folder}": Path(folder_path).name if folder_path else info.get("folder", ""),
            "{aspect}": str(info.get("aspect_ratio", "")),
            "{pitch}": str(info.get("pitch_score", "")),
            "{brightness}": str(info.get("brightness", "")),
        }

        result_lines = []
        for tmpl in templates:
            out = tmpl
            for k, v in values.items():
                out = out.replace(k, v)
            out = apply_replacements(out, self._parse_rep_rules())
            if "." not in out and values["{ext}"]:
                out += "." + values["{ext}"]
            result_lines.append(out)

        return " → ".join(result_lines)

    def preview_names(self):
        self._folder_counters = {}
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            p = Path(it.data(0, Qt.ItemDataRole.UserRole))
            folder = str(p.parent)
            idx = self._get_folder_index(folder)
            info = self.info.get(str(p), {"filename": str(p), "primary": p.stem})
            it.setText(2, self._build_preview_name_from_info(info, idx, folder))
        self.log.append("预览已刷新")

    def execute_rename(self):
        self._folder_counters = {}
        self.rename_history = []
        copy_mode = self.chk_copy_mode.isChecked()

        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            src = Path(it.data(0, Qt.ItemDataRole.UserRole))
            folder = str(src.parent)
            idx = self._get_folder_index(folder)
            info = self.info.get(str(src), {"filename": str(src), "primary": src.stem})

            chain = self._build_preview_name_from_info(info, idx, folder)
            if not chain:
                continue
            final_name = chain.split(" → ")[-1]

            dest = src.parent / final_name

            # 解决文件名冲突
            base, ext = Path(final_name).stem, Path(final_name).suffix
            i = 1
            while dest.exists():
                dest = src.parent / f"{base}_{i}{ext}"
                i += 1

            if copy_mode:
                shutil.copy2(src, dest)
                self.rename_history.append((None, dest))
            else:
                old_path = src
                src.rename(dest)
                self.rename_history.append((old_path, dest))

            # 更新树视图（可选）
            it.setText(0, dest.name)
            it.setData(0, Qt.ItemDataRole.UserRole, str(dest))

        mode_str = "复制" if copy_mode else "重命名"
        self.log.append(f"执行{mode_str}完成")

    def undo_all(self):
        for old, new in reversed(self.rename_history):
            if old is None:
                # copy mode: delete copy
                new.unlink(missing_ok=True)
            else:
                # rename mode: rename back
                new.rename(old)
        self.rename_history = []
        self.log.append("撤销完成")
        # 重新扫描以更新视图（可选）
        self.scan()

    # ==============================================================
    # 排序（新增近远排序）
    # ==============================================================
    def apply_sort(self):
        selected = [self.sort_list.item(i).text() for i in range(self.sort_list.count())
                    if self.sort_list.item(i).isSelected()]
        if not selected:
            QMessageBox.information(self, "提示", "请至少选择一条排序规则")
            return

        groups = {}
        for p in self.files:
            groups.setdefault(str(p.parent), []).append(p)

        new_order = []
        for folder, paths in groups.items():
            items = [(p, self.info.get(str(p), {})) for p in paths]

            # 按用户选择的顺序，从最低优先级到最高优先级（稳定排序）
            for rule in reversed(selected):
                reverse = "大→小" in rule or "多→少" in rule or "新→旧" in rule or "亮→暗" in rule or "远→近" in rule

                if "分辨率" in rule:
                    key = lambda x: x[1].get("w", 0) * x[1].get("h", 0)
                elif "长宽比" in rule:
                    key = lambda x: x[1].get("aspect_ratio", 0.0)
                elif "景深" in rule:
                    key = lambda x: x[1].get("depth_score", 0.0)
                elif "俯仰角" in rule:
                    key = lambda x: x[1].get("pitch_score", 0.0)
                elif "光线" in rule:
                    key = lambda x: x[1].get("brightness", 0.0)
                elif "元素数量" in rule:
                    key = lambda x: x[1].get("object_count", 0)
                elif "创建时间" in rule:
                    key = lambda x: x[0].stat().st_mtime
                elif "文件名" in rule:
                    key = lambda x: x[0].name.lower()
                elif rule == "同一物体(近→远)":
                    # 假设 analyzer 给每张图返回了主要物体的类型 + 平均深度
                    def obj_key(x):
                        typ = x[1].get("primary_object_type", "")
                        depth = x[1].get("primary_object_depth", 999999)
                        return (typ, depth)
                    items.sort(key=obj_key)
                    continue
                elif rule == "同一标志(近→远)":
                    def sign_key(x):
                        typ = x[1].get("sign_type", "")
                        depth = x[1].get("sign_depth", 999999)
                        return (typ, depth)
                    items.sort(key=sign_key)
                    continue
                else:
                    key = lambda x: 0

                items.sort(key=key, reverse=reverse)

            new_order.extend([p for p, _ in items])

        self.files = new_order
        self.tree.clear()
        for p in self.files:
            it = QTreeWidgetItem([p.name, str(p.parent), ""])
            it.setData(0, Qt.ItemDataRole.UserRole, str(p))
            self.tree.addTopLevelItem(it)

        self.log.append(f"排序完成：{', '.join(selected)}")

    def sort_move_up(self):
        row = self.sort_list.currentRow()
        if row <= 0: return
        item = self.sort_list.takeItem(row)
        self.sort_list.insertItem(row - 1, item)
        self.sort_list.setCurrentRow(row - 1)

    def sort_move_down(self):
        row = self.sort_list.currentRow()
        if row >= self.sort_list.count() - 1: return
        item = self.sort_list.takeItem(row)
        self.sort_list.insertItem(row + 1, item)
        self.sort_list.setCurrentRow(row + 1)

    # ==============================================================
    # 方案保存/加载
    # ==============================================================
    def save_scheme(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存方案", "", "JSON (*.json)")
        if not path: return
        data = {
            "extensions": self.ext_input.text(),
            "templates": self.template_edit.toPlainText(),
            "sequence": {
                "type": self.seq_type.currentText(),
                "start": self.seq_start.text(),
                "digits": self.seq_digits.value(),
                "sub_type": self.subseq_type.currentText(),
                "sub_start": self.subseq_start.text(),
            },
            "replace_rules": self.rep_text.toPlainText(),
        }
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log.append(f"方案已保存：{path}")

    def load_scheme(self):
        path, _ = QFileDialog.getOpenFileName(self, "加载方案", "", "JSON (*.json)")
        if not path: return
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.ext_input.setText(data.get("extensions", ""))
        self.template_edit.setPlainText(data.get("templates", ""))
        seq = data.get("sequence", {})
        self.seq_type.setCurrentText(seq.get("type", "数字(递增)"))
        self.seq_start.setText(seq.get("start", "1"))
        self.seq_digits.setValue(seq.get("digits", 4))
        self.subseq_type.setCurrentText(seq.get("sub_type", "中文序号(一二三)"))
        self.subseq_start.setText(seq.get("sub_start", "一"))
        self.rep_text.setPlainText(data.get("replace_rules", ""))
        self.log.append(f"方案已加载：{path}")

    def _parse_rep_rules(self):
        rules = []
        for line in self.rep_text.toPlainText().splitlines():
            if "=>" in line:
                a, b = line.split("=>", 1)
                rules.append((a.strip(), b.strip()))
        return rules
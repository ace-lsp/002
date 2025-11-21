# 002-RenamerAI2.5
#文件夹及子文件夹图片等识别，重命名：“近远、角度、明暗、大小”等排序自定义替换命名
#通过AI（gpt和grok）应用，代码、调试、制作
RenamerAI/
│
├─ main.py                # 启动主程序
├─ gui.py                 # 界面逻辑
├─ config/
│   └─ default_cfg.json   # 默认配置
├─ core/
│   ├─ __init__.py
│   ├─ scanner.py         # 文件扫描
│   ├─ analyzer.py        # AI 分析
│   └─ renamer.py         # 批量重命名 + 撤销
├─ rules/
│   ├─ __init__.py
│   ├─ sequences.py       # 序列生成器
│   └─ replacer.py        # 替换规则
└─ resources/
    └─ icons/             # 可放程序图标

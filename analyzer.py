# core/analyzer.py
"""
Analyzer：对图片进行轻量级“AI”分析（真实接入模型可替换下面的方法）
输出字段（info dict）至少包含：
 - filename: 文件名
 - w, h: 宽和高
 - primary: 主要对象（这里用文件名占位）
 - object_count: 元素数量（简易估计或模拟）
 - depth_score: 景深评分（模拟或来自深度模型）
 - layers: 分层识别字符串列表（如 "layer1:前景"）
 - all: 所有信息合并字符串
 - aspect_ratio: 长宽比（w/h）
 - pitch_score: 俯仰角估算（简易图像亮度梯度估计）
 - brightness: 图像平均亮度（0-255）
"""
from pathlib import Path
import random
from PIL import Image, ImageStat, ImageFilter

try:
    import numpy as np
except Exception:
    np = None

class Analyzer:
    def __init__(self, mode="BLIP"):
        self.mode = mode

    def switch_mode(self, new_mode=None):
        if new_mode:
            self.mode = new_mode
        else:
            self.mode = "ZoeDepth" if self.mode == "BLIP" else "BLIP"
        return self.mode

    def analyze(self, filepath: Path):
        """
        对单张图片进行分析，优先使用 PIL + numpy 做局部计算（brightness, aspect, pitch）
        对象计数与深度为模拟（可替换为 BLIP / ZoeDepth 的真实实现）
        """
        p = Path(filepath)
        info = {"filename": p.name}
        # 默认随机/占位值
        info["primary"] = p.stem
        info["object_count"] = 0
        info["depth_score"] = 0.0
        info["layers"] = []
        info["all"] = p.stem

        try:
            img = Image.open(p).convert("RGB")
            w, h = img.size
            info["w"], info["h"] = w, h
            # aspect ratio
            info["aspect_ratio"] = round(w / h, 3) if h != 0 else 0.0

            # brightness (平均亮度)
            stat = ImageStat.Stat(img.convert("L"))
            brightness = stat.mean[0] if stat.mean else 0.0
            info["brightness"] = round(float(brightness), 2)

            # pitch_score: 用简单方法估计“俯仰/倾斜”——垂直亮度梯度的中心偏移
            # 将图像缩小，加速计算
            small = img.resize((64, 64)).convert("L")
            if np is not None:
                arr = np.asarray(small).astype(float)
                # 计算每行平均亮度，找到亮度重心
                row_mean = arr.mean(axis=1)
                weights = np.arange(len(row_mean))
                if row_mean.sum() != 0:
                    centroid = (weights * row_mean).sum() / row_mean.sum()
                else:
                    centroid = len(row_mean)/2
                # 将 centroid 转换为偏离中心的分数（中心为 0，越偏上/下绝对值越大）
                pitch_score = (centroid - (len(row_mean)-1)/2)
                # 标准化到 -1..1
                pitch_score = float(pitch_score) / (len(row_mean)/2)
                info["pitch_score"] = round(pitch_score, 3)
            else:
                # 无 numpy 时采用简单估算：顶半区均值 vs 底半区均值
                small_arr = list(small.getdata())
                half = (64*64)//2
                top_mean = sum(small_arr[:half]) / half
                bot_mean = sum(small_arr[half:]) / half
                info["pitch_score"] = round((bot_mean - top_mean) / 255.0, 3)

            # object_count & depth_score & layers: 简单模拟或用基本图像特征
            # object_count：用边缘强度估计（ImageFilter.FIND_EDGES）
            edges = small.filter(ImageFilter.FIND_EDGES)
            est_edges = ImageStat.Stat(edges).sum[0]
            info["object_count"] = int(min(30, max(0, est_edges // 5000)))
            # depth_score: 随机+亮度/contrast因素简单融合，范围 0..100
            info["depth_score"] = round(min(100, max(0, info["brightness"] * 0.2 + random.uniform(0,40))), 2)

            # layers：使用中心裁剪和文本占位（真实情况用 BLIP 模型）
            center = img.crop((w//4, h//4, 3*w//4, 3*h//4)).resize((384,384))
            info["layers"] = [
                f"最前景:{p.stem}",
                f"中景:{p.stem}",
                f"远景:{p.stem}"
            ]
            info["all"] = f"{info['primary']}|ar={info['aspect_ratio']}|b={info['brightness']}"
        except Exception as e:
            # 如果读图失败，填默认
            info.setdefault("w", 0)
            info.setdefault("h", 0)
            info.setdefault("aspect_ratio", 0.0)
            info.setdefault("pitch_score", 0.0)
            info.setdefault("brightness", 0.0)
            info.setdefault("object_count", 0)
            info.setdefault("depth_score", 0.0)
            info.setdefault("layers", [])
            info.setdefault("all", p.stem)
        return info

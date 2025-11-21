# rules/sequences.py
class SequenceGenerator:
    def __init__(self):
        self.chinese_nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]  # 示例，扩展更多

    def gen_sub(self, seq_type: str, start: str, index: int) -> str:
        """
        生成次级序列。
        
        Args:
            seq_type (str): 类型 ('中文序号(一二三)', '小写字母(a..z)', '自定义列表')
            start (str): 起始值 (自定义列表用逗号分隔)
            index (int): 索引 (从0开始)
        
        Returns:
            str: 生成的序列值
        """
        if seq_type == "中文序号(一二三)":
            if index < len(self.chinese_nums):
                return self.chinese_nums[index]
            else:
                return str(index + 1)  # 超出时用数字
        elif seq_type == "小写字母(a..z)":
            return chr(97 + index % 26)  # a-z 循环
        elif seq_type == "自定义列表":
            custom_list = [item.strip() for item in start.split(",")]
            if index < len(custom_list):
                return custom_list[index]
            else:
                return str(index + 1)
        return ""
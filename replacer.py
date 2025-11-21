# rules/replacer.py
def apply_replacements(text: str, rules: list[tuple[str, str]]) -> str:
    """
    应用替换规则到文本。
    
    Args:
        text (str): 输入文本
        rules (list[tuple[str, str]]): 规则列表 (find, replace)，replace为空表示删除
    
    Returns:
        str: 处理后的文本
    """
    for find, replace in rules:
        if replace == "":  # 删除
            text = text.replace(find, "")
        else:
            text = text.replace(find, replace)
    return text
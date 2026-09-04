"""文件读取与列名适配工具。

CSV 编码回退链：utf-8-sig → gb18030 → gbk → big5 → latin1
（gb18030 是 GBK 的超集，必须排在 gbk 前面；latin1 永不抛错，作最后兜底）
"""
import re

import pandas as pd
from io import StringIO, BytesIO

ENCODE_CHAIN = ("utf-8-sig", "gb18030", "gbk", "big5", "latin1")

# 目标列 -> 可接受的源列名（匹配时忽略大小写、去空格、去括号内容）
COLUMN_ALIASES = {
    "date": ("日期", "销售日期", "date"),
    "product_name": ("商品名称", "商品", "品名", "product_name"),
    "category": ("品类", "类别", "分类", "category"),
    "unit_price": ("售价", "单价", "销售价", "unit_price"),
    "cost_price": ("成本", "成本价", "进价", "cost_price"),
    "quantity": ("数量", "销售数量", "销量", "quantity"),
}


def decode_csv(content: bytes) -> str:
    for enc in ENCODE_CHAIN:
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别的文件编码")


def read_table(content: bytes, filename: str) -> pd.DataFrame:
    """按文件后缀读取 xlsx/csv，返回保持原始列名的 DataFrame。"""
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return pd.read_csv(StringIO(decode_csv(content)))
    return pd.read_excel(BytesIO(content))


def normalize_header(name) -> str:
    """表头标准化：转字符串、去括号内容、去空格、转小写。"""
    s = "" if name is None else str(name)
    s = re.sub(r"[（(].*?[）)]", "", s)
    return s.strip().lower()


def detect_mapping(df: pd.DataFrame) -> dict:
    """识别列映射，返回 {目标列: 实际源列名}，未识别到的目标列不出现。"""
    normalized = {normalize_header(c): c for c in df.columns}
    mapping = {}
    for target, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            key = normalize_header(alias)
            if key in normalized:
                mapping[target] = normalized[key]
                break
    return mapping


def apply_mapping(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """按 {目标列: 源列名} 重命名，只保留已识别的目标列。"""
    out = df.rename(columns={src: tgt for tgt, src in mapping.items()})
    return out[list(mapping.keys())]

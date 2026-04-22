"""数据加载模块 - 加载任意文本文件"""

from pathlib import Path
from typing import List, Tuple

from .step2_loader import load_texts_from_step2_output


def load_text(path: Path) -> Tuple[str, str]:
    """
    加载单个文本文件

    Args:
        path: 文件路径

    Returns:
        (text, source_id) 元组
    """
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    if not path.is_file():
        raise ValueError(f"路径不是文件: {path}")

    # 读取文件内容
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    # source_id 使用文件名（不含扩展名）
    source_id = path.stem

    return text, source_id


def load_texts(path: Path, mode: str = "auto") -> List[Tuple[str, str]]:
    """
    加载目录下所有文本文件

    Args:
        path: 文件或目录路径
        mode: 加载模式
            - "auto": 自动检测（默认）
            - "step2_output": 从 Step2 输出的 XML 文件加载
            - "raw": 直接加载文本文件

    Returns:
        [(text, source_id), ...] 列表
    """
    path = Path(path)

    # Step2 输出模式
    if mode == "step2_output" or (mode == "auto" and path.is_dir() and any(path.glob("*_reasoning_chain_refine.xml"))):
        return load_texts_from_step2_output(path)

    # 如果是文件，直接加载
    if path.is_file():
        return [load_text(path)]

    # 如果是目录，加载所有支持的文件
    if not path.is_dir():
        raise ValueError(f"路径既不是文件也不是目录: {path}")

    supported_extensions = {'.txt', '.xml', '.json', '.md'}
    results = []

    for file_path in sorted(path.iterdir()):
        if file_path.is_file() and file_path.suffix in supported_extensions:
            try:
                text, source_id = load_text(file_path)
                results.append((text, source_id))
            except Exception as e:
                print(f"  ✗ 加载文件失败 {file_path.name}: {e}")

    return results

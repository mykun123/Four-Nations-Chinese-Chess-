# super_ai — 高性能四国象棋AI（并行搜索）
import sys
import os

# 确保自身目录在 sys.path 中，使直接导入生效
_super_ai_dir = os.path.dirname(__file__)
if _super_ai_dir not in sys.path:
    sys.path.insert(0, _super_ai_dir)

from search import SuperAI

__all__ = ["SuperAI"]

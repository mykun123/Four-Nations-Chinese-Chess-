# 搜索配置
# ============================================================

# 根节点展开数（root moves 上限）
MAX_ROOT_MOVES = 12

# 己方/队友内部节点展开数
MAX_AI_MOVES = 8

# 对手内部节点展开数
MAX_OPP_MOVES = 4

# 静态搜索深度
MAX_Q_DEPTH = 3

# 默认搜索深度（迭代加深上限）
DEFAULT_DEPTH = 8

# 并行工作进程数（等于 CPU 核心数时最优）
NUM_WORKERS = 8

# 搜索时间限制
MIN_TIME = 0.5    # 最少搜索秒数
MAX_TIME = 15.0   # 最多搜索秒数

# 换子阈值（低于此分的局面触发绝境换子逻辑）
DESPERATION_THRESHOLD = -3000

# 空着剪枝（Null Move Pruning）相关
NULL_MOVE_DEPTH_REDUCTION = 2  # 空着减层数
NULL_MOVE_MIN_DEPTH = 3        # 至少这个深度才尝试空着

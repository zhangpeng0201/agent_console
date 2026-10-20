'''
定义返回容器
'''

from dataclasses import dataclass


# 路由
@dataclass
class RouterDecision:
    type: str  # command、chat、answer  任务类型是指令还是闲聊
    tool: str | None  # 要调哪个工具
    args: dict   # 工具的参数字典
    text: str | None = None  # 任务类型为 answer 时模型的回复


# 工具调用结果
@dataclass
class ToolResult:
    ok: bool  # True or False
    reply: str  # 给用户看的话术
    id: int | None  # memos.json 里的序列号
    candidate: list | None = None  # 候选行号列表

# api 调用结果
@dataclass
class ApiResult:
    ok: bool
    reply: str
    steps: list
    error: str | None = None



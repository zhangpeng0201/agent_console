'''
B2 组：原生 function calling + 机制中立的 prompt

与 B1（router_fc.py）的唯一差别是 SYSTEM_PROMPT。代码一字未改，
两个文件的结构完全对称，diff 只差 prompt 那一段。

B1 的 prompt 是从 A 组 PROMPT 直接裁三段得来的，里面残留 6 处 JSON 语境：
  · "# 角色" 里"并输出对应的 json"
  · 定义 command / chat / answer 三个类别（B 组没有 type 字段，answer 单轮用不到）
  · "tool 填 null，args 填 {}"
  · "只有在收到【工具结果】之后才能给 answer"
  · "text 要汇总成人话"
  · "放进 args.text" / "args 填 {}"
这套措辞与 tools 通道是两个方向，模型被两边撕着走。

本文件的 prompt 做了两类改动，写报告时要分开说：

【一类 · 等价翻译】把 A 组规则原意换成不依赖 JSON 的说法，信息量不变
  - 角色：意图识别助手 → 生活助理（"要动手/不用动手"取代"归为哪一类"）
  - 规则条目：command / chat → "要动手的 / 不用动手的"
  - 一句话多事：改为"逐个调工具"，去掉 answer 语境
  - 参数段：去掉 "args.text" / "args 填 {}"，改说"作为参数 / 不用传参数"
  - 整段删除 answer 相关规则（单轮路由用不到）

【二类 · 补充翻译】A 组靠例子承载、B 组没有例子可用的边界知识
  - 新增"记东西用哪个工具"整段：add_todo / add_memo 的区分
  - 新增"陈述一件已经成立的事实"算不用动手（对应「我女朋友的生日是三月十二号」）
  理由：tools 模式下模型看不到示例，只能靠文字说清边界；
  这两条不是新增规则，是把 A 组例子里隐含的判断标准写成话。
'''
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import llm_client          # 提供 DEEPSEEK_CLIENT 和 PROVIDERS
from tools import get_current_time
from schemas import RouterDecision
from tool_schema import TOOLS_SCHEMA

CURRENT_DATE = get_current_time().reply.split('，')[0]

# 系统提示词 —— 机制中立版：只说"什么时候动手""怎么填参数"，不说"输出什么结构"
SYSTEM_PROMPT = '''
# 角色
你的名字是一一，你是一个生活助理。用户说一句话，你判断要不要替他做点事：
要做，就调用对应的工具；不用做，就直接跟他聊。

# 当前日期
{CURRENT_DATE}

# 什么时候要动手
1. 以"用户是不是在指使你做一件具体的事"为准，不要只看句子里有没有"记"字。
2. 要动手的，常见这么几种：
   - 明确要求：记一下…／帮我记…／存一下…／提醒我…
   - 隐含提醒：别忘记…／别漏了…／可别忘…／记得提醒我…（句子里没有"记"字，但确实在要你提醒）
   - 询问记录：我记了哪些…／我还有多少…没做／清单上还有什么／备忘里都有啥
3. 不用动手的：
   - 表达感受、闲聊：今天真是累坏了
   - 只是提到"记"字或"忘"字，但没让你做事：我这两天记性不太行／我老是忘事儿
   - 只是在告诉你一件事，并没有请你记下来，说完就完了

# 记东西用哪个工具
- 带着时间点、或者"要去做"的意思 → add_todo。比如：明天下午三点开会、后天去交材料。
- 只是一个信息、一件事实 → add_memo。比如：门禁密码是8899、妈妈的生日是三月十二号。
- 分不清时看时间点：有具体时间的多半是待办，没有的多半是备忘。

# 一句话里不止一件事
出现"两个""都""前几条""顺便""还有"这类说法时，逐个调用对应的工具，不要只办第一件；
同一件事要办几次就调几次（比如"前两条都办完了"要连着调两次完成待办）。

# 多轮对话
你可能会收到之前的对话记录（user / assistant 交替出现），assistant 那几轮是系统执行后留下的回执，
可以用它了解"刚才聊了什么"。
如果用户这一句省略了内容，而上一轮刚提到某件事，就把那件事补进参数里；历史里也找不到就直接聊。

# 参数
- 需要内容参数的工具：只去掉句首的动作词（记一下／帮我记／帮我记一下／存一下／备忘一下），
  剩下的原样放进去。句子里的时间词（明天、后天、周六、下午三点）是内容的一部分，要保留。
  不要自己补充、改写或追加上下文里没有的信息。
- 不需要参数的工具：不用传参数。
- 删除类工具二选一：用户给了明确序号就用序号；用户描述的是内容特征就用关键词。
'''


def _call(text: str, history: list | None = None):
    res = llm_client.DEEPSEEK_CLIENT.chat.completions.create(
        messages=[{'role': 'system', 'content': SYSTEM_PROMPT.replace('{CURRENT_DATE}', CURRENT_DATE)}] + (history or []) + [
            {'role': 'user', 'content': text} ],
        **llm_client.PROVIDERS[0]['private'],
        max_tokens=800,
        temperature=0,
        timeout=5,
        tools=TOOLS_SCHEMA,
        tool_choice='auto'
    )
    response = res.choices[0].message
    return response

def route(text: str, history: list | None = None) -> RouterDecision:
    response = _call(text, history)
    if response.tool_calls:
        return RouterDecision(
            type='command',
            tool=response.tool_calls[0].function.name,
            args=json.loads(response.tool_calls[0].function.arguments)
        )
    return RouterDecision(
        type='chat',
        tool=None,
        args={}
    )


if __name__ == '__main__':
    S = SYSTEM_PROMPT.replace('{CURRENT_DATE}', CURRENT_DATE)
    print('system 长度:', len(S), ' 行数:', S.count('\n') + 1)
    for bad in ['json', 'args', 'command', 'answer', 'tool 填']:
        print(f'  残留 {bad!r}: {S.count(bad)}')
    print()
    for t in ['记一下明天交水电费', '你好呀', '把待办第2条删掉']:
        d = route(t)
        print(f'{t!r:24} → {d.type} / {d.tool} / {d.args}')

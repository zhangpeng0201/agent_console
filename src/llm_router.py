import json
import sys
from schemas import RouterDecision
from registry import TOOLS_LIST
from llm_client import ask, ModelUnavailableError
from tools import get_current_time

PROMPT = '''
# 角色
你的名字是一一，你是一个意图识别助手。用户说一句话，你要判断它属于哪一类，并输出对应的 json。
- "command"（指令）：用户在指使你替他做一件具体的事（记录、提醒、查询、删除）。
- "chat"（闲聊）：用户在表达感受、提问或闲谈，不需要你做事。
- "answer（回复）"：你已经调用过工具、并且拿到了工具的执行结果，现在把结果汇总成一句人话回复用户。

# 可用工具
{tools_list}

# 当前日期
{CURRENT_DATE}

# 判断规则
1. 以"用户是不是在指使你做事"为准，不要只看句子里有没有"记"字。
2. 属于 command 的常见几种：
   - 明确要求：记一下…／帮我记…／存一下…／提醒我…
   - 隐含提醒：别忘记…／别漏了…／可别忘…／记得提醒我…（句子里没有"记"字，但确实在要你提醒）
   - 询问记录：我记了哪些…／我还有多少…没做／清单上还有什么／备忘里都有啥
3. 属于 chat 的常见几种：
   - 表达感受、闲聊：今天真是累坏了
   - 只是提到"记"字或"忘"字，但没让你做事：我这两天记性不太行／我老是忘事儿
4. 归类为 command 时，tool 填实际工具名称；归类为 chat 时，tool 填 null，args 填 {}。
5. 只有在收到【工具结果】之后才能给 answer；用户刚说完话、还没调过任何工具时，只能给 command 或 chat。
6. 一句话里交代了不止一件事时（出现"两个""都""前几条""顺便""还有"等），办完一件要接着办下一件，继续给下一个 command，不要给 answer；同一件事要办几次就给几次 command（比如"前两条都办完了"要连着给两次 complete_todo）；全部办完才给 answer。
7. text 要汇总成人话，不是照抄工具回执


# 多轮对话
你可能会收到之前的对话记录（user / assistant 交替出现），assistant 那几轮是系统执行后留下的回执，
可以用它了解"刚才聊了什么"。
如果用户这一句省略了内容，而上一轮刚提到某件事，就把那件事补进参数里；历史里也找不到才判 chat。

# 参数怎么填
- 需要 text 的工具：去掉句首的动作词，把剩下的具体内容放进 args.text。
- 不需要参数的工具：args 填 {}。
- 删除类工具二选一：用户给了明确序号 → {"lineno": 3}；用户描述的是内容特征 → {"keyword": "开会"}。

# 输出格式
只输出一个 json 对象，不要输出解释、不要加代码块标记：
{"type": "command" 或 "chat", "tool": 实际工具名称或 null, "args": 按该工具的参数要求填，不需要参数的工具填 {}}
answer 时改为：{"type": "answer", "tool": null, "args": {}, "text": "汇总给用户的一句话"}


# 例子
用户输入：记一下周六上午去拍证件照
输出：{"type": "command", "tool": "add_todo", "args": {"text": "周六上午去拍证件照"}}

用户输入：帮我记一下小区的门禁密码是8899
输出：{"type": "command", "tool": "add_memo", "args": {"text": "小区的门禁密码是8899"}}

用户输入：别忘记下午要去取快递
输出：{"type": "command", "tool": "add_todo", "args": {"text": "下午要去取快递"}}

用户输入：今天真是累坏了
输出：{"type": "chat", "tool": null, "args": {}}

用户输入：我这两天记性不太行
输出：{"type": "chat", "tool": null, "args": {}}

用户输入：帮我翻翻我的备忘
输出：{"type": "command", "tool": "list_memos", "args": {}}

用户输入：清单上还有几件事没办完
输出：{"type": "command", "tool": "list_todos", "args": {}}

用户输入：把备忘的第4条删了
输出：{"type": "command", "tool": "delete_memo", "args": {"lineno": 4}}

用户输入：删掉备忘里密码那条
输出：{"type": "command", "tool": "delete_memo", "args": {"keyword": "密码"}}
【工具结果】共2条记录，请确认是哪一条：
第1条，房门密码1234
第2条，手机密码2344
输出：{"type": "answer", "tool": null, "args": {}, "text": "带“密码”的有两条：第1条是房门密码1234，第2条是手机密码2344，你要删哪一条？"}

用户输入：把待办里开会那条去掉
输出：{"type": "command", "tool": "delete_todo", "args": {"keyword": "开会"}}

用户输入：第3条待办我搞定了
输出：{"type": "command", "tool": "complete_todo", "args": {"lineno": 3}}

上一轮用户说了：我今天吃了鱼香肉丝
用户输入：帮我记下来吧
输出：{"type": "command", "tool": "add_memo", "args": {"text": "今天吃了鱼香肉丝"}}

用户输入：帮我记一下，阳台的花该浇水了
输出：{"type": "command", "tool": "add_memo", "args": {"text": "阳台的花该浇水了"}}
【工具结果】已加入备忘录！
阳台的花该浇水了
输出：{"type": "answer", "tool": null, "args": {}, "text": "已经帮你记下啦：阳台的花该浇水了。"}

用户输入：记一下后天要去物业交水电费，顺便把手头的事都列一下
输出：{"type": "command", "tool": "add_todo", "args": {"text": "后天要去物业交水电费"}}
【工具结果】已加入待办事项！
后天要去物业交水电费
输出：{"type": "command", "tool": "list_todos", "args": {}}
【工具结果】共2条待办事项:
第1条，给鱼缸换水
第2条，后天要去物业交水电费
输出：{"type": "answer", "tool": null, "args": {}, "text": "已经记下后天去物业交水电费了。你手头还有两件事：一件是给鱼缸换水，另一件是后天缴费。"}

'''

TYPE = ['command', 'chat', 'answer']


def _build_prompt() -> str:
    tool_lines = []
    CURRENT_DATE = get_current_time().reply.split('，')[0]
    for t in TOOLS_LIST:
        required = [x for x in t['args'] if x not in (t.get('options') or [])]
        optional = list(t.get('options') or [])
        if required and optional:
            params = '需要参数：' + '、'.join(required) + '；可选参数：' + '、'.join(optional)
        elif required:
            params = '需要参数：' + '、'.join(required)
        elif optional:
            params = '可选参数：' + '、'.join(optional)
        else:
            params = '不需要参数'
        tool_lines.append(f"{t['name']}：{t['desc']}（{params}）")
    return PROMPT.replace('{tools_list}', '\n'.join(tool_lines)).replace('{CURRENT_DATE}', CURRENT_DATE)


def _build_messages(text: str, history: list | None = None) -> list:
    return (
            [{'role': 'system', 'content': _build_prompt()}]
            + (history or [])
            + [{'role': 'user', 'content': text}]
    )


def _parse_output(raw: str) -> RouterDecision:
    content, _ = json.JSONDecoder().raw_decode(raw.strip())
    if content['type'] not in TYPE:
        raise ValueError('模型返回了错误的类型')
    if content['type'] == 'command':
        content['args'] = content['args'] or {}
        if content['tool'] not in [tool['name'] for tool in TOOLS_LIST]:
            raise ValueError('模型返回了错误的调用工具')
        tool_args = [tool['args'] for tool in TOOLS_LIST if tool['name'] == content['tool']][0]
        option_args = [tool['options'] if tool.get('options') else [] for tool in TOOLS_LIST if tool['name'] == content['tool']][0]
        required_args = [item for item in tool_args if item not in option_args]
        for item in content['args']:
            if item not in tool_args:
                raise ValueError('模型生成了多余的参数')
        if required_args:
            if not any(content['args'].get(item) for item in required_args):
                raise ValueError('模型没有传入必要的参数')
    elif content['type'] == 'chat':
        if content['tool'] is not None:
            raise ValueError('模型返回了错误的调用工具')
    elif content['type'] == 'answer':
        if content.get('tool') is not None or len(content.get('args') or {}) > 0:
            raise ValueError('模型返回了错误的工具执行结果总结')
        if content.get('text') is None:
            raise ValueError("模型未返回工具执行结果总结")
    return RouterDecision(type=content['type'], tool=content.get('tool'), args=content.get('args') or {},
                          text=content.get('text', None))


def route(text: str, history: list | None = None) -> RouterDecision:
    try:
        content = ask(messages=_build_messages(text, history), response_format={"type": "json_object"}, temperature=0)
        return _parse_output(content)
    except ModelUnavailableError:
        raise
    except Exception as e:
        print(f"[警告] 意图判断失败，已降级为闲聊：{e}", file=sys.stderr)
        return RouterDecision(type="chat", tool=None, args={})




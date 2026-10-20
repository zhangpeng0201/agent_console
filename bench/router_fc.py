'''
把结构化输出方式从 json_mode 换成 function_calling
'''
import sys,os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import llm_client          # 提供 DEEPSEEK_CLIENT 和 PROVIDERS
from tools import get_current_time
from schemas import RouterDecision
from tool_schema import TOOLS_SCHEMA

CURRENT_DATE = get_current_time().reply.split('，')[0]

# 系统提示词
SYSTEM_PROMPT = '''
# 角色
你的名字是一一，你是一个意图识别助手。用户说一句话，你要判断它属于哪一类，并输出对应的 json。
- "command"（指令）：用户在指使你替他做一件具体的事（记录、提醒、查询、删除）。
- "chat"（闲聊）：用户在表达感受、提问或闲谈，不需要你做事。
- "answer（回复）"：你已经调用过工具、并且拿到了工具的执行结果，现在把结果汇总成一句人话回复用户。

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
    print(_call('记一下我的手机密码是123，然后提醒我明天去上班'))

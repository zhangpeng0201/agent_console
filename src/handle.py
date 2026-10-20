from llm_router import route
from registry import TOOLS_LIST
from chat import chat
import json
import sys
from llm_client import ModelUnavailableError
from tools import X, U, clean_session_id
from schemas import ApiResult
from time import perf_counter as pc

STORE = {}
HISTORY_LIMIT = 20

# 上一轮列出的候选列表，用户正对着它回答「第N条」
# 形状：{'tool': 'delete_todo', 'linenos': [1, 6]}   —— 里面存的是真实行号
MAX_EPOCH = 5


def run_agent(text: str, session_id: str = 'default', user_id: str = '') -> ApiResult:
    session_id = clean_session_id(session_id)
    U.set(user_id)
    X.set(session_id)
    if session_id not in STORE:
        STORE[session_id] = {
            'history': [],
            'chat_history': [],
            'pending': None
        }
    try:
        epoch = 1
        messages = []
        steps = []
        start = pc()
        decision = route(text, STORE[session_id]['history'])
        first_decision = decision
        messages.append({'role': 'user', 'content': text})
        while epoch <= MAX_EPOCH:
            print(f'[路由] 第{epoch}轮 type={decision.type} tool={decision.tool} args={decision.args}',
                  file=sys.stderr)

            # 本轮消息列表
            tool_result = None  # 工具调用结果
            # 上一轮刚列过候选 → 用户说的「第N条」指候选里第 N 项，换算成真实行号
            if (
                    STORE[session_id]['pending'] is not None
                    and decision.type == 'command'
                    and decision.tool == STORE[session_id]['pending']['tool']
                    and decision.args.get('lineno') is not None
            ):
                n = decision.args['lineno']
                if 1 <= n <= len(STORE[session_id]['pending']['linenos']):
                    decision.args['lineno'] = STORE[session_id]['pending']['linenos'][n - 1]
                else:
                    decision.args['lineno'] = 0  # 候选里没这一项 → 让工具回“没有该记录”，不误删
            if decision.type == 'chat':
                result = chat(text, STORE[session_id]['chat_history'])
                end = pc()
                messages.append({'role': 'assistant', 'content': result})
                STORE[session_id]['pending'] = None
                steps.append({
                    'epoch': epoch,
                    'type': decision.type,
                    'tool': decision.tool,
                    'args': decision.args,
                    'result': result,
                    'ms': round((end - start) * 1000)})
                break
            if decision.type == 'answer':
                result = decision.text
                end = pc()
                steps.append({
                    'epoch': epoch,
                    'type': decision.type,
                    'tool': decision.tool,
                    'args': decision.args,
                    'result': result,
                    'ms': round((end - start) * 1000)})
                break
            func = next(
                (item['func'] for item in TOOLS_LIST if item['name'] == decision.tool),
                None,
            )
            if func is None:
                result = '未找到调用的工具'  # 赋值，不是 return
            else:
                tool_result = func(**decision.args)
                result = tool_result.reply
            # 候选只在「这一轮又列出一份候选」时驻留；其余情况一律作废
            if tool_result is not None and tool_result.candidate:
                STORE[session_id]['pending'] = {'tool': decision.tool, 'linenos': tool_result.candidate}
            else:
                STORE[session_id]['pending'] = None
            messages.append({'role': 'assistant', 'content': json.dumps(
                {"type": decision.type, "tool": decision.tool, "args": decision.args},
                ensure_ascii=False) + f'\n（已回复用户：{result}）'})
            reply = '【工具结果】：' + result
            end = pc()
            steps.append({
                'epoch': epoch,
                'type': decision.type,
                'tool': decision.tool,
                'args': decision.args,
                'result': result,
                'ms': round((end - start) * 1000)
            })
            start = pc()
            decision = route(reply, STORE[session_id]['history'] + messages)
            epoch += 1

        STORE[session_id]['history'].append({'role': 'user', 'content': text})
        STORE[session_id]['history'].append({'role': 'assistant', 'content': json.dumps(
            {"type": first_decision.type, "tool": first_decision.tool, "args": first_decision.args},
            ensure_ascii=False) + f'\n（已回复用户：{result}）'})
        STORE[session_id]['chat_history'].append({'role': 'user', 'content': text})
        STORE[session_id]['chat_history'].append({'role': 'assistant', 'content': result})
        del STORE[session_id]['history'][:-HISTORY_LIMIT]
        del STORE[session_id]['chat_history'][:-HISTORY_LIMIT]
        return ApiResult(
            ok=True,
            reply=result,
            steps=steps
        )
    except ModelUnavailableError:
        return ApiResult(
            ok=False,
            reply='当前模型不可用，请稍后再试',
            steps=[],
            error='model_unavailable'
        )

def handle(text: str, session_id: str = 'default') -> str:
    reply = run_agent(text, session_id).reply
    return reply
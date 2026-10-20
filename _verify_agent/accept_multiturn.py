'''
多轮测试集 - 零 API 验收

两件事：
A. 数据文件 multiturn_set.json 的格式自检（字段齐不齐、工具名/参数名合不合法）
B. run_multiturn.py 的 build_history() 拼出来的历史，与 handle.py 真实往 HISTORY 里
   塞的历史逐字节一致（这是整个多轮数据集可信的前提：历史形状不对，测出来的就不算数）

全程不碰网络：把 llm_router.ask 换成一个假函数，喂预设的 JSON。

跑法：cd src 不用；直接在项目根跑
    python _verify_agent/accept_multiturn.py
'''

import sys, os, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'bench'))

import llm_router
import registry
import handle as handle_mod
import run_multiturn

DATA_PATH = os.path.join(ROOT, 'bench', 'multiturn_set.json')
TOOL_NAMES = [tool['name'] for tool in registry.TOOLS_LIST]
TOOL_ARGS = {tool['name']: tool['args'] for tool in registry.TOOLS_LIST}

PASS = 0
FAIL = 0


def check(ok: bool, label: str, detail: str = ''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  [OK] {label}')
    else:
        FAIL += 1
        print(f'  [X ] {label}   {detail}')


def load_dialogs():
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


# ── A 组：数据文件格式 ─────────────────────────────────────────
def check_data():
    print('A 组：数据文件格式')
    dialogs = load_dialogs()
    check(len(dialogs) >= 10, f'对话条数 {len(dialogs)} >= 10')
    turn_total = 0
    args_turn_total = 0
    for dialog in dialogs:
        name = dialog.get('name', '<无名字>')
        check('name' in dialog and dialog['name'], f'{name} 有 name')
        check('turns' in dialog and len(dialog['turns']) >= 2, f'{name} 至少 2 轮')
        for index, turn in enumerate(dialog['turns']):
            turn_total += 1
            check('user' in turn and turn['user'], f'{name} 第{index + 1}轮 有 user')
            # 非末轮 = 已经发生过的轮次，必须带“真实回执”两件套
            is_past = index < len(dialog['turns']) - 1
            if is_past:
                decision = turn.get('assistant_decision')
                check(isinstance(decision, dict) and set(decision) == {'type', 'tool', 'args'},
                      f'{name} 第{index + 1}轮 assistant_decision 三键齐全')
                check(isinstance(turn.get('assistant_reply'), str) and turn['assistant_reply'],
                      f'{name} 第{index + 1}轮 有 assistant_reply')
            # 标准答案：expect 优先，没有就用 assistant_decision（首轮的情况）
            expect = turn.get('expect') or turn.get('assistant_decision')
            check(isinstance(expect, dict) and 'type' in expect and 'tool' in expect,
                  f'{name} 第{index + 1}轮 有标准答案 type/tool')
            if expect and expect.get('type') == 'command':
                check(expect['tool'] in TOOL_NAMES,
                      f'{name} 第{index + 1}轮 工具名合法', f'{expect.get("tool")}')
                for arg_key in (expect.get('args') or {}):
                    check(arg_key in TOOL_ARGS.get(expect['tool'], []),
                          f'{name} 第{index + 1}轮 参数名 {arg_key} 属于 {expect["tool"]}')
            if expect and expect.get('args'):
                args_turn_total += 1
    print(f'  —— 共 {len(dialogs)} 条对话 / {turn_total} 个轮次 / 其中 {args_turn_total} 轮带参数标准答案')
    return dialogs


# ── B 组：历史拼接与 handle.py 一致 ────────────────────────────
def _run_two_rounds():
    '''真跑 handle() 两轮（假 client），把 HISTORY 抓回来。'''
    plans = [
        [json.dumps({'type': 'command', 'tool': 'list_todos', 'args': {}}, ensure_ascii=False),
         json.dumps({'type': 'answer', 'tool': None, 'args': {}, 'text': '你有这些待办。'}, ensure_ascii=False)],
        [json.dumps({'type': 'command', 'tool': 'list_memos', 'args': {}}, ensure_ascii=False),
         json.dumps({'type': 'answer', 'tool': None, 'args': {}, 'text': '你记了这些。'}, ensure_ascii=False)],
    ]
    state = {'round': 0, 'pos': 0}

    def fake_ask(messages=None, **kwargs):
        plan = plans[state['round']]
        raw = plan[state['pos']]
        state['pos'] += 1
        return raw

    original_ask = llm_router.ask
    original_history = handle_mod.HISTORY[:]
    try:
        llm_router.ask = fake_ask
        handle_mod.HISTORY.clear()
        handle_mod.PENDING = None
        handle_mod.handle('我有哪些待办')
        state['round'] = 1
        state['pos'] = 0
        handle_mod.handle('我记了些什么')
        snapshot = list(handle_mod.HISTORY)
    finally:
        llm_router.ask = original_ask
        handle_mod.HISTORY[:] = original_history
        handle_mod.PENDING = None
    return snapshot


def check_history_equals():
    snapshot = _run_two_rounds()
    check(len(snapshot) == 4, f'handle 两轮后 HISTORY 长度 = 4', f'实际 {len(snapshot)}')
    if len(snapshot) != 4:
        return

    # 反解出 handle 真实写进 HISTORY 的内容
    def parse(content: str):
        first, _, rest = content.partition('\n（已回复用户：')
        decision = json.loads(first)
        reply = rest[:-1] if rest.endswith('）') else rest
        return decision, reply

    d1, r1 = parse(snapshot[1]['content'])
    d2, r2 = parse(snapshot[3]['content'])

    # 用 run_multiturn.build_history 拼同样两轮
    mine = run_multiturn.build_history([
        {'user': '我有哪些待办', 'assistant_decision': d1, 'assistant_reply': r1},
        {'user': '我记了些什么', 'assistant_decision': d2, 'assistant_reply': r2},
    ])

    check(mine[0] == snapshot[0], 'B1 第1轮 user 格一致', f'{mine[0]!r} != {snapshot[0]!r}')
    check(mine[1] == snapshot[1], 'B2 第1轮 assistant 格一致')
    check(mine[2] == snapshot[2], 'B3 第2轮 user 格一致')
    check(mine[3] == snapshot[3], 'B4 第2轮 assistant 格一致（关键：json 序列化 + 换行 + 括号）')

    # 再单独验一次“历史长度 = 1 + 已走轮数”的偶数对齐
    check(len(mine) % 2 == 0, 'B5 拼出来的历史长度是偶数（user/assistant 成对）')
    check(all(item['role'] in ('user', 'assistant') for item in mine), 'B6 每格的 role 都是 user/assistant')

    print('  —— 真实 assistant 格样例：')
    print('     ' + repr(snapshot[1]['content'])[:120])


def main():
    print('=' * 60)
    print('多轮测试集 零 API 验收')
    print('=' * 60)
    check_data()
    print()
    check_history_equals()
    print()
    print('=' * 60)
    print(f'结果：{PASS}/{PASS + FAIL} 通过' + ('' if FAIL == 0 else f'，{FAIL} 项失败'))
    print('=' * 60)
    return 0 if FAIL == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

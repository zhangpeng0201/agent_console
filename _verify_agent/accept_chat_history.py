'''
CHAT_HISTORY 形态 - 零 API 验收

背景：handle.py 把「上一轮的结果」写进 CHAT_HISTORY 给 chat 看。
原来写的是 answer 轮的润色文本（已经帮你记下啦：X）→ chat 会照抄，
变成「判 chat（没办事）却说已经帮你记下了」的虚假承诺。
现在改成写一句**系统口吻、不含内容**的标记。

盯五件事：
A 非闲聊轮 → CHAT_HISTORY 的 assistant 格 == 系统标记（不是工具回执，也不是 answer 润色文本）
B 闲聊轮   → CHAT_HISTORY 的 assistant 格 == chat 的回复（这条能力不能被改坏）
C 标记形状自检：不含用户说的话、不含「已加入/已记录」、不含第一人称承诺
D route 用的那份 HISTORY 不受影响（仍是 decision JSON + 「（已回复用户：X）」）
E CHAT_HISTORY 仍是 user/assistant 交替，长度为偶数

手法：把 handle.route / handle.chat 换成脚本化的假函数，
     用 list_todos（只读，不写文件）跑完整一轮 —— 不调任何 API、不改任何文件。

跑法（项目根）：
    python _verify_agent/accept_chat_history.py
'''

import sys, os, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))

import handle
from schemas import RouterDecision

# 约定的系统标记（改这里即可，验收按这个常量判）
MARKER = '（上一句由系统处理）'

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


def reset():
    handle.HISTORY.clear()
    handle.CHAT_HISTORY.clear()
    handle.PENDING = None


def run_turn(scripted, text, chat_reply='（假闲聊回复）'):
    """用脚本化的 route / chat 跑一轮 handle，返回 (回复, route 收到过的 history 快照)"""
    seq = list(scripted)
    seen = {'histories': []}

    def fake_route(t, history=None):
        seen['histories'].append([dict(x) for x in (history or [])])
        return seq.pop(0)

    def fake_chat(t, history=None):
        return chat_reply

    old_route, old_chat = handle.route, handle.chat
    handle.route, handle.chat = fake_route, fake_chat
    try:
        result = handle.handle(text)
    finally:
        handle.route, handle.chat = old_route, old_chat
    return result, seen


def main():
    print('=' * 64)
    print(f'约定标记：{MARKER!r}')
    print('=' * 64)

    # ---------- A 组：非闲聊轮 ----------
    print('A 组：非闲聊轮 → assistant 格 == 系统标记')
    reset()
    text = '我有哪些待办'
    run_turn([
        RouterDecision(type='command', tool='list_todos', args={}),
        RouterDecision(type='answer', tool=None, args={}, text='你有这些待办。'),
    ], text)
    content = handle.CHAT_HISTORY[-1]['content']
    check(handle.CHAT_HISTORY[-2]['content'] == text, 'user 格 == 用户原话', repr(handle.CHAT_HISTORY[-2]['content']))
    check(handle.CHAT_HISTORY[-1]['role'] == 'assistant', 'assistant 格 role 正确')
    check(content == MARKER, 'assistant 格 == 系统标记', f'实际 {content!r}')
    check('已加入' not in content and '共' not in content,
          '没有把工具回执（已加入…！/共N条…）塞进去', repr(content))
    check(content != '你有这些待办。', '没有把 answer 轮润色文本塞进去')

    # ---------- B 组：闲聊轮 ----------
    print('B 组：闲聊轮 → assistant 格 == chat 的回复（不受影响）')
    reset()
    reply = '哎呀，那可真够呛～'
    run_turn([RouterDecision(type='chat', tool=None, args={})], '今天真是累坏了', chat_reply=reply)
    content = handle.CHAT_HISTORY[-1]['content']
    check(content == reply, 'assistant 格 == chat 回复', f'实际 {content!r}')

    # ---------- C 组：标记形状自检 ----------
    print('C 组：标记形状自检（防以后有人把回执/承诺塞回来）')
    check('已加入' not in MARKER, '不含「已加入」')
    check('记录了' not in MARKER and '已记录' not in MARKER, '不含「已记录」')
    check(not any(m in MARKER for m in ['帮你记', '已经帮', '帮你存']), '不含第一人称承诺')
    check('待办' not in MARKER and '备忘' not in MARKER, '不绑定某类工具（查询/天气/搜索也适用）')

    # ---------- D 组：HISTORY（给 route 的那份）不受影响 ----------
    print('D 组：route 用的 HISTORY 不受影响')
    reset()
    text = '我有哪些待办'
    run_turn([
        RouterDecision(type='command', tool='list_todos', args={}),
        RouterDecision(type='answer', tool=None, args={}, text='你有这些待办。'),
    ], text)
    hist_assistant = handle.HISTORY[-1]['content']
    check('"type": "command"' in hist_assistant, 'HISTORY 仍存 decision JSON', repr(hist_assistant[:60]))
    check('（已回复用户：' in hist_assistant, 'HISTORY 仍带「（已回复用户：…）」')
    check(handle.HISTORY[-2]['content'] == text, 'HISTORY 的 user 格 == 用户原话')

    # ---------- E 组：CHAT_HISTORY 结构 ----------
    print('E 组：CHAT_HISTORY 结构')
    roles = [x['role'] for x in handle.CHAT_HISTORY]
    check(len(roles) % 2 == 0, '长度为偶数', f'实际 {len(roles)}')
    check(roles == ['user', 'assistant'], '交替 user/assistant', repr(roles))

    print()
    print('=' * 64)
    total = PASS + FAIL
    print(f'结果：{PASS}/{total} 通过' + ('' if FAIL == 0 else f'，{FAIL} 项失败'))
    print('=' * 64)
    if FAIL:
        print('提示：若 A 组第一项不过，说明 handle.py 还没改 / 标记与常量不一致；')
        print(f'      此时先把 handle.py 里写的那句贴出来，我核对 {MARKER!r} 要不要对齐。')
    return 0 if FAIL == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

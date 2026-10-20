'''
零 API 验收：handle 的会话隔离（STORE）

做法：把 handle 模块里的 route / chat / TOOLS_LIST 换成假的（注入假决策 + 假工具），
      既不调 LLM、也不读写任何数据文件。

用法：
    python _verify_agent/accept_session.py            # 零 API（默认）
    python _verify_agent/accept_session.py --api      # 额外跑 H 组：真链路跨会话不串话
'''
import sys
import re
import io
import inspect
import contextlib

sys.path.insert(0, r'D:/Project/voice_assistant/src')
import handle as H

PASS, FAIL = 0, 0
NOTES = []


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  ✅ {name}' + (f'  — {detail}' if detail else ''))
    else:
        FAIL += 1
        print(f'  ❌ {name}' + (f'  — {detail}' if detail else ''))
    return ok


def note(text):
    NOTES.append(text)


# ---------------- 假的决策 / 工具 / 模型 ----------------
class D:
    def __init__(self, type_, tool=None, args=None, text=None):
        self.type = type_
        self.tool = tool
        self.args = args if args is not None else {}
        self.text = text


class TR:
    def __init__(self, reply, candidate=None, ok=True, id=None):
        self.ok = ok
        self.reply = reply
        self.id = id
        self.candidate = candidate


class Script:
    '''按脚本依次吐决策，并记录每次被调用的 (text, history 长度)'''

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.log = []

    def __call__(self, text, history=None):
        self.log.append((text, len(history or [])))
        return self.decisions.pop(0)


class FakeChat:
    def __init__(self):
        self.seen = []

    def __call__(self, text, history=None):
        self.seen.append([dict(x) for x in (history or [])])
        return f'（闲聊）{text}'


DELETED = []
CALLS = []


def fake_list_todos(**kw):
    # 真实 tools.py 的 _list 不设 candidate（全项目只有"关键字删除命中多条"才设）
    return TR('共2条待办事项:\n第1条，给鱼缸换水\n第2条，交水电费', candidate=None)


def fake_delete_todo(**kw):
    DELETED.append(dict(kw))
    return TR(f'已删除第{kw.get("lineno")}条', candidate=None)


def fake_delete_hits(**kw):
    '''模拟"关键字删除命中多条 → 反问候选"：工具这一轮返回了 candidate'''
    DELETED.append(dict(kw))
    return TR('共2条记录，请确认是哪一条：\n第1条，周会纪要\n第2条，评审会',
              candidate=[2, 5], ok=False)


def fake_delete_candidate(**kw):
    '''模拟真实 tools.py 的"关键字删除命中多条 → 反问候选"（candidate=真实行号）'''
    CALLS.append(dict(kw))
    if 'keyword' in kw:
        return TR('共2条记录，请确认是哪一条：\n第1条，周会纪要\n第2条，评审会',
                  candidate=[2, 5], ok=False)
    return TR('已删除该条备忘录', candidate=None)


FAKE_TOOLS = [
    {'name': 'list_todos', 'func': fake_list_todos},
    {'name': 'delete_todo', 'func': fake_delete_todo},
]

ORIG = {'route': H.route, 'chat': H.chat, 'TOOLS_LIST': H.TOOLS_LIST, 'STORE': H.STORE}


def patch(decisions, keep_store=False):
    if not keep_store:
        H.STORE = {}
    H.route = Script(decisions)
    H.chat = FakeChat()
    H.TOOLS_LIST = FAKE_TOOLS
    DELETED.clear()
    return H.route, H.chat


def restore():
    H.route, H.chat, H.TOOLS_LIST = ORIG['route'], ORIG['chat'], ORIG['TOOLS_LIST']


def quiet(fn, *a, **kw):
    with contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


# ================= A 组：三个名字是否收进 STORE =================
def group_a():
    print('A 组：三个名字收进 STORE（静态）')
    check('A1 STORE 是模块级字典', isinstance(ORIG['STORE'], dict))
    check('A2 模块里不再有 HISTORY 变量', not hasattr(H, 'HISTORY'))
    check('A3 模块里不再有 CHAT_HISTORY 变量', not hasattr(H, 'CHAT_HISTORY'))
    src = inspect.getsource(H)
    bare = []
    for i, line in enumerate(src.splitlines(), 1):
        code = line.split('#')[0]
        if re.search(r'(?<![\w.\["\'])PENDING\b', code):
            bare.append((i, line.strip()))
    ok = check('A4 代码里没有裸的 PENDING 引用', not bare,
               '' if not bare else f'仍有 {bare}')
    if not ok:
        note('A4：模块级 `PENDING = None` 已是死变量（函数体里没人用它），'
             '留着容易让人以为它还是全局状态 → 建议删掉')
    sig = inspect.signature(H.handle)
    params = list(sig.parameters.items())
    ok2 = (len(params) == 2 and params[1][0] == 'session_id' and params[1][1].default == 'default')
    check('A5 签名 handle(text, session_id="default")', ok2,
          f'实际 {sig}' if not ok2 else '')
    hl = re.search(r'HISTORY_LIMIT\s*=\s*(\d+)', src)
    check('A6 裁剪上限仍是模块常量 20', hl is not None and hl.group(1) == '20',
          f'HISTORY_LIMIT={hl.group(1) if hl else "缺失"}')


# ================= B 组：懒创建 + 向后兼容 =================
def group_b():
    print('B 组：懒创建 + 单参调用向后兼容')
    patch([D('chat')])
    r = quiet(H.handle, '你好')
    check('B1 不传 id 也能跑（向后兼容）', r == '（闲聊）你好', f'返回 {r!r}')
    sess = H.STORE.get('default')
    check('B2 自动建出 default 这一格', isinstance(sess, dict))
    keys = set(sess or {})
    check('B3 三件套齐全', keys == {'history', 'chat_history', 'pending'}, f'实际 {sorted(keys)}')
    check('B4 新建会话 history 收了 2 条（user+assistant）',
          len(sess['history']) == 2, f'实际 {len(sess["history"])}')

    patch([D('chat')], keep_store=True)
    quiet(H.handle, '你好', 'u2')
    check('B5 两个会话各占一格', len(H.STORE) == 2, f'store 里 {sorted(H.STORE)}')
    check('B6 两格是不同对象（不是同一个 dict）',
          H.STORE['default'] is not H.STORE['u2'])
    restore()


def seed(spec):
    '''手工铺好每个会话的 pending，用来直接验隔离语义（不受 answer 清空影响）'''
    H.STORE = {sid: {'history': [], 'chat_history': [], 'pending': p}
               for sid, p in spec.items()}


# ================= C 组：候选隔离（核心） =================
def group_c():
    print('C 组：候选（pending）按会话隔离')
    seed({'u1': {'tool': 'delete_todo', 'linenos': [1, 6]},
          'u2': None,
          'u3': {'tool': 'list_todos', 'linenos': [1, 6]}})

    patch([D('command', 'delete_todo', {'lineno': 2}), D('answer', None, {}, '已删除。')],
          keep_store=True)
    quiet(H.handle, '把第2条删了', 'u2')
    check('C1 u2 没有候选 → 不换算，lineno 保持 2', DELETED == [{'lineno': 2}],
          f'假工具收到 {DELETED}')
    check('C2 u2 的动作没动到 u1 的候选',
          H.STORE['u1']['pending'] == {'tool': 'delete_todo', 'linenos': [1, 6]},
          f"u1 pending={H.STORE['u1']['pending']}")

    patch([D('command', 'delete_todo', {'lineno': 2}), D('answer', None, {}, '已删除。')],
          keep_store=True)
    quiet(H.handle, '把第2条删了', 'u1')
    check('C3 u1 有候选 → 候选第2项换算成真实行号 6', DELETED == [{'lineno': 6}],
          f'假工具收到 {DELETED}')
    check('C4 u1 用完候选 → pending 作废', H.STORE['u1']['pending'] is None)

    patch([D('command', 'delete_todo', {'lineno': 1}), D('answer', None, {}, '已删除。')],
          keep_store=True)
    quiet(H.handle, '把第1条删了', 'u3')
    check('C5 工具名不一致（候选是 list_todos，来的是 delete_todo）→ 不换算',
          DELETED == [{'lineno': 1}], f'假工具收到 {DELETED}')
    restore()


# ================= D 组：裁剪按会话独立 =================
def group_d():
    print('D 组：20 条裁剪按会话独立')
    H.STORE = {}
    patch([D('chat')] * 30)
    for i in range(30):
        quiet(H.handle, f'第{i}句', 'u1')
    patch([D('chat')], keep_store=True)
    quiet(H.handle, '只我一句', 'u2')
    check('D1 u1 塞 30 轮 → 裁到 20 条', len(H.STORE['u1']['history']) == 20,
          f"实际 {len(H.STORE['u1']['history'])}")
    check('D2 u2 不受影响，仍是自己那 2 条', len(H.STORE['u2']['history']) == 2,
          f"实际 {len(H.STORE['u2']['history'])}")
    restore()


# ================= E 组：pending 三条离场路径（会话内） =================
def group_e():
    print('E 组：pending 三条离场路径')
    H.STORE = {}
    patch([D('command', 'list_todos', {}), D('answer', None, {}, '列完了。')])
    quiet(H.handle, '列一下', 'e1')
    a = H.STORE['e1']['pending']
    check('E1 工具轮没返回候选（列清单）→ pending 为 None', a is None, f'实际 {a}')

    seed({'e2': {'tool': 'delete_todo', 'linenos': [1, 6]}})
    patch([D('chat')], keep_store=True)
    quiet(H.handle, '随便聊聊', 'e2')
    check('E2 chat 轮 → pending 清空', H.STORE['e2']['pending'] is None)

    seed({'e3': {'tool': 'delete_todo', 'linenos': [1, 6]}})
    patch([D('answer', None, {}, '直接回答。')], keep_store=True)
    quiet(H.handle, '再说一遍', 'e3')
    check('E3 answer 轮 → 不动候选（候选是同一次调用里工具刚建的，不能被它清掉）',
          H.STORE['e3']['pending'] == {'tool': 'delete_todo', 'linenos': [1, 6]},
          f"实际 {H.STORE['e3']['pending']}")

    # 工具这一轮真的列出了候选（命中多条 → 反问）→ 必须驻留，供下一轮「第N条」
    patch([D('command', 'delete_memo', {'keyword': '会'}),
           D('answer', None, {}, '你要删哪一条？')])
    H.TOOLS_LIST = [{'name': 'delete_memo', 'func': fake_delete_hits}]
    quiet(H.handle, '把带会的那条备忘删了', 'e4')
    check('E4 工具轮返回候选 → pending 驻留成 {tool, linenos}',
          H.STORE['e4']['pending'] == {'tool': 'delete_memo', 'linenos': [2, 5]},
          f"实际 {H.STORE['e4']['pending']}")

    patch([D('command', 'list_todos', {}), D('answer', None, {}, '列完了。')],
          keep_store=True)
    quiet(H.handle, '列一下待办', 'e4')
    check('E5 候选驻留后，下一轮工具轮又没候选 → 上一轮候选被冲掉（不残留）',
          H.STORE['e4']['pending'] is None, f"实际 {H.STORE['e4']['pending']}")
    restore()


# ================= F 组：两份历史的形状没变 =================
def group_f():
    print('F 组：两份历史的形状不变')
    H.STORE = {}
    patch([D('command', 'list_todos', {}), D('answer', None, {}, '你有这些待办。')])
    quiet(H.handle, '我有哪些待办', 'f1')
    hist = H.STORE['f1']['history']
    chat_hist = H.STORE['f1']['chat_history']
    check('F1 history 仍是 user/assistant 交替',
          [x['role'] for x in hist] == ['user', 'assistant'],
          f"实际 {[x['role'] for x in hist]}")
    check('F2 history 的 assistant 格 = JSON + 「（已回复用户：…）」',
          '"type"' in hist[1]['content'] and '（已回复用户：' in hist[1]['content'])
    check('F3 chat_history 的 assistant 格 = 回复原文',
          chat_hist[1]['content'] == '你有这些待办。', f"实际 {chat_hist[1]['content']!r}")
    check('F4 history 里的 user 格与 chat_history 的 user 格字字相同',
          hist[0]['content'] == chat_hist[0]['content'] == '我有哪些待办')
    restore()


# ================= G 组：STORE 是模块级（抓"建在函数里"的错） =================
def group_g():
    print('G 组：STORE 必须是模块级（不能每次调用新建）')
    H.STORE = {}
    patch([D('chat'), D('chat')])
    quiet(H.handle, '第一句')
    quiet(H.handle, '第二句')
    check('G1 两次调用仍只有一格（默认会话）', len(H.STORE) == 1, f'store 里 {sorted(H.STORE)}')
    check('G2 历史累加到 4 条（说明上一轮没丢）',
          len(H.STORE['default']['history']) == 4,
          f"实际 {len(H.STORE['default']['history'])}")
    restore()


def safe_tools():
    '''真链路上兜住"所有"工具名：即使路由判成 command，也只是个假函数，绝不写你的数据文件'''
    from registry import TOOLS_LIST as REAL
    return [{'name': t['name'], 'func': (lambda **kw: TR('（假工具，未真正执行）'))}
            for t in REAL]


# ================= H 组：真链路端到端（--api） =================
def group_h():
    print('H 组（真路由 + 真闲聊，工具全部换成假的以防写文件）：跨会话不串话')
    H.STORE = {}
    H.route = ORIG['route']
    H.chat = ORIG['chat']
    H.TOOLS_LIST = safe_tools()
    try:
        quiet(H.handle, '我叫小明', 'u1')
        u1 = quiet(H.handle, '我叫什么名字', 'u1')
        print(f'    u1 两轮后答：{u1.strip()!r}')
        check('H1 u1 自己那格收了 4 条（两轮各 2 条）',
              len(H.STORE['u1']['chat_history']) == 4,
              f"实际 {len(H.STORE['u1']['chat_history'])}")
        u2 = quiet(H.handle, '我叫什么名字', 'u2')
        print(f'    u2 首轮答：{u2.strip()!r}')
        check('H2 u2 自己那格只有 2 条（u1 的两轮没串进来）',
              len(H.STORE['u2']['chat_history']) == 2,
              f"实际 {len(H.STORE['u2']['chat_history'])}")
        check('H3 两格的历史内容确实不同',
              H.STORE['u1']['chat_history'] != H.STORE['u2']['chat_history'])
        check('H4 u2 的回复里不出现 u1 的名字「小明」', '小明' not in u2, f'u2 答：{u2.strip()!r}')
    finally:
        restore()


class Spy:
    '''包住真 route，记录它每轮到底返回了什么（用来钉死"谁清掉了 pending"）'''

    def __init__(self, inner):
        self.inner = inner
        self.rec = []

    def __call__(self, text, history=None):
        d = self.inner(text, history)
        self.rec.append((text[:26], d.type, d.tool, dict(d.args or {})))
        return d


def group_i():
    print('I 组（真路由 + 假工具，零副作用）：删除反问出的候选 → 说「第N条」在真链路上对不对')
    H.STORE = {}
    spy = Spy(ORIG['route'])
    H.route = spy                     # 真路由（外面包一层记录）
    H.chat = ORIG['chat']
    H.TOOLS_LIST = [                  # 假工具：只读、零副作用
        {'name': 'delete_memo', 'func': fake_delete_candidate},
        {'name': 'delete_todo', 'func': fake_delete_candidate},
        {'name': 'list_memos', 'func': lambda **kw: TR('共1条备忘录:\n第1条，买牛奶')},
        {'name': 'list_todos', 'func': lambda **kw: TR('共1条待办事项:\n第1条，换水')},
    ]
    try:
        r1 = quiet(H.handle, '把带会议的那条备忘删了', 's1')
        print(f'    第1轮回复：{r1.strip()!r}')
        print('    第1轮 route 调用：')
        for t, ty, tl, ar in spy.rec:
            print(f'      · {t!r} → {ty}/{tl} {ar}')
        print(f"    第1轮结束后 pending = {H.STORE['s1']['pending']}")
        spy.rec.clear()
        CALLS.clear()
        r2 = quiet(H.handle, '把第2条删了', 's1')
        print(f'    第2轮回复：{r2.strip()!r}')
        print('    第2轮 route 调用：')
        for t, ty, tl, ar in spy.rec:
            print(f'      · {t!r} → {ty}/{tl} {ar}')
        print(f'    假工具收到 {CALLS}')
        got = CALLS[0].get('lineno') if CALLS else None
        check('I1 真链路上「第2条」换算成候选里的真实行号 5', got == 5,
              f'收到 {CALLS}（若是 2，说明换算没生效 → 会删错记录）')
    finally:
        restore()


def main():
    print('零 API 验收：handle 会话隔离（STORE）')
    print('=' * 70)
    try:
        group_a()
        group_b()
        group_c()
        group_d()
        group_e()
        group_f()
        group_g()
        print('=' * 70)
        print(f'零 API 结果：{PASS} 通过 / {FAIL} 失败')
        if NOTES:
            print('待清理 / 待确认：')
            for n in NOTES:
                print(f'  · {n}')
        if '--api' in sys.argv:
            print('=' * 70)
            zero_only = (PASS, FAIL)
            group_i()
            print(f'I 组：{PASS - zero_only[0]} 通过 / {FAIL - zero_only[1]} 失败')
            group_h()
            print(f'含 H/I 组累计：{PASS} 通过 / {FAIL} 失败')
    finally:
        restore()
        H.STORE = {}
    return 0 if FAIL == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

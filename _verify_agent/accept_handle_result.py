'''
零 API 验收：run_agent 交出的容器（schemas.ApiResult）+ handle 薄壳

做法：把 handle 模块里的 route / chat / TOOLS_LIST 换成假的，
      既不调 LLM、也不读写任何数据文件。

用法：
    python _verify_agent/accept_handle_result.py
'''
import sys
import io
import ast
import contextlib
import pathlib

SRC = pathlib.Path(r'D:/Project/voice_assistant/src')
sys.path.insert(0, str(SRC))
import handle as H

PASS, FAIL = 0, 0
WARNS = []


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  ✅ {name}' + (f'  — {detail}' if detail else ''))
    else:
        FAIL += 1
        print(f'  ❌ {name}' + (f'  — {detail}' if detail else ''))
    return ok


def warn(t):
    WARNS.append(t)


# ---------------- 假件 ----------------
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
    def __init__(self, decisions):
        self.decisions = list(decisions)

    def __call__(self, text, history=None):
        return self.decisions.pop(0)


class FakeChat:
    def __init__(self):
        self.seen = []

    def __call__(self, text, history=None):
        self.seen.append([dict(x) for x in (history or [])])
        return f'（闲聊）{text}'


CALLS = []


def fake_time(**kw):
    CALLS.append(('get_current_time', dict(kw)))
    return TR('二零二六年十月十六日星期五，十六时四十九分五十七秒')


def fake_add_todo(**kw):
    CALLS.append(('add_todo', dict(kw)))
    return TR('已加入待办事项！\n' + str(kw.get('text')))


def fake_delete_plain(**kw):
    CALLS.append(('delete_todo', dict(kw)))
    return TR(f'已删除第{kw.get("lineno")}条')


def fake_delete_cand(**kw):
    CALLS.append(('delete_todo', dict(kw)))
    return TR('共2条记录，请确认是哪一条：\n第1条，周会纪要\n第2条，评审会',
              candidate=[2, 5], ok=False)


def mk(*specs):
    return [{'name': n, 'func': f} for n, f in specs]


TOOLS_ALL = mk(('get_current_time', fake_time),
               ('add_todo', fake_add_todo),
               ('delete_todo', fake_delete_plain))
TOOLS_CAND = mk(('delete_todo', fake_delete_cand))

_ORIG = (H.route, H.chat, H.TOOLS_LIST)


def install(decisions, tool_list=None, keep_store=False):
    if not keep_store:
        H.STORE.clear()
    H.route = Script(decisions)
    H.chat = FakeChat()
    H.TOOLS_LIST = tool_list if tool_list is not None else TOOLS_ALL


def restore():
    H.route, H.chat, H.TOOLS_LIST = _ORIG


def quiet(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        return fn(*a, **kw)


# ms：B-7 起每步带耗时（本轮 route 决策 + 执行），单位为毫秒
KEYS = {'epoch', 'type', 'tool', 'args', 'result', 'ms'}

# ---------------- A 组：三场景逐字段 ----------------
print('A 组：三场景逐字段')

install([D('chat')])
r1 = quiet(H.run_agent, '你好呀', 'r1')
print(f'     [chat] ok={r1.ok!r} reply={r1.reply!r}')
print(f'            steps={r1.steps}')
check('A1 chat 一轮 → steps 长度 1', len(r1.steps) == 1, f'实际 {len(r1.steps)}')
check('A1 chat 轮 epoch=1 / type=chat / tool=None',
      r1.steps[0]['epoch'] == 1 and r1.steps[0]['type'] == 'chat' and r1.steps[0]['tool'] is None,
      f"实际 {r1.steps[0]}")
check('A1 chat 轮 result == 闲聊回复', r1.steps[0]['result'] == '（闲聊）你好呀',
      f"实际 {r1.steps[0]['result']!r}")
check('A1 顶层 ok is True（真布尔）', r1.ok is True, f'实际 {r1.ok!r}')
check('A1 顶层 error is None', r1.error is None, f'实际 {r1.error!r}')

install([D('command', 'add_todo', {'text': '明天交水电费'}),
         D('answer', None, {}, '已经帮你记下啦：明天交水电费。')])
r2 = quiet(H.run_agent, '帮我记一下明天交水电费', 'r2')
print(f'     [单工具] reply={r2.reply!r}')
print(f'              steps={r2.steps}')
check('A2 单工具 → steps 长度 2', len(r2.steps) == 2, f'实际 {len(r2.steps)}')
check('A2 steps[0] = command/add_todo',
      r2.steps[0]['type'] == 'command' and r2.steps[0]['tool'] == 'add_todo',
      f"实际 {r2.steps[0]}")
check('A2 steps[0].result == 工具回执原文',
      r2.steps[0]['result'] == '已加入待办事项！\n明天交水电费',
      f"实际 {r2.steps[0]['result']!r}")
check('A2 steps[1] = answer/tool=None',
      r2.steps[1]['type'] == 'answer' and r2.steps[1]['tool'] is None,
      f"实际 {r2.steps[1]}")
check('A2 reply == answer 轮的 text', r2.reply == '已经帮你记下啦：明天交水电费。',
      f'实际 {r2.reply!r}')

install([D('command', 'get_current_time', {}),
         D('command', 'add_todo', {'text': '今天晚上去烧烤'}),
         D('answer', None, {}, '今天是二零二六年十月十六日星期五。已经帮你记下今晚去烧烤啦。')])
r3 = quiet(H.run_agent, '今天星期几，你帮我记一下今天晚上去烧烤', 'r3')
print(f'     [双工具] reply={r3.reply!r}')
for s in r3.steps:
    print(f'              {s}')
check('A3 双工具 → steps 长度 3', len(r3.steps) == 3, f'实际 {len(r3.steps)}')
check('A3 三步的 tool 序列 = [get_current_time, add_todo, None]',
      [s['tool'] for s in r3.steps] == ['get_current_time', 'add_todo', None],
      f"实际 {[s['tool'] for s in r3.steps]}")
check('A3 steps[0].result == 时间工具回执',
      r3.steps[0]['result'] == '二零二六年十月十六日星期五，十六时四十九分五十七秒',
      f"实际 {r3.steps[0]['result']!r}")
check('A3 steps[1].result == add_todo 回执',
      r3.steps[1]['result'] == '已加入待办事项！\n今天晚上去烧烤',
      f"实际 {r3.steps[1]['result']!r}")

# ---------------- B 组：形状自洽 ----------------
print('\nB 组：形状自洽（三场景一起）')
for tag, r in (('chat', r1), ('单工具', r2), ('双工具', r3)):
    check(f'B 每项 key 集合一致（{tag}）',
          all(set(s.keys()) == KEYS for s in r.steps),
          f"实际 {[sorted(s.keys()) for s in r.steps]}")
    check(f'B epoch 连续 1..N（{tag}）',
          [s['epoch'] for s in r.steps] == list(range(1, len(r.steps) + 1)),
          f"实际 {[s['epoch'] for s in r.steps]}")
    check(f'B 每项 ms 是非负整数（{tag}）',
          all(isinstance(s['ms'], int) and not isinstance(s['ms'], bool) and s['ms'] >= 0
              for s in r.steps),
          f"实际 {[s['ms'] for s in r.steps]}")
    check(f'B 最后一轮是收尾轮（answer/chat）（{tag}）',
          r.steps[-1]['type'] in ('answer', 'chat'),
          f"实际 {r.steps[-1]['type']!r}")
    check(f'B steps[-1].result == reply（{tag}）',
          r.steps[-1]['result'] == r.reply,
          f"{r.steps[-1]['result']!r} vs {r.reply!r}")
check('B ok 不是字符串（防止 \'True\' 这种静默坑）',
      not isinstance(r1.ok, str), f'实际 {type(r1.ok).__name__}')

# ---------------- C 组：候选换算后记的是真实行号 ----------------
print('\nC 组：候选换算 —— 记的必须是「真正执行了什么」')
H.STORE.clear()
install([D('command', 'delete_todo', {'keyword': '会议'}),
         D('answer', None, {}, '共2条记录，请确认是哪一条：\n第1条，周会纪要\n第2条，评审会')],
        tool_list=TOOLS_CAND, keep_store=True)
quiet(H.run_agent, '删掉会议', 'r4')
check('C 前置：pending 候选已建立',
      H.STORE.get('r4', {}).get('pending') == {'tool': 'delete_todo', 'linenos': [2, 5]},
      f"实际 {H.STORE.get('r4', {}).get('pending')}")

CALLS.clear()
install([D('command', 'delete_todo', {'lineno': 2}),
         D('answer', None, {}, '已经删掉「评审会」啦。')],
        tool_list=TOOLS_ALL, keep_store=True)
r4 = quiet(H.run_agent, '第2条', 'r4')
got = CALLS[-1][1] if CALLS else {}
print(f"     [第2条] 工具实际收到={got}   steps[0].args={r4.steps[0]['args']}")
check('C 工具实际收到 lineno=5（候选里第2项 → 真实行号）',
      got.get('lineno') == 5, f'实际 {got}')
check('C steps[0].args 记的是换算后的 5（不是 LLM 原话的 2）',
      r4.steps[0]['args'].get('lineno') == 5, f"实际 {r4.steps[0]['args']}")

# ---------------- D 组：模型挂 ----------------
print('\nD 组：模型不可用')


def boom(text, history=None):
    raise H.ModelUnavailableError('假的上游挂了')


H.STORE.clear()
H.route = boom
H.chat = FakeChat()
H.TOOLS_LIST = TOOLS_ALL
r5 = quiet(H.run_agent, '你好', 'r5')
print(f'     [挂] ok={r5.ok!r}  error={r5.error!r}')
print(f'          reply={r5.reply!r}  steps={r5.steps!r}')
check('D ok is False（真布尔）', r5.ok is False, f'实际 {r5.ok!r}')
check('D steps 是空列表 []（前端能直接 for，不是 None）',
      r5.steps == [], f'实际 {r5.steps!r}')
check("D error 是机器码枚举 'model_unavailable'（不是中文话术）",
      r5.error == 'model_unavailable', f'实际 {r5.error!r}')
check('D reply 仍留着给用户看的那句话', isinstance(r5.reply, str) and r5.reply,
      f'实际 {r5.reply!r}')

# ---------------- E 组：薄壳 ----------------
print('\nE 组：handle 薄壳')
install([D('chat')])
a = quiet(H.run_agent, '你好呀', 'r6')
install([D('chat')])
b = quiet(H.handle, '你好呀', 'r6')
check('E handle 返回的仍是 str', isinstance(b, str), f'实际 {type(b).__name__}')
check('E handle(x) == run_agent(x).reply', b == a.reply, f'{b!r} vs {a.reply!r}')

# ---------------- F 组：静态 ----------------
print('\nF 组：静态检查')
src = (SRC / 'handle.py').read_text(encoding='utf-8')
tree = ast.parse(src)
top = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
n_handle = top.count('handle')
check('F 模块里只有一个顶层 handle（没有死代码）', n_handle == 1,
      f'实际出现 {n_handle} 次；顶层函数 = {top}')
check('F run_agent 存在', 'run_agent' in top, f'实际 {top}')
check('F 用的是裸 import（无 from src.）', 'from src.' not in src)
if 'run_agent' in top and 'handle' in top:
    last_handle = len(top) - 1 - top[::-1].index('handle')
    check('F 最后一个 handle 定义在 run_agent 之后',
          last_handle > top.index('run_agent'), f'实际 {top}')
if '__main__' in src:
    warn('handle.py 底部还有 __main__ 调试块，提交前删掉')

restore()

print(f'\n零 API 结果：{PASS} 通过 / {FAIL} 失败')
for w in WARNS:
    print(f'⚠️ {w}')

'''
零 API：证明「把 handle 主体搬进 run_agent」是等价搬家，不是重写

做法：
  1. 从 git 取改动前的 handle.py（HEAD 版）写到临时目录，当对照组 handle_old
  2. 同一组假 route / 假 chat / 假工具，分别喂给 OLD.handle 和 NEW.run_agent
  3. 逐项比对：reply / 工具实际收到的 kwargs / HISTORY / CHAT_HISTORY / pending

用法：
    python _verify_agent/accept_refactor_equiv.py
'''
import sys
import io
import shutil
import pathlib
import tempfile
import contextlib
import subprocess

ROOT = r'D:/Project/voice_assistant'
SRC = pathlib.Path(ROOT) / 'src'
TMP = pathlib.Path(tempfile.mkdtemp(prefix='wb_old_handle_'))

# ⚠️ 对照组必须锁在「拆分前」那一版。
#    原先取 HEAD —— 一旦拆分被提交，HEAD 就前进了，对照组变成「拆分后」，
#    脚本立刻从「证明等价」退化成「自己跟自己比」。
#    d77e4de = 「容器 + 拆分」那次提交，取其父提交即拆分前的最后状态。
BASE = 'd77e4de^'

_old_src = subprocess.run(['git', 'show', f'{BASE}:src/handle.py'], cwd=ROOT,
                          capture_output=True, text=True, encoding='utf-8').stdout
if not _old_src.strip():
    print(f'❌ 取不到 {BASE} 版 handle.py，无法对照')
    sys.exit(1)
(TMP / 'handle_old.py').write_text(_old_src, encoding='utf-8')

sys.path.insert(0, str(SRC))
sys.path.insert(0, str(TMP))
import handle as NEW
import handle_old as OLD

PASS, FAIL = 0, 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  ✅ {name}' + (f'  — {detail}' if detail else ''))
    else:
        FAIL += 1
        print(f'  ❌ {name}' + (f'  — {detail}' if detail else ''))
    return ok


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
    def __call__(self, text, history=None):
        return f'（闲聊）{text}'


CALLS = []


def fake_time(**kw):
    CALLS.append(('get_current_time', dict(kw)))
    return TR('二零二六年十月十六日星期五，十六时五十四分零秒')


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


ALL = mk(('get_current_time', fake_time),
         ('add_todo', fake_add_todo),
         ('delete_todo', fake_delete_plain))
CAND = mk(('delete_todo', fake_delete_cand))


def equip(mod, decisions, tool_list):
    mod.STORE.clear()
    mod.route = Script(decisions)
    mod.chat = FakeChat()
    mod.TOOLS_LIST = tool_list


def entry(mod):
    return mod.run_agent if hasattr(mod, 'run_agent') else mod.handle


def unwrap(r):
    """旧版 `handle` 直接返回 str；新版 `run_agent` 返回容器。

    比对时一律取「给人看的那一句」，否则会变成 `str == ApiResult` 恒不等。
    """
    return r.reply if hasattr(r, 'reply') else r


def quiet(fn, *a):
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        return fn(*a)


def snap(mod, sid):
    st = mod.STORE.get(sid, {})
    return {'history': st.get('history'),
            'chat_history': st.get('chat_history'),
            'pending': st.get('pending')}


# ---------------- 三个主场景 ----------------
def s_chat():
    return [D('chat')]


def s_one():
    return [D('command', 'add_todo', {'text': '明天交水电费'}),
            D('answer', None, {}, '已经帮你记下啦：明天交水电费。')]


def s_two():
    return [D('command', 'get_current_time', {}),
            D('command', 'add_todo', {'text': '今天晚上去烧烤'}),
            D('answer', None, {}, '今天是X。已经帮你记下今晚去烧烤啦。')]


SCENARIOS = [
    ('chat 一轮', s_chat, '你好呀'),
    ('单工具→answer', s_one, '帮我记一下明天交水电费'),
    ('双工具→answer', s_two, '今天星期几，你帮我记一下今天晚上去烧烤'),
]

print('=' * 74)
print('第一组：三条主路径，新旧逐项比对')
for name, factory, text in SCENARIOS:
    CALLS.clear()
    equip(NEW, factory(), ALL)
    rn = quiet(entry(NEW), text, 's')
    cn = [c for c in CALLS]
    sn = snap(NEW, 's')

    CALLS.clear()
    equip(OLD, factory(), ALL)
    ro = quiet(entry(OLD), text, 's')
    co = [c for c in CALLS]
    so = snap(OLD, 's')

    print(f'\n  【{name}】')
    check(f'{name} · reply 一致', unwrap(rn) == unwrap(ro),
          f'{unwrap(rn)!r} vs {unwrap(ro)!r}')
    check(f'{name} · 工具收到的 kwargs 序列一致', cn == co, f'{cn} vs {co}')
    check(f'{name} · 两条历史字面一致',
          sn['history'] == so['history'] and sn['chat_history'] == so['chat_history'],
          f"HISTORY {len(sn['history'] or [])} vs {len(so['history'] or [])} 行")
    check(f'{name} · pending 一致', sn['pending'] == so['pending'],
          f"{sn['pending']} vs {so['pending']}")

# ---------------- 候选换算（两轮） ----------------
print('\n' + '=' * 74)
print('第二组：候选换算（两轮，"第2条" 必须换算成真实行号）')


def candidate_run2(mod):
    CALLS.clear()
    mod.STORE.clear()
    mod.route = Script([D('command', 'delete_todo', {'keyword': '会议'}),
                        D('answer', None, {}, '共2条记录，请确认是哪一条：\n第1条，周会纪要\n第2条，评审会')])
    mod.chat = FakeChat()
    mod.TOOLS_LIST = CAND
    quiet(entry(mod), '删掉会议', 's')
    p1 = dict(mod.STORE['s']['pending'] or {})

    CALLS.clear()
    mod.route = Script([D('command', 'delete_todo', {'lineno': 2}),
                        D('answer', None, {}, '已经删掉「评审会」啦。')])
    mod.TOOLS_LIST = ALL
    r = quiet(entry(mod), '第2条', 's')
    return p1, r, [c for c in CALLS], snap(mod, 's')


p_n, rn, c_n, sn = candidate_run2(NEW)
p_o, ro, c_o, so = candidate_run2(OLD)
print(f"  【候选】NEW 工具收到={c_n[-1][1] if c_n else None}   OLD 工具收到={c_o[-1][1] if c_o else None}")
check('候选 · 第一轮 pending 一致', p_n == p_o, f'{p_n} vs {p_o}')
check('候选 · 换算后工具收到的 kwargs 一致（都该是 lineno=5）', c_n == c_o, f'{c_n} vs {c_o}')
check('候选 · reply 一致', unwrap(rn) == unwrap(ro), f'{unwrap(rn)!r} vs {unwrap(ro)!r}')
check('候选 · 第二轮 pending 一致', sn['pending'] == so['pending'], f"{sn['pending']} vs {so['pending']}")
check('候选 · 历史一致',
      sn['history'] == so['history'] and sn['chat_history'] == so['chat_history'])

# ---------------- 模型挂 ----------------
print('\n' + '=' * 74)
print('第三组：模型不可用')
check('两边用的是同一个异常类（import 一致）',
      NEW.ModelUnavailableError is OLD.ModelUnavailableError)


def boom(text, history=None):
    raise NEW.ModelUnavailableError('假的上游挂了')


for mod in (NEW, OLD):
    mod.STORE.clear()
    mod.route = boom
    mod.chat = FakeChat()
    mod.TOOLS_LIST = ALL
rn = quiet(entry(NEW), '你好', 's')
ro = quiet(entry(OLD), '你好', 's')
print(f"  【挂】NEW 交回 reply={unwrap(rn)!r}   OLD 返回={unwrap(ro)!r}")
check('模型挂 · 两边的用户可见文案一致', unwrap(rn) == unwrap(ro),
      f'{unwrap(rn)!r} vs {unwrap(ro)!r}')
check('模型挂 · 两边都不写 HISTORY',
      (snap(NEW, 's')['history'] or []) == [] and (snap(OLD, 's')['history'] or []) == [])

shutil.rmtree(TMP, ignore_errors=True)

print('\n' + '=' * 74)
print(f'结果：{PASS} 通过 / {FAIL} 失败')
print('（全部零 API：假 route / 假 chat / 假工具）')

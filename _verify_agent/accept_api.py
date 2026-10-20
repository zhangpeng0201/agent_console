# -*- coding: utf-8 -*-
"""
api.py 零 API 验收 —— 用 fastapi.testclient 直接发请求，不起 uvicorn、不烧 API。

落点：把 tools.OUTPUT_DIR 整体换到临时目录，绝不碰真实 output/。

五组：
  A 正常 200  —— 六字段齐 / session_id 回带 / steps 原样 / elapsed_ms 是整数
  B 400       —— 脏 id（穿越/空/大写/中文/default）→ invalid_session_id；
                 空 / 纯空格 / 制表符 text → invalid_text；同一形状且错误码可区分
  C 503       —— run_agent 报 ok=False → 503 且同一形状（reply 仍有话术）
  D 隔离      —— 走**真** run_agent + 假 route/chat：两个 sid 落两个目录、不串号
  F 兜底      —— 让 run_agent 抛 KeyError → 500 + 同一形状 + stderr 留痕；再回归 200/503 没被吞
  E 静态      —— 路由是同步 def（不是 async def）/ 裸 import / 字段名与容器对齐
"""
import sys
import json
import shutil
import pathlib
import tempfile

sys.path.insert(0, r'D:\Project\voice_assistant\src')

_TMP = pathlib.Path(tempfile.mkdtemp(prefix='accept_api_'))
import tools                                    # noqa: E402
tools.OUTPUT_DIR = _TMP                         # 落点整体换到临时目录

import api                                      # noqa: E402
import handle as H                              # noqa: E402
import registry                                 # noqa: E402
from schemas import ApiResult, RouterDecision   # noqa: E402
from fastapi.testclient import TestClient       # noqa: E402

client = TestClient(api.app)
REAL_RUN_AGENT = api.run_agent                  # 先存下真的，D 组要用

PASS = FAIL = 0


def check(desc, ok, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  ✅ {desc}')
    else:
        FAIL += 1
        print(f'  ❌ {desc}')
        if extra:
            print(f'       {extra}')


def body_of(r):
    try:
        return r.json()
    except Exception:
        return {'<非 JSON>': r.text[:120]}


SIX = {'session_id', 'elapsed_ms', 'ok', 'reply', 'steps', 'error'}


def check_shape(tag, r, status):
    b = body_of(r)
    keys = set(b)
    check(f'{tag} 状态码 = {status}', r.status_code == status, f'实际 {r.status_code}  body={b}')
    check(f'{tag} 六字段齐（{sorted(SIX)}）', keys == SIX, f'实际 {sorted(keys)}')
    return b


# ============================================================ A 组：正常 200
print('\nA 组：正常请求')
FAKE_STEPS = [
    {'epoch': 1, 'type': 'command', 'tool': 'add_todo',
     'args': {'text': '明天交水电费'}, 'result': '已加入待办事项！\n明天交水电费'},
    {'epoch': 2, 'type': 'answer', 'tool': None, 'args': {},
     'result': '已经帮你记下啦：明天交水电费'},
]


def fake_ok(text, session_id='default', user_id=None):
    return ApiResult(ok=True, reply='已经帮你记下啦：明天交水电费',
                     steps=[dict(s) for s in FAKE_STEPS], error=None)


api.run_agent = fake_ok
r = client.post('/chat', json={'session_id': 'apitest', 'text': '帮我记一下明天交水电费'})
b = check_shape('A1', r, 200)
check('A2 session_id 原样回带', b['session_id'] == 'apitest', f"实际 {b['session_id']!r}")
check('A3 ok 是真布尔 True（不是 "True"）', b['ok'] is True, f"实际 {b['ok']!r} ({type(b['ok']).__name__})")
check('A4 reply 就是容器里那句', b['reply'] == '已经帮你记下啦：明天交水电费', f"实际 {b['reply']!r}")
check('A5 steps 原样透传（2 步、字段一字不改）', b['steps'] == FAKE_STEPS,
      f'实际 {b["steps"]}')
check('A6 elapsed_ms 是整数且 >= 0',
      isinstance(b['elapsed_ms'], int) and b['elapsed_ms'] >= 0, f"实际 {b['elapsed_ms']!r}")
check('A7 error 为 None', b['error'] is None, f"实际 {b['error']!r}")

# ============================================================ B 组：400 / 422
print('\nB 组：非法输入')
BAD_IDS = [
    ('../evil', '路径穿越'),
    ('..\\win', '反斜杠穿越'),
    ('', '空串'),
    ('default', '兜底会话（会串号）'),
    ('U1', '大写（clean 会降成小写，不等于自身）'),
    ('中文', '非白名单字符'),
    ('a' * 65, '超长 65'),
]
for sid, why in BAD_IDS:
    r = client.post('/chat', json={'session_id': sid, 'text': '你好'})
    b = body_of(r)
    ok = (r.status_code == 400 and set(b) == SIX
          and b['ok'] is False and b['error'] == 'invalid_session_id'
          and b['session_id'] is None and b['steps'] == []
          and b['elapsed_ms'] == 0)
    check(f'B {why:38s} sid={sid[:14]!r:18s} → 400 + 同一形状', ok,
          f'实际 HTTP {r.status_code}  body={b}')

r = client.post('/chat', json={'session_id': 'apitest', 'text': ''})
b = body_of(r)
check('B 空 text → 400 + error=invalid_text + 同一形状',
      r.status_code == 400 and set(b) == SIX and b['ok'] is False
      and b['error'] == 'invalid_text' and b['steps'] == []
      and b['elapsed_ms'] == 0 and b['session_id'] == 'apitest',
      f'实际 HTTP {r.status_code}  body={b}')

r = client.post('/chat', json={'session_id': 'apitest', 'text': '   '})
b = body_of(r)
check('B 纯空格 text → 400（strip 后为空）+ error=invalid_text',
      r.status_code == 400 and b.get('error') == 'invalid_text',
      f'实际 HTTP {r.status_code}  body={b}')

r = client.post('/chat', json={'session_id': 'apitest', 'text': '\t\n  '})
b = body_of(r)
check('B 制表符/换行 text → 400（同样被 strip 掉）+ error=invalid_text',
      r.status_code == 400 and b.get('error') == 'invalid_text',
      f'实际 HTTP {r.status_code}  body={b}')

# 两类 400 必须给**不同**的机器码 —— 前端才分得清「该刷新页面」还是「该重新输入」
_bad_sid = body_of(client.post('/chat', json={'session_id': 'default', 'text': '你好'}))
_bad_txt = body_of(client.post('/chat', json={'session_id': 'apitest', 'text': ''}))
check('B 两类 400 的 error 互不相同（sid 病 / text 病 可区分）',
      _bad_sid.get('error') == 'invalid_session_id' and _bad_txt.get('error') == 'invalid_text',
      f"实际 sid={_bad_sid.get('error')!r}  text={_bad_txt.get('error')!r}")
check('B 两类 400 的 session_id 处理也不同（sid 病 → None；text 病 → 回带，因为 sid 是好的）',
      _bad_sid.get('session_id') is None and _bad_txt.get('session_id') == 'apitest',
      f"实际 sid={_bad_sid.get('session_id')!r}  text={_bad_txt.get('session_id')!r}")

# 反向：下划线**是**合法的（白名单 = [a-zA-Z0-9_-]）—— 防这条口径被改回去
r = client.post('/chat', json={'session_id': 'u_1', 'text': '你好'})
check('B 下划线 id（u_1）合法 → 放行，不是 400',
      r.status_code == 200, f'实际 {r.status_code}  body={body_of(r)}')

r = client.post('/chat', json={'text': '你好'})
check('B 整个缺 session_id → 422（Pydantic 拦，形状是 detail —— 已知取舍）',
      r.status_code == 422, f'实际 {r.status_code}')

# ============================================================ C 组：503
print('\nC 组：模型不可用')
C_REPLY = '当前模型不可用，请稍后再试'


def fake_fail(text, session_id='default', user_id=None):
    return ApiResult(ok=False, reply=C_REPLY, steps=[], error='model_unavailable')


api.run_agent = fake_fail
r = client.post('/chat', json={'session_id': 'apitest', 'text': '你好'})
b = check_shape('C1', r, 503)
check('C2 ok 是真布尔 False', b['ok'] is False, f"实际 {b['ok']!r}")
check('C3 error 是机器码 model_unavailable（不是中文话术）',
      b['error'] == 'model_unavailable', f"实际 {b['error']!r}")
check('C4 reply 仍是给人看的话术（不是 None）', b['reply'] == C_REPLY, f"实际 {b['reply']!r}")
check('C5 steps 是空列表（不是 None —— 前端 for...of 会崩）',
      b['steps'] == [], f"实际 {b['steps']!r}")
check('C6 session_id 照样回带', b['session_id'] == 'apitest', f"实际 {b['session_id']!r}")

# ============================================================ D 组：隔离
print('\nD 组：HTTP 层会话隔离（真 run_agent + 假 route/chat）')


class Script:
    """按脚本吐决策，调一次移一位。"""

    def __init__(self, seq):
        self.seq = list(seq)
        self.i = 0

    def __call__(self, text, history=None):
        d = self.seq[self.i]
        self.i += 1
        return d


def D(t, tool=None, args=None, text=None):
    return RouterDecision(type=t, tool=tool, args=args or {}, text=text)


api.run_agent = REAL_RUN_AGENT                 # 换回真身
H.chat = lambda text, history=None: '（假闲聊，不消耗 API）'
H.STORE.clear()


def send(sid, text, seq):
    H.route = Script(seq)
    return client.post('/chat', json={'session_id': sid, 'text': text})


# D1：sida 记一条待办 → 落 _TMP/sida/
r = send('sida', '帮我记一下 HTTP 侧待办',
         [D('command', 'add_todo', {'text': 'HTTP 侧待办'}),
          D('answer', None, {}, '已经帮你记下啦：HTTP 侧待办')])
b = body_of(r)
check('D1 sida 记待办 → 200', r.status_code == 200, f'实际 {r.status_code}  body={b}')
check('D2 STORE 的 key 是 sida', list(H.STORE) == ['sida'], f'实际 {list(H.STORE)}')
fa = _TMP / 'sida' / 'todos.json'
check('D3 真落到了 <tmp>/sida/todos.json', fa.exists(),
      f'实际存在 {sorted(p.relative_to(_TMP).as_posix() for p in _TMP.rglob("*"))}')
_a = json.loads(fa.read_text(encoding='utf-8')) if fa.exists() else []
check('D4 sida 文件内容 = 1 条「HTTP 侧待办」',
      len(_a) == 1 and _a[0]['text'] == 'HTTP 侧待办', f'实际 {_a}')
check('D5 此刻还没有 sidb 的目录', not (_TMP / 'sidb').exists())

# D2：换 sidb 记另一条 → 落 _TMP/sidb/，sida 不受影响
r = send('sidb', '帮我记一下另一件事',
         [D('command', 'add_todo', {'text': '另一件事'}),
          D('answer', None, {}, '已经帮你记下啦：另一件事')])
fb = _TMP / 'sidb' / 'todos.json'
_b = json.loads(fb.read_text(encoding='utf-8')) if fb.exists() else []
_a2 = json.loads(fa.read_text(encoding='utf-8')) if fa.exists() else []
check('D6 sidb 有自己那份，且只有 1 条（没和 sida 合并）',
      len(_b) == 1 and _b[0]['text'] == '另一件事', f'实际 {_b}')
check('D7 sida 的没被动过（仍是 1 条「HTTP 侧待办」）',
      len(_a2) == 1 and _a2[0]['text'] == 'HTTP 侧待办', f'实际 {_a2}')
check('D8 STORE 里现在是两格：sida / sidb',
      sorted(H.STORE) == ['sida', 'sidb'], f'实际 {sorted(H.STORE)}')

# D3：sidb 问「我刚才记了什么」→ 只看得见自己的
seen = []


def spy_route(text, history=None):
    seen.append([h for h in (history or [])])
    return D('answer', None, {}, '（假回答）')


H.route = spy_route
client.post('/chat', json={'session_id': 'sidb', 'text': '我刚才让你记了什么'})
hist = seen[-1] if seen else []
txt = json.dumps(hist, ensure_ascii=False)
check('D9 sidb 的 history 里看不到 sida 的内容', 'HTTP 侧待办' not in txt,
      f'sidb 的 history = {txt[:200]}')
check('D10 sidb 的 history 里看得到自己的「另一件事」', '另一件事' in txt,
      f'sidb 的 history = {txt[:200]}')

# ============================================================ F 组：意外异常兜底
print('\nF 组：意外异常兜底（500 + 同一形状）')
import io as _io                                          # noqa: E402
import time as _time                                      # noqa: E402
from contextlib import redirect_stderr as _redir          # noqa: E402


def boom_key(text, session_id='default', user_id=None):
    # 真实场景：llm_router._parse_output 里 content['type'] 是硬取，
    # 模型吐了畸形 JSON 时会 KeyError —— 这就是漏网异常的样子
    raise KeyError('type')


api.run_agent = boom_key
_err = _io.StringIO()
escaped = None
try:
    with _redir(_err):
        r = client.post('/chat', json={'session_id': 'apitest', 'text': '你好'})
except Exception as _exc:      # TestClient 默认 raise_server_exceptions=True → 没兜住就会炸到这里
    escaped = _exc
    r = None

check('F1 异常被兜住（没逃逸出 HTTP 层）', escaped is None,
      f'逃逸了：{type(escaped).__name__}: {escaped}')

if escaped is None:
    b = body_of(r)
    check('F2 状态码 = 500', r.status_code == 500, f'实际 {r.status_code}  body={b}')
    check('F3 六字段齐（500 也破不了形）', set(b) == SIX, f'实际 {sorted(b)}')
    check('F4 ok 是真布尔 False', b['ok'] is False, f"实际 {b['ok']!r}")
    check('F5 error == internal_error（又一个独立机器码）',
          b['error'] == 'internal_error', f"实际 {b['error']!r}")
    check('F6 reply 是中文话术，不是 traceback 原文',
          b['reply'] == '服务内部出错，请稍后再试', f"实际 {b['reply']!r}")
    check('F7 steps == []、elapsed_ms 是整数（前端 for...of 不会崩）',
          b['steps'] == [] and isinstance(b['elapsed_ms'], int),
          f"实际 steps={b['steps']!r}  ms={b['elapsed_ms']!r}")
    check('F8 session_id 回带 apitest', b['session_id'] == 'apitest', f"实际 {b['session_id']!r}")
    print(f'       ℹ️ 兜底分支的 elapsed_ms = {b["elapsed_ms"]}'
          '（真耗时 —— pc() 在 except 里现取，不是写死的 0）')
else:
    for _i in range(2, 9):
        check(f'F{_i} （F1 没兜住，此条无意义）', False)

_txt = _err.getvalue()
check('F9 stderr 里有留痕（不是哑巴 500）', _txt.strip() != '', 'stderr 是空的 —— 线上出问题无从查起')
if _txt.strip():
    _lines = _txt.strip().splitlines()
    print('       ℹ️ 留痕原文（首行 + 尾行）：')
    print(f'          {_lines[0]}')
    print(f'          ...（共 {len(_lines)} 行）')
    print(f'          {_lines[-1]}')

# 回归：兜底就位后，老的三条出口一条都不许变
api.run_agent = fake_ok
r = client.post('/chat', json={'session_id': 'apitest', 'text': '帮我记一下明天交水电费'})
_b = body_of(r)
check('F10 回归：正常路径仍是 200（try 没把好路吞成 500）',
      r.status_code == 200 and _b.get('ok') is True and _b.get('error') is None,
      f'实际 {r.status_code}  body={_b}')

api.run_agent = fake_fail
r = client.post('/chat', json={'session_id': 'apitest', 'text': '你好'})
_b = body_of(r)
check('F11 回归：503 仍是 503（except 范围没写大到把模型挂也吃成 500）',
      r.status_code == 503 and _b.get('error') == 'model_unavailable',
      f'实际 {r.status_code}  body={_b}')

# F12/F13：兜底分支自己必须活得下来 —— 假 run_agent 先睡 50ms 再炸
def slow_boom(text, session_id='default', user_id=None):
    _time.sleep(0.05)
    raise RuntimeError('慢炸')


api.run_agent = slow_boom
_err2 = _io.StringIO()
_esc2 = None
try:
    with _redir(_err2):
        r = client.post('/chat', json={'session_id': 'apitest', 'text': '你好'})
except Exception as _e2:
    _esc2 = _e2
    r = None

if _esc2 is None:
    b = body_of(r)
    check('F12 兜底分支的 elapsed_ms 是真耗时（> 0，不是写死的 0）',
          r.status_code == 500 and isinstance(b['elapsed_ms'], int) and b['elapsed_ms'] >= 30,
          f"实际 {r.status_code}  ms={b.get('elapsed_ms')!r}（假 run_agent 睡了 50ms）")
else:
    check('F12 兜底分支自己抛异常了（异常路径下变量没绑定）', False,
          f'逃逸出 HTTP 层：{type(_esc2).__name__}: {_esc2}')

_t2 = _err2.getvalue()
check('F13 留痕里有完整堆栈（带文件名 + 行号，不是光一句 str(e)）',
      'Traceback (most recent call last)' in _t2 and 'api.py' in _t2,
      f'stderr = {_t2.strip()!r}')

# ============================================================ G 组：user_id（数据归属）
print('\nG 组：user_id —— 数据按【人】存，不按【会话】存')
api.run_agent = REAL_RUN_AGENT          # ⚠️ F 组最后把它换成了 slow_boom，必须换回真身
H.STORE.clear()


def send_u(sid, uid, text, seq):
    H.route = Script(seq)
    body = {'session_id': sid, 'text': text}
    if uid is not None:                 # None = 完全不传这个字段
        body['user_id'] = uid
    return client.post('/chat', json=body)


def dump_tmp():
    return sorted(p.relative_to(_TMP).as_posix() for p in _TMP.rglob('*'))


def tool_result_of(resp):
    """工具真正返回了什么 —— 不能看最终 reply！
    list 类命令走两轮：step[0] 是工具回执，step[1] 是 answer 话术，
    最终 reply 是 step[1].result（一句「（假回答）」），拿它判断会假通过。"""
    st = resp.get('steps') or []
    return st[0].get('result', '') if st else ''


# G1：同一个人，会话 A 记一条
r = send_u('gu-sessa', 'gu-user', '帮我记一下 G 组待办',
           [D('command', 'add_todo', {'text': 'G 组待办'}),
            D('answer', None, {}, '已经帮你记下啦：G 组待办')])
b = body_of(r)
check('G1 带合法 user_id → 200', r.status_code == 200, f'实际 {r.status_code}  body={b}')
_gu = _TMP / 'gu-user' / 'todos.json'
check('G2 落点是 <tmp>/<user_id>/todos.json', _gu.exists(), f'实际有 {dump_tmp()}')
check('G3 没有 <user_id>/<session_id>/ 这层多余目录（不是两层拼接）',
      not (_TMP / 'gu-user' / 'gu-sessa').exists(), f'实际有 {dump_tmp()}')
check('G4 STORE 的 key 仍是 session_id，不是 user_id',
      'gu-sessa' in H.STORE and 'gu-user' not in H.STORE, f'实际 {sorted(H.STORE)}')

# G5：⭐ 换个会话，还是同一个人 —— 必须读得到上一条
r = send_u('gu-sessb', 'gu-user', '帮我记一下 G 组第二件',
           [D('command', 'add_todo', {'text': 'G 组第二件'}),
            D('answer', None, {}, '已经帮你记下啦：G 组第二件')])
_g2 = json.loads(_gu.read_text(encoding='utf-8')) if _gu.exists() else []
check('G5 ⭐ 换会话、同一 user → 读得到上一条，并成 2 条（B 的核心目的）',
      len(_g2) == 2 and {x['text'] for x in _g2} == {'G 组待办', 'G 组第二件'},
      f'实际 {_g2}（若是 1 条，说明新会话又开了一个抽屉）')
check('G6 两个会话在 STORE 里各占一格', {'gu-sessa', 'gu-sessb'} <= set(H.STORE),
      f'实际 {sorted(H.STORE)}')

# G7：第三个会话也能列出来
r = send_u('gu-sessc', 'gu-user', '我有哪些待办',
           [D('command', 'list_todos', {}), D('answer', None, {}, '（假回答）')])
_re = tool_result_of(body_of(r))
check('G7 第三个会话列得出这两条', 'G 组待办' in _re and 'G 组第二件' in _re,
      f'step[0].result = {_re[:200]!r}')

# G8：换个人，同一 session —— 看不到
r = send_u('gu-sessa', 'gu-other', '我有哪些待办',
           [D('command', 'list_todos', {}), D('answer', None, {}, '（假回答）')])
_re = tool_result_of(body_of(r))
check('G8 换一个 user（同一 session）→ 看不到别人的待办',
      _re != '' and 'G 组待办' not in _re,
      f'step[0].result = {_re[:200]!r}（空串说明还没读到磁盘，是假通过）')

# G9/G10：不带 user_id → 退回老行为（CLI / bench 靠这条）
r = send_u('gu-legacy', None, '帮我记一下 老行为待办',
           [D('command', 'add_todo', {'text': '老行为待办'}), D('answer', None, {}, 'ok')])
check('G9 不带 user_id → 落 <tmp>/<session_id>/（老行为不变）',
      (_TMP / 'gu-legacy' / 'todos.json').exists(), f'实际有 {dump_tmp()}')
r = send_u('gu-legacy2', None, '我有哪些待办',
           [D('command', 'list_todos', {}), D('answer', None, {}, '（假回答）')])
_re = tool_result_of(body_of(r))
check('G10 不带 user_id 时仍按会话隔离（等价于老逻辑）',
      _re != '' and '老行为待办' not in _re,
      f'step[0].result = {_re[:200]!r}（空串说明还没读到磁盘，是假通过）')

# G11：非法 user_id 一律 400，且不许在磁盘上越界
for bad, tag in [('../evil', '路径穿越'), ('default', '兜底值'), ('User_A', '大写'),
                 ('中文', '非白名单'), ('a' * 65, '超长'), ('', '空串')]:
    r = client.post('/chat', json={'session_id': 'gu-sessa', 'user_id': bad, 'text': '你好'})
    b = body_of(r)
    check(f'G11 user_id=\'{bad[:10]}\'（{tag}）→ 400 invalid_user_id',
          r.status_code == 400 and b.get('error') == 'invalid_user_id',
          f"实际 {r.status_code}  error={b.get('error')!r}")
check('G12 越界 user_id 没在 output 之外造出目录', not (_TMP.parent / 'evil').exists(),
      f'意外出现 {_TMP.parent / "evil"}')

# ============================================================ E 组：静态
print('\nE 组：静态检查')
src = pathlib.Path(r'D:\Project\voice_assistant\src\api.py').read_text(encoding='utf-8')
check('E1 路由是同步 def（不是 async def —— 否则阻塞事件循环）',
      'def chat(' in src and 'async def chat(' not in src)
check('E2 裸 import（from handle import ...，不是 from src.handle）',
      'from handle import' in src and 'from src.' not in src)
check('E3 用了 perf_counter（不是 time.time）', 'perf_counter' in src)

api_fields = set(ApiResult.__dataclass_fields__)               # ok/reply/steps/error
resp_fields = set(api.ChatResponse.model_fields)               # 六字段
check('E4 容器四字段全在响应模型里（名字一字不改）',
      {'ok', 'reply', 'steps', 'error'} <= resp_fields,
      f'缺 {sorted({"ok", "reply", "steps", "error"} - resp_fields)}')
check('E5 响应模型只比容器多 2 个（session_id / elapsed_ms）',
      resp_fields - api_fields == {'session_id', 'elapsed_ms'},
      f'实际多出 {sorted(resp_fields - api_fields)}')
check('E6 ChatRequest 就是三个字段：session_id / text / user_id',
      set(api.ChatRequest.model_fields) == {'session_id', 'text', 'user_id'},
      f'实际 {sorted(api.ChatRequest.model_fields)}')
check('E7 user_id 可省略（默认 None）—— 老调用 curl/CLI 不用改',
      api.ChatRequest.model_fields['user_id'].default is None,
      f"实际默认值 {api.ChatRequest.model_fields['user_id'].default!r}")

# ============================================================ 收尾
print('\n' + '=' * 72)
print(f'零 API 结果：{PASS} 通过 / {FAIL} 失败')
print(f'临时目录里留下的：{sorted(p.relative_to(_TMP).as_posix() for p in _TMP.rglob("*"))}')
shutil.rmtree(_TMP, ignore_errors=True)
print('（临时目录已删；真实 output/ 一个字节没动）')
sys.exit(1 if FAIL else 0)

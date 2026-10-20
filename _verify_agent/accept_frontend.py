# -*- coding: utf-8 -*-
"""
前端页（服务化第 3 步）零 API 验收 —— 不开浏览器、不起 uvicorn、不烧 API。

分五组：
  A 路由       —— GET / 返回 200 + text/html；STATIC_DIR 用 __file__ 定位且文件真实存在
  B 页面骨架   —— 内联样式/脚本、七个必需 id、双 id（user_id 长期 / session_id 临时）、决策卡五键渲染
  C 零外链     —— 页面里没有任何 http(s) 外链资源（防 CDN 不通 → 白屏，上次 /docs 的坑）
  D 错误码对齐 —— 五个机器码在「页面」与「服务端(api.py + handle.py)」两侧双向对齐
  E 回归       —— 新增 GET / 没弄坏老路径：/chat 仍六字段、两个路由都是同步 def
"""
import sys
import re
import pathlib

sys.path.insert(0, r'D:\Project\voice_assistant\src')

import api                                      # noqa: E402
from fastapi.testclient import TestClient       # noqa: E402

client = TestClient(api.app)

SRC       = pathlib.Path(r'D:\Project\voice_assistant\src')
HTML_PATH = SRC / 'static' / 'index.html'
API_PATH  = SRC / 'api.py'

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


api_src = API_PATH.read_text(encoding='utf-8')

# ============================================================ A 组：路由与定位
print('\nA 组：GET / 与文件定位')
r = client.get('/')
check('A1  GET / → 200', r.status_code == 200, f'实际 HTTP {r.status_code}')
ct = r.headers.get('content-type', '')
check('A2  content-type 是 text/html', ct.startswith('text/html'), f'实际 {ct!r}')
html = r.text
check('A3  返回完整 HTML（<!DOCTYPE html> 开头、</html> 收尾）',
      html.lstrip().lower().startswith('<!doctype html>') and '</html>' in html.lower(),
      f'开头 40 字符 = {html[:40]!r}')
check('A4  页面非空（> 3000 字符）', len(html) > 3000, f'实际 {len(html)} 字符')
check('A5  STATIC_DIR 用 __file__ 定位（不依赖启动时的工作目录）',
      'Path(__file__)' in api_src and 'os.getcwd' not in api_src,
      'api.py 里没看到 Path(__file__) 定位')
check('A6  STATIC_DIR == src/static 且目录存在',
      api.STATIC_DIR.resolve() == (SRC / 'static').resolve() and api.STATIC_DIR.is_dir(),
      f'实际 {api.STATIC_DIR}')
check('A7  index.html 在磁盘上真实存在', HTML_PATH.is_file(), f'缺失：{HTML_PATH}')
check('A8  GET / 已注册在 api.py（@app.get）', "@app.get('/')" in api_src)

import hashlib                                                     # noqa: E402
_disk = HTML_PATH.read_bytes()
check('A9  服务端返回的字节 == 磁盘文件（md5 逐字节一致，不是"接口通了"就算）',
      hashlib.md5(r.content).hexdigest() == hashlib.md5(_disk).hexdigest(),
      f'返回 {len(r.content)}B / 磁盘 {len(_disk)}B —— 页面被另一份副本顶掉了')

# ============================================================ B 组：页面骨架
print('\nB 组：页面骨架')
check('B1  样式内联（有 <style>，无 <link rel="stylesheet">）',
      '<style>' in html and 'rel="stylesheet"' not in html)
check('B2  脚本内联（有 <script>，且没有 <script src=）',
      '<script>' in html and '<script src' not in html)

for _id in ['msgs', 'input', 'sendBtn', 'newBtn', 'sidBadge', 'userBadge', 'notice']:
    check(f'B3  必需元素 id="{_id}" 存在', f'id="{_id}"' in html)

check('B4  session_id 存 sessionStorage（关标签 = 新会话）',
      'sessionStorage' in html and 'SID_KEY' in html)
check('B5  user_id 存 localStorage（关浏览器 = 还是同一个人）',
      "localStorage, UID_KEY" in html and "UID_KEY   = 'va_user'" in html,
      '页面没把 user_id 挂到 localStorage')
check('B6  session_id 由 crypto.randomUUID() 生成（带非 secure context 兜底）',
      'randomUUID' in html and 'genId' in html)
check('B7  发送走 POST /chat', "fetch('/chat'" in html and "'POST'" in html)
check('B8  请求体同时带 session_id 与 user_id',
      "session_id: sid, user_id: uid" in html,
      '请求体里没同时看到 session_id 和 user_id')
check('B9  中文输入法回车不误发（e.isComposing）', 'isComposing' in html)

print('  —— 决策卡五键渲染（与 handle.py 里 steps.append 的键一一对应）')
for _k in ['s.epoch', 's.type', 's.tool', 's.args', 's.result']:
    check(f'B10 决策卡用到 {_k}', _k in html)
check('B11 轮数 = steps 条数、耗时用 elapsed_ms',
      'data.steps.length' in html and 'elapsed_ms' in html)
check('B12 决策卡默认收起（点标题栏才展开）',
      "'card collapsed'" in html and "classList.toggle('collapsed')" in html
      and '.card.collapsed .steps' in html,
      '决策卡不是默认折叠，或缺 toggle / 缺 .collapsed 的 CSS')

print('  —— 双 id 分工：新会话只换 session_id，不换身份')
_newbtn = re.search(r'newBtn\.addEventListener\(.*?\n  \}\);', html, re.S)
check('B13 「新会话」按钮只调用 resetSid()，绝不调用 resetUid()',
      bool(_newbtn) and 'resetSid()' in _newbtn.group(0)
      and 'resetUid' not in _newbtn.group(0),
      '新会话按钮把身份也换了 —— 待办会「消失」，退化成方案 A')
check('B14 resetSid / resetUid 分别只写各自的 store',
      "sessionStorage, SID_KEY" in html and "localStorage, UID_KEY" in html)
check('B15 页面加载时立刻画出两个 id（paintUser + paintSid）',
      'paintUser();' in html and 'paintSid();' in html)
check('B16 身份可复制、可粘贴恢复（单击复制 / 双击 prompt 切回旧 id）',
      'navigator.clipboard' in html and 'window.prompt' in html
      and 'dblclick' in html)
check('B17 隐私模式不炸：localStorage 读写包了 try/catch',
      'function readStore' in html and 'function writeStore' in html)

# ============================================================ C 组：零外链
print('\nC 组：零外链资源（防 CDN 不通 → 白屏）')
_ext = re.findall(r'(?:src|href)\s*=\s*["\']https?://[^\'"]+', html)
check('C1  没有 http(s) 外链资源（src=/href=）', not _ext, f'发现外链：{_ext}')
check('C2  没有 CSS @import', '@import' not in html)
check('C3  没有 <link> 引外部字体/样式',
      not re.search(r'<link[^>]+href\s*=\s*["\'](?!data:)', html),
      '页面里有指向外部文件的 <link>')

# ============================================================ D 组：错误码双向对齐
print('\nD 组：五个机器码在「页面」与「服务端」两侧对齐')
CODES = ['invalid_session_id', 'invalid_user_id', 'invalid_text',
         'model_unavailable', 'internal_error']
handle_src = (SRC / 'handle.py').read_text(encoding='utf-8')
server_src = api_src + handle_src
for c in CODES:
    check(f'D1  服务端会产出 {c}', c in server_src, f'{c} 在 api.py / handle.py 里都找不到')
    check(f'D2  页面会处理 {c}', c in html, f'页面里没有 {c}')
check('D3  页面把三类 400 分开了（sid 病 → 换会话；uid 病 → 换身份；text 病 → 提示重输）',
      "error === 'invalid_session_id'" in html
      and "error === 'invalid_user_id'" in html
      and "error === 'invalid_text'" in html)
_iu = html.find("error === 'invalid_user_id'")
_branch = html[_iu:_iu + 420]        # 只看这一段分支，别被后面的 newBtn 干扰
check('D4  invalid_user_id 分支里换的是身份（resetUid），不是会话',
      _iu != -1 and 'resetUid()' in _branch and 'resetSid()' not in _branch,
      'uid 非法却去换 session_id —— 下一句还是会被 400')

# ============================================================ E 组：回归
print('\nE 组：新增 GET / 没弄坏老路径')
SIX = {'session_id', 'elapsed_ms', 'ok', 'reply', 'steps', 'error'}
r2 = client.post('/chat', json={'session_id': 'default', 'text': '你好'})
b2 = r2.json()
check('E1  /chat 脏 sid 仍是 400', r2.status_code == 400, f'实际 {r2.status_code}')
check('E2  /chat 仍是六字段同形状', set(b2.keys()) == SIX,
      f'实际 {sorted(b2.keys())}')
check('E3  /chat 仍走 invalid_session_id', b2.get('error') == 'invalid_session_id',
      f"实际 {b2.get('error')!r}")
check('E4  chat 仍是同步 def（不是 async def，ContextVar 隔离靠它）',
      'def chat(' in api_src and 'async def chat(' not in api_src)
check('E5  index 是同步 def', 'def index(' in api_src and 'async def index(' not in api_src)
_r404 = client.get('/no-such-path')
check('E6  未定义路径仍是框架 404（不在六字段承诺内，属已知边界）',
      _r404.status_code == 404, f'实际 {_r404.status_code}')
check('E7  /chat 的 POST 方法没被 GET / 顶掉（方法不混）',
      client.get('/chat').status_code == 405, f'实际 {client.get("/chat").status_code}')
_r8 = client.post('/chat', json={'session_id': 'abc123', 'text': '   '})
check('E8  不带 user_id 不触发 invalid_user_id（老调用 curl/CLI 不受影响）',
      _r8.json().get('error') == 'invalid_text',
      f"实际 error={_r8.json().get('error')!r} —— 说明缺省 user_id 被判成脏值")
_r9 = client.post('/chat', json={'session_id': 'default', 'text': 'x', 'user_id': 'default'})
check('E9  user_id="default" → 400 invalid_user_id', 
      _r9.status_code == 400 and _r9.json().get('error') == 'invalid_user_id',
      f"实际 {_r9.status_code} / {_r9.json().get('error')!r}")
check('E10 api.py 里 user_id 校验排在 session_id 之前',
      -1 < api_src.find('invalid_user_id') < api_src.find('invalid_session_id'),
      '顺序反了：sid 先报错，前端换掉 session 后下一句仍 400（病根在 user_id）')
check('E11 校验失败的响应也是六字段（不破坏统一形状）', set(_r9.json().keys()) == SIX,
      f'实际 {sorted(_r9.json().keys())}')

# ============================================================ 收尾
print('\n' + '=' * 72)
print(f'零 API 结果：{PASS} 通过 / {FAIL} 失败')
sys.exit(1 if FAIL else 0)

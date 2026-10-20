'''
验收：session_id 清洗 —— 纯函数参照值 + 端到端落点

零副作用：OUTPUT_DIR 整体换成临时目录，跑完删掉，不碰真实 output/
跑法：python _verify_agent/accept_clean_sid.py
'''
import sys
import tempfile
import pathlib
import shutil
import json

sys.path.insert(0, r'D:/Project/voice_assistant/src')
import tools
from tools import clean_session_id

PASS, FAIL = 0, 0
FAILED = []

UUID = '9f3a1c2e-4b6d-4a8f-9c11-7e2b0d5a6f43'


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  ✅ {name}' + (f'  — {detail}' if detail else ''))
    else:
        FAIL += 1
        FAILED.append(name)
        print(f'  ❌ {name}' + (f'  — {detail}' if detail else ''))


print('=' * 74)
print('验收：session_id 清洗')
print('=' * 74)

# ---------------------------------------------------------------- A 组：纯函数
print('\nA 组：纯函数参照值（直接调 tools.clean_session_id）')

CASES = [
    (UUID,      UUID,      '标准 UUID 原样通过'),
    ('default', 'default', '普通白名单串'),
    ('u1',      'u1',      '短 id（验收/手测常用）—— 别被长度卡掉'),
    ('a-b',     'a-b',     '连字符在白名单内（UUID 自带 4 个）'),
    ('a_b',     'a_b',     '下划线在白名单内（口径 = [a-zA-Z0-9_-]）'),
    ('ABC-123', 'abc-123', '大小写归一'),
    ('',        'default', '空字符串'),
    ('   ',     'default', '纯空格'),
    ('../evil', 'default', '路径穿越：`..` + `/`'),
    ('..\\win', 'default', '路径穿越：反斜杠'),
    ('a/b',     'default', '斜杠'),
    ('C:',      'default', '冒号（Windows 盘符）'),
    ('中文',    'default', '中文'),
    ('a' * 64,  'a' * 64,  '边界：恰好 64 → 放行'),
    ('a' * 65,  'default', '边界：65 → 判废'),
    (None,      'default', 'None'),
    (123,       'default', '非字符串 int（不能抛异常）'),
]

for src, want, why in CASES:
    try:
        got = clean_session_id(src)
    except Exception as e:
        check(why, False, f'抛异常了：{type(e).__name__}: {e}')
        continue
    show = repr(src) if not isinstance(src, str) or len(src) <= 30 else repr(src[:12] + f'...(共{len(src)})')
    check(why, got == want, f'入={show} 出={got!r}' + ('' if got == want else f'  期望 {want!r}'))

# ------------------------------------------------------- B 组：端到端落点
print('\nB 组：端到端 —— 脏 id 到底落在哪（OUTPUT_DIR 指到临时目录）')
tmp = pathlib.Path(tempfile.mkdtemp(prefix='clean_sid_'))
tools.OUTPUT_DIR = tmp
print(f'  临时落点：{tmp}')

ENDER = [
    (UUID,       UUID,                 '标准 UUID → 自己的目录'),
    ('U1',       'u1',                 '大写 → 归一到 u1'),
    ('a_b',      'a_b',                '下划线 id → 自己的目录 a_b（白名单含 `_`）'),
    ('../evil',  'default',            '穿越 → 退回 default，且不许出 output/'),
    ('',         'default',            '空 → 必须落 default（不能是 output/ 本身！）'),
    (None,       'default',            'None → default'),
]

for src, want_dir, why in ENDER:
    tools.X.set(src)
    tools.save_file('memos.json', [{'id': 1, 'text': f'{src!r} 写的'}])
    # 找出刚才到底写进哪个目录
    written = [p for p in tmp.rglob('memos.json')]
    # 每轮清掉，保证下一轮只看新生成的
    got_rel = None
    for p in written:
        try:
            rel = p.relative_to(tmp).parent.as_posix()
        except ValueError:
            rel = '<越界>'
        if rel == want_dir or rel == '(none)':
            got_rel = rel
    # 更直接：直接算期望路径存不存在 + 检查有没有逃出 tmp
    expect_path = tmp / want_dir / 'memos.json'
    escaped = []
    for p in tmp.rglob('memos.json'):
        try:
            p.resolve().relative_to(tmp.resolve())
        except ValueError:
            escaped.append(str(p))
    check(why, expect_path.exists() and not escaped,
          f'期望 {want_dir}/memos.json 存在={expect_path.exists()}，越界文件={escaped or "无"}')
    for p in tmp.rglob('memos.json'):
        p.unlink()

print(f'\n  临时目录里最终剩下：{sorted(p.relative_to(tmp).as_posix() for p in tmp.rglob("*"))}')

shutil.rmtree(tmp, ignore_errors=True)

# ------------------------------------------------- C 组：入口函数层 静态+动态
print('\nC 组：入口函数（run_agent）—— 清洗是否真的在 `set` 之前、且 STORE 也用同一个值')

src_txt = pathlib.Path(r'D:/Project/voice_assistant/src/handle.py').read_text(encoding='utf-8')
lines = src_txt.splitlines()
# 主体已从 handle 搬进 run_agent → 按「函数定义行」定位，不再写死行号
start = next((i for i, ln in enumerate(lines) if ln.startswith('def run_agent(')), None)
head = ([f'{i + 1}: {lines[i].strip()}' for i in range(start, start + 4)]
        if start is not None else ['未找到 def run_agent'])


def _idx_in_head(pat, span=8):
    """在函数开头 span 行里找第一次出现的行号；找不到返回 -1。"""
    if start is None:
        return -1
    for i in range(start, min(start + span, len(lines))):
        if pat in lines[i]:
            return i
    return -1


_i_clean = _idx_in_head('clean_session_id(session_id)')
_i_xset = _idx_in_head('X.set(session_id)')
_i_uset = _idx_in_head('U.set(')
check('run_agent 开头先清洗、再 X.set（顺序对，不写死行号）',
      0 <= _i_clean < _i_xset,
      f'清洗行={_i_clean}  X.set 行={_i_xset}  / ' + ' / '.join(head))
check('U.set 也在开头（用户维度同样每轮必设，防线程池残留）',
      _i_uset > 0, f'U.set 行={_i_uset}  / ' + ' / '.join(head))

_imp = next((ln for ln in lines if ln.startswith('from tools import')), '')
_imp_names = [_n.strip() for _n in _imp.split('import', 1)[-1].split(',')] if _imp else []
check('导入的是裸 import（同一个 X 对象，不是 from src.tools）',
      'X' in _imp_names and 'clean_session_id' in _imp_names and 'src.tools' not in _imp,
      f'实际导入行：{_imp!r}  解析出 {_imp_names}')

try:
    import handle as H
    from schemas import RouterDecision

    H.route = lambda t, h=None: RouterDecision(type='chat', tool=None, args={}, text=None)
    H.chat = lambda t, h=None: '嗯嗯'
    H.STORE.clear()
    H.handle('随便说点什么', '../evil')
    H.handle('再来一句', 'U1')
    print(f"  （假 route/chat，不消耗 API；handle 跑完后 STORE 的 key = {sorted(H.STORE)}）")
    check('handle 收到脏 id → STORE 的 key 是清洗后的值',
          sorted(H.STORE) == ['default', 'u1'], f'实际 {sorted(H.STORE)}')
except Exception as e:
    check('handle 层动态检查', False, f'{type(e).__name__}: {e}')

print('\n' + '=' * 74)
print(f'结果：{PASS} 通过 / {FAIL} 失败')
if FAILED:
    print('失败项：')
    for n in FAILED:
        print(f'  - {n}')

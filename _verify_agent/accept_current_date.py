'''
当前日期注入（方案 A）- 零 API 验收

盯六件事：
A 日期段在不在、格式对不对（只该有 1 处）
B 日期值 == 独立算出来的"今天"
C 日期值 与 tools._get_current_time() 是同一天（同源）
   —— 否则会出现「prompt 说今天是 10 月 15 号、用户一问工具说 16 号」这种自相矛盾
D 除日期段外，全文与「动手前冻结的基线」逐行一致（证明只加了一段，没顺手动别的）
E 日期段不与黄金集任何样本互为子串（泄题双检）
F 十个工具名一个不少
G 日期在调用时取（不是 import 时定死）

日期段格式（以现有代码为准，汉字写法）：
    # 当前日期
    二零二六年十月十五日星期四

跑法（项目根）：
    python _verify_agent/accept_current_date.py              # 正式验收
    python _verify_agent/accept_current_date.py --selftest   # 自检模式：用内存伪造的"已改好" prompt 验证脚本自身
'''

import sys, os, re, json
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'src'))

import llm_router
import registry
import tools

BASELINE_PATH = os.path.join(HERE, 'prompt_baseline_before_date.txt')
GOLDEN_PATH = os.path.join(ROOT, 'bench', 'golden_set.json')

# 日期段：整行形如「二零二六年十月十五日星期四」（汉字数字，日与星期之间无标点，行尾可带空白）
DATE_RE = re.compile(
    r'^([零一二三四五六七八九]{4})年([一二三四五六七八九十]+)月'
    r'([一二三四五六七八九十]+)日星期([一二三四五六日])[ \t]*$', re.M)
TITLE_RE = re.compile(r'^#[ \t]*当前日期[ \t]*$', re.M)

CN_DIGIT = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9}
CN_NUM = '零一二三四五六七八九'

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


def cn_to_int(s: str) -> int:
    """汉字数字 -> 整数，覆盖 1~31（月/日）"""
    if '十' in s:
        head, _, tail = s.partition('十')
        tens = CN_DIGIT[head] if head else 1
        ones = CN_DIGIT[tail] if tail else 0
        return tens * 10 + ones
    return CN_DIGIT[s]


def cn_to_year(s: str) -> str:
    """'二零二六' -> '2026'"""
    return ''.join(str(CN_DIGIT[c]) for c in s)


def year_to_cn(y: int) -> str:
    """2026 -> '二零二六'"""
    return ''.join(CN_NUM[int(c)] for c in str(y))


def int_to_cn(n: int) -> str:
    """1~31 -> 汉字（十 / 十五 / 二十 / 三十一）"""
    if n < 10:
        return CN_NUM[n]
    if n == 10:
        return '十'
    if n < 20:
        return '十' + CN_NUM[n % 10]
    if n % 10 == 0:
        return CN_NUM[n // 10] + '十'
    return CN_NUM[n // 10] + '十' + CN_NUM[n % 10]


def format_today() -> str:
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    return (f'{year_to_cn(now.year)}年{int_to_cn(now.month)}月'
            f'{int_to_cn(now.day)}日星期{"一二三四五六日"[now.isoweekday() - 1]}')


def normalize(text: str) -> list:
    """去掉日期段/标题行/空行/行尾空格，只留有效行 —— 用来做 D 组的逐行比对"""
    text = DATE_RE.sub('', text)
    text = TITLE_RE.sub('', text)
    return [line.rstrip() for line in text.split('\n') if line.strip()]


def gather_prompt() -> str:
    return llm_router._build_prompt()


def selftest_prompt() -> str:
    """伪造一个「已经改好」的 prompt：在「# 判断规则」前插一段当前日期"""
    base = llm_router._build_prompt()
    base = DATE_RE.sub('', base)
    base = TITLE_RE.sub('', base)
    return base.replace('# 判断规则', f'# 当前日期\n{format_today()}\n\n# 判断规则', 1)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    prompt = selftest_prompt() if mode == '--selftest' else gather_prompt()
    if mode == '--selftest':
        print('（自检模式：用内存伪造的「已改好」prompt 验证脚本自身逻辑，不代表你的文件已改好）')

    with open(BASELINE_PATH, 'r', encoding='utf-8') as f:
        baseline = f.read()

    print('A 组：日期段存在与格式')
    hits = DATE_RE.findall(prompt)
    check(len(hits) == 1, '恰好找到 1 处日期段', f'实际找到 {len(hits)} 处')
    if not hits:
        print('  —— 没找到日期段：说明日期那行还没加进去（或格式与约定不符）')
        print('     约定格式（独立成行）：二零二六年十月十五日星期四')
        return finish()

    year_s, month_s, day_s, weekday = hits[0]
    year, month, day = int(cn_to_year(year_s)), cn_to_int(month_s), cn_to_int(day_s)
    print(f'  —— 解析出：{year}年{month}月{day}日，星期{weekday}')

    print('B 组：日期值 == 独立算出来的今天')
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    check((year, month, day) == (now.year, now.month, now.day),
          '年月日 == 今天', f'prompt={year}-{month}-{day}，实际={now.year}-{now.month}-{now.day}')
    check(weekday == '一二三四五六日'[now.isoweekday() - 1],
          '星期 == 今天', f'prompt={weekday}，实际={"一二三四五六日"[now.isoweekday() - 1]}')

    print('C 组：与 get_current_time 工具同源')
    tool_date = tools._get_current_time().split(' ')[0]
    check(f'{year:04d}-{month:02d}-{day:02d}' == tool_date,
          'prompt 里的日期 与 工具返回的日期 是同一天', f'prompt={year}-{month}-{day}，工具={tool_date}')

    print('D 组：除日期段外，全文与基线逐行一致')
    now_lines = normalize(prompt)
    base_lines = normalize(baseline)
    check(now_lines == base_lines, '有效行完全一致（只多了一段日期，别的没动）',
          f'当前 {len(now_lines)} 行 vs 基线 {len(base_lines)} 行')
    if now_lines != base_lines:
        import difflib
        for diff in list(difflib.unified_diff(base_lines, now_lines, 'baseline', 'current', lineterm=''))[:30]:
            print(f'      {diff}')

    print('E 组：日期段不与黄金集样本互为子串（泄题双检）')
    with open(GOLDEN_PATH, 'r', encoding='utf-8') as f:
        golden = json.load(f)
    date_line = format_today()
    leaked = [case['text'] for case in golden
              if case['text'] in date_line or date_line in case['text']]
    check(len(leaked) == 0, f'{len(golden)} 条样本零重合', f'重合：{leaked}')

    print('F 组：工具名一个不少')
    for tool in registry.TOOLS_LIST:
        check(tool['name'] in prompt, f'工具 {tool["name"]} 在 prompt 里')

    print('G 组：日期在调用时取，不是 import 时定死')
    check(not hasattr(llm_router, 'CURRENT_DATE'),
          'llm_router 没有模块级 CURRENT_DATE（常驻进程跨零点不会过期）',
          '发现模块级 CURRENT_DATE：进程活得比一天久就会用昨天的日期')

    return finish()


def finish():
    print()
    print('=' * 60)
    total = PASS + FAIL
    print(f'结果：{PASS}/{total} 通过' + ('' if FAIL == 0 else f'，{FAIL} 项失败'))
    print('=' * 60)
    return 0 if FAIL == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

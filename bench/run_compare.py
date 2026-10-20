'''
框架对照实验：同一个模型、同一批样本、同一份工具说明，只换「结构化输出的拿法」

  A_手写         —— prompt 里列工具 + response_format=json_object → 文本解析（现状）
  B1_照搬prompt  —— 原生 tools= 手写 client，prompt 直接裁自 A 组（保留 JSON 语境）
  B2_配平prompt  —— 原生 tools= 手写 client，prompt 重写为机制中立
  C1_lc照搬      —— LangChain bind_tools，prompt 直接用 B1 那份（import，不复制）
  C2_lc配平      —— LangChain bind_tools，prompt 直接用 B2 那份（import，不复制）

这是 2×2 因子设计（机制 × prompt），配上 A 组当基线：

               JSON 语境 prompt     机制中立 prompt
  手写 client      A_手写              （不存在）
  原生 tools       B1                  B2
  LangChain        C1                  C2

三个差值各有含义：
  A  → B1  照搬现有 prompt 换机制的代价
  B1 → B2  把 prompt 配平能救回多少
  B1 → C1  换成框架（同机制同 prompt）的损耗 —— 这一项是「LangChain 值不值得用」的直接答案
  B2 → C2  同上，换个 prompt 再验一次（防止 C1 的结论是 prompt 凑巧）
  C1 → C2  框架内部再过一遍 prompt 配平效应，看是否复现 B1→B2

C1/C2 的 prompt 是 import 来的同一份常量，不是复制粘贴 —— 保证与 B1/B2 一字不差。

评分逻辑不复制：judge / summarize / group_rows 全部从 run_eval.py 导入。
两边口径一旦分叉，这个对照就白做了。
'''

import sys, os, json, math

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', 'src'))
sys.path.insert(0, _HERE)          # 为了 import 同目录的 router_fc / tool_schema / router_lc

from run_eval import load_cases, judge, summarize, group_rows, CASES_PATH
import llm_router as A
import router_fc as B1             # 原生 tools + 照搬 A 组 prompt（裁三段）
import router_fc2 as B2            # 原生 tools + 机制中立的 prompt（配平版）
import llm_client

try:
    import router_lc as C
except ImportError as e:
    C = None
    _C_ERR = f'{type(e).__name__}: {e}'

OUT_PATH = os.path.join(_HERE, 'compare_result.json')


# ---------------------------------------------------------------- 组注册
class _PromptFixed:
    '''把「用哪个 prompt」固定成一个带 route 的假模块。

    judge() 只做 router.route(case['text'])，所以只要能提供 route 就行。
    这样 C1/C2 共用 router_lc.py 的同一份代码，只有 prompt 不同 ——
    「框架」这个变量在两组之间完全没动。
    '''

    def __init__(self, mod, prompt, label):
        self._mod = mod
        self._prompt = prompt
        self._label = label

    def route(self, text, history=None):
        return self._mod.route(text, history, prompt=self._prompt)

    def __repr__(self):
        return self._label


def build_routers(prompt_json, prompt_neutral) -> dict:
    routers = {'A_手写': A, 'B1_照搬prompt': B1, 'B2_配平prompt': B2}
    if C is not None:
        routers['C1_lc照搬'] = _PromptFixed(C, prompt_json, 'C1_lc照搬')
        routers['C2_lc配平'] = _PromptFixed(C, prompt_neutral, 'C2_lc配平')
    else:
        print(f'[跳过 C1/C2] router_lc 导入失败 → {_C_ERR}')
    return routers


def check_prompt_sync() -> bool:
    '''确认 B1/B2/C 用的是同一份 prompt 常量。

    C1/C2 靠 import 复用 router_fc/router_fc2 的常量，理论上不可能漂移；
    但 router_lc 若哪天自己抄了一份，这里要能立刻炸出来。
    '''
    if C is None:
        return True
    ok = (C.PROMPT_JSON is B1.SYSTEM_PROMPT) and (C.PROMPT_NEUTRAL is B2.SYSTEM_PROMPT)
    print(f'prompt 同一对象：C1↔B1 {C.PROMPT_JSON is B1.SYSTEM_PROMPT}'
          f'　C2↔B2 {C.PROMPT_NEUTRAL is B2.SYSTEM_PROMPT}')
    if not ok:
        print('⚠️  router_lc 的 prompt 不是 import 来的同一对象 —— 2×2 对照失去意义')
    return ok


# ---------------------------------------------------------------- 健康探针
def health_check() -> bool:
    '''跑大批量之前先确认主模型活着。

    DeepSeek 余额耗尽会 402，A 组 route() 里 except 静默降级成 chat →
    分数凭空掉一大截，看起来像"代码改坏了"。这个洞 10-17 踩过一次。
    '''
    try:
        llm_client.DEEPSEEK_CLIENT.chat.completions.create(
            messages=[{'role': 'user', 'content': 'hi'}],
            **llm_client.PROVIDERS[0]['private'],
            max_tokens=1,
            timeout=8,
        )
        print('主模型 DeepSeek：可用')
        return True
    except Exception as e:
        print(f'⚠️  主模型不可用：{type(e).__name__}: {e}')
        print('    A 组会把失败静默降级成 chat，分数会假跌 —— 先解决这个再跑。')
        return False


# ---------------------------------------------------------------- 单组执行
def run_one(router, cases: list) -> list:
    '''逐条调用；单条抛异常只记这一条，不打断整批。

    B / C 组定义为「异常不降级」，所以它们一定会把接口错误抛到这里。
    如果不接住，一条超时就能让 112 条白跑。
    '''
    rows = []
    for case in cases:
        try:
            row = judge(case, router)
            row['error'] = None
        except Exception as e:
            has_args = case.get('args') is not None
            row = {
                'text': case['text'],
                'expect_type': case['type'],
                'expect_tool': case['tool'],
                'got_type': None,
                'got_tool': None,
                'type_hit': False,
                'tool_hit': False,
                'all_hit': False,
                'args_hit': False if has_args else None,
                'error': f'{type(e).__name__}: {e}',
            }
        rows.append(row)
    return rows


# ---------------------------------------------------------------- McNemar
def mcnemar(rows_x: list, rows_y: list) -> tuple:
    '''配对卡方，配对单位 = 这一条「分流 + 工具」是否全对。

    只数两边判定不同的样本：b = 前者对后者错，c = 前者错后者对。
    连续性校正：chi2 = (|b-c|-1)^2 / (b+c)，且校正后不许为负（b≈c 时记 0）。

    p 用 erfc 算：自由度 1 时，卡方分布的生存函数正好等于 erfc(sqrt(chi2/2))，
    数学上完全等价，省掉一个 scipy 依赖。
    '''
    b = sum(1 for x, y in zip(rows_x, rows_y) if x['all_hit'] and not y['all_hit'])
    c = sum(1 for x, y in zip(rows_x, rows_y) if not x['all_hit'] and y['all_hit'])
    if b + c == 0:
        return b, c, 0.0, 1.0
    chi2 = max(0.0, abs(b - c) - 1) ** 2 / (b + c)
    p = math.erfc(math.sqrt(chi2 / 2))
    return b, c, chi2, p


def verdict(p: float) -> str:
    if p < 0.01:
        return '差异极显著'
    if p < 0.05:
        return '差异显著'
    return '无显著差异'


# ---------------------------------------------------------------- 输出
def rate(hit: int, total: int) -> str:
    return f'{hit / total * 100:.2f}%' if total else '—'


def report(rows_by_group: dict, cases: list):
    names = list(rows_by_group)
    print()
    print('=' * 78)
    print(f'框架对照　样本 {len(cases)} 条　同一模型 / temperature=0 / 同一份工具说明')
    print('=' * 78)

    summaries = {k: summarize(v) for k, v in rows_by_group.items()}

    print(f'{"组":<14}{"总数":>6}{"分流":>10}{"完整":>10}{"参数":>16}')
    print('-' * 78)
    for k, s in summaries.items():
        args_part = f'{rate(s["args_hits"], s["args_total"])} ({s["args_hits"]}/{s["args_total"]})'
        print(f'{k:<14}{s["total"]:>6}{rate(s["type_hits"], s["total"]):>10}'
              f'{rate(s["all_hits"], s["total"]):>10}{args_part:>16}')

    # 按期望工具分组，看差异集中在哪个工具
    print()
    print('按工具分组（完整命中 / 总数）')
    print('-' * 78)
    grouped = {k: group_rows(v) for k, v in rows_by_group.items()}
    all_tools = sorted({t for g in grouped.values() for t in g})
    print(f'{"工具":<18}' + ''.join(f'{n:>16}' for n in names))
    for tool in all_tools:
        line = f'{tool:<18}'
        for name in names:
            g = grouped[name].get(tool)
            cell = f'{g["hits"]}/{g["total"]}' if g else '—'
            line += f'{cell:>16}'
        print(line)

    # 失败明细
    for name, rows in rows_by_group.items():
        fails = [r for r in rows if not r['all_hit'] or r['args_hit'] is False]
        print()
        print(f'{name} 失败明细（{len(fails)} 条）')
        print('-' * 78)
        if not fails:
            print('  （空）')
        for r in fails:
            tag = r['error'] or f'args_hit={r["args_hit"]}'
            print(f'  {r["text"]}')
            print(f'      期望 {r["expect_type"]}/{r["expect_tool"]}　'
                  f'实际 {r["got_type"]}/{r["got_tool"]}　{tag}')

    # McNemar 两两配对
    print()
    print('McNemar 配对检验（配对单位 = 分流 + 工具都判对）')
    print('-' * 78)
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            x, y = names[i], names[j]
            b, c, chi2, p = mcnemar(rows_by_group[x], rows_by_group[y])
            pairs.append({'pair': f'{x} vs {y}', 'b': b, 'c': c,
                          'chi2': round(chi2, 4), 'p': round(p, 4),
                          'verdict': verdict(p)})
            if b + c == 0:
                print(f'{x} vs {y}: 两组判定完全一致（b=0 c=0）→ 无差异可言')
            else:
                print(f'{x} vs {y}: b={b} c={c} → χ²={chi2:.2f} p={p:.3f} → {verdict(p)}')
                print(f'    念法：假如两套方法其实一样好，光凭运气看到这个差距的概率是 {p * 100:.1f}%')

    return summaries, grouped, pairs


def main():
    cases = load_cases(CASES_PATH)
    print(f'样本：{len(cases)} 条（{CASES_PATH}）')
    if not check_prompt_sync():
        print('\n已中止：先让 router_lc 复用 router_fc / router_fc2 的 prompt 常量。')
        return
    if not health_check():
        print('\n已中止：先修模型可用性，否则跑出来的数字不可信。')
        return

    routers = build_routers(B1.SYSTEM_PROMPT, B2.SYSTEM_PROMPT)
    rows_by_group = {}
    for name, router in routers.items():
        print(f'\n正在跑 {name} …')
        rows_by_group[name] = run_one(router, cases)

    summaries, grouped, pairs = report(rows_by_group, cases)

    payload = {
        'sample_size': len(cases),
        'cases_path': CASES_PATH,
        'summary': summaries,
        'groups': grouped,
        'mcnemar': pairs,
        'rows': rows_by_group,
    }
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f'\n明细已写入 {OUT_PATH}')


if __name__ == '__main__':
    main()

'''跑新验收集（holdout）：五组机制 × 57 条，不调参，只出一次数。

与 run_compare.py 的区别：
  - 样本换成 bench/holdout_set.json（写标准答案时没看过任何模型输出）
  - 不写回 compare_result.json，另存 holdout_result.json
  - 其余全部复用：judge 判卷、McNemar、组注册、健康探针

用法：cd bench && python run_holdout.py
'''
import os
import sys
import json

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', 'src'))
sys.path.insert(0, _HERE)

import run_compare as RC
from run_eval import load_cases, summarize, group_rows

HOLDOUT_PATH = os.path.join(_HERE, 'holdout_set.json')
OUT_PATH = os.path.join(_HERE, 'holdout_result.json')


def main():
    cases = load_cases(HOLDOUT_PATH)
    print(f'新验收集：{len(cases)} 条（{HOLDOUT_PATH}）')
    print('⚠️ 这一集在写标准答案时没有跑过任何模型；下面的结果不改标答、不回调 prompt。')

    if not RC.check_prompt_sync():
        print('\n已中止：prompt 对照条件被破坏。')
        return
    if not RC.health_check():
        print('\n已中止：主模型不可用。')
        return

    routers = RC.build_routers(RC.B1.SYSTEM_PROMPT, RC.B2.SYSTEM_PROMPT)
    rows_by_group = {}
    for name, router in routers.items():
        print(f'\n正在跑 {name} …')
        rows_by_group[name] = RC.run_one(router, cases)

    summaries, grouped, pairs = RC.report(rows_by_group, cases)

    payload = {
        'sample_size': len(cases),
        'cases_path': HOLDOUT_PATH,
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

'''
搜索样本 query 探针（只看 query 质量，不打分）

run_eval.py 里给 search 样本只评 type / tool，不评 query ——
因为「query 提炼得够不够短」这件事没有唯一标准答案，硬比对会造出一堆假失败。
但 query 又是搜索准不准的另一半，所以要有个地方把它打印出来，人工过目一遍。

用法：python bench/probe_search_query.py
'''

import sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import llm_router as llm

CASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'golden_set.json')


def main():
    with open(CASES_PATH, 'r', encoding='utf-8') as f:
        cases = json.load(f)
    targets = [case for case in cases if case.get('tool') == 'web_search']
    print(f'共 {len(targets)} 条搜索样本，逐条打印模型生成的 query：')
    print('=' * 60)
    for case in targets:
        decision = llm.route(case['text'])
        query = decision.args.get('query', '')
        flag = ''
        plain_query = query.replace(' ', '')
        if decision.tool != 'web_search':
            flag = f'  ← 没判成搜索（实际 {decision.type}/{decision.tool}）'
        elif plain_query in case['text'] and len(plain_query) >= len(case['text']) * 0.8:
            # query 去空格后整段还在原句里 → 说明只是把原句抄了一遍，没提炼
            flag = '  ← 疑似照抄原句，没提炼'
        print(f"原句：{case['text']}")
        print(f"  query = {query!r}{flag}")
        print('-' * 60)


if __name__ == '__main__':
    main()

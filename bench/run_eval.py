'''
测评
'''

import sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import fake_router as fake, keyword_router as keyword, llm_router as llm

CASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'golden_set.json')

DECISION = {'fake': fake, 'keyword': keyword, 'llm': llm}

# 加载验证集
def load_cases(path: str) -> list[dict]:
    with open(path, 'r', encoding='utf-8') as f:
        cases = json.load(f)
    return cases


def judge (case: dict, decision) -> dict:
    router = decision.route(case['text'])
    result = {
        'text': case['text'],
        'expect_type': case['type'],
        'expect_tool': case['tool'],
        'got_type': router.type,
        'got_tool': router.tool,
        'type_hit': bool(case['type'] == router.type),
        'tool_hit': bool(case['tool'] == router.tool),
        'all_hit': bool(case['type'] == router.type and case['tool'] == router.tool ),
    }
    evidence = case.get('args', None)
    if evidence is not None:
        # 通用比对：样本里写了哪几个参数，就比哪几个（现在 mostly 是 lineno，
        # 以后要评 query / keyword 也不用改这里）
        result['args_hit'] = all(router.args.get(key) == value for key, value in evidence.items())
    else:
        result['args_hit'] = None
    return result


def run(router, cases: list) -> list[dict]:
    result_list = []
    for case in cases:
        result = judge(case, router)
        result_list.append(result)
    return result_list


def summarize(rows: list[dict]) -> dict:
    # args_hit 是三态：True / False / None。None 表示"这条没有参数标准答案"，不能进分母
    args_rows = [row for row in rows if row.get('args_hit') is not None]
    return {
        'total': len(rows),
        'type_hits': sum(row.get('type_hit', 0) for row in rows),
        'tool_hits': sum(row.get('tool_hit', 0) for row in rows),
        'all_hits': sum(row.get('all_hit', 0) for row in rows),
        'args_total': len(args_rows),
        'args_hits': sum(1 for row in args_rows if row['args_hit']),
    }


def group_rows(rows: list[dict]) -> dict:
    '''按「期望工具」分组统计，用来看单个工具准不准（尤其新加的工具会不会拖后腿）'''
    groups = {}
    for row in rows:
        key = row['expect_tool'] or 'chat'
        group = groups.setdefault(key, {'total': 0, 'hits': 0})
        group['total'] += 1
        if row['type_hit'] and row['tool_hit']:
            group['hits'] += 1
    return groups


def main():
    cases = load_cases(CASES_PATH)
    fail_dict = {}
    rows_dict = {}
    print('对比表:')
    print('router\t总数\t分流准确率\t完整准确率\t参数准确率')
    for key, value in DECISION.items():
        result_list = run(value, cases)
        rows_dict[key] = result_list
        fail_list = [item for item in result_list if item['type_hit'] == False or item['tool_hit'] == False or item['args_hit'] == False]
        fail_dict[key] = fail_list
        summary = summarize(result_list)
        if summary['args_total']:
            args_rate = summary['args_hits'] / summary['args_total'] * 100
        else:
            args_rate = 0.0
        print(f'{key}\t{summary["total"]}\t{summary["type_hits"]/summary["total"]*100}%\t{summary["all_hits"]/summary["total"]*100}%\t{args_rate}% ({summary["args_hits"]}/{summary["args_total"]})')
        print('-----------------------')
    print('llm 分组准确率（按样本期望的工具分组）:')
    for name, group in group_rows(rows_dict['llm']).items():
        print(f'  {name:<18}{group["hits"]}/{group["total"]}')
    print('-----------------------')
    for key, value in fail_dict.items():
        print(f'{key} 失败明细:')
        for fail in value:
            print(f'{fail["text"]}\t期望 {fail["expect_type"]}/{fail["expect_tool"]}\t实际 {fail["got_type"]}/{fail["got_tool"]}')
        print('-----------------------')


if __name__ == '__main__':
    main()







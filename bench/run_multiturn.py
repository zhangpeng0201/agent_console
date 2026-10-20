'''
多轮测评

与 run_eval.py 的分工：
- run_eval.py 跑的是单轮（golden_set.json），每条样本互相独立；
- 本文件跑的是多轮（multiturn_set.json），一条数据 = 一段对话，
  后面几轮要带着前面几轮的历史一起判断。

测的是 route(text, history) 这一层：纯函数、有副作用为零、可复现。
history 的形状完全照 handle.py 往 HISTORY 里塞的样子拼（见 build_history）。

只评 type / tool / lineno 这类有唯一标准答案的字段；
args.text / args.query 的“写得好不好”是主观的，不在这里评（另有探针打印出来人工看）。
'''

import sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import llm_router as llm

CASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'multiturn_set.json')


def load_dialogs(path: str) -> list[dict]:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_history(done_turns: list[dict]) -> list[dict]:
    '''把「已经发生过的轮次」拼成 route 认的历史。

    必须和 handle.py 第 73-78 行的写法一致：
      user 那格 = 原话
      assistant 那格 = decision 的 json + 换行 + （已回复用户：X）
    '''
    history = []
    for turn in done_turns:
        decision = turn['assistant_decision']
        history.append({'role': 'user', 'content': turn['user']})
        history.append({'role': 'assistant', 'content': json.dumps(
            {'type': decision['type'], 'tool': decision['tool'], 'args': decision['args']},
            ensure_ascii=False) + f'\n（已回复用户：{turn["assistant_reply"]}）'})
    return history


def judge_turn(turn: dict, done_turns: list[dict]) -> dict:
    history = build_history(done_turns)
    router = llm.route(turn['user'], history)
    # 每一轮都评：第一轮拿 assistant_decision 当标准答案（那本来就是我写好的“真实发生过”）
    expect = turn.get('expect') or turn['assistant_decision']
    row = {
        'user': turn['user'],
        'expect_type': expect['type'],
        'expect_tool': expect['tool'],
        'got_type': router.type,
        'got_tool': router.tool,
        'type_hit': bool(expect['type'] == router.type),
        'tool_hit': bool(expect['tool'] == router.tool),
    }
    evidence = expect.get('args', None)
    if evidence is not None:
        row['args_hit'] = all(router.args.get(key) == value for key, value in evidence.items())
    else:
        row['args_hit'] = None
    return row


def run_dialog(dialog: dict) -> list[dict]:
    rows = []
    done_turns = []
    for turn in dialog['turns']:
        rows.append(judge_turn(turn, done_turns))
        done_turns.append(turn)
    return rows


def summarize(rows: list[dict]) -> dict:
    args_rows = [row for row in rows if row.get('args_hit') is not None]
    return {
        'total': len(rows),
        'type_hits': sum(row['type_hit'] for row in rows),
        'tool_hits': sum(row['tool_hit'] for row in rows),
        'all_hits': sum(1 for row in rows if row['type_hit'] and row['tool_hit']),
        'args_total': len(args_rows),
        'args_hits': sum(1 for row in args_rows if row['args_hit']),
    }


def main():
    dialogs = load_dialogs(CASES_PATH)
    all_rows = []
    dialog_correct = 0
    dialog_total = len(dialogs)

    print('逐条对话:')
    for dialog in dialogs:
        rows = run_dialog(dialog)
        all_rows.extend(rows)
        ok = all(row['type_hit'] and row['tool_hit'] and row['args_hit'] is not False for row in rows)
        dialog_correct += 1 if ok else 0
        print(f"{'[OK] ' if ok else '[NG] '}{dialog['name']}（{len(rows)}轮）")
        for row in rows:
            flags = ('' if row['type_hit'] else ' type✗') + ('' if row['tool_hit'] else ' tool✗')
            if row['args_hit'] is False:
                flags += ' args✗'
            if flags:
                print(f"    {row['user']}  期望 {row['expect_type']}/{row['expect_tool']}  实际 {row['got_type']}/{row['got_tool']}{flags}")
        print('  ' + '-' * 40)

    summary = summarize(all_rows)
    print('汇总:')
    print(f"  轮次总数        {summary['total']}")
    print(f"  分流准确率      {summary['type_hits']}/{summary['total']} = {summary['type_hits'] / summary['total'] * 100:.1f}%")
    print(f"  工具准确率      {summary['tool_hits']}/{summary['total']} = {summary['tool_hits'] / summary['total'] * 100:.1f}%")
    print(f"  整轮全对率      {summary['all_hits']}/{summary['total']} = {summary['all_hits'] / summary['total'] * 100:.1f}%")
    if summary['args_total']:
        args_rate = summary['args_hits'] / summary['args_total'] * 100
    else:
        args_rate = 0.0
    print(f"  参数准确率      {summary['args_hits']}/{summary['args_total']} = {args_rate:.1f}%")
    print(f"  整条对话全对率  {dialog_correct}/{dialog_total} = {dialog_correct / dialog_total * 100:.1f}%")


if __name__ == '__main__':
    main()

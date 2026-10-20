'''
认真版的关键词路由（对照组）

与 fake_router 的区别：
- fake_router 是任务 1 的产物，只会输出 add_memo / chat 两种结果，
  在 todo / list 类样本上「理论上不可能答对」→ 拿它当基线，对比不公平。
- 本模块覆盖全部 4 个工具 + chat，与 llm_router 的能力值域一致，
  这样两个 router 的差距才只反映「方法差异」。

规则约束：所有规则写成「什么样的说法归哪类」，不针对任何具体测试句子。
'''

import re

from schemas import RouterDecision


# ── 第 1 层：干扰片段 ───────────────────────────────────────────
# 谈论「记忆能力 / 记忆状态」的说法，不是「让我记东西」。
# 先把它们从文本里抠掉，后面的动作词判断就不会被误触发。
# 这一层是它区别于 fake_router 的关键：fake_router 只会 '记' in text，
# 于是「今天记性真差」这种感叹也被当成命令。
MEMORY_TALK = ['记不记得', '记不得', '记不起来', '记性', '记忆', '记得吗', '记住没']


# ── 第 2 层：查询 ──────────────────────────────────────────────
QUERY_WORDS = ['哪些', '什么', '多少', '几条', '几个', '啥']          # 疑问词
QUERY_DOMAIN = ['记', '备忘', '待办', '事情', '东西', '任务', '安排']   # 问的是「记忆里的东西」
TODO_DOMAIN = ['待办', '没做', '没完成', '还没', '要做']                # 问的是「待办」而不是「备忘」


# ── 第 3 层：命令 ──────────────────────────────────────────────
ACTION_WORDS = ['记', '存', '备忘', '提醒', '别忘']                    # 让我去做事的动作词
TODO_HINT = ['提醒', '开会', '会议', '面试', '聚会', '上班', '上学', '预约']
TIME_HINT = ['明天', '后天', '大后天', '下周', '下星期', '下个月', '明年']
TIME_HINT += [f'周{d}' for d in '一二三四五六日'] + [f'星期{d}' for d in '一二三四五六日']
# 注意：「今天」故意不在 TIME_HINT 里 —— 它是当前时间，不是将来要做的事。
# 所以「记一下今天是他的生日」判 add_memo，而「记一下明天下午三点开会」判 add_todo。


# ── 剥掉句首的动作词，用来填 args.text（本轮不评 args，但形状要对）──
_LEAD = re.compile(
    r'^(帮我|请|麻烦|你|给我)?\s*'
    r'(记一下|记下来|记录一下|记得提醒我|记得提醒|记下|记'
    r'|存一下|存下来|存下|存'
    r'|提醒我|提醒'
    r'|别忘了|别忘'
    r'|备忘一下|备忘)'
    r'[一了下：:，,、\s]*'
)


def _hit(text: str, words: list) -> bool:
    '''text 里是否出现了 words 中的任意一个'''
    return any(w in text for w in words)


def route(text: str) -> RouterDecision:
    # 先抠掉「谈论记忆」的片段，避免误触发
    core = text
    for w in MEMORY_TALK:
        core = core.replace(w, '')

    # ① 查询：有疑问词，且在问「记忆里的东西」
    #    必须排在命令前面 —— 「我记了什么」含「记」字，先判命令就必错
    if _hit(core, QUERY_WORDS) and _hit(core, QUERY_DOMAIN):
        tool = 'list_todos' if _hit(core, TODO_DOMAIN) else 'list_memos'
        return RouterDecision(type='command', tool=tool, args={})

    # ② 命令：有动作词
    if _hit(core, ACTION_WORDS):
        # 将来要做的事 → 待办；其余当成一条信息 → 备忘
        is_todo = _hit(core, TODO_HINT) or _hit(core, TIME_HINT)
        tool = 'add_todo' if is_todo else 'add_memo'
        content = _LEAD.sub('', text).strip() or text
        return RouterDecision(type='command', tool=tool, args={'text': content})

    # ③ 兜底：闲聊
    return RouterDecision(type='chat', tool=None, args={})


if __name__ == '__main__':
    probes = [
        '帮我记一下房门密码是1234',
        '记一下明天下午三点开会',
        '我记了什么',
        '我还有哪些待办事项',
        '今天记性真差',
        '你记不记得我上次说的那个',
        '存一下我的车牌号是京A12345',
    ]
    for s in probes:
        d = route(s)
        print(f'{s}\t->\t{d.type}/{d.tool}\t{d.args}')

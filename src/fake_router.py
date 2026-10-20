'''
模拟路由分发
'''

from schemas import RouterDecision

PREFIXES = ['提醒我', '记一下']

# 去掉带有指定字符的输入前缀
def remove_prefix(text: str) -> str:
    for prefix in PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix):]
    return text

def route(text: str) -> RouterDecision:
    if '记' in text or '提醒' in text:
        router = RouterDecision(
            type='command',
            tool='add_memo',
            args={'text': remove_prefix(text)}
        )
    else:
        router = RouterDecision(
            type='chat',
            tool=None,
            args={}
        )
    return router


if __name__ == '__main__':
    text_list = ['记一下明天下午三点开会', '提醒我买牛奶', '今天好累啊', '今天记性真差']
    for text in text_list:
        result = route(text)
        print(result)


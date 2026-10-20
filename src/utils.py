'''
公用工具
'''
import re

_CN_NUM = '零一二三四五六七八九'
_CN_UNIT = ('', '十', '百', '千')
_CN_SECT = ('', '万', '亿')

def _sec_to_cn(sec: int) -> str:
    """把 0~9999 转成中文（内部用）"""
    out = ''
    need_zero = False
    for i, ch in enumerate(str(sec).zfill(4)):
        d = int(ch)
        if d == 0:
            need_zero = True
        else:
            if need_zero and out:
                out += '零'
            need_zero = False
            out += _CN_NUM[d] + _CN_UNIT[3 - i]
    if out.startswith('一十'):
        out = out[1:]
    return out


def num_to_cn(n: int) -> str:
    """整数 → 中文读法。  71 → 七十一 ｜ 101 → 一百零一 ｜ 10001 → 一万零一"""
    if n == 0:
        return '零'
    if n < 0:
        return '负' + num_to_cn(-n)
    groups = []  # 从低位到高位，每 4 位一组
    while n > 0:
        groups.append(n % 10000)
        n //= 10000
    out = ''
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        if out and g < 1000:  # 中间有空段 → 补一个"零"
            out += '零'
        out += _sec_to_cn(g) + (_CN_SECT[i] if i < len(_CN_SECT) else '')
    return out


def digits_to_cn(s: str) -> str:
    """数字串 → 逐位中文：'123456' → '一二三四五六'"""
    return ''.join(_CN_NUM[int(ch)] for ch in s)


def text_clean(text: str) -> str:
    text = re.sub(r'[\x00-\x1f\x7f-\x9f\u200b\u200c\u200d\ufeff\s]+', '', text)  # 去除换行和空格
    return text



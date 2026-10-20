'''
文字转语音
'''
import sys
import sherpa_onnx
import numpy as np, sounddevice as sd
import re
from tools import BASE_DIR
from utils import _CN_NUM, _CN_UNIT, _CN_SECT, _sec_to_cn, num_to_cn, digits_to_cn

MODEL_DIR = BASE_DIR.joinpath('model').joinpath('sherpa-onnx-vits-zh-ll')


# 字符替换表：左边 → 右边
#   ，。！？ 是词表里仅有的可用标点
#   冒号/顿号/分号 → 逗号
#   括号类 → 直接删掉（内容才是要听的）
#   波浪号/连字符/换行 → 逗号（顺带当成停顿）
_PUNCT = str.maketrans({
    '：': '，', '、': '，', '；': '，', ':': '，', ';': '，',
    ',': '，', '.': '。', '!': '！', '?': '？',
    '[': '', ']': '', '(': '', ')': '', '（': '', '）': '',
    '~': '，', '～': '，', '·': '，', '-': '，', '－': '，',
    '\n': '，', '\r': '', '\t': '，', '“': '', '”': ''
})

# 号码类内容（密码/手机号等）要逐位念：123456 → 一二三四五六
# 金额、序号、数量仍走 num_to_cn 的数值读法：1234 → 一千二百三十四
_PIN_HINTS = ('密码', '手机号', '身份证', '卡号', '验证码', '车牌')


def to_speakable(text: str) -> str:
    """把 TTS 读不出的字符，换成读得出的形式"""
    if any(hint in text for hint in _PIN_HINTS):
        text = re.sub(r'\d+', lambda m: digits_to_cn(m.group()), text)  # 号码类 → 逐位读
    else:
        text = re.sub(r'\d+', lambda m: num_to_cn(int(m.group())), text)  # 其余 → 数值读
    text = text.translate(_PUNCT)  # 再转标点
    return re.sub(r'[^\u4e00-\u9fff，。！？—…]', '', text)


TTS_Base = sherpa_onnx.OfflineTtsVitsModelConfig(
    model=str(MODEL_DIR.joinpath('model.onnx')),
    lexicon=str(MODEL_DIR.joinpath('lexicon.txt')),
    tokens=str(MODEL_DIR.joinpath('tokens.txt')),
    dict_dir=str(MODEL_DIR.joinpath('dict')),
    noise_scale_w=0
)

TTS_MODEL = sherpa_onnx.OfflineTtsModelConfig(
    vits=TTS_Base,
    num_threads=2,
    provider='cpu',
    debug=False,
)

TTS_ENGINE = sherpa_onnx.OfflineTtsConfig(
    model=TTS_MODEL,
    max_num_sentences=1,
)

TTS = sherpa_onnx.OfflineTts(TTS_ENGINE)


def speak(text: str) -> bool:
    try:
        text = to_speakable(text)
        if text.strip() == '':
            return False
        sound = TTS.generate(text, sid=2, speed=0.9)
        sound_samples = np.asarray(sound.samples, dtype=np.float32)
        head = np.zeros((1600,), dtype=np.float32)
        tail = np.zeros((4800,), dtype=np.float32)
        sound_samples = np.concatenate((head, sound_samples, tail))
        sound_max = np.abs(sound_samples).max()
        sound_norm = sound_samples / sound_max * 0.9
        sd.play(sound_norm, sound.sample_rate)
        sd.wait()
        return True
    except Exception as e:
        print(f'[警告] TTS 失败：{e!r}', file=sys.stderr)
        return False


if __name__ == '__main__':
    speak('我的手机密码是一二三四')

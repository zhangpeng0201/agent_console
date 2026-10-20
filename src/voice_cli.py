from asr import record_until_silence, transcribe
from handle import handle
from tts import speak

END_WORD = ["退出", "结束", "再见"]

GREETING = '你好,我是你的语音小助手一一,有什么可以帮助你的呀!'
FAREWELL = '拜拜，下次再见哦！'

def speek_to_user(text: str) -> None:
    if speak(text):
        print(f'小助手：{text}')
    else:
        print(f'[语音播报失败] 小助手：{text}')

def main():
    speek_to_user(GREETING)
    while True:
        print('-' * 66)
        audio = record_until_silence()
        text = transcribe(audio)
        print(f'用户：{text}')
        if any(w in text for w in END_WORD):
            speek_to_user(FAREWELL)
            break
        if not text.strip():
            continue
        reply = handle(text)
        speek_to_user(reply)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("用户中断退出")

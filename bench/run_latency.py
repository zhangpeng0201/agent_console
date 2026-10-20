'''
延迟基准：把「掐表手测」换成脚本自动跑，输出各环节耗时的分布。

用法：
    cd bench
    python run_latency.py                # 每项 20 轮，静音（不向声卡播放）
    python run_latency.py -n 5           # 快速跑 5 轮
    python run_latency.py --play         # TTS 真实播放（会出声）
    python run_latency.py --skip-record  # 跳过录音项（不动麦克风）

关于输入语音：用本机 sherpa-onnx 合成一段话，当「模拟麦克风输入」喂给 ASR。
本地合成、不联网；采样率天生 16kHz，与 asr.py 完全对齐。
（注意：合成语音比真实麦克风干净，识别更容易 —— 这一栏的数字偏乐观。）

关于「静音」：TTS 默认把 speak() 里的 sd.play / sd.wait 换成空操作，
所以「TTS 语音合成」一栏只含「本地合成 + 补头尾静音」，不含播放。
播放耗时 ≈ 音频时长（实时播放，压不掉），脚本会单独量出来并列在推算里。

关于数据安全：跑 handle() 会真的写 output/<session_id>/*.json，
所以脚本把 tools.OUTPUT_DIR 指到临时目录，跑完自动消失，不污染真实数据。
'''

import argparse
import contextlib
import io
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

import numpy as np

BENCH_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BENCH_DIR, '..', 'src'))

import tools
from asr import record, transcribe
from handle import handle
from llm_client import ask
from tts import TTS, speak

CMD_TEXT = '记一下明天下午三点开会'
CHAT_TEXT = '今天好累啊'
TTS_TEXT = '明天下午三点有个会，别忘了'
SID = 2  # 助手音色，与 tts.py 的 speak() 里用的那个保持一致


def pad(text: str, width: int) -> str:
    '''按终端显示宽度补空格（一个汉字占两格）'''
    shown = sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)
    return text + ' ' * max(0, width - shown)


def check_api() -> bool:
    try:
        ask([{'role': 'user', 'content': '你好'}])
        return True
    except Exception as e:
        print(f'  探测失败：{type(e).__name__}: {str(e)[:140]}')
        return False


def measure(func, rounds: int, warmup: int = 1) -> list:
    '''跑 rounds 轮，返回每轮耗时（秒）。warmup 轮不计入，
    避免「第一次调用」的建连/缓存开销污染结果。'''
    times = []
    with contextlib.redirect_stdout(io.StringIO()):
        for _ in range(warmup):
            func()
        for _ in range(rounds):
            start = time.perf_counter()
            func()
            times.append(time.perf_counter() - start)
    return times


def make_speech_audio():
    '''用本地 sherpa-onnx 合成一段话 → (16kHz 单声道 float32 数组, 采样率)，
    当「模拟麦克风输入」。不落盘、不联网。'''
    audio = TTS.generate(CMD_TEXT, sid=SID, speed=1)
    return np.asarray(audio.samples, dtype=np.float32), audio.sample_rate


def measure_play_seconds(text: str) -> float:
    '''静音跑一次 speak()，从「送给声卡的波形」反推播放时长（= 音频时长）。
    现在不落 mp3 了，所以只能这样量，不能再解码文件。'''
    captured = {}

    def fake_play(data, samplerate=None, **kwargs):
        captured['samples'] = len(np.asarray(data))
        captured['rate'] = samplerate

    with mock.patch('sounddevice.play', side_effect=fake_play), \
         mock.patch('sounddevice.wait'):
        ok = speak(text)
    if not ok or not captured:
        raise RuntimeError('speak() 没有向声卡送数据，播放时长测不出来')
    return captured['samples'] / captured['rate']


def main():
    parser = argparse.ArgumentParser(description='语音链路延迟基准')
    parser.add_argument('-n', '--rounds', type=int, default=20, help='每项测量轮数（默认 20）')
    parser.add_argument('--play', action='store_true', help='TTS 真实播放（默认静音）')
    parser.add_argument('--skip-record', action='store_true', help='跳过录音项（不动麦克风）')
    args = parser.parse_args()
    n = args.rounds

    print('=' * 66)
    print('语音链路延迟基准')
    print(f'每项 {n} 轮 ｜ TTS 播放：{"开启" if args.play else "关闭（静音）"}'
          f' ｜ 录音：{"跳过" if args.skip_record else "测量"}')
    print('=' * 66)

    print('\n[1] 探测 LLM API')
    if not check_api():
        print('  API 不可用，退出（否则跑出来全是降级后的假数字）')
        sys.exit(1)
    print('  可用')

    print('\n[2] 准备测试语音（本地 sherpa-onnx 合成 → 16kHz 单声道）')
    audio, sr = make_speech_audio()
    print(f'  时长 {len(audio) / sr:.2f}s ｜ 内容：{CMD_TEXT}')

    rows = []

    with tempfile.TemporaryDirectory() as tmpdir:
        # 工具会把记录写进 OUTPUT_DIR/<session_id>/；指到临时目录，跑完即删
        with mock.patch('tools.OUTPUT_DIR', Path(tmpdir)):
            print('\n[3] 分环节测量')
            if args.skip_record:
                print('  录音：已跳过（--skip-record，不动麦克风）')
                rec_times = None
            else:
                rec_rounds = min(n, 3)
                print(f'  录音 {rec_rounds} 轮（占用麦克风约 {5 * rec_rounds} 秒）')
                try:
                    rec_times = measure(lambda: record(5), rec_rounds, warmup=0)
                    rows.append(('录音（固定 5 秒）', rec_rounds, rec_times))
                except Exception as e:
                    print(f'  跳过录音：{type(e).__name__}: {str(e)[:100]}')
                    rec_times = None

            print(f'  ASR 语音识别 {n} 轮')
            asr_times = measure(lambda: transcribe(audio), n)
            rows.append(('ASR 语音识别', n, asr_times))

            print(f'  意图路由+执行（指令）{n} 轮')
            cmd_times = measure(lambda: handle(CMD_TEXT), n)
            rows.append(('路由+执行（指令）', n, cmd_times))

            print(f'  意图路由+执行（闲聊）{n} 轮')
            chat_times = measure(lambda: handle(CHAT_TEXT), n)
            rows.append(('路由+执行（闲聊）', n, chat_times))

            print(f'  TTS 语音合成 {n} 轮（{"真实播放" if args.play else "静音"}）')
            if args.play:
                tts_times = measure(lambda: speak(TTS_TEXT), n)
            else:
                with mock.patch('sounddevice.play'), mock.patch('sounddevice.wait'):
                    first = speak(TTS_TEXT)
                    if not first:
                        print('  ！speak() 返回 False，以下 TTS 数字不可信')
                    tts_times = measure(lambda: speak(TTS_TEXT), n, warmup=0)
            rows.append(('TTS 语音合成', n, tts_times))

            print('\n[4] 端到端一轮（用合成语音替代麦克风，跳过录音）')
            e2e_rounds = min(n, 10)
            print(f'  跑 {e2e_rounds} 轮：transcribe → handle → speak')

            def one_round():
                text = transcribe(audio)
                speak(handle(text))

            if args.play:
                e2e_times = measure(one_round, e2e_rounds)
            else:
                with mock.patch('sounddevice.play'), mock.patch('sounddevice.wait'):
                    e2e_times = measure(one_round, e2e_rounds)

    play_sec = measure_play_seconds(TTS_TEXT)

    print('\n' + '=' * 66)
    print(pad('环节', 26) + pad('轮数', 8) + pad('中位数', 12) + pad('最快', 11) + '最慢')
    print('-' * 66)
    for label, rounds, times in rows:
        print(pad(label, 26) + pad(str(rounds), 8)
              + pad(f'{statistics.median(times):.2f}s', 12)
              + pad(f'{min(times):.2f}s', 11) + f'{max(times):.2f}s')
    print('-' * 66)
    print(pad('端到端一轮（不含录音）', 26) + pad(str(e2e_rounds), 8)
          + pad(f'{statistics.median(e2e_times):.2f}s', 12)
          + pad(f'{min(e2e_times):.2f}s', 11) + f'{max(e2e_times):.2f}s')
    print('=' * 66)

    asr_med = statistics.median(asr_times)
    cmd_med = statistics.median(cmd_times)
    tts_med = statistics.median(tts_times)
    e2e_med = statistics.median(e2e_times)

    play_part = 0.0 if args.play else play_sec
    e2e_full = e2e_med + play_part
    rec_med = statistics.median(rec_times) if rec_times else None

    seg_total = asr_med + cmd_med + tts_med + play_sec
    seg_line = (f'ASR {asr_med:.2f} + 路由执行 {cmd_med:.2f}'
                f' + 合成 {tts_med:.2f} + 播放 {play_sec:.2f}')

    print('\n[5] 语音一轮的账（各环节取中位数）')
    if rec_med is not None:
        print(f'    分环节相加：录音 {rec_med:.2f} + {seg_line} = {rec_med + seg_total:.2f}s')
    else:
        print(f'    分环节相加：{seg_line} = {seg_total:.2f}s')
    print(f'    端到端实测：{e2e_med:.2f}s（{"含" if args.play else "不含"}播放，不含录音）')
    if not args.play:
        print(f'                + 播放 {play_sec:.2f}s → {e2e_full:.2f}s')
    if rec_med is not None:
        print(f'                + 录音 {rec_med:.2f}s → {e2e_full + rec_med:.2f}s  ← 真实语音一轮')

    print(f'\n    口径：播放 {play_sec:.2f}s 是音频时长本身（实时播放，压不掉）；')
    print(f'          端到端默认静音，所以那行不含播放 —— 看"真实语音一轮"那个数。')


if __name__ == '__main__':
    main()

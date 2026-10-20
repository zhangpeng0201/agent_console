import sounddevice as sd
from faster_whisper import WhisperModel
import numpy as np
import sherpa_onnx
from tools import BASE_DIR

MODEL_DIR = BASE_DIR.joinpath('model').joinpath('silero-vad')

MAX_RECORD_SECONDS = 15      # 硬上限：最长录这么久
NO_SPEECH_SECONDS = 5        # 一直没人说话，等这么久就放弃

VAD_BASE = sherpa_onnx.SileroVadModelConfig(
    model=str(MODEL_DIR.joinpath('silero_vad.onnx')),
    threshold=0.5,
    min_silence_duration=0.8,
    min_speech_duration=0.25
)

VAD_MODEL = sherpa_onnx.VadModelConfig(
    silero_vad=VAD_BASE,
    sample_rate=16000,
)

VAD = sherpa_onnx.VadModel.create(VAD_MODEL)

print("正在加载语音识别模型")
# 建模型
MODEL = WhisperModel('small', device='cpu', compute_type='int8',
                     cpu_threads=8, local_files_only=True)
print("语音模型已就绪")

# 录音
def record(seconds: int) -> np.ndarray:
    print("开始录音")
    audio = sd.rec(int(seconds * 16000), samplerate=16000, channels=1, dtype='float32')
    sd.wait()
    print('录音结束')
    audio = audio.squeeze()
    return audio

def record_until_silence() -> np.ndarray:
    print('开始录音')

    frame_size = VAD.window_size()        # 576 样本，从 VAD 拿，别写死

    frames = []                           # 装每一小格波形
    has_speech = False                    # 这次录音里，出现过人声没有
    total = 0                             # 已经录了多少样本

    max_samples = MAX_RECORD_SECONDS * 16000
    no_speech_samples = NO_SPEECH_SECONDS * 16000

    with sd.InputStream(samplerate=16000, channels=1,
                        dtype='float32', blocksize=frame_size) as stream:
        while True:
            chunk, _ = stream.read(frame_size)                    # 读一格
            chunk = np.ascontiguousarray(chunk[:, 0], dtype=np.float32)
            frames.append(chunk)
            total += len(chunk)

            if VAD.is_speech(chunk):      # 这一格有人声
                has_speech = True
            elif has_speech:              # 说过话、现在静音 → 说完了
                break

            if total >= max_samples:      # 兜底一：说太久，强制停
                break
            if not has_speech and total >= no_speech_samples:     # 兜底二：没人说话
                break

    print('录音结束')

    if not has_speech:                    # 全程没说话 → 空数组
        return np.array([], dtype=np.float32)

    return np.concatenate(frames)         # 一维 float32，与 record() 形状一致


# 录音转文字
def transcribe(audio : np.ndarray) -> str:
    segments, info = MODEL.transcribe(
        audio,
        language='zh',
        initial_prompt='以下是普通话的句子。',
        without_timestamps=True,
    )
    text = ''
    for seg in segments:
        text = text + seg.text
    return text

if __name__ == '__main__':
    audio = record(5)
    text = transcribe(audio)
    print(text)

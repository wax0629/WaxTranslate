"""Offline English speech. A short-lived child owns synthesis and audio playback."""
import asyncio
import io
import json
import sys
import wave
import winsound


class SpeechUnavailable(Exception):
    pass


def english_desktop_voice():
    from comtypes import COMError
    from comtypes.client import CreateObject

    voice = CreateObject("SAPI.SpVoice", dynamic=True)

    def is_english(token):
        try:
            # SAPI stores hexadecimal Windows language IDs; 0x09 is English.
            languages = token.GetAttribute("Language").split(";")
            return any(int(code, 16) & 0x3ff == 0x09 for code in languages if code.strip())
        except (AttributeError, COMError, OSError, ValueError):
            return False

    if is_english(voice.Voice):
        return voice
    tokens = voice.GetVoices()
    for index in range(tokens.Count):
        token = tokens.Item(index)
        if is_english(token):
            voice.Voice = token
            return voice
    return None


async def modern_voice_audio(text, slow):
    from winrt.windows.media.speechsynthesis import SpeechSynthesizer
    from winrt.windows.storage.streams import DataReader

    voice = next((v for v in SpeechSynthesizer.all_voices if v.language.split("-")[0].lower() == "en"), None)
    if voice is None:
        raise SpeechUnavailable("请在 Windows「设置 → 时间和语言 → 语音」添加英语声音，然后重试。")
    with SpeechSynthesizer() as synth:
        synth.voice = voice
        synth.options.speaking_rate = 0.72 if slow else 1.0
        with await synth.synthesize_text_to_stream_async(text) as stream:
            with DataReader(stream) as reader:
                await reader.load_async(stream.size)
                audio = bytearray(reader.unconsumed_buffer_length)
                reader.read_bytes(audio)
                return bytes(audio)


def synthesize(text, slow):
    from comtypes import COMError

    # Older desktop and modern Windows voices have separate inventories.
    try:
        voice = english_desktop_voice()
    except (COMError, OSError):
        voice = None
    if voice is None:
        return asyncio.run(modern_voice_audio(text, slow))
    from comtypes.client import CreateObject

    stream = CreateObject("SAPI.SpMemoryStream", dynamic=True)
    voice.AudioOutputStream = stream
    voice.Rate = -4 if slow else 0
    voice.Speak(text, 16)  # SVSFIsNotXML: article text is always plain text.
    fmt = stream.Format.GetWaveFormatEx()
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setparams((fmt.Channels, fmt.BitsPerSample // 8, fmt.SamplesPerSec, 0, "NONE", ""))
        wav.writeframes(bytes(stream.GetData()))
    return audio.getvalue()


if __name__ == "__main__":
    text, slow = json.loads(sys.stdin.buffer.read())
    try:
        winsound.PlaySound(synthesize(text, slow), winsound.SND_MEMORY | winsound.SND_NODEFAULT)
    except SpeechUnavailable as error:
        sys.stdout.buffer.write(str(error).encode("utf-8"))
        sys.exit(1)
    except Exception:
        sys.stdout.buffer.write("未能播放英语语音。请检查 Windows 声音输出设备和已安装的英语声音，再试一次。".encode("utf-8"))
        sys.exit(1)

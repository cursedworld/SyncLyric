"""
Модуль предобработки аудио перед подачей в Whisper.
pydub используется для нормализации громкости и приведения к моно/16кГц,
что критично для качества распознавания речи в песнях.
"""
from pydub import AudioSegment
import os
import tempfile


class AudioProcessor:
    @staticmethod
    def preprocess(audio_path: str) -> str:
        """
        Загружает аудио, конвертирует в моно, нормализует громкость
        и сохраняет во временный WAV (16 кГц, 16 бит).
        """
        audio = AudioSegment.from_file(audio_path)

        # Моно канал — критично для распознавания речи
        audio = audio.set_channels(1)

        # Нормализация: выравнивает тихие речевые фрагменты
        # относительно громких инструментальных партий
        audio = audio.normalize(headroom=0.1)

        # Whisper ожидает 16 кГц — приводим частоту дискретизации
        audio = audio.set_frame_rate(16000)
        audio = audio.set_sample_width(2)

        # Сохраняем во временный файл без сжатия для скорости
        fd, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        audio.export(temp_path, format="wav")
        return temp_path

"""
Обертка над faster-whisper.
Загружает модель medium на GPU (float16) и извлекает word-level тайминги.
"""
from faster_whisper import WhisperModel
from typing import List, Dict, Optional, Callable


class Transcriber:
    def __init__(self, model_size: str = "medium", device: str = "cuda", compute_type: str = "float16"):
        try:
            self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        except Exception as e:
            if device == "cuda":
                print(f"CUDA initialization failed ({e}). Falling back to CPU with int8 quantization...")
                self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
            else:
                raise e

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
        use_vad: bool = False,
        initial_prompt: Optional[str] = None,
    ) -> tuple[List[Dict], float, float]:
        """
        Возвращает:
            words — список слов с полями 'word', 'start', 'end';
            duration — полная длительность аудио (сек);
            duration_after_vad — длительность после фильтрации (если VAD включен).
        """
        segments, info = self.model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            vad_filter=use_vad,            # опционально: True отсекает тишину
            condition_on_previous_text=True,
            initial_prompt=initial_prompt,
        )

        words: List[Dict] = []
        for segment in segments:
            if progress_callback:
                progress_callback(f"Сегмент {segment.start:.1f}s – {segment.end:.1f}s")
            if segment.words:
                for w in segment.words:
                    words.append({
                        "word": w.word.strip(),
                        "start": w.start,
                        "end": w.end
                    })

        duration_after_vad = getattr(info, "duration_after_vad", None)
        if duration_after_vad is None:
            duration_after_vad = info.duration

        return words, info.duration, duration_after_vad

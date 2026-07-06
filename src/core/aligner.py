"""
Алгоритм сопоставления текста пользователя с результатами Whisper.
Использует difflib.SequenceMatcher для fuzzy matching на уровне слов
и линейную интерполяцию для восстановления пропущенных таймингов.
"""
import difflib
import re
import statistics
from typing import List, Dict, Tuple, Optional


class Aligner:
    DEFAULT_WORD_STEP = 0.35
    MIN_WORD_STEP = 0.12
    MAX_WORD_STEP = 0.80
    SIMILARITY_THRESHOLD = 0.60

    @staticmethod
    def normalize(word: str) -> str:
        "Приводит слово к каноническому виду для сравнения."
        word = word.lower()
        word = word.replace("ё", "е")
        # Оставляем буквы, цифры, дефисы; удаляем пунктуацию
        word = re.sub(r"[^\w\s-]", "", word, flags=re.UNICODE)
        return word.strip()

    @classmethod
    def _estimate_word_step(cls, asr_words: List[Dict]) -> float:
        intervals = []
        prev_start: Optional[float] = None

        for word in asr_words:
            start = word.get("start")
            if start is None:
                continue
            start = float(start)

            if prev_start is not None:
                gap = start - prev_start
                if cls.MIN_WORD_STEP <= gap <= 1.20:
                    intervals.append(gap)

            end = word.get("end")
            if end is not None:
                duration = float(end) - start
                if cls.MIN_WORD_STEP <= duration <= 1.20:
                    intervals.append(duration)

            prev_start = start

        if not intervals:
            return cls.DEFAULT_WORD_STEP

        return min(cls.MAX_WORD_STEP, max(cls.MIN_WORD_STEP, statistics.median(intervals)))

    @classmethod
    def _similar_enough(cls, left: str, right: str) -> bool:
        if left == right:
            return True
        if len(left) <= 2 or len(right) <= 2:
            return False
        return difflib.SequenceMatcher(None, left, right, autojunk=False).ratio() >= cls.SIMILARITY_THRESHOLD

    def align(self, source_lines: List[str], asr_words: List[Dict]) -> List[Tuple[float, str]]:
        """
        Сопоставляет исходные строки с ASR-словами.
        Возвращает список (timestamp_seconds, оригинальная_строка).
        """
        # 1. Разбиваем пользовательский текст на плоский список слов
        text_words: List[str] = []
        line_boundaries: List[Tuple[int, int]] = []  # границы строк в word-индексах

        for line in source_lines:
            line = line.strip()
            if not line:
                line_boundaries.append((len(text_words), len(text_words)))
                continue
            raw_words = line.split()
            start = len(text_words)
            for w in raw_words:
                normalized = self.normalize(w)
                if normalized:
                    text_words.append(normalized)
            line_boundaries.append((start, len(text_words)))

        if not text_words:
            return []

        # 2. Нормализуем слова от Whisper
        asr_tokens = []
        for word in asr_words:
            normalized = self.normalize(str(word.get("word", "")))
            if normalized and word.get("start") is not None:
                asr_tokens.append({
                    "word": normalized,
                    "start": float(word["start"]),
                    "end": None if word.get("end") is None else float(word["end"]),
                })

        asr_norm = [w["word"] for w in asr_tokens]
        word_step = self._estimate_word_step(asr_tokens)

        # 3. Fuzzy sequence matching
        # autojunk=False — важно для коротких текстов (песен), иначе длинные повторяющиеся блоки (припевы) могут исказить сопоставление
        matcher = difflib.SequenceMatcher(None, text_words, asr_norm, autojunk=False)
        opcodes = matcher.get_opcodes()

        word_times: List[Optional[float]] = [None] * len(text_words)

        for tag, i1, i2, j1, j2 in opcodes:
            if tag == "equal":
                # Прямое совпадение: переносим временную метку из Whisper
                for i in range(i1, i2):
                    word_times[i] = asr_tokens[j1 + (i - i1)]["start"]

            elif tag == "replace":
                # Если количество слов совпадает, переносим только похожие слова.
                # Иначе чужой куплет той же длины может стать ложным якорем.
                if (i2 - i1) == (j2 - j1):
                    for i in range(i1, i2):
                        j = j1 + (i - i1)
                        if self._similar_enough(text_words[i], asr_norm[j]):
                            word_times[i] = asr_tokens[j]["start"]
                # Иначе оставляем None для последующей интерполяции

        # 4. Интерполяция пропущенных таймингов
        first_known = next((i for i, t in enumerate(word_times) if t is not None), None)

        if first_known is None:
            # Полное несовпадение — сохраняем структуру с нулевыми метками
            return [(0.0, line.rstrip("\n")) for line in source_lines if line.strip()]

        # Заполняем начало назад от первого якоря. Не растягиваем неизвестный префикс от 0
        # до первого совпадения: это давало строки [00:00] перед реальным входом вокала.
        if first_known > 0:
            for k in range(first_known - 1, -1, -1):
                word_times[k] = max(0.0, word_times[k + 1] - word_step)

        prev = first_known
        for i in range(first_known + 1, len(word_times)):
            if word_times[i] is not None:
                if i > prev + 1:
                    t0, t1 = word_times[prev], word_times[i]
                    step = (t1 - t0) / (i - prev)
                    for k in range(prev + 1, i):
                        word_times[k] = t0 + step * (k - prev)
                prev = i

        # Заполняем хвост
        for k in range(prev + 1, len(word_times)):
            word_times[k] = word_times[k - 1] + word_step

        # 5. Собираем строки
        result: List[Tuple[float, str]] = []
        last_line_time = -0.1
        for line_idx, (s_idx, e_idx) in enumerate(line_boundaries):
            if s_idx == e_idx:
                continue  # пропускаем пустые строки

            line_time = None
            for idx in range(s_idx, e_idx):
                if word_times[idx] is not None:
                    line_time = word_times[idx]
                    break

            if line_time is None:
                line_time = 0.0

            # Принудительная монотонность: каждая строка должна идти строго вперед
            if line_time <= last_line_time:
                line_time = last_line_time + 0.5
            last_line_time = line_time

            original = source_lines[line_idx].rstrip("\n")
            result.append((line_time, original))

        return result

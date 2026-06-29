"""
Алгоритм сопоставления текста пользователя с результатами Whisper.
Использует difflib.SequenceMatcher для fuzzy matching на уровне слов
и линейную интерполяцию для восстановления пропущенных таймингов.
"""
import difflib
import re
from typing import List, Dict, Tuple, Optional


class Aligner:
    @staticmethod
    def normalize(word: str) -> str:
        "Приводит слово к каноническому виду для сравнения."
        word = word.lower()
        word = word.replace("ё", "е")
        # Оставляем буквы, цифры, дефисы; удаляем пунктуацию
        word = re.sub(r"[^\w\s-]", "", word, flags=re.UNICODE)
        return word.strip()

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
                text_words.append(self.normalize(w))
            line_boundaries.append((start, len(text_words)))

        # 2. Нормализуем слова от Whisper
        asr_norm = [self.normalize(w["word"]) for w in asr_words]

        # 3. Fuzzy sequence matching
        # autojunk=False — важно для коротких текстов (песен), иначе длинные повторяющиеся блоки (припевы) могут исказить сопоставление
        matcher = difflib.SequenceMatcher(None, text_words, asr_norm, autojunk=False)
        opcodes = matcher.get_opcodes()

        word_times: List[Optional[float]] = [None] * len(text_words)

        for tag, i1, i2, j1, j2 in opcodes:
            if tag == "equal":
                # Прямое совпадение: переносим временную метку из Whisper
                for i in range(i1, i2):
                    word_times[i] = asr_words[j1 + (i - i1)]["start"]

            elif tag == "replace":
                # Если количество слов совпадает — сопоставляем по порядку.
                # Это помогает, когда Whisper слегка исказил слово, но не добавил/удалил слова.
                if (i2 - i1) == (j2 - j1):
                    for i in range(i1, i2):
                        word_times[i] = asr_words[j1 + (i - i1)]["start"]
                # Иначе оставляем None для последующей интерполяции

        # 4. Интерполяция пропущенных таймингов
        first_known = next((i for i, t in enumerate(word_times) if t is not None), None)

        if first_known is None:
            # Полное несовпадение — сохраняем структуру с нулевыми метками
            return [(0.0, line.rstrip("\n")) for line in source_lines if line.strip()]

        # Заполняем начало: равномерное распределение от 0.00 до первого найденного слова
        t_first = word_times[first_known]
        if first_known > 0:
            step = t_first / first_known
            for k in range(0, first_known):
                word_times[k] = step * k

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
            word_times[k] = word_times[prev]

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

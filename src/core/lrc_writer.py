"""Генерация файла в формате LRC (построчные тайминги)."""
from typing import List, Tuple


class LRCWriter:
    @staticmethod
    def format_time(seconds: float) -> str:
        """Формат [mm:ss.xx], где xx — сотые доли секунды."""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        cs = int(round((seconds - int(seconds)) * 100))
        if cs >= 100:
            cs = 99
        return f"[{minutes:02d}:{secs:02d}.{cs:02d}]"

    @classmethod
    def write(cls, lrc_lines: List[Tuple[float, str]], output_path: str):
        with open(output_path, "w", encoding="utf-8") as f:
            last_t = -0.1
            for raw_t, line in lrc_lines:
                t = raw_t
                if t <= last_t:
                    t = last_t + 0.5
                last_t = t
                f.write(f"{cls.format_time(t)}{line}\n")

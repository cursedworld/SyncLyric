"""
Главное окно приложения на CustomTkinter с поддержкой Drag-and-Drop (tkinterdnd2).
Все тяжелые операции выполняются в фоновом потоке, чтобы GUI не зависал.
"""
import os
import queue
import threading
from tkinter import filedialog

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES

from src.core.audio_utils import AudioProcessor
from src.core.transcriber import Transcriber
from src.core.aligner import Aligner
from src.core.lrc_writer import LRCWriter


class App(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.title("SyncLyric — Генератор LRC")
        self.geometry("800x650")
        self.minsize(700, 550)

        self.audio_path: str | None = None
        self.text_path: str | None = None
        self.msg_queue = queue.Queue()

        self._build_ui()
        self.after(100, self._poll_queue)

    # Построение интерфейса
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkFrame(self)
        container.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        container.grid_columnconfigure((0, 1), weight=1)
        container.grid_rowconfigure(5, weight=1)

        #  Зоны Drag & Drop 
        self.audio_frame = ctk.CTkFrame(container, height=130, fg_color=("gray85", "gray20"))
        self.audio_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="nsew")
        self.audio_frame.drop_target_register(DND_FILES)
        self.audio_frame.dnd_bind("<<Drop>>", self._on_audio_drop)
        self.audio_frame.bind("<Button-1>", lambda e: self._browse_audio())

        self.audio_lbl = ctk.CTkLabel(
            self.audio_frame,
            text="🎵 Аудио\nПеретащите MP3 / WAV / FLAC сюда",
            font=ctk.CTkFont(size=15)
        )
        self.audio_lbl.place(relx=0.5, rely=0.5, anchor="center")

        self.text_frame = ctk.CTkFrame(container, height=130, fg_color=("gray85", "gray20"))
        self.text_frame.grid(row=0, column=1, padx=10, pady=(10, 5), sticky="nsew")
        self.text_frame.drop_target_register(DND_FILES)
        self.text_frame.dnd_bind("<<Drop>>", self._on_text_drop)
        self.text_frame.bind("<Button-1>", lambda e: self._browse_text())

        self.text_lbl = ctk.CTkLabel(
            self.text_frame,
            text="📝 Текст песни\nПеретащите .txt сюда",
            font=ctk.CTkFont(size=15)
        )
        self.text_lbl.place(relx=0.5, rely=0.5, anchor="center")

        # Настройки
        settings = ctk.CTkFrame(container)
        settings.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(settings, text="Язык песни:").pack(side="left", padx=10)
        self.lang_var = ctk.StringVar(value="Auto")
        ctk.CTkOptionMenu(
            settings,
            values=["Auto", "ru", "en", "de", "fr", "es", "it", "ja", "zh", "ko", "pt", "uk", "pl"],
            variable=self.lang_var,
            width=120
        ).pack(side="left")

        ctk.CTkLabel(settings, text="Модель: medium | GPU: float16").pack(side="right", padx=10)

        # Дополнительные настройки
        advanced = ctk.CTkFrame(container)
        advanced.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="ew")

        self.vad_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            advanced,
            text="Пропускать тишину (VAD)",
            variable=self.vad_var,
            onvalue=True,
            offvalue=False
        ).pack(side="left", padx=10)

        ctk.CTkLabel(advanced, text="Initial prompt:").pack(side="left", padx=(20, 5))
        self.prompt_entry = ctk.CTkEntry(advanced, width=350, placeholder_text="Первые слова песни (помогает Whisper)")
        self.prompt_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # Прогресс и кнопка
        self.progress = ctk.CTkProgressBar(container, mode="indeterminate")
        self.progress.grid(row=3, column=0, columnspan=2, padx=10, pady=(5, 5), sticky="ew")
        self.progress.stop()
        self.progress.set(0)

        self.run_btn = ctk.CTkButton(
            container,
            text="Сгенерировать LRC",
            command=self._start_process,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.run_btn.grid(row=4, column=0, columnspan=2, padx=10, pady=(5, 10))

        # Лог
        self.log_box = ctk.CTkTextbox(container, wrap="word")
        self.log_box.grid(row=5, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="nsew")
        self.log_box.configure(state="disabled")

    # Лог
    def _log(self, text: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # Drop / Browse
    def _on_audio_drop(self, event):
        files = self.tk.splitlist(event.data)
        if files:
            self._set_audio(files[0])

    def _set_audio(self, path: str):
        if os.path.isfile(path):
            self.audio_path = path
            self.audio_lbl.configure(text=f"🎵 {os.path.basename(path)}")
            self._log(f"Аудио: {path}")

    def _browse_audio(self):
        path = filedialog.askopenfilename(
            filetypes=[("Audio", "*.mp3 *.wav *.flac *.m4a *.ogg")]
        )
        if path:
            self._set_audio(path)

    def _on_text_drop(self, event):
        files = self.tk.splitlist(event.data)
        if files:
            self._set_text(files[0])

    def _set_text(self, path: str):
        if os.path.isfile(path):
            self.text_path = path
            self.text_lbl.configure(text=f"📝 {os.path.basename(path)}")
            self._log(f"Текст: {path}")

    def _browse_text(self):
        path = filedialog.askopenfilename(filetypes=[("Text", "*.txt")])
        if path:
            self._set_text(path)

    # Процесс
    def _start_process(self):
        if not self.audio_path or not self.text_path:
            self._log("⚠️ Выберите оба файла (аудио + текст).")
            return
        self.run_btn.configure(state="disabled")
        self.progress.start()
        self.progress.set(0)
        threading.Thread(target=self._process_thread, daemon=True).start()

    def _process_thread(self):
        temp_audio = None
        try:
            self.msg_queue.put(("log", "Шаг 1/4: Предобработка аудио (pydub)..."))
            temp_audio = AudioProcessor.preprocess(self.audio_path)

            self.msg_queue.put(("log", "Шаг 2/4: Загрузка модели Whisper (medium)..."))
            transcriber = Transcriber(model_size="medium", device="cuda", compute_type="float16")

            lang = self.lang_var.get()
            if lang == "Auto":
                lang = None

            self.msg_queue.put(("log", "Шаг 3/4: Транскрибация аудио... Это может занять 1–3 минуты."))
            use_vad = self.vad_var.get()
            initial_prompt = self.prompt_entry.get().strip() or None
            asr_words, duration, duration_after_vad = transcriber.transcribe(
                temp_audio, language=lang, use_vad=use_vad, initial_prompt=initial_prompt
            )
            self.msg_queue.put(("log", f"Распознано {len(asr_words)} слов. Полная длительность: {duration:.1f}s | После VAD: {duration_after_vad:.1f}s"))

            self.msg_queue.put(("log", "Шаг 4/4: Выравнивание текста и генерация LRC..."))
            with open(self.text_path, "r", encoding="utf-8") as f:
                source_lines = f.readlines()

            aligner = Aligner()
            lrc_lines = aligner.align(source_lines, asr_words)

            out_path = os.path.splitext(self.audio_path)[0] + ".lrc"
            LRCWriter.write(lrc_lines, out_path)

            self.msg_queue.put(("done", out_path))
        except Exception as exc:
            self.msg_queue.put(("error", str(exc)))
        finally:
            if temp_audio and os.path.exists(temp_audio):
                try:
                    os.remove(temp_audio)
                except Exception:
                    pass

    def _poll_queue(self):
        try:
            while True:
                msg_type, payload = self.msg_queue.get_nowait()
                if msg_type == "log":
                    self._log(payload)
                elif msg_type == "done":
                    self.progress.stop()
                    self.progress.set(1)
                    self.run_btn.configure(state="normal")
                    self._log(f"✅ Готово! Сохранено: {payload}")
                elif msg_type == "error":
                    self.progress.stop()
                    self.progress.set(0)
                    self.run_btn.configure(state="normal")
                    self._log(f"❌ Ошибка: {payload}")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

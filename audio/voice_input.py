from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger("mayday.audio.voice_input")


@dataclass
class VoiceInput:
    timeout_seconds: int = 5
    phrase_time_limit: int = 20
    whisper_model: object | None = None
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)

    def is_available(self) -> bool:
        return self.get_backend() != "unavailable"

    def get_backend(self) -> str:
        if self.whisper_model is not None:
            return "whisper_local"
        try:
            import pyaudio  # noqa: F401
            import speech_recognition as sr  # noqa: F401

            return "google_sr"
        except Exception:
            return "unavailable"

    def start_listening(self, callback: Callable[[str], None]) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._listen_loop,
            args=(callback,),
            daemon=True,
            name="mayday-voice-input",
        )
        self._thread.start()

    def stop_listening(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)

    def listen(self) -> str:
        backend = self.get_backend()
        if backend == "google_sr":
            return self._listen_google_sr()
        if backend == "whisper_local":
            return self._listen_whisper_local()
        return ""

    def _listen_loop(self, callback: Callable[[str], None]) -> None:
        while not self._stop_event.is_set():
            text = self.listen()
            if text:
                try:
                    callback(text)
                except Exception as exc:
                    logger.warning("Voice callback failed: %s", exc)
            if self.get_backend() == "unavailable":
                break

    def _listen_google_sr(self) -> str:
        try:
            import speech_recognition as sr

            recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.25)
                audio = recognizer.listen(
                    source,
                    timeout=self.timeout_seconds,
                    phrase_time_limit=self.phrase_time_limit,
                )
            return recognizer.recognize_google(audio)
        except Exception as exc:
            logger.info("Google SpeechRecognition unavailable: %s", exc)
            return ""

    def _listen_whisper_local(self) -> str:
        transcribe = getattr(self.whisper_model, "transcribe", None)
        if not callable(transcribe):
            return ""
        try:
            result = transcribe()
        except Exception as exc:
            logger.info("Whisper local transcription failed: %s", exc)
            return ""
        if isinstance(result, dict):
            return str(result.get("text", "")).strip()
        return str(result).strip()


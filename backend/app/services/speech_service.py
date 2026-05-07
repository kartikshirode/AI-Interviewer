import asyncio
import logging
import os
import tempfile
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class SpeechToTextService:
    """Whisper-based speech-to-text. Model is loaded lazily on first use to
    avoid blocking app startup, and inference is funneled through a
    semaphore so that we don't run unbounded concurrent CPU jobs on the
    FastAPI threadpool."""

    # Cap concurrent transcriptions. The whisper model is CPU-bound; running
    # many in parallel just thrashes the threadpool.
    MAX_CONCURRENT_TRANSCRIBES = 2

    def __init__(self) -> None:
        self._model = None
        self._model_lock = threading.Lock()
        self._semaphore = threading.Semaphore(self.MAX_CONCURRENT_TRANSCRIBES)

    def _get_model(self):
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    from faster_whisper import WhisperModel  # heavy import
                    self._model = WhisperModel("base", device="cpu", compute_type="int8")
        return self._model

    def transcribe_audio(self, audio_path: str) -> str:
        """Transcribe audio file using faster-whisper (local, free).

        Phase 0.5: exceptions are propagated to the caller — the
        background-task handler in `candidate.py` catches them and
        marks the answer's `flag_reason = "transcription_failed"`.
        Previously this method swallowed every exception and returned
        an empty string, which the caller misclassified as "silence".
        """
        with self._semaphore:
            model = self._get_model()
            segments, _info = model.transcribe(audio_path, beam_size=5)
            result = " ".join(segment.text for segment in segments)
            return result.strip()

    async def transcribe_audio_async(self, audio_path: str) -> str:
        """Async wrapper that offloads inference to a worker thread."""
        return await asyncio.to_thread(self.transcribe_audio, audio_path)

    def transcribe_video(
        self, video_path: str, temp_audio_path: Optional[str] = None
    ) -> str:
        """Extract audio from video and transcribe.

        Phase 0.5: exceptions propagate. We still own the cleanup of the
        VideoFileClip and the temp audio file via try/finally — the only
        thing that changed is we no longer swallow the exception itself.
        """
        try:
            from moviepy.editor import VideoFileClip
        except ImportError:
            return self.transcribe_audio(video_path)

        video = None
        owns_temp = temp_audio_path is None
        try:
            if owns_temp:
                tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tmp.close()
                temp_audio_path = tmp.name

            video = VideoFileClip(video_path)
            video.audio.write_audiofile(temp_audio_path, verbose=False, logger=None)
            return self.transcribe_audio(temp_audio_path)
        finally:
            if video is not None:
                try:
                    video.close()
                except Exception:
                    pass
            if owns_temp and temp_audio_path:
                try:
                    if os.path.exists(temp_audio_path):
                        os.remove(temp_audio_path)
                except OSError:
                    pass

    def transcribe_from_blob(self, audio_blob: bytes, filename: str = "audio.webm") -> str:
        """Transcribe audio from blob in memory. Phase 0.5: exceptions
        propagate; caller must handle. Temp file cleanup still runs."""
        suffix = ".webm" if "webm" in filename else ".mp3"
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(audio_blob)
                tmp_path = tmp.name
            return self.transcribe_audio(tmp_path)
        finally:
            if tmp_path:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except OSError:
                    pass


speech_service = SpeechToTextService()

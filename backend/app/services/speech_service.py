import os
import tempfile
from typing import Optional
from pathlib import Path
from faster_whisper import WhisperModel

class SpeechToTextService:
    def __init__(self):
        self.model = WhisperModel("base", device="cpu", compute_type="int8")
    
    def transcribe_audio(self, audio_path: str) -> str:
        """Transcribe audio file using faster-whisper (local, free)"""
        try:
            segments, info = self.model.transcribe(audio_path, beam_size=5)
            result = " ".join([segment.text for segment in segments])
            return result.strip()
        except Exception as e:
            print(f"Error transcribing audio: {e}")
            return ""
    
    def transcribe_video(self, video_path: str, temp_audio_path: Optional[str] = None) -> str:
        """Extract audio from video and transcribe"""
        try:
            from moviepy.editor import VideoFileClip
        except ImportError:
            return self.transcribe_audio(video_path)
        
        try:
            if temp_audio_path is None:
                temp_audio_path = tempfile.mktemp(suffix=".mp3")
            
            video = VideoFileClip(video_path)
            video.audio.write_audiofile(temp_audio_path, verbose=False, logger=None)
            video.close()
            
            transcript = self.transcribe_audio(temp_audio_path)
            
            if os.path.exists(temp_audio_path) and temp_audio_path.startswith(tempfile.gettempdir()):
                os.remove(temp_audio_path)
            
            return transcript
        except Exception as e:
            print(f"Error processing video: {e}")
            return ""
    
    def transcribe_from_blob(self, audio_blob: bytes, filename: str = "audio.webm") -> str:
        """Transcribe audio from blob in memory"""
        try:
            suffix = ".webm" if "webm" in filename else ".mp3"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(audio_blob)
                tmp_path = tmp.name
            
            transcript = self.transcribe_audio(tmp_path)
            
            os.remove(tmp_path)
            return transcript
        except Exception as e:
            print(f"Error transcribing blob: {e}")
            return ""

speech_service = SpeechToTextService()

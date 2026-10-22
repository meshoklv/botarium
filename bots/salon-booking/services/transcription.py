from openai import OpenAI
from config import GROQ_API_KEY, logger
import tempfile
import os

class TranscriptionService:
    """Service for transcribing voice messages using Groq Whisper API"""

    def __init__(self):
        self.client = OpenAI(
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1"
        )

    async def transcribe_voice(self, voice_file) -> str:
        """Transcribe voice message to text"""
        try:
            # Download voice file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.ogg')
            await voice_file.download_to_drive(temp_file.name)

            logger.info(f"Transcribing voice file: {temp_file.name}")

            # Transcribe using Groq Whisper API
            with open(temp_file.name, 'rb') as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo",
                    file=audio_file,
                    language="ru",
                    response_format="text"
                )

            # Clean up temp file
            os.unlink(temp_file.name)

            transcription = transcript.strip() if isinstance(transcript, str) else transcript.text.strip()
            logger.info(f"Transcription successful: {transcription[:100]}...")

            return transcription

        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}")
            return None


# Global service instance
transcription_service = TranscriptionService()

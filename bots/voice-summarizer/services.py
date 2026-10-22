import requests
import json
import tempfile
import os
from typing import Optional, List
from openai import OpenAI
from config import GROQ_API_KEY, OUTER_API_KEY, AI_MODEL, OPENROUTER_API_URL, SYSTEM_PROMPT_TEMPLATE, SHORT_SUMMARY_PROMPT_TEMPLATE, PERSONAL_VOICE_PROMPT, logger

# Initialize Groq client for Whisper (OpenAI-compatible)
groq_client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

class TranscriptionService:
    """Service for transcribing voice messages using Groq Whisper API"""

    @staticmethod
    async def transcribe_voice(voice_file) -> Optional[str]:
        """
        Transcribe a voice message using Groq Whisper API

        Args:
            voice_file: Telegram voice file object

        Returns:
            Transcribed text or None if failed
        """
        temp_file_path = None
        try:
            # Create temporary file for voice message
            with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
                temp_file_path = temp_file.name
                # Download voice file to temporary location
                await voice_file.download_to_drive(temp_file_path)

            # Transcribe using Groq Whisper API
            with open(temp_file_path, 'rb') as audio_file:
                transcript = groq_client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo",
                    file=audio_file,
                    language="ru",  # Russian language
                    response_format="text"
                )

            # Clean up temporary file
            os.unlink(temp_file_path)

            logger.info(f"Transcription successful: {transcript[:100]}...")
            return transcript.strip()

        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}")
            # Clean up temporary file if it exists
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
            return None

class SummaryService:
    """Service for generating summaries using Gemini Flash 2.0 via OpenRouter"""
    
    @staticmethod
    async def generate_summary(transcribed_texts: List[str], speaker_name: str = "Спикер") -> Optional[str]:
        """
        Generate summary using AI via OpenRouter

        Args:
            transcribed_texts: List of transcribed text chunks
            speaker_name: Name of the person speaking

        Returns:
            Generated summary or None if failed
        """
        try:
            logger.info(f"Starting summary generation for {speaker_name}...")

            # Combine all transcribed texts
            combined_text = "\n\n".join(transcribed_texts)
            logger.info(f"Combined text length: {len(combined_text)} characters")

            # Format system prompt with speaker name
            system_prompt = SYSTEM_PROMPT_TEMPLATE.format(speaker_name=speaker_name)

            # Prepare request payload
            payload = {
                "model": AI_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": f"Создайте хорошо структурированное резюме следующего транскрибированного текста от {speaker_name}. Организуйте информацию по темам, используйте абзацы для удобства чтения, без эмодзи:\n\n{combined_text}"
                    }
                ]
            }
            
            headers = {
                "Authorization": f"Bearer {OUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            
            logger.info("Making API request to OpenRouter...")
            
            # Make API request to OpenRouter
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=60  # Increased timeout
            )
            
            logger.info(f"API response status: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                summary = response_data['choices'][0]['message']['content']
                logger.info(f"Summary generated successfully: {summary[:100]}...")
                return summary
            else:
                logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Summary generation timed out")
            return None
        except Exception as e:
            logger.error(f"Summary generation failed: {str(e)}")
            return None
    
    @staticmethod
    async def generate_short_summary(original_summary: str, speaker_name: str = "Спикер") -> Optional[str]:
        """
        Generate a very short summary from the original summary

        Args:
            original_summary: The original full summary text
            speaker_name: Name of the person speaking

        Returns:
            Very short summary or None if failed
        """
        try:
            logger.info(f"Starting short summary generation for {speaker_name}...")

            # Format system prompt with speaker name
            system_prompt = SHORT_SUMMARY_PROMPT_TEMPLATE.format(speaker_name=speaker_name)

            # Prepare request payload
            payload = {
                "model": AI_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": f"Создайте очень короткое резюме (в 2.5 раза короче) следующего текста. Только самое важное:\n\n{original_summary}"
                    }
                ]
            }
            
            headers = {
                "Authorization": f"Bearer {OUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            
            logger.info("Making API request to OpenRouter for short summary...")
            
            # Make API request to OpenRouter
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=60
            )
            
            logger.info(f"Short summary API response status: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                short_summary = response_data['choices'][0]['message']['content']
                logger.info(f"Short summary generated successfully: {short_summary[:100]}...")
                return short_summary
            else:
                logger.error(f"OpenRouter API error for short summary: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("Short summary generation timed out")
            return None
        except Exception as e:
            logger.error(f"Short summary generation failed: {str(e)}")
            return None

    @staticmethod
    async def generate_personal_summary(transcription: str) -> Optional[str]:
        """
        Generate a structured summary for personal voice message (instant mode)

        Args:
            transcription: Single voice message transcription

        Returns:
            Structured summary or None if failed
        """
        try:
            logger.info("Starting personal voice summary generation...")

            # Prepare request payload with personal voice prompt
            payload = {
                "model": AI_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": PERSONAL_VOICE_PROMPT
                    },
                    {
                        "role": "user",
                        "content": f"Создайте структурированную выжимку из этого голосового сообщения:\n\n{transcription}"
                    }
                ]
            }

            headers = {
                "Authorization": f"Bearer {OUTER_API_KEY}",
                "Content-Type": "application/json"
            }

            logger.info("Making API request to OpenRouter for personal summary...")

            # Make API request to OpenRouter
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=60
            )

            logger.info(f"Personal summary API response status: {response.status_code}")

            if response.status_code == 200:
                response_data = response.json()
                summary = response_data['choices'][0]['message']['content']
                logger.info(f"Personal summary generated successfully: {summary[:100]}...")
                return summary
            else:
                logger.error(f"OpenRouter API error for personal summary: {response.status_code} - {response.text}")
                return None

        except requests.exceptions.Timeout:
            logger.error("Personal summary generation timed out")
            return None
        except Exception as e:
            logger.error(f"Personal summary generation failed: {str(e)}")
            return None

class SessionManager:
    """Manages user sessions for voice message collection"""
    
    def __init__(self):
        self.sessions = {}  # user_id -> session_data
        self.last_summaries = {}  # user_id -> (last_summary_text, speaker_name)

    def start_session(self, user_id: int, speaker_name: str = "Спикер"):
        """Start a new session for a user with speaker name"""
        self.sessions[user_id] = {
            'voice_messages': [],
            'transcriptions': [],
            'speaker_name': speaker_name,
            'active': True
        }
        logger.info(f"Started new session for user {user_id} with speaker {speaker_name}")
    
    def add_voice_message(self, user_id: int, voice_file, transcription: str):
        """Add a voice message and its transcription to the session"""
        if user_id not in self.sessions or not self.sessions[user_id]['active']:
            return False
        
        self.sessions[user_id]['voice_messages'].append(voice_file)
        self.sessions[user_id]['transcriptions'].append(transcription)
        logger.info(f"Added voice message to session for user {user_id}")
        return True
    
    def get_session_transcriptions(self, user_id: int) -> List[str]:
        """Get all transcriptions from the current session"""
        if user_id not in self.sessions:
            return []
        return self.sessions[user_id]['transcriptions']
    
    def end_session(self, user_id: int):
        """End the current session and return transcriptions"""
        if user_id not in self.sessions:
            return []
        
        transcriptions = self.sessions[user_id]['transcriptions']
        del self.sessions[user_id]
        logger.info(f"Ended session for user {user_id}")
        return transcriptions
    
    def save_last_summary(self, user_id: int, summary: str, speaker_name: str):
        """Save the last summary for short summary generation"""
        self.last_summaries[user_id] = (summary, speaker_name)
        logger.info(f"Saved last summary for user {user_id}")

    def get_last_summary(self, user_id: int) -> Optional[tuple]:
        """Get the last summary and speaker name for a user"""
        return self.last_summaries.get(user_id)

    def get_speaker_name(self, user_id: int) -> str:
        """Get the speaker name for current session"""
        if user_id in self.sessions:
            return self.sessions[user_id].get('speaker_name', 'Спикер')
        return 'Спикер'
    
    def has_active_session(self, user_id: int) -> bool:
        """Check if user has an active session"""
        return user_id in self.sessions and self.sessions[user_id]['active']
    
    def get_session_count(self, user_id: int) -> int:
        """Get the number of voice messages in the current session"""
        if user_id not in self.sessions:
            return 0
        return len(self.sessions[user_id]['voice_messages'])

# Initialize global session manager
session_manager = SessionManager()

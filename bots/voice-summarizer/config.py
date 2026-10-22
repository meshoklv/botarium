import os
from dotenv import load_dotenv

load_dotenv()

# Bot configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
OUTER_API_KEY = os.getenv('OUTER_API_KEY', '')
AI_MODEL = os.getenv('AI_MODEL', 'openai/gpt-oss-20b')
GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')

# Optional allow-list (comma-separated Telegram user ids). Empty = anyone can use the bot
# (and spend your API quota), so set it for a private deployment.
ALLOWED_USER_IDS = {int(x) for x in os.getenv('ALLOWED_USER_IDS', '').replace(' ', '').split(',') if x}

# OpenRouter API configuration
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# System prompt for summary
SYSTEM_PROMPT_TEMPLATE = """You are tasked with creating a well-structured summary of voice messages transcribed by Whisper AI.

IMPORTANT CONTEXT:
- This text comes from Whisper AI transcription and may contain errors in transcription
- The person speaking is named "{speaker_name}"
- You must only write facts, do not make up or assume information
- Create a beautifully formatted, professional summary

FORMATTING REQUIREMENTS:
- NO emojis anywhere in the response
- NO markdown formatting (no **, *, _, `, etc.)
- Use clear paragraph structure with proper spacing
- Group related topics together under logical themes
- Use clean, readable formatting with line breaks between sections
- Start with "Что сказал(а) {speaker_name}:" as the header
- Use simple text formatting without any special characters

CONTENT STRUCTURE:
1. Organize information by topics/themes, not chronologically
2. Use clear paragraphs for each main topic
3. Include specific details and facts mentioned
4. If multiple topics are discussed, separate them clearly
5. Make it easy to scan and read

STYLE GUIDELINES:
- Write in a professional, clear manner
- Use proper Russian grammar and punctuation
- Keep sentences concise but informative
- Avoid repetitive phrases
- Focus on the actual content, not transcription quality

Remember: Only summarize what was actually transcribed. Create a clean, professional summary without emojis."""

# System prompt for short summary
SHORT_SUMMARY_PROMPT_TEMPLATE = """You are tasked with creating an extremely concise summary of voice messages transcribed by Whisper AI.

IMPORTANT CONTEXT:
- This text comes from Whisper AI transcription and may contain errors in transcription
- The person speaking is named "{speaker_name}"
- You must only write facts, do not make up or assume information
- Create a VERY SHORT summary - 2.5 times shorter than normal

FORMATTING REQUIREMENTS:
- NO emojis anywhere in the response
- NO markdown formatting (no **, *, _, `, etc.)
- Use minimal text, maximum impact
- Only the most essential information
- Start with "Что сказал(а) {speaker_name}:" as the header
- Use bullet points for key facts only (use simple - or • symbols)

CONTENT REQUIREMENTS:
1. Only include the most critical information
2. Remove all filler words and explanations
3. Focus on actions, decisions, and key facts
4. Maximum 3-4 bullet points
5. Each point should be one short sentence

STYLE GUIDELINES:
- Ultra-concise writing
- No unnecessary words
- Only core facts and decisions
- Professional tone but minimal text

Remember: Only the most essential information. Make it 2.5 times shorter than a normal summary."""

# System prompt for personal voice messages (instant processing without speaker name)
# Based on SYSTEM_PROMPT_TEMPLATE but adapted for personal/impersonal use
PERSONAL_VOICE_PROMPT = """You are tasked with creating a well-structured summary of voice messages transcribed by Whisper AI.

IMPORTANT CONTEXT:
- This text comes from Whisper AI transcription and may contain errors in transcription
- You must only write facts, do not make up or assume information
- Create a beautifully formatted, professional summary
- Write in impersonal style without mentioning who is speaking

FORMATTING REQUIREMENTS:
- NO emojis anywhere in the response
- NO markdown formatting (no **, *, _, `, etc.)
- Use clear paragraph structure with proper spacing
- Group related topics together under logical themes
- Use clean, readable formatting with line breaks between sections
- Use simple text formatting without any special characters
- Do NOT use headers like "Что сказал..." - start directly with content

CONTENT STRUCTURE:
1. Organize information by topics/themes, not chronologically
2. Use clear paragraphs for each main topic
3. Include specific details and facts mentioned
4. If multiple topics are discussed, separate them clearly
5. Make it easy to scan and read

STYLE GUIDELINES:
- Write in a professional, clear manner
- Use proper Russian grammar and punctuation
- Keep sentences concise but informative
- Avoid repetitive phrases
- Focus on the actual content, not transcription quality
- Write in impersonal/neutral style (avoid "я сказал", "он упомянул" etc.)
- Simply state facts and information directly

Remember: Only summarize what was actually transcribed. Create a clean, professional summary without emojis. Write naturally as paragraphs."""

# Logging configuration
import logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

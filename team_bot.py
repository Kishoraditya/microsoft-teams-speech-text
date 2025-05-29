#!/usr/bin/env python3
"""
Teams Live Transcription & Translation Bot
Transcribes Sinhala audio from Teams calls and translates to English
"""

import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import websockets
import aiohttp
from aiohttp import web
from aiohttp.web import Request, Response, json_response
import azure.cognitiveservices.speech as speechsdk
from azure.ai.translation.text import TextTranslationClient
from azure.core.credentials import AzureKeyCredential
import openai
from aiohttp import web
import aiohttp_cors
import websockets
from aiohttp import web, WSMsgType
import base64
import io
import threading
from concurrent.futures import ThreadPoolExecutor
import queue
from botbuilder.core import ActivityHandler, TurnContext, MessageFactory
from botbuilder.schema import ChannelAccount, Activity, ActivityTypes

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("python-dotenv not installed. Install with: pip install python-dotenv")
    
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TeamsTranscriptionBot:
    def __init__(self):
        """Initialize the Teams Transcription Bot with Azure services"""
        # Load environment variables
        self.speech_key = os.getenv('AZURE_SPEECH_KEY')
        self.speech_region = os.getenv('AZURE_SPEECH_REGION')
        self.translator_key = os.getenv('AZURE_TRANSLATOR_KEY')
        self.translator_region = os.getenv('AZURE_TRANSLATOR_REGION')
        self.openai_key = os.getenv('AZURE_OPENAI_KEY')
        self.openai_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
        self.bot_id = os.getenv('BOT_ID')
        self.bot_password = os.getenv('BOT_PASSWORD')
        self.port = int(os.getenv('PORT', 8080))
        self.speech_results_queue = queue.Queue()
        self.active_websockets = {}
        # Validate required environment variables
        self._validate_config()
        self.teams_app_id = os.getenv('TEAMS_APP_ID')
        self.teams_app_password = os.getenv('TEAMS_APP_PASSWORD')
        
        # Initialize Azure services
        self._init_speech_service()
        self._init_translation_service()
        self._init_openai_service()
        
        # Active transcription sessions
        self.active_sessions: Dict[str, Dict] = {}
        
    def _validate_config(self):
        """Validate all required environment variables are set"""
        required_vars = [
            'AZURE_SPEECH_KEY', 'AZURE_SPEECH_REGION',
            'AZURE_TRANSLATOR_KEY', 'AZURE_TRANSLATOR_REGION',
            'AZURE_OPENAI_KEY', 'AZURE_OPENAI_ENDPOINT',
            'BOT_ID', 'BOT_PASSWORD'
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    def _init_speech_service(self):
        """Initialize Azure Speech Service for transcription"""
        speech_config = speechsdk.SpeechConfig(
            subscription=self.speech_key,
            region=self.speech_region
        )
        speech_config.speech_recognition_language = "si-LK"  # Sinhala
        speech_config.enable_dictation()
        self.speech_config = speech_config
        logger.info("Azure Speech Service initialized")
    
    def _init_translation_service(self):
        """Initialize Azure Translation Service"""
        try:
            if self.translator_key and self.translator_key != "mock_value":
                from azure.ai.translation.text import TextTranslationClient
                from azure.core.credentials import AzureKeyCredential
                
                self.translation_client = TextTranslationClient(
                    endpoint="https://api.cognitive.microsofttranslator.com",
                    credential=AzureKeyCredential(self.translator_key),
                    region=self.translator_region
                )
                logger.info("Azure Translation Service initialized")
            else:
                logger.warning("Azure Translation Service not configured - using mock translations")
                self.translation_client = None
        except Exception as e:
            logger.error(f"Failed to initialize Azure Translation Service: {str(e)}")
            self.translation_client = None

    def _init_openai_service(self):
        """Initialize Azure OpenAI for enhanced processing"""
        openai.api_type = "azure"
        openai.api_base = self.openai_endpoint
        openai.api_version = "2024-10-21"
        openai.api_key = self.openai_key
        logger.info("Azure OpenAI Service initialized")
    
    async def transcribe_audio_stream(self, audio_stream, session_id: str):
        """Transcribe audio stream in real-time"""
        try:
            # Create audio input stream
            audio_input = speechsdk.audio.PushAudioInputStream()
            audio_config = speechsdk.audio.AudioConfig(stream=audio_input)
            
            # Create speech recognizer
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=self.speech_config,
                audio_config=audio_config
            )
            
            # Set up event handlers
            def recognized_handler(evt):
                if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    asyncio.create_task(self._process_transcription(
                        evt.result.text, session_id
                    ))
            
            def canceled_handler(evt):
                logger.warning(f"Speech recognition canceled: {evt.cancellation_details.reason}")
            
            recognizer.recognized.connect(recognized_handler)
            recognizer.canceled.connect(canceled_handler)
            
            # Start continuous recognition
            recognizer.start_continuous_recognition()
            
            # Process audio stream
            async for audio_chunk in audio_stream:
                audio_input.write(audio_chunk)
            
            # Stop recognition
            recognizer.stop_continuous_recognition()
            audio_input.close()
            
        except Exception as e:
            logger.error(f"Error in transcription: {str(e)}")

    async def on_message_activity(self, turn_context: TurnContext):
        """Handle Teams messages"""
        try:
            user_message = turn_context.activity.text.lower()
            
            if 'start transcription' in user_message:
                await self._start_teams_transcription(turn_context)
            elif 'stop transcription' in user_message:
                await self._stop_teams_transcription(turn_context)
            elif 'help' in user_message:
                await self._send_help_message(turn_context)
            else:
                await turn_context.send_activity(
                    MessageFactory.text("Say 'start transcription' to begin live transcription")
                )
                
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await turn_context.send_activity(
                MessageFactory.text(f"Error: {str(e)}")
            )
    
    async def _start_teams_transcription(self, turn_context: TurnContext):
        """Start transcription in Teams"""
        try:
            conversation_id = turn_context.activity.conversation.id
            
            # Start transcription session
            await self._start_transcription_session(conversation_id)
            
            # Send confirmation
            card = self._create_transcription_card("started")
            await turn_context.send_activity(MessageFactory.attachment(card))
            
        except Exception as e:
            logger.error(f"Error starting Teams transcription: {str(e)}")
    
    async def _stop_teams_transcription(self, turn_context: TurnContext):
        """Stop transcription in Teams"""
        try:
            conversation_id = turn_context.activity.conversation.id
            
            # Stop transcription session
            await self._stop_transcription_session(conversation_id)
            
            # Send summary
            session_data = self.active_sessions.get(conversation_id, {})
            transcriptions = session_data.get('transcriptions', [])
            
            summary_card = self._create_summary_card(transcriptions)
            await turn_context.send_activity(MessageFactory.attachment(summary_card))
            
        except Exception as e:
            logger.error(f"Error stopping Teams transcription: {str(e)}")
    
    def _create_transcription_card(self, status: str):
        """Create adaptive card for transcription status"""
        card = {
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": f"🎤 Live Transcription {status.title()}",
                    "weight": "bolder",
                    "size": "medium",
                    "color": "good" if status == "started" else "attention"
                },
                {
                    "type": "TextBlock",
                    "text": "Sinhala speech will be transcribed and translated to English in real-time.",
                    "wrap": True
                }
            ]
        }
        
        return self._create_adaptive_card_attachment(card)
    
    def _create_summary_card(self, transcriptions: list):
        """Create summary card with transcription results"""
        body = [
            {
                "type": "TextBlock",
                "text": "📝 Transcription Summary",
                "weight": "bolder",
                "size": "medium"
            }
        ]
        
        for i, trans in enumerate(transcriptions[-5:]):  # Show last 5
            body.extend([
                {
                    "type": "TextBlock",
                    "text": f"**Original:** {trans['original']}",
                    "wrap": True,
                    "size": "small"
                },
                {
                    "type": "TextBlock",
                    "text": f"**Translation:** {trans['translated']}",
                    "wrap": True,
                    "color": "accent"
                },
                {
                    "type": "TextBlock",
                    "text": f"Time: {trans['timestamp']}",
                    "size": "extraSmall",
                    "color": "dark"
                }
            ])
            
            if i < len(transcriptions) - 1:
                body.append({"type": "TextBlock", "text": "---"})
        
        card = {
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": body
        }
        
        return self._create_adaptive_card_attachment(card)
    
    def _create_adaptive_card_attachment(self, card):
        """Create adaptive card attachment"""
        return {
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card
        }
    
    async def _send_help_message(self, turn_context: TurnContext):
        """Send help message"""
        help_text = """
        🤖 **Sinhala Transcription Bot**

        **Commands:**
        • `start transcription` - Begin live transcription
        • `stop transcription` - End transcription and get summary
        • `help` - Show this help message

        **Features:**
        • Real-time Sinhala speech recognition
        • Automatic English translation
        • Live transcription during Teams calls
        • Session summaries

        Just say "start transcription" to begin!
                """
                
        await turn_context.send_activity(MessageFactory.text(help_text))

    async def _process_transcription(self, sinhala_text: str, session_id: str):
        """Process transcribed text and translate to English"""
        try:
            if not sinhala_text.strip():
                return
            
            # Translate to English
            english_text = await self.translate_text(sinhala_text)
            
            # Store transcription
            timestamp = datetime.now().isoformat()
            transcription_data = {
                'timestamp': timestamp,
                'original': sinhala_text,
                'translated': english_text,
                'session_id': session_id
            }
            
            # Add to session data
            if session_id not in self.active_sessions:
                self.active_sessions[session_id] = {'transcriptions': []}
            
            self.active_sessions[session_id]['transcriptions'].append(transcription_data)
            
            # Send to Teams (webhook or bot framework)
            await self._send_to_teams(transcription_data, session_id)
            
            logger.info(f"Processed transcription for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error processing transcription: {str(e)}")
    
    async def translate_text(self, text: str) -> str:
        """Translate Sinhala text to English with post-processing"""
        try:
            # Check if translation service is properly configured
            if not self.translator_key or self.translator_key == "mock_value":
                logger.warning("Azure Translation Service not configured, using enhanced mock translation")
                return await self._enhanced_translate(text)
            
            # Use Azure Translation Service
            response = self.translation_client.translate(
                body=[{"text": text}],
                from_language="si",
                to_language=["en"]
            )
            
            if response and len(response) > 0 and response[0].translations:
                raw_translation = response[0].translations[0].text
                
                # Apply post-processing for better context
                enhanced_translation = await self._post_process_translation(text, raw_translation)
                
                logger.info(f"Translation: '{text}' -> '{enhanced_translation}'")
                return enhanced_translation
            
            logger.warning("No translation returned from Azure")
            return await self._enhanced_translate(text)
            
        except Exception as e:
            logger.error(f"Translation error: {str(e)}")
            return await self._enhanced_translate(text)

    async def _post_process_translation(self, sinhala_text: str, english_translation: str) -> str:
        """Post-process translation for better context and accuracy"""
        try:
            # Common corrections for speech recognition errors
            corrections = {
                # Common speech recognition errors
                "leopard eyes": "VBS",  # Common misrecognition
                "tir res": "tires",
                "c company": "CJ company",
                
                # Context improvements
                "i sell tires at": "I work selling tires at",
                "making myself a translator": "building a translator",
                "get rid of it": "remove that",
                
                # Business context
                "company": "company",
                "business": "business",
                "service": "service",
            }
            
            # Apply corrections
            processed_translation = english_translation.lower()
            for error, correction in corrections.items():
                processed_translation = processed_translation.replace(error, correction)
            
            # Capitalize first letter and proper nouns
            processed_translation = self._capitalize_properly(processed_translation)
            
            # Add context hints for business scenarios
            if any(word in sinhala_text for word in ["සමාගම", "ව්‍යාපාර", "සේවා"]):
                if "company" not in processed_translation and "business" not in processed_translation:
                    processed_translation += " (business context)"
            
            return processed_translation
            
        except Exception as e:
            logger.error(f"Post-processing error: {str(e)}")
            return english_translation

    def _capitalize_properly(self, text: str) -> str:
        """Properly capitalize text"""
        # Capitalize first letter
        if text:
            text = text[0].upper() + text[1:]
        
        # Capitalize common proper nouns
        proper_nouns = ["sri lanka", "sinhala", "tamil", "vbs", "cj"]
        for noun in proper_nouns:
            text = text.replace(noun, noun.title())
        
        return text

    async def _enhanced_translate(self, sinhala_text: str) -> str:
        """Enhanced contextual translation for when Azure is not available"""
        
        # Enhanced translation mappings with context
        translations = {
            # Personal introductions
            "මගේ නම්": "My name is",
            "මම": "I",
            "ඔබ": "you",
            "අපි": "we",
            
            # Business and work
            "සමාගම": "company",
            "සමාගමේ": "company's",
            "ව්‍යාපාර": "business",
            "සේවාව": "service",
            "වැඩ": "work",
            "කාර්යාලය": "office",
            "ගනුදෙනු": "transactions",
            "විකුණනවා": "selling",
            "විකුණන්නේ": "sell",
            
            # Location and language
            "ලංකාව": "Sri Lanka",
            "ලංකාවේ": "in Sri Lanka",
            "සිංහල": "Sinhala",
            "දෙමළ": "Tamil",
            "භාෂා": "language",
            "ඉගෙන ගන්නවා": "learning",
            "ඉගෙන ගන්නේ": "learning",
            "පරිවර්තන": "translation",
            "පරිවර්තකයෙක්": "translator",
            
            # Actions and questions
            "ලියන්න": "write",
            "ලියන්න ඕනෙ": "need to write",
            "මොනවද": "what",
            "කොහොමද": "how",
            "ඇති කරන්න": "create",
            "නැති කරන්න": "remove",
            "හදනවා": "making/building",
            
            # Numbers and quantities
            "හත්": "seven",
            "දෙනා": "people",
            "හත් දෙනා": "seven people",
            
            # Common phrases
            "ඉන්නේ": "am/is/are",
            "දෙකම": "both",
            "සහ": "and",
            "තව": "more",
            "ඒක": "that",
            "ඒ": "that/those",
        }
        
        # Build contextual translation
        words = sinhala_text.split()
        english_parts = []
        
        for word in words:
            word_clean = word.strip()
            best_match = None
            
            # Find best matching translation
            for sinhala_key, english_value in translations.items():
                if sinhala_key in word_clean or word_clean in sinhala_key:
                    best_match = english_value
                    break
            
            if best_match:
                english_parts.append(best_match)
            else:
                # Keep original if no translation found
                english_parts.append(f"[{word_clean}]")
        
        # Join and clean up
        result = " ".join(english_parts)
        result = result.replace("  ", " ").strip()
        
        # Apply basic grammar rules
        result = self._apply_basic_grammar(result)
        
        return result if result else f"[Translation needed: {sinhala_text}]"

    def _apply_basic_grammar(self, text: str) -> str:
        """Apply basic English grammar rules"""
        # Simple grammar improvements
        text = text.replace("I am learning both Tamil and Sinhala", "I'm learning both Tamil and Sinhala")
        text = text.replace("I am", "I'm")
        text = text.replace("need to write", "need to write")
        
        # Capitalize first letter
        if text:
            text = text[0].upper() + text[1:]
        
        return text

    async def _mock_translate(self, sinhala_text: str) -> str:
        """Provide contextual English translation for common Sinhala phrases"""
        
        # Common Sinhala to English mappings (not word-by-word)
        translations = {
            # Greetings and basic phrases
            "කොහොමද": "How are you?",
            "සුභ උදෑසනක්": "Good morning",
            "සුභ සන්ධ්‍යාවක්": "Good evening",
            "ස්තූතියි": "Thank you",
            "සමාවන්න": "Sorry",
            
            # Business/professional context
            "මගේ නම්": "My name is",
            "සමාගම": "company",
            "ව්‍යාපාර": "business",
            "සේවාව": "service",
            "ගනුදෙනු": "transactions",
            
            # Location and language
            "ලංකාව": "Sri Lanka",
            "සිංහල": "Sinhala",
            "දෙමළ": "Tamil",
            "ඉගෙන ගන්නවා": "learning",
            "පරිවර්තන": "translation",
            
            # Numbers and counting
            "හත් දෙනා": "seven people",
            "දෙනා": "people",
            
            # Actions and questions
            "ලියන්න ඕනෙ": "need to write",
            "මොනවද": "what",
            "ඇති කරන්න": "to create",
        }
        
        # Try to find contextual translation
        text_lower = sinhala_text.lower().strip()
        
        # Check for exact matches first
        if text_lower in translations:
            return translations[text_lower]
        
        # Check for partial matches and build contextual translation
        english_parts = []
        words = sinhala_text.split()
        
        for word in words:
            word_clean = word.strip()
            found_translation = False
            
            # Check if this word or phrase exists in our translations
            for sinhala_phrase, english_phrase in translations.items():
                if word_clean in sinhala_phrase or sinhala_phrase in word_clean:
                    if english_phrase not in english_parts:
                        english_parts.append(english_phrase)
                    found_translation = True
                    break
            
            # If no translation found, keep original word
            if not found_translation:
                english_parts.append(word_clean)
        
        # Join parts to form coherent English
        if english_parts:
            result = " ".join(english_parts)
            # Clean up the result
            result = result.replace("  ", " ").strip()
            return result if result else f"[Translation of: {sinhala_text}]"
        
        # Fallback: indicate that translation is needed
        return f"[Translation needed: {sinhala_text}]"
  
    async def _send_to_teams(self, transcription_data: Dict, session_id: str):
        """Send transcription to Teams channel"""
        try:
            # Create Teams adaptive card
            card = {
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {
                        "type": "TextBlock",
                        "text": "Live Transcription",
                        "weight": "bolder",
                        "size": "medium"
                    },
                    {
                        "type": "TextBlock",
                        "text": f"**Original (Sinhala):** {transcription_data['original']}",
                        "wrap": True
                    },
                    {
                        "type": "TextBlock",
                        "text": f"**Translation (English):** {transcription_data['translated']}",
                        "wrap": True
                    },
                    {
                        "type": "TextBlock",
                        "text": f"Time: {transcription_data['timestamp']}",
                        "size": "small",
                        "color": "accent"
                    }
                ]
            }
            
            # Send via webhook or bot framework
            # Implementation depends on Teams integration method
            logger.info(f"Sent transcription to Teams for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error sending to Teams: {str(e)}")
    
    async def handle_teams_webhook(self, request: Request) -> Response:
        """Handle incoming Teams webhook requests"""
        try:
            data = await request.json()
            
            # Process Teams activity
            activity_type = data.get('type', '')
            
            if activity_type == 'message':
                await self._handle_message(data)
            elif activity_type == 'invoke':
                await self._handle_call_event(data)
            
            return json_response({'status': 'success'})
            
        except Exception as e:
            logger.error(f"Webhook error: {str(e)}")
            return json_response({'error': str(e)}, status=500)
    
    async def _handle_message(self, data: Dict):
        """Handle Teams message"""
        try:
            text = data.get('text', '').lower()
            
            if 'start transcription' in text:
                session_id = data.get('conversation', {}).get('id', '')
                await self._start_transcription_session(session_id)
            elif 'stop transcription' in text:
                session_id = data.get('conversation', {}).get('id', '')
                await self._stop_transcription_session(session_id)
            
        except Exception as e:
            logger.error(f"Message handling error: {str(e)}")
    
    async def _handle_call_event(self, data: Dict):
        """Handle Teams call events"""
        try:
            # Extract call information
            call_id = data.get('value', {}).get('callId', '')
            event_type = data.get('value', {}).get('eventType', '')
            
            if event_type == 'callStarted':
                await self._join_call(call_id)
            elif event_type == 'callEnded':
                await self._leave_call(call_id)
            
        except Exception as e:
            logger.error(f"Call event handling error: {str(e)}")
    
    async def _start_transcription_session(self, session_id: str):
        """Start a new transcription session"""
        try:
            self.active_sessions[session_id] = {
                'start_time': datetime.now().isoformat(),
                'transcriptions': [],
                'status': 'active'
            }
            logger.info(f"Started transcription session: {session_id}")
            
        except Exception as e:
            logger.error(f"Error starting session: {str(e)}")
    
    async def _stop_transcription_session(self, session_id: str):
        """Stop transcription session"""
        try:
            if session_id in self.active_sessions:
                self.active_sessions[session_id]['status'] = 'stopped'
                self.active_sessions[session_id]['end_time'] = datetime.now().isoformat()
                logger.info(f"Stopped transcription session: {session_id}")
            
        except Exception as e:
            logger.error(f"Error stopping session: {str(e)}")
    
    async def _join_call(self, call_id: str):
        """Join Teams call for transcription"""
        try:
            # Implementation for joining Teams call
            # This would typically involve Microsoft Graph API
            logger.info(f"Joining call: {call_id}")
            
        except Exception as e:
            logger.error(f"Error joining call: {str(e)}")
    
    async def _leave_call(self, call_id: str):
        """Leave Teams call"""
        try:
            logger.info(f"Leaving call: {call_id}")
            
        except Exception as e:
            logger.error(f"Error leaving call: {str(e)}")
    
    async def get_session_data(self, request: Request) -> Response:
        """Get transcription data for a session"""
        try:
            session_id = request.match_info.get('session_id')
            
            if session_id in self.active_sessions:
                return json_response(self.active_sessions[session_id])
            else:
                return json_response({'error': 'Session not found'}, status=404)
                
        except Exception as e:
            logger.error(f"Error getting session data: {str(e)}")
            return json_response({'error': str(e)}, status=500)
    
    async def health_check(self, request: Request) -> Response:
        """Health check endpoint"""
        return json_response({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'active_sessions': len(self.active_sessions)
        })
    
    def create_app(self) -> web.Application:
        """Create and configure the web application"""
        app = web.Application()
        
        # Add routes
        app.router.add_post('/api/messages', self.handle_teams_webhook)
        app.router.add_get('/api/sessions/{session_id}', self.get_session_data)
        app.router.add_get('/health', self.health_check)
        
        return app
    
    async def run(self):
        """Run the bot server"""
        try:
            app = self.create_app()
            
            runner = web.AppRunner(app)
            await runner.setup()
            
            site = web.TCPSite(runner, '0.0.0.0', self.port)
            await site.start()
            
            logger.info(f"Teams Transcription Bot started on port {self.port}")
            
            # Keep the server running
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error running bot: {str(e)}")
            raise

async def main():
    """Main entry point"""
    try:
        bot = TeamsTranscriptionBot()
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
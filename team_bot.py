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
        
        # Validate required environment variables
        self._validate_config()
        
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
        self.translation_client = TextTranslationClient(
            endpoint="https://api.cognitive.microsofttranslator.com",
            credential=AzureKeyCredential(self.translator_key),
            region=self.translator_region
        )
        logger.info("Azure Translation Service initialized")
    
    def _init_openai_service(self):
        """Initialize Azure OpenAI for enhanced processing"""
        openai.api_type = "azure"
        openai.api_base = self.openai_endpoint
        openai.api_version = "2024-02-01"
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
        """Translate Sinhala text to English"""
        try:
            response = self.translation_client.translate(
                content=[text],
                from_language="si",
                to_language=["en"]
            )
            
            if response and len(response) > 0:
                return response[0].translations[0].text
            
            return text
            
        except Exception as e:
            logger.error(f"Translation error: {str(e)}")
            return text
    
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
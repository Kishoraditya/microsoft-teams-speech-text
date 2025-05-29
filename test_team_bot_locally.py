from team_bot import TeamsTranscriptionBot
from team_bot import *
import asyncio
import json
from datetime import datetime
from aiohttp import web, WSMsgType
import aiohttp_cors
import queue

class LocalTestBot(TeamsTranscriptionBot):
    def __init__(self):
        super().__init__()
        self.speech_results_queue = queue.Queue()
        self.active_websockets = {}
    


    async def serve_test_interface(self, request: Request) -> Response:
            """Serve the test interface"""
            try:
                with open('test_interface.html', 'r') as f:
                    html_content = f.read()
                return web.Response(text=html_content, content_type='text/html')
            except FileNotFoundError:
                return web.Response(text="Test interface not found", status=404)
            
    async def test_translation(self, request: Request) -> Response:
        """Test translation endpoint"""
        try:
            data = await request.json()
            text = data.get('text', '')
            
            if not text:
                return json_response({'error': 'No text provided'}, status=400)
            
            translated = await self.translate_text(text)
            
            return json_response({
                'original': text,
                'translation': translated,
                'service': 'azure' if self.translation_client else 'mock'
            })
            
        except Exception as e:
            logger.error(f"Translation test error: {str(e)}")
            return json_response({'error': str(e)}, status=500)

    async def handle_translation_test(self, request: Request) -> Response:
        """Handle translation test requests"""
        try:
            data = await request.json()
            text = data.get('text', '')
            
            if not text:
                return json_response({'error': 'No text provided'}, status=400)
            
            # Use your existing translation method
            translated_text = await self.translate_text(text)
            
            return json_response({
                'original': text,
                'translation': translated_text,
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Translation test error: {str(e)}")
            return json_response({'error': str(e)}, status=500)

    async def websocket_handler(self, request):
        """Handle WebSocket connections for real-time transcription"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        session_id = f"ws-session-{datetime.now().timestamp()}"
        logger.info(f"WebSocket connection established: {session_id}")
        
        # Initialize speech recognizer for this session
        recognizer = None
        audio_stream = None
        
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    logger.info(f"[WS RECEIVED] {data}")  # Log incoming messages
                    
                    if data['type'] == 'start_transcription':
                        logger.info("Starting transcription...")
                        # Start transcription session
                        recognizer, audio_stream = await self._start_realtime_transcription(ws, session_id)
                        if recognizer and audio_stream:
                            response = {
                                'type': 'transcription_started',
                                'session_id': session_id,
                                'message': 'Real-time transcription started'
                            }
                            logger.info(f"[WS SENDING] {response}")  # Log outgoing messages
                            await ws.send_str(json.dumps(response))
                            logger.info("Transcription started successfully")
                        else:
                            error_response = {
                                'type': 'error',
                                'message': 'Failed to start transcription'
                            }
                            logger.info(f"[WS SENDING] {error_response}")
                            await ws.send_str(json.dumps(error_response))
                    
                    elif data['type'] == 'stop_transcription':
                        logger.info("Stopping transcription...")
                        # Stop transcription
                        if recognizer:
                            recognizer.stop_continuous_recognition()
                        if audio_stream:
                            audio_stream.close()
                        # Remove from active websockets
                        if session_id in self.active_websockets:
                            del self.active_websockets[session_id]
                        response = {
                            'type': 'transcription_stopped',
                            'message': 'Transcription stopped'
                        }
                        logger.info(f"[WS SENDING] {response}")
                        await ws.send_str(json.dumps(response))
                
                elif msg.type == WSMsgType.BINARY:
                    # Receive audio data
                    if audio_stream:
                        try:
                            audio_stream.write(msg.data)
                            logger.debug(f"[AUDIO] Received {len(msg.data)} bytes")
                        except Exception as e:
                            logger.error(f"Error writing audio data: {str(e)}")
                
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f'WebSocket error: {ws.exception()}')
                    break
        
        except Exception as e:
            logger.error(f"WebSocket error: {str(e)}")
        
        finally:
            # Clean up
            if recognizer:
                try:
                    recognizer.stop_continuous_recognition()
                except:
                    pass
            if audio_stream:
                try:
                    audio_stream.close()
                except:
                    pass
            # Remove from active websockets
            if session_id in self.active_websockets:
                del self.active_websockets[session_id]
            logger.info(f"WebSocket connection closed: {session_id}")
        
        return ws

    async def _start_mock_transcription(self, ws, session_id):
        """Start mock transcription for testing without Azure services"""
        try:
            logger.info("Starting mock transcription (Azure services not available)")
            
            # Simulate transcription after a delay
            async def mock_transcription():
                await asyncio.sleep(2)
                
                # Send mock partial result
                await ws.send_str(json.dumps({
                    'type': 'partial_result',
                    'text': 'කොහොමද',
                    'language': 'si',
                    'timestamp': datetime.now().isoformat()
                }))
                
                await asyncio.sleep(1)
                
                # Send mock final result
                await self._process_realtime_transcription(
                    'කොහොමද ඔබට?', session_id, ws
                )
            
            # Start mock transcription task
            asyncio.create_task(mock_transcription())
            
            return "mock_recognizer", "mock_stream"
            
        except Exception as e:
            logger.error(f"Error in mock transcription: {str(e)}")
            return None, None

    async def _send_partial_result(self, text):
        """Send partial result to WebSocket"""
        try:
            if hasattr(self, '_current_ws') and self._current_ws:
                await self._current_ws.send_str(json.dumps({
                    'type': 'partial_result',
                    'text': text,
                    'language': 'si',
                    'timestamp': datetime.now().isoformat()
                }))
        except Exception as e:
            logger.error(f"Error sending partial result: {str(e)}")

    async def _send_error(self, message):
        """Send error message to WebSocket"""
        try:
            if hasattr(self, '_current_ws') and self._current_ws:
                await self._current_ws.send_str(json.dumps({
                    'type': 'error',
                    'message': message
                }))
        except Exception as e:
            logger.error(f"Error sending error message: {str(e)}")


    async def _start_realtime_transcription(self, ws, session_id):
        """Start real-time transcription with Azure Speech Service"""
        try:
            # Check if Azure services are properly configured
            if not self.speech_key or self.speech_key == "mock_value":
                logger.warning("Azure Speech Service not configured, using mock transcription")
                return await self._start_mock_transcription(ws, session_id)
            
            # Create push audio input stream
            audio_stream = speechsdk.audio.PushAudioInputStream()
            audio_config = speechsdk.audio.AudioConfig(stream=audio_stream)
            
            # Create speech recognizer
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=self.speech_config,
                audio_config=audio_config
            )
            
            # Store WebSocket reference
            self.active_websockets[session_id] = ws
            
            # Start background task to process speech results
            asyncio.create_task(self._process_speech_results(session_id))
            
            # Event handlers that use thread-safe queue
            def recognizing_handler(evt):
                """Handle intermediate recognition results"""
                if evt.result.text:
                    try:
                        self.speech_results_queue.put({
                            'type': 'partial',
                            'text': evt.result.text,
                            'session_id': session_id,
                            'timestamp': datetime.now().isoformat()
                        })
                        logger.debug(f"Partial result queued: {evt.result.text}")
                    except Exception as e:
                        logger.error(f"Error queuing partial result: {str(e)}")
            
            def recognized_handler(evt):
                """Handle final recognition results"""
                if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech and evt.result.text:
                    try:
                        self.speech_results_queue.put({
                            'type': 'final',
                            'text': evt.result.text,
                            'session_id': session_id,
                            'timestamp': datetime.now().isoformat()
                        })
                        logger.info(f"Final result queued: {evt.result.text}")
                    except Exception as e:
                        logger.error(f"Error queuing final result: {str(e)}")
            
            def canceled_handler(evt):
                """Handle recognition cancellation"""
                logger.warning(f"Speech recognition canceled: {evt.cancellation_details.reason}")
                try:
                    self.speech_results_queue.put({
                        'type': 'error',
                        'message': f'Recognition canceled: {evt.cancellation_details.reason}',
                        'session_id': session_id,
                        'timestamp': datetime.now().isoformat()
                    })
                except Exception as e:
                    logger.error(f"Error queuing error: {str(e)}")
            
            # Connect event handlers
            recognizer.recognizing.connect(recognizing_handler)
            recognizer.recognized.connect(recognized_handler)
            recognizer.canceled.connect(canceled_handler)
            
            # Start continuous recognition
            recognizer.start_continuous_recognition()
            logger.info("Azure Speech recognition started")
            
            return recognizer, audio_stream
            
        except Exception as e:
            logger.error(f"Error starting real-time transcription: {str(e)}")
            # Fall back to mock mode
            logger.info("Falling back to mock transcription")
            return await self._start_mock_transcription(ws, session_id)

    async def _process_speech_results(self, session_id):
        """Process speech results from the queue in the main event loop"""
        logger.info(f"Started speech results processor for session {session_id}")
        
        while session_id in self.active_websockets:
            try:
                # Check for new results (non-blocking)
                try:
                    result = self.speech_results_queue.get_nowait()
                    
                    # Only process results for this session
                    if result.get('session_id') == session_id:
                        await self._handle_speech_result(result, session_id)
                    else:
                        # Put back results for other sessions
                        self.speech_results_queue.put(result)
                        
                except queue.Empty:
                    # No results available, wait a bit
                    await asyncio.sleep(0.1)
                    continue
                    
            except Exception as e:
                logger.error(f"Error processing speech results: {str(e)}")
                await asyncio.sleep(0.1)
        
        logger.info(f"Speech results processor stopped for session {session_id}")

    async def _handle_speech_result(self, result, session_id):
        """Handle a speech recognition result"""
        try:
            ws = self.active_websockets.get(session_id)
            if not ws:
                return
            
            if result['type'] == 'partial':
                # Send partial result
                await ws.send_str(json.dumps({
                    'type': 'partial_result',
                    'text': result['text'],
                    'language': 'si',
                    'timestamp': result['timestamp']
                }))
                logger.debug(f"Sent partial result: {result['text']}")
                
            elif result['type'] == 'final':
                # Process final result with translation
                await self._process_final_transcription(result['text'], session_id, ws)
                
            elif result['type'] == 'error':
                # Send error
                await ws.send_str(json.dumps({
                    'type': 'error',
                    'message': result['message']
                }))
                
        except Exception as e:
            logger.error(f"Error handling speech result: {str(e)}")

    async def _process_final_transcription(self, sinhala_text: str, session_id: str, ws):
        """Process final transcription and translate"""
        try:
            logger.info(f"Processing final transcription: {sinhala_text}")
            
            # Translate to English
            english_text = await self.translate_text(sinhala_text)
            
            # Create transcription result
            result = {
                'type': 'final_result',
                'session_id': session_id,
                'timestamp': datetime.now().isoformat(),
                'original': {
                    'text': sinhala_text,
                    'language': 'si'
                },
                'translated': {
                    'text': english_text,
                    'language': 'en'
                }
            }
            
            # Send to WebSocket client
            await ws.send_str(json.dumps(result))
            logger.info(f"Sent final result: {sinhala_text} -> {english_text}")
            
            # Store in session data
            if session_id not in self.active_sessions:
                self.active_sessions[session_id] = {'transcriptions': []}
            
            self.active_sessions[session_id]['transcriptions'].append(result)
            
        except Exception as e:
            logger.error(f"Error processing final transcription: {str(e)}")
            await ws.send_str(json.dumps({
                'type': 'error',
                'message': f'Processing error: {str(e)}'
            }))

    async def _process_realtime_transcription(self, sinhala_text: str, session_id: str, ws):
        """Process real-time transcription and send results"""
        try:
            # Translate to English
            english_text = await self.translate_text(sinhala_text)
            
            # Create transcription result
            result = {
                'type': 'final_result',
                'session_id': session_id,
                'timestamp': datetime.now().isoformat(),
                'original': {
                    'text': sinhala_text,
                    'language': 'si'
                },
                'translated': {
                    'text': english_text,
                    'language': 'en'
                }
            }
            
            # Send to WebSocket client
            await ws.send_str(json.dumps(result))
            
            # Store in session data
            if session_id not in self.active_sessions:
                self.active_sessions[session_id] = {'transcriptions': []}
            
            self.active_sessions[session_id]['transcriptions'].append(result)
            
            logger.info(f"Processed real-time transcription for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error processing real-time transcription: {str(e)}")
            await ws.send_str(json.dumps({
                'type': 'error',
                'message': f'Processing error: {str(e)}'
            }))
    def create_app(self) -> web.Application:
        """Create and configure the web application"""
        app = web.Application()
        
        # Configure CORS for local testing
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods="*"
            )
        })
        
        # Add routes
        app.router.add_get('/', self.serve_test_interface)
        app.router.add_get('/ws', self.websocket_handler)  # WebSocket endpoint
        app.router.add_post('/api/messages', self.handle_teams_webhook)
        app.router.add_post('/api/translate', self.handle_translation_test)
        app.router.add_get('/api/sessions/{session_id}', self.get_session_data)
        app.router.add_post('/api/translate', self.test_translation)
        app.router.add_get('/health', self.health_check)
        
        # Add CORS to all routes except WebSocket
        for route in list(app.router.routes()):
            if route.method != 'GET' or '/ws' not in str(route.resource):
                cors.add(route)
        
        return app
    
async def main():
    bot = LocalTestBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())

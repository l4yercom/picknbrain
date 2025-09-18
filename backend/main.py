from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import aiohttp
import os
import uuid
import json
import random
from datetime import datetime, timedelta
import threading
import time
from typing import Dict, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="Pick N Brain Backend")

# Mount static files (if needed for future assets)
app.mount("/static", StaticFiles(directory="."), name="static")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Get API key from environment
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set")

# Question categories for variety
QUESTION_CATEGORIES = [
    "colores (de ropa, cabello, objetos, fondo)",
    "posiciones (dónde están parados/sentados los personajes)",
    "acciones (qué están haciendo los personajes)",
    "emociones (expresiones faciales: feliz, triste, sorprendido, etc.)",
    "ropa/accesorios (qué llevan puesto los personajes)",
    "objetos (qué elementos hay en la escena)",
    "cantidades (cuántos personajes u objetos se ven)",
    "tamaños (comparaciones: más grande/pequeño)",
    "formas (formas de objetos o elementos)",
    "relaciones (quién está al lado de quién, interacciones)"
]

# Session storage
sessions: Dict[str, Dict] = {}
ip_sessions: Dict[str, List[str]] = {}

# Cleanup expired sessions every 5 minutes
def cleanup_sessions():
    while True:
        time.sleep(300)  # 5 minutes
        now = datetime.now()
        expired_tokens = []
        for token, session in sessions.items():
            if now > session['expires_at']:
                expired_tokens.append(token)
                # Remove from IP tracking
                ip_list = ip_sessions.get(session['ip'], [])
                if token in ip_list:
                    ip_list.remove(token)
                    if not ip_list:
                        del ip_sessions[session['ip']]

        for token in expired_tokens:
            del sessions[token]

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_sessions, daemon=True)
cleanup_thread.start()

# Pydantic models
class StartSessionResponse(BaseModel):
    sessionToken: str
    expiresAt: str

class GenerateSceneRequest(BaseModel):
    scenePrompt: str

class GenerateSceneResponse(BaseModel):
    sceneImage: str

class AnalyzeSceneRequest(BaseModel):
    sceneData: str

class AnalyzeSceneResponse(BaseModel):
    challenge: str
    solution: str

class ValidateChallengeRequest(BaseModel):
    challenge: str
    solution: str
    playerResponse: str

class ValidateChallengeResponse(BaseModel):
    correct: bool

# Dependency to get and validate session
async def get_session(request: Request) -> Dict:
    auth_header = request.headers.get('authorization', '')
    if not auth_header.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing session token")

    token = auth_header[7:]
    session = sessions.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session token")

    if datetime.now() > session['expires_at']:
        del sessions[token]
        raise HTTPException(status_code=401, detail="Session expired")

    return session

# Rate limit check function
def check_rate_limit(session: Dict, endpoint: str, requests_per_hour: int):
    now = datetime.now()
    window_start = now - timedelta(hours=1)

    # Reset counts if window passed
    if session.get('window_start', datetime.min) < window_start:
        session['window_start'] = now
        session['request_counts'] = {'generate_scene': 0, 'analyze_scene': 0, 'validate_challenge': 0}

    count_key = f"{endpoint}_count"
    if session['request_counts'].get(count_key, 0) >= requests_per_hour:
        raise HTTPException(status_code=429, detail="Rate limit exceeded for this session")

    session['request_counts'][count_key] = session['request_counts'].get(count_key, 0) + 1

# Middleware to check max sessions per IP
@app.middleware("http")
async def check_max_sessions(request: Request, call_next):
    if request.url.path == "/api/game/start-session":
        client_ip = request.client.host
        active_sessions = ip_sessions.get(client_ip, [])
        if len(active_sessions) >= 3:
            raise HTTPException(status_code=429, detail="Maximum sessions per IP reached")

    response = await call_next(request)
    return response

# Serve index.html at root
@app.get("/")
async def serve_index():
    return FileResponse("index.html", media_type="text/html")

# Routes
@app.post("/api/game/start-session", response_model=StartSessionResponse)
async def start_session(request: Request):
    client_ip = request.client.host
    session_token = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(hours=1)

    session = {
        'token': session_token,
        'ip': client_ip,
        'created_at': datetime.now(),
        'expires_at': expires_at,
        'request_counts': {'generate_scene': 0, 'analyze_scene': 0, 'validate_challenge': 0},
        'window_start': datetime.now()
    }

    sessions[session_token] = session

    # Track sessions per IP
    if client_ip not in ip_sessions:
        ip_sessions[client_ip] = []
    ip_sessions[client_ip].append(session_token)

    return StartSessionResponse(
        sessionToken=session_token,
        expiresAt=expires_at.isoformat()
    )

@app.post("/api/game/generate-scene", response_model=GenerateSceneResponse)
async def generate_scene(request: GenerateSceneRequest, session: Dict = Depends(get_session)):
    check_rate_limit(session, 'generate_scene', 50)

    if not request.scenePrompt or len(request.scenePrompt) > 200:
        raise HTTPException(status_code=400, detail="Invalid scene prompt")

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={GEMINI_API_KEY}"
    payload = {
        "instances": [{"prompt": request.scenePrompt}],
        "parameters": {"sampleCount": 1}
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json=payload) as response:
            if not response.ok:
                raise HTTPException(status_code=500, detail="Failed to generate scene")

            result = await response.json()

    if result.get('predictions') and result['predictions'][0].get('bytesBase64Encoded'):
        return GenerateSceneResponse(sceneImage=result['predictions'][0]['bytesBase64Encoded'])
    else:
        raise HTTPException(status_code=500, detail="No image generated")

@app.post("/api/game/analyze-scene", response_model=AnalyzeSceneResponse)
async def analyze_scene(request: AnalyzeSceneRequest, session: Dict = Depends(get_session)):
    check_rate_limit(session, 'analyze_scene', 50)

    if not request.sceneData:
        raise HTTPException(status_code=400, detail="Invalid scene data")

    # Randomly select a question category
    selected_category = random.choice(QUESTION_CATEGORIES)

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={GEMINI_API_KEY}"
    prompt = f"Observa esta imagen. Genera un objeto JSON con el siguiente esquema. La 'challenge' debe ser una pregunta simple sobre {selected_category} en la imagen. La 'solution' debe ser la respuesta corta y directa a esa pregunta. El texto debe estar en español."

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inlineData": {"mimeType": "image/png", "data": request.sceneData}}
            ]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "challenge": {"type": "STRING"},
                    "solution": {"type": "STRING"}
                },
                "required": ["challenge", "solution"]
            }
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json=payload) as response:
            if not response.ok:
                raise HTTPException(status_code=500, detail="Failed to analyze scene")

            result = await response.json()

    if result.get('candidates') and result['candidates'][0].get('content') and result['candidates'][0]['content'].get('parts'):
        try:
            content = result['candidates'][0]['content']['parts'][0]['text']
            parsed = json.loads(content)
            return AnalyzeSceneResponse(challenge=parsed['challenge'], solution=parsed['solution'])
        except:
            raise HTTPException(status_code=500, detail="Invalid response from AI")
    else:
        raise HTTPException(status_code=500, detail="No content generated")

@app.post("/api/game/validate-challenge", response_model=ValidateChallengeResponse)
async def validate_challenge(request: ValidateChallengeRequest, session: Dict = Depends(get_session)):
    check_rate_limit(session, 'validate_challenge', 50)
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={GEMINI_API_KEY}"

    system_prompt = "Eres un evaluador de respuestas para un juego. Tu única función es determinar si la respuesta de un usuario es correcta. Debes responder ÚNICAMENTE con la palabra 'si' o 'no', en minúsculas y sin ningún otro texto o puntuación."
    user_prompt = f"Pregunta: \"{request.challenge}\"\nRespuesta Correcta: \"{request.solution}\"\nRespuesta del Usuario: \"{request.playerResponse}\""

    payload = {
        "contents": [{"parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]}
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json=payload) as response:
            if not response.ok:
                raise HTTPException(status_code=500, detail="Failed to validate challenge")

            result = await response.json()

    if result.get('candidates') and result['candidates'][0].get('content') and result['candidates'][0]['content'].get('parts'):
        validation = result['candidates'][0]['content']['parts'][0]['text'].strip().lower()
        return ValidateChallengeResponse(correct=validation == 'si')
    else:
        raise HTTPException(status_code=500, detail="No validation result")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

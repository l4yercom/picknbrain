# Pick N Brain - Juego de Memoria con IA

Un juego educativo donde los niños responden preguntas sobre imágenes generadas por IA de personajes famosos.

## Características

- **Backend Seguro**: API key de Gemini almacenada de forma segura en variables de entorno
- **Rate Limiting**: Control de uso por sesión (50 requests/hora por endpoint) y por IP (máx 3 sesiones)
- **Sesiones Automáticas**: Se crean automáticamente al iniciar el juego
- **Preguntas Variadas**: 10 categorías diferentes de preguntas (colores, acciones, posiciones, emociones, etc.)
- **Interfaz Amigable**: Diseño colorido y animado para niños

## Requisitos

- Python 3.8+
- pip

## Instalación y Ejecución

1. **Instalar dependencias:**
   ```bash
   cd backend
   source venv/bin/activate  # En Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configurar API key:**
   Crear archivo `.env` en el directorio `backend/`:
   ```
   GEMINI_API_KEY=tu_api_key_aqui
   ```

3. **Ejecutar el servidor:**
   ```bash
   cd backend
   source venv/bin/activate
   python main.py
   ```

4. **Acceder al juego:**
   Abrir navegador en: `http://localhost:8000`

## Arquitectura

### Backend (FastAPI)
- **Sesiones**: UUID únicos, expiración automática (1 hora)
- **Rate Limiting**: Por sesión y por IP
- **Preguntas**: 10 categorías seleccionadas aleatoriamente:
  1. Colores (ropa, cabello, objetos, fondo)
  2. Posiciones (dónde están los personajes)
  3. Acciones (qué están haciendo)
  4. Emociones (expresiones faciales)
  5. Ropa/accesorios (qué llevan puesto)
  6. Objetos (elementos en la escena)
  7. Cantidades (cuántos personajes/objetos)
  8. Tamaños (comparaciones)
  9. Formas (de objetos/elementos)
  10. Relaciones (interacciones entre personajes)
- **Endpoints**:
  - `POST /api/game/start-session` - Inicia sesión
  - `POST /api/game/generate-scene` - Genera imagen
  - `POST /api/game/analyze-scene` - Analiza imagen y genera pregunta
  - `POST /api/game/validate-challenge` - Valida respuesta

### Frontend (Vanilla JS)
- Interfaz de usuario completa
- Comunicación con backend vía fetch API
- Manejo de sesiones automático

## Seguridad

- API key nunca expuesta al cliente
- Rate limiting previene abuso
- Validación de inputs
- Sesiones con expiración automática
- CORS configurado

## Desarrollo

Para desarrollo local, el servidor incluye hot reload con `--reload`:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Producción

Para producción:
- Configurar variables de entorno seguras
- Usar un servidor ASGI como Gunicorn + Uvicorn
- Configurar HTTPS
- Limitar CORS a dominios específicos
# picknbrain

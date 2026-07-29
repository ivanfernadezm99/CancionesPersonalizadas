# Workflow: Generación de Canciones Personalizadas con Suno AI

> Tipo: **Cliente final entrega canción personalizada**  
> Stack: Suno AI Cover (`sunoapi.org`), Nextcloud WebDAV, Whisper, Python  
> Historial real probado en: Brenda (Julio 2026)

---

## Visión General

Pipeline para generar canciones personalizadas a partir de un audio de referencia (voz) + letras custom. El usuario/cliente da un audio hablado y una historia; el sistema lo convierte en canción sin decir el nombre de la persona hasta el final (sorpresa).

---

## Flujo Paso a Paso

### 1. Input del Cliente

- **Audio de referencia**: mensaje de voz, nota de audio, lo que sea — idealmente con la voz clara de la persona homenajeada
- **Historia/Contexto**: anécdotas, momentos clave, cómo se conocieron, qué los une
- **Opcional**: estilo musical deseado (balada, pop, cumbia, etc.)

### 2. Transcripción y Extracción de Datos

```bash
# Transcribir audio de referencia para capturar tono y frases reales
whisper /tmp/audio_cliente.mp3 --model tiny --language Spanish
```

- Usar `tiny` en CPU, `small` o `medium` si hay GPU
- No solo para transcribir palabras: para capturar **ritmo, pausas, entonación** de la persona

### 3. Escritura de Letra (co-creación con el usuario)

Estructura de canción Sundo Cover:

```
[Intro]        -> instrumental (opcional)
[Verse 1]      -> historia, contexto, la primera impresión
[Pre-Coro]     -> construcción, crescendo emocional
[Coro]         -> el hook, la declaración central
[Verse 2]      -> más historia, momentos específicos
[Pre-Coro]     -> igual o variante
[Coro]         -> mismo hook
[Puente]       -> reflexión, promesa, giro
[Coro Final]   -> hook con más potencia
[Outro]        -> ¡ACA REVELAR EL NOMBRE!
```

**Reglas de la letra:**
- **NO decir el nombre de la persona hasta el Outro** — la sorpresa es parte de la magia
- Usar "vos", "tus", "tu" para referirse a la persona sin nombrarla
- El Outro debe ser corto y contundente: `"[Nombre]... mi compañera, mi amiga, mi fe..."`
- Versos de 8 sílabas aprox (ritmo pop/balada)
- Mantener rima asonante o consonante en cada verso

### 4. Hostear Audio de Referencia (público)

Suno Cover necesita una URL pública al audio de referencia.

**Opción recomendada: Nextcloud file drop público**

```
URL pública: https://enlaceschacocloud.duckdns.org/public.php/webdav/reference.mp3
Auth en URL:  https://TOKEN:@dominio/public.php/webdav/reference.mp3
```

```bash
curl -T /tmp/reference.mp3 \
  -H "Content-Type: audio/mpeg" \
  "https://TOKEN:@enlaceschacocloud.duckdns.org/public.php/webdav/reference.mp3"
```

- Verificar con `curl -I` (debe dar 200/201)
- Suno descarga el audio de esta URL

### 5. Generar Canción (Suno Cover v4.5)

Script Python (`generate_suno.py`):

```python
import httpx, json

payload = {
    "instrumental": False,
    "name": "Nombre Cancion - Cover",
    "prompt": LETRA_COMPLETA,
    "audioUrl": URL_AUDIO_REFERENCIA_PUBLICA,
    "title": "Nombre Cancion",
    "tags": "pop balada romantic",
    "callBackUrl": "https://hook.whatever.com/callback",
    "model": "V4_5ALL"
}

r = httpx.post(
    f"{BASE_URL}/api/v1/generate/upload-cover",
    json=payload,
    headers={"Authorization": f"Bearer {SUNO_API_KEY}"}
)
```

### 6. Polling de Resultado

La API responde inmediatamente con un `taskId`. Hay que pollear:

```python
status_url = f"{BASE_URL}/api/v1/record?taskId={taskId}"
while True:
    r = httpx.get(...)
    data = r.json()
    if data["data"]["status"] == "SUCCESS":
        audio_url = data["data"]["response"]["sunoData"][0]["audioUrl"]
        break
```

**Mapeo de respuesta:**
- `status: "SUCCESS"` (no `"complete"`, no `"finished"`)
- `audioUrl` está en `response.sunoData[0].audioUrl`
- `response.sunoData` es un array, tomar el primer elemento

### 7. Iteración con el Cliente

- Reproducir canción generada con `ffplay`
- El cliente pide cambios en la letra
- Actualizar `prompt` y regenerar (Suno Cover tarda ~1-2 min)
- Repetir hasta aprobación final

### 8. Entrega Final

- Archivo MP3 generado en `output/{taskId}/generated.mp3`
- Subir a Nextcloud para compartir con el cliente
- Opcional: guardar letra final en Engram para referencia futura

---

## Comandos Rápidos

```bash
# Transcribir audio
whisper /tmp/audio.mp3 --model tiny --language Spanish

# Subir referencia a Nextcloud
curl -T /tmp/reference.mp3 -H "Content-Type: audio/mpeg" \
  "https://TOKEN:@enlaceschacocloud.duckdns.org/public.php/webdav/reference.mp3"

# Verificar disponibilidad
curl -sI "https://TOKEN:@enlaceschacocloud.duckdns.org/public.php/webdav/reference.mp3" | head -1

# Generar canción
python generate_suno.py

# Escuchar
ffplay output/{taskid}/generated.mp3 -nodisp -autoexit
```

---

## Secretos de Producción (descubiertos empíricamente)

| Situación | Solución |
|-----------|----------|
| Suno nunca termina | Verificar que `callBackUrl` no esté vacío (campo obligatorio aunque no se use) |
| Error de audio | `instrumental` debe ser `false` para Cover con voz |
| No se escucha la voz de referencia | La referencia debe ser voz clara, sin música de fondo |
| Letra muy larga (>3000 chars) | Suno puede timeoutear; acortar o simplificar |
| Status raro | El status exitoso es `"SUCCESS"` (todo mayúscula), no `"complete"` |
| Audio referencias privadas | Usar Nextcloud pública, no localhost |

---

## Próximas Ideas (a discutir)

- Cliente final chatbot tipo: usuario sube audio + historia, recibe canción
- UI web para iterar letras sin código
- Banco de estilos musicales para elegir
- Múltiples proveedores (Suno, Udio, etc.)
- Cola de generación con webhooks reales

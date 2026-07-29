#!/usr/bin/env python3
"""
Generate Brenda's song via Suno AI Cover mode.
Ref audio hosted on Nextcloud public WebDAV.
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

from app.music import _select_music_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("brenda-suno")

# Ref audio hosted on Nextcloud public WebDAV (token as username, empty password)
NEXTCLOUD_TOKEN = "ojAcbHDQBTX97oD"
REF_AUDIO_URL = f"https://{NEXTCLOUD_TOKEN}:@enlaceschacocloud.duckdns.org/public.php/webdav/reference.mp3"

LYRICS = """[Verse 1]
Hacía calor esa tarde dorada,
tus ojos marrones brillaban como el sol.
Con tu llama alcanzaba, el tiempo se olvidaba,
tu sonrisa me atrapo, mi corazón se iluminó.

[Pre-Coro]
Y cada día a tu lado es especial,
un regalo que no puedo dejar de valorar,
tu presencia llena todo mi ser,
no hay forma de esconder...

[Coro]
Sos dueña de mi corazón,
en las plazas todo fue magia y amor.
Tus besos, tus caricias, tu voz,
hermosa por fuera y por dentro, te amo con locura, mi amor.

[Verse 2]
Te cantaba por teléfono canciones,
con mis idas y vueltas siempre estabas vos.
Esa noche de fin de año nos unió para siempre,
desde esa noche el destino nos encontró.

[Pre-Coro]
Y cada día a tu lado es especial,
un regalo que no puedo dejar de valorar,
tu presencia llena todo mi ser,
no hay forma de esconder...

[Coro]
Sos dueña de mi corazón,
en las plazas todo fue magia y amor.
Tus besos, tus caricias, tu voz,
hermosa por fuera y por dentro, te amo con locura, mi amor.

[Puente]
Pase lo que pase, siempre voy a estar,
a tu lado, dispuesto a amar,
cada sonrisa, cada lágrima también,
juntos construimos nuestro bien.

[Coro Final]
Sos dueña de mi corazón,
en las plazas todo fue magia y amor.
Tus besos, tus caricias, tu voz,
hermosa por fuera y por dentro, te amo con locura.

[Outro]
Brenda...
mi compañera, mi amiga, mi fe,
juntos por siempre,
porque así lo queremos los dos."""


async def main():
    provider = _select_music_provider()
    log.info("Generating Brenda song via Suno Cover mode...")
    log.info("Ref audio URL: %s", REF_AUDIO_URL.replace(NEXTCLOUD_TOKEN, "***"))
    log.info("Voice prompt: bachata romántica latina")
    log.info("Model: %s", provider._model if hasattr(provider, '_model') else "default")

    result = await provider.generate(
        lyrics=LYRICS,
        voice_prompt="bachata romántica latina",
        reference_audio=REF_AUDIO_URL,
    )
    log.info("SUCCESS! Song generated at: %s", result)
    print(f"\n🎵 CANCIÓN GENERADA: {result}")


if __name__ == "__main__":
    asyncio.run(main())

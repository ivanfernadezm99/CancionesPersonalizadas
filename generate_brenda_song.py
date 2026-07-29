"""Run clip-chain generation for Brenda's full song."""
import asyncio
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

async def main():
    from app.music.clipchain import generate_stitched
    
    lyrics = Path("brenda_lyrics_final.txt").read_text()
    
    voice_prompt = (
        "Balada acústica romántica, íntima y suave, "
        "voz masculina cálida, tempo moderado, energía baja a media, "
        "guitarra acústica, producción minimalista, "
        "estilo personal y sincero, dedicado con amor"
    )
    
    reference_description = (
        "Canción íntima y suave, energía baja, tempo moderado, "
        "voz masculina cálida y emotiva, balada acústica romántica"
    )
    
    output = await generate_stitched(
        lyrics=lyrics,
        voice_prompt=voice_prompt,
        model="google/lyria-3-clip-preview",
        reference_description=reference_description,
        job_id="brenda-final-song",
    )
    
    print(f"\n✅ CANCIÓN GENERADA: {output}")

if __name__ == "__main__":
    asyncio.run(main())

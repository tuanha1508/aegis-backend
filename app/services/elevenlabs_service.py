from app.config import ELEVENLABS_API_KEY


def generate_voice_alert(text: str) -> bytes | None:
    if not ELEVENLABS_API_KEY:
        return None
    # Will be implemented when ElevenLabs integration is built
    return None

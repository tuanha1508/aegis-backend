import base64
from app.config import ELEVENLABS_API_KEY


def generate_voice_alert(text: str) -> dict:
    """Generate a voice alert using ElevenLabs TTS.

    Returns a dict with status and base64-encoded audio when configured,
    or a skip message when the API key is not set.
    """
    if not ELEVENLABS_API_KEY:
        return {"status": "skipped", "reason": "ElevenLabs not configured"}

    try:
        from elevenlabs import ElevenLabs

        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

        # Use a clear, authoritative voice for emergency alerts
        audio_iterator = client.text_to_speech.convert(
            voice_id="JBFqnCBsd6RMkjVDRZzb",  # "George" — clear male voice
            model_id="eleven_multilingual_v2",
            text=text,
        )

        # Collect all audio chunks
        audio_bytes = b"".join(chunk for chunk in audio_iterator)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        return {
            "status": "generated",
            "audio_base64": audio_b64,
            "format": "mp3",
            "text": text,
        }

    except Exception as e:
        return {"status": "error", "reason": str(e)}

from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER


def send_sms(to: str, body: str) -> dict:
    if not TWILIO_ACCOUNT_SID:
        return {"status": "skipped", "reason": "Twilio not configured"}
    from twilio.rest import Client

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    message = client.messages.create(body=body, from_=TWILIO_PHONE_NUMBER, to=to)
    return {"status": "sent", "sid": message.sid}

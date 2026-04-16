import httpx
import os
import logging

logger = logging.getLogger("STUDIO.TelegramNotifier")

# ID Telegram de Admin User (@S_am_Co)
FATHER_CHAT_ID = "999999999"

async def send_telegram_alert(message: str, chat_id: str = None, custom_token: str = None):
    """Envoie une notification Telegram. Par défaut à TELEGRAM_CHAT_ID et au Père."""
    token = custom_token or os.getenv("TELEGRAM_BOT_TOKEN")
    
    # Construction de la liste des destinataires
    recipients = []
    if chat_id:
        recipients.append(chat_id)
    else:
        main_id = os.getenv("TELEGRAM_CHAT_ID")
        if main_id:
            recipients.append(main_id)
        # On ajoute systématiquement le Père pour les alertes globales
        recipients.append(FATHER_CHAT_ID)
    
    # Nettoyage des doublons et des valeurs nulles
    recipients = [str(r) for r in set(recipients) if r]

    if not token or not recipients:
        logger.warning(f"[Telegram] Config ou destinataires manquants. Notification annulée.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    success_all = True
    try:
        async with httpx.AsyncClient() as client:
            for rid in recipients:
                payload = {
                    "chat_id": rid,
                    "text": message,
                    "parse_mode": "HTML"
                }
                resp = await client.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    logger.info(f"[Telegram] Alerte envoyée à {rid} !")
                else:
                    logger.error(f"[Telegram] Erreur {resp.status_code} pour {rid}: {resp.text}")
                    success_all = False
            return success_all
    except Exception as e:
        logger.error(f"[Telegram] Exception critique : {e}")
        return False

async def notify_father(message: str):
    """Envoie un message spécifique uniquement au père de l'utilisateur."""
    return await send_telegram_alert(message, chat_id=FATHER_CHAT_ID)

async def send_stats_update(stats_dict: dict):
    """Envoie un rapport de statistiques formaté."""
    from datetime import datetime
    msg = "📊 <b>Le Pr\xE9sentateur - Rapport Quotidien</b>\n\n"
    for plate, info in stats_dict.items():
        msg += f"🔹 <b>{plate.upper()}</b> : {info}\n"
    
    msg += f"\n📅 Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    return await send_telegram_alert(msg)

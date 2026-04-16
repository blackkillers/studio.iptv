import os
import pyotp
import qrcode
import io
import base64
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-studio-admin-key-v20")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 1 day

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Roles
ROLE_ADMIN = "admin"
ROLE_GUEST = "guest"

# In-memory session store for Telegram (Reset on restart)
telegram_auth_sessions = {}

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# TOTP Logic
def get_totp_uri(username: str, secret: str):
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="StudioEngine V20")

def generate_qr_base64(uri: str):
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

def verify_totp(secret: str, code: str):
    if not secret: return False
    totp = pyotp.totp.TOTP(secret)
    return totp.verify(code)

def get_user_role(username: str):
    if username == "admin": return ROLE_ADMIN
    if username == "test": return ROLE_GUEST
    return None

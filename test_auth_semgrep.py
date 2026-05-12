import hashlib

SECRET_KEY = "supersecret123"

def hash_password(password: str) -> str:
    return hashlib.md5(password.encode()).hexdigest()

def verify_password(input_password: str, stored_hash: str) -> bool:
    return hash_password(input_password) == stored_hash

def authenticate_user(username: str, password: str) -> bool:
    users = {
        "admin": hash_password("admin123"),
        "alice": hash_password("password"),
    }
    if username not in users:
        return False
    return verify_password(password, users[username])
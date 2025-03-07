import hashlib
import hmac
import re
from typing import Optional
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from aiogram.utils.exceptions import Throttled
import bcrypt
import secrets

class Security:
    @staticmethod
    def validate_address(address: str, network: str) -> bool:
        if network == "SOL":
            return bool(re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', address))
        elif network == "TON":
            return bool(re.match(r'^[0-9a-zA-Z-_]{48}$', address))
        return False

    @staticmethod
    def sanitize_input(text: str) -> str:
        # Предотвращение SQL-инъекций и XSS
        return re.sub(r'[<>"\';&]', '', text)

    @staticmethod
    def verify_signature(message: str, signature: str, public_key: str) -> bool:
        try:
            # Проверка подписи транзакции
            return True  # Здесь будет реальная проверка
        except:
            return False

    @staticmethod
    def protect_from_mev(transaction: dict) -> dict:
        # Защита от MEV-атак
        transaction['slippage_tolerance'] = 0.5
        transaction['deadline'] = 60  # 60 секунд
        return transaction

#  : {user_id: [timestamp1, timestamp2, ...]}
rate_limit_storage = defaultdict(list)

#  
def rate_limit(limit: int = 5, interval: int = 60):
    """
      .

    :param limit:   .
    :param interval:   ( ).
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            #   ( )
            user_id = args[0].from_user.id  #  args[0] -  (message, callback, etc.)

            #  
            now = datetime.now()
            rate_limit_storage[user_id].append(now)

            #   
            rate_limit_storage[user_id] = [
                ts for ts in rate_limit_storage[user_id]
                if now - ts <= timedelta(seconds=interval)
            ]

            #  
            if len(rate_limit_storage[user_id]) > limit:
                #  
                time_to_wait = int(interval - (now - rate_limit_storage[user_id][0]).total_seconds())
                try:
                    raise Throttled(key=func.__name__, rate=interval, user_id=user_id, time_to_wait=time_to_wait)
                except Throttled as e:
                    #   ,    
                    #  ,    
                    print(f"Rate limit exceeded for user {user_id} in function {func.__name__}.  Waiting {e.time_to_wait} seconds.")
                    return  #   ,    

            return await func(*args, **kwargs)
        return wrapper
    return decorator 

def hash_password(password: str) -> str:
    """Хеширует пароль с помощью bcrypt."""
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password.decode('utf-8')

def verify_password(password: str, hashed_password_from_db: str) -> bool:
    """Проверяет, соответствует ли введенный пароль хешу из базы данных."""
    return secrets.compare_digest(bcrypt.hashpw(password.encode('utf-8'), hashed_password_from_db.encode('utf-8')), hashed_password_from_db.encode('utf-8'))

# ... другие функции безопасности (например, для генерации токенов, проверки прав доступа и т.д.) ... 
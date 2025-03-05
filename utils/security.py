import hashlib
import hmac
import re
from typing import Optional

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
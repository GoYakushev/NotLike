from sqlalchemy import event
from core.database.database import Database
import re
import hashlib
import json
import time

class SecurityService:
    def __init__(self):
        self.db = Database()
        self._setup_sql_injection_protection()
        self._setup_rate_limiting()
        self.rate_limits = {}
        
    def _setup_sql_injection_protection(self):
        """Настраивает защиту от SQL-инъекций"""
        @event.listens_for(self.db.engine, 'before_execute')
        def before_execute(conn, clauseelement, multiparams, params):
            # Проверяем SQL на инъекции
            sql = str(clauseelement)
            if self._detect_sql_injection(sql):
                raise Exception("Обнаружена попытка SQL-инъекции")
                
    def _detect_sql_injection(self, sql: str) -> bool:
        """Проверяет SQL на наличие инъекций"""
        dangerous_patterns = [
            r';\s*DROP\s+TABLE',
            r';\s*DELETE\s+FROM',
            r';\s*UPDATE\s+.*SET',
            r'UNION\s+SELECT',
            r'--\s*$',
            r'/\*.*\*/',
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, sql, re.IGNORECASE):
                return True
        return False
        
    def check_rate_limit(self, user_id: int, action: str, limit: int = 10, window: int = 60) -> bool:
        """Проверяет ограничение частоты запросов"""
        now = time.time()
        key = f"{user_id}:{action}"
        
        if key not in self.rate_limits:
            self.rate_limits[key] = []
            
        # Очищаем старые записи
        self.rate_limits[key] = [t for t in self.rate_limits[key] if t > now - window]
        
        if len(self.rate_limits[key]) >= limit:
            return False
            
        self.rate_limits[key].append(now)
        return True
        
    def sanitize_input(self, text: str) -> str:
        """Очищает пользовательский ввод"""
        # Удаляем CRLF
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Экранируем HTML
        text = text.replace('<', '&lt;').replace('>', '&gt;')
        
        # Удаляем управляющие символы
        text = ''.join(char for char in text if ord(char) >= 32 or char == '\n')
        
        return text
        
    def validate_transaction(self, tx_data: dict) -> bool:
        """Проверяет транзакцию на MEV-атаки"""
        # Проверяем газ
        if 'gas_price' in tx_data and tx_data['gas_price'] > self._get_safe_gas_price():
            return False
            
        # Проверяем получателя
        if not self._is_safe_address(tx_data.get('to', '')):
            return False
            
        # Проверяем данные транзакции
        if not self._validate_tx_data(tx_data.get('data', '')):
            return False
            
        return True
        
    def _get_safe_gas_price(self) -> int:
        """Получает безопасную цену газа"""
        # Здесь можно добавить логику получения цены газа
        return 100 * 10**9  # 100 Gwei
        
    def _is_safe_address(self, address: str) -> bool:
        """Проверяет адрес на безопасность"""
        # Проверяем формат адреса
        if not re.match(r'^(0x[a-fA-F0-9]{40}|[a-zA-Z0-9]{48})$', address):
            return False
            
        # Проверяем адрес в черном списке
        blacklist = self._load_blacklist()
        return address not in blacklist
        
    def _validate_tx_data(self, data: str) -> bool:
        """Проверяет данные транзакции"""
        # Проверяем на известные сигнатуры атак
        dangerous_signatures = [
            '0x23b872dd',  # transferFrom
            '0x095ea7b3'   # approve
        ]
        
        return not any(sig in data for sig in dangerous_signatures)
        
    def _load_blacklist(self) -> set:
        """Загружает черный список адресов"""
        try:
            with open('blacklist.json', 'r') as f:
                return set(json.load(f))
        except:
            return set() 
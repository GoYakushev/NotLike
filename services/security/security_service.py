from sqlalchemy import event
from core.database.database import Database
import re
import hashlib
import json
import time
from typing import Dict, List, Optional, Tuple, Union
import logging
from datetime import datetime, timedelta
import aiohttp
import asyncio
from decimal import Decimal
from services.notifications.notification_service import NotificationService, NotificationType, NotificationPriority
from core.database.models import User, SecurityLog, LoginAttempt, IPAddress

logger = logging.getLogger(__name__)

class SecurityService:
    def __init__(self, notification_service: NotificationService):
        self.db = Database()
        self.logger = logging.getLogger(__name__)
        self.notification_service = notification_service
        self._setup_sql_injection_protection()
        self._setup_rate_limiting()
        self.rate_limits = {}
        self._suspicious_addresses = set()
        self._blocked_ips = set()
        self._rate_limits = {}  # user_id -> {action: [timestamps]}
        self.max_login_attempts = 5
        self.login_timeout = 30  # минут
        self.suspicious_countries = ['CN', 'RU', 'IR', 'KP']
        self._transaction_history = {}  # user_id -> [transactions]
        self._user_sessions = {}  # user_id -> {session_id: session_data}
        
        # Система оценки рисков
        self.risk_scores = {}  # user_id -> risk_score
        self.risk_thresholds = {
            'low': 30,
            'medium': 60,
            'high': 90
        }
        self.risk_weights = {
            'suspicious_ip': 20,
            'failed_login': 10,
            'suspicious_transaction': 30,
            'sql_injection': 50,
            'rate_limit': 15
        }
        
    def _setup_sql_injection_protection(self):
        """Настраивает защиту от SQL-инъекций"""
        @event.listens_for(self.db.engine, 'before_execute')
        def before_execute(conn, clauseelement, multiparams, params):
            # Проверяем SQL на инъекции
            sql = str(clauseelement)
            if self._detect_sql_injection(sql):
                self.logger.error(f"Обнаружена попытка SQL-инъекции: {sql}")
                raise Exception("Обнаружена попытка SQL-инъекции")
                
    def _detect_sql_injection(self, sql: str) -> bool:
        """Проверяет SQL на наличие инъекций"""
        if not isinstance(sql, str):
            return True
            
        dangerous_patterns = [
            r';\s*DROP\s+TABLE',
            r';\s*DELETE\s+FROM',
            r';\s*UPDATE\s+.*SET',
            r'UNION\s+SELECT',
            r'--\s*$',
            r'/\*.*\*/',
            r';\s*INSERT\s+INTO',
            r';\s*ALTER\s+TABLE',
            r';\s*CREATE\s+TABLE',
            r';\s*TRUNCATE\s+TABLE'
        ]
        
        return any(re.search(pattern, sql, re.IGNORECASE) for pattern in dangerous_patterns)
        
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
        
    async def check_rate_limit(
        self,
        user_id: int,
        action: str,
        limit: int,
        window: int
    ) -> bool:
        """Проверяет ограничение частоты действий."""
        try:
            if not isinstance(user_id, int) or user_id <= 0:
                raise ValueError("Некорректный ID пользователя")
            if not isinstance(action, str) or not action:
                raise ValueError("Некорректное действие")
            if not isinstance(limit, int) or limit <= 0:
                raise ValueError("Некорректный лимит")
            if not isinstance(window, int) or window <= 0:
                raise ValueError("Некорректное окно времени")
                
            now = datetime.utcnow()
            
            if user_id not in self._rate_limits:
                self._rate_limits[user_id] = {}
            
            if action not in self._rate_limits[user_id]:
                self._rate_limits[user_id][action] = []
            
            # Очищаем старые записи
            self._rate_limits[user_id][action] = [
                ts for ts in self._rate_limits[user_id][action]
                if (now - ts).total_seconds() < window
            ]
            
            # Проверяем лимит
            if len(self._rate_limits[user_id][action]) >= limit:
                await self.notification_service.send_security_alert(
                    user_id,
                    "rate_limit_exceeded",
                    f"Превышен лимит действий {action}",
                    f"Пожалуйста, подождите {window} секунд перед следующей попыткой.",
                    is_important=True
                )
                return False
            
            # Добавляем новое действие
            self._rate_limits[user_id][action].append(now)
            return True
            
        except ValueError as e:
            self.logger.error(f"Ошибка валидации при проверке rate limit: {str(e)}")
            return False
        except Exception as e:
            self.logger.error(f"Ошибка при проверке rate limit: {str(e)}")
            return False
        
    def sanitize_input(self, text: Union[str, None]) -> str:
        """Очищает пользовательский ввод"""
        if text is None:
            return ""
            
        if not isinstance(text, str):
            text = str(text)
            
        # Удаляем CRLF
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Экранируем HTML
        text = text.replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
        
        # Удаляем управляющие символы
        text = ''.join(char for char in text if ord(char) >= 32 or char == '\n')
        
        # Ограничиваем длину
        return text[:10000]  # Разумное ограничение на длину текста
        
    def validate_transaction(self, tx_data: dict) -> bool:
        """Проверяет транзакцию на MEV-атаки"""
        if not isinstance(tx_data, dict):
            return False
            
        try:
            # Проверяем обязательные поля
            required_fields = ['to', 'value', 'gas_price']
            if not all(field in tx_data for field in required_fields):
                return False
                
            # Проверяем газ
            if not isinstance(tx_data['gas_price'], (int, float, Decimal)):
                return False
                
            if Decimal(str(tx_data['gas_price'])) > self._get_safe_gas_price():
                return False
                
            # Проверяем получателя
            if not self._is_safe_address(tx_data.get('to', '')):
                return False
                
            # Проверяем данные транзакции
            if not self._validate_tx_data(tx_data.get('data', '')):
                return False
                
            return True
        except Exception as e:
            self.logger.error(f"Ошибка при валидации транзакции: {str(e)}")
            return False
        
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

    async def verify_transaction(
        self,
        user_id: int,
        network: str,
        from_address: str,
        to_address: str,
        amount: Decimal,
        token_symbol: str
    ) -> Tuple[bool, str]:
        """Проверяет безопасность транзакции."""
        try:
            if not isinstance(user_id, int) or user_id <= 0:
                raise ValueError("Некорректный ID пользователя")
            if not isinstance(network, str) or not network:
                raise ValueError("Некорректная сеть")
            if not isinstance(from_address, str) or not from_address:
                raise ValueError("Некорректный адрес отправителя")
            if not isinstance(to_address, str) or not to_address:
                raise ValueError("Некорректный адрес получателя")
            if not isinstance(amount, Decimal) or amount <= 0:
                raise ValueError("Некорректная сумма")
            if not isinstance(token_symbol, str) or not token_symbol:
                raise ValueError("Некорректный символ токена")

            checks = [
                self._check_address_blacklist(to_address),
                self._check_transaction_limits(user_id, amount, token_symbol),
                await self._check_address_reputation(to_address),
                self._check_unusual_activity(user_id, amount, token_symbol)
            ]
            
            failed_checks = [check[1] for check in checks if not check[0]]
            
            if failed_checks:
                # Логируем неудачную проверку
                await self.log_security_event(
                    user_id=user_id,
                    event_type="failed_transaction_check",
                    details={
                        "network": network,
                        "from_address": from_address,
                        "to_address": to_address,
                        "amount": str(amount),
                        "token_symbol": token_symbol,
                        "failed_checks": failed_checks
                    }
                )
                
                # Отправляем уведомление о подозрительной транзакции
                await self.notification_service.send_security_alert(
                    user_id,
                    "suspicious_transaction",
                    "\n".join(failed_checks),
                    "Пожалуйста, проверьте детали транзакции и убедитесь в её безопасности.",
                    is_important=True
                )
                return False, "Транзакция отклонена по соображениям безопасности:\n" + "\n".join(failed_checks)
            
            # Логируем успешную проверку
            await self.log_security_event(
                user_id=user_id,
                event_type="successful_transaction_check",
                details={
                    "network": network,
                    "from_address": from_address,
                    "to_address": to_address,
                    "amount": str(amount),
                    "token_symbol": token_symbol
                }
            )
            
            return True, "Транзакция прошла проверку безопасности"
            
        except ValueError as e:
            self.logger.error(f"Ошибка валидации при проверке транзакции: {str(e)}")
            return False, f"Ошибка валидации: {str(e)}"
        except Exception as e:
            self.logger.error(f"Ошибка при проверке транзакции: {str(e)}")
            return False, "Произошла ошибка при проверке безопасности"

    async def verify_user_session(
        self,
        user_id: int,
        session_id: str,
        ip_address: str,
        user_agent: str
    ) -> Tuple[bool, str]:
        """Проверяет безопасность пользовательской сессии."""
        try:
            # Валидация входных данных
            if not isinstance(user_id, int) or user_id <= 0:
                raise ValueError("Некорректный ID пользователя")
            if not isinstance(session_id, str) or not session_id:
                raise ValueError("Некорректный ID сессии")
            if not isinstance(ip_address, str) or not ip_address:
                raise ValueError("Некорректный IP адрес")
            if not isinstance(user_agent, str):
                raise ValueError("Некорректный User-Agent")

            # Проверяем IP
            if ip_address in self._blocked_ips:
                await self.log_security_event(
                    user_id=user_id,
                    event_type="blocked_ip_login_attempt",
                    ip_address=ip_address,
                    details={"user_agent": user_agent}
                )
                return False, "Доступ с данного IP адреса заблокирован"
                
            # Проверяем необычную активность
            if await self._is_suspicious_login(user_id, ip_address, user_agent):
                await self.log_security_event(
                    user_id=user_id,
                    event_type="suspicious_login_attempt",
                    ip_address=ip_address,
                    details={"user_agent": user_agent}
                )
                return False, "Подозрительная попытка входа"
                
            # Проверяем существующие сессии
            if user_id in self._user_sessions:
                # Очищаем старые сессии
                current_time = datetime.utcnow()
                expired_sessions = []
                for sid, session_data in self._user_sessions[user_id].items():
                    last_activity = datetime.fromisoformat(session_data['last_activity'])
                    if (current_time - last_activity).total_seconds() > 3600:  # 1 час
                        expired_sessions.append(sid)
                
                for sid in expired_sessions:
                    del self._user_sessions[user_id][sid]
                
                # Проверяем количество активных сессий
                if len(self._user_sessions[user_id]) >= 5:  # Максимум 5 активных сессий
                    await self.notification_service.send_security_alert(
                        user_id,
                        "max_sessions_reached",
                        "Достигнут лимит активных сессий",
                        "Пожалуйста, завершите одну из существующих сессий.",
                        is_important=True
                    )
                    return False, "Достигнут лимит активных сессий"
            
            # Создаем или обновляем сессию
            session_data = {
                'ip_address': ip_address,
                'user_agent': user_agent,
                'created_at': datetime.utcnow().isoformat(),
                'last_activity': datetime.utcnow().isoformat()
            }
            
            if user_id not in self._user_sessions:
                self._user_sessions[user_id] = {}
            
            self._user_sessions[user_id][session_id] = session_data
            
            # Логируем успешную авторизацию
            await self.log_security_event(
                user_id=user_id,
                event_type="successful_login",
                ip_address=ip_address,
                details={"user_agent": user_agent}
            )
            
            return True, "Сессия успешно проверена"
            
        except ValueError as e:
            self.logger.error(f"Ошибка валидации при проверке сессии: {str(e)}")
            return False, f"Ошибка валидации: {str(e)}"
        except Exception as e:
            self.logger.error(f"Ошибка при проверке сессии: {str(e)}")
            return False, "Произошла ошибка при проверке сессии"

    async def _is_suspicious_login(
        self,
        user_id: int,
        ip_address: str,
        user_agent: str
    ) -> bool:
        """Проверяет подозрительность попытки входа."""
        try:
            # Проверяем историю входов
            login_history = await self.get_login_history(user_id, limit=10)
            
            if not login_history:
                # Если это первый вход, не считаем его подозрительным
                return False
                
            # Проверяем, использовался ли этот IP раньше
            known_ips = {entry['ip_address'] for entry in login_history}
            if ip_address not in known_ips:
                # Новый IP - повышенное внимание
                
                # Проверяем геолокацию
                country_code = await self._get_ip_country(ip_address)
                if country_code in self.suspicious_countries:
                    return True
                    
                # Проверяем временной паттерн
                last_login = datetime.fromisoformat(login_history[0]['timestamp'])
                if (datetime.utcnow() - last_login).total_seconds() < 300:  # 5 минут
                    return True
                    
            # Проверяем User-Agent
            known_agents = {entry['user_agent'] for entry in login_history}
            if user_agent not in known_agents:
                # Проверяем на подозрительные паттерны в User-Agent
                suspicious_patterns = [
                    r'curl/',
                    r'python-requests/',
                    r'Postman',
                    r'[Bb]ot',
                    r'[Ss]craper',
                    r'[Cc]rawler'
                ]
                if any(re.search(pattern, user_agent) for pattern in suspicious_patterns):
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Ошибка при проверке подозрительности входа: {str(e)}")
            return True  # В случае ошибки считаем вход подозрительным

    def add_suspicious_address(self, address: str, reason: str) -> None:
        """Добавляет адрес в черный список."""
        self._suspicious_addresses.add(address)
        self.logger.info(f"Адрес {address} добавлен в черный список. Причина: {reason}")

    def block_ip(self, ip_address: str, reason: str) -> None:
        """Блокирует IP-адрес."""
        self._blocked_ips.add(ip_address)
        self.logger.info(f"IP {ip_address} заблокирован. Причина: {reason}")

    def _check_address_blacklist(self, address: str) -> Tuple[bool, str]:
        """Проверяет адрес по черному списку."""
        if address in self._suspicious_addresses:
            return False, "Адрес находится в черном списке"
        return True, ""

    def _check_transaction_limits(
        self,
        user_id: int,
        amount: Decimal,
        token_symbol: str
    ) -> Tuple[bool, str]:
        """Проверяет лимиты транзакций."""
        # Получаем историю транзакций пользователя
        history = self._transaction_history.get(user_id, [])
        
        # Проверяем дневной объем
        daily_volume = sum(
            tx['amount'] for tx in history
            if datetime.fromisoformat(tx['timestamp']) > datetime.utcnow() - timedelta(days=1)
            and tx['token_symbol'] == token_symbol
        )
        
        if daily_volume + amount > Decimal('10000'):  # Пример лимита
            return False, "Превышен дневной лимит транзакций"
            
        return True, ""

    async def _check_address_reputation(self, address: str) -> Tuple[bool, str]:
        """Проверяет репутацию адреса через внешние сервисы."""
        try:
            async with aiohttp.ClientSession() as session:
                # Здесь должен быть запрос к API для проверки репутации адреса
                # Это пример заглушки
                return True, ""
        except Exception as e:
            self.logger.error(f"Ошибка при проверке репутации адреса: {str(e)}")
            return True, ""  # В случае ошибки пропускаем транзакцию

    def _check_unusual_activity(
        self,
        user_id: int,
        amount: Decimal,
        token_symbol: str
    ) -> Tuple[bool, str]:
        """Проверяет необычную активность."""
        history = self._transaction_history.get(user_id, [])
        
        if not history:
            return True, ""
            
        # Вычисляем среднюю сумму транзакций
        avg_amount = sum(
            tx['amount'] for tx in history
            if tx['token_symbol'] == token_symbol
        ) / len(history)
        
        # Если текущая сумма в 5 раз больше средней
        if amount > avg_amount * 5:
            return False, "Необычно большая сумма транзакции"
            
        return True, ""

    def add_transaction_to_history(
        self,
        user_id: int,
        transaction: Dict
    ) -> None:
        """Добавляет транзакцию в историю."""
        if user_id not in self._transaction_history:
            self._transaction_history[user_id] = []
            
        transaction['timestamp'] = datetime.utcnow().isoformat()
        self._transaction_history[user_id].append(transaction)
        
        # Ограничиваем историю последними 1000 транзакциями
        if len(self._transaction_history[user_id]) > 1000:
            self._transaction_history[user_id] = self._transaction_history[user_id][-1000:]

    def cleanup_old_sessions(self) -> None:
        """Очищает старые сессии."""
        now = datetime.utcnow()
        for user_id in list(self._user_sessions.keys()):
            self._user_sessions[user_id] = {
                session_id: data
                for session_id, data in self._user_sessions[user_id].items()
                if now - datetime.fromisoformat(data['created_at']) < timedelta(days=7)
            } 

    async def log_security_event(
        self,
        user_id: int,
        event_type: str,
        ip_address: str,
        details: Optional[Dict] = None
    ) -> Dict:
        """Логирует событие безопасности."""
        try:
            # Создаем запись в логе
            log = SecurityLog(
                user_id=user_id,
                event_type=event_type,
                ip_address=ip_address,
                details=details,
                created_at=datetime.utcnow()
            )
            await log.save()

            # Проверяем подозрительную активность
            is_suspicious = await self._check_suspicious_activity(
                user_id,
                event_type,
                ip_address
            )

            if is_suspicious:
                # Отправляем уведомление о подозрительной активности
                await self.notification_service.send_notification(
                    user_id=user_id,
                    message=f"Обнаружена подозрительная активность!\nТип: {event_type}\nIP: {ip_address}",
                    notification_type='security_alert',
                    is_important=True
                )

            return {
                'success': True,
                'log_id': log.id,
                'is_suspicious': is_suspicious
            }

        except Exception as e:
            logger.error(f"Ошибка при логировании события безопасности: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def check_login_attempt(
        self,
        user_id: int,
        ip_address: str,
        country_code: str
    ) -> Dict:
        """Проверяет попытку входа."""
        try:
            # Проверяем количество неудачных попыток
            recent_attempts = await LoginAttempt.filter(
                user_id=user_id,
                ip_address=ip_address,
                is_successful=False,
                created_at__gte=datetime.utcnow() - timedelta(minutes=self.login_timeout)
            ).count()

            if recent_attempts >= self.max_login_attempts:
                return {
                    'success': False,
                    'error': 'Превышено количество попыток входа',
                    'timeout_minutes': self.login_timeout
                }

            # Проверяем страну
            if country_code in self.suspicious_countries:
                await self.notification_service.send_notification(
                    user_id=user_id,
                    message=f"Попытка входа из подозрительной страны: {country_code}",
                    notification_type='security_alert',
                    is_important=True
                )

            # Создаем запись о попытке входа
            attempt = LoginAttempt(
                user_id=user_id,
                ip_address=ip_address,
                country_code=country_code,
                is_successful=True,
                created_at=datetime.utcnow()
            )
            await attempt.save()

            return {
                'success': True,
                'attempt_id': attempt.id
            }

        except Exception as e:
            logger.error(f"Ошибка при проверке попытки входа: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def verify_ip_address(
        self,
        user_id: int,
        ip_address: str
    ) -> Dict:
        """Проверяет безопасность IP адреса."""
        try:
            if not isinstance(user_id, int) or user_id <= 0:
                raise ValueError("Некорректный ID пользователя")
            if not isinstance(ip_address, str) or not ip_address:
                raise ValueError("Некорректный IP адрес")

            result = {
                'is_safe': True,
                'warnings': [],
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Проверяем черный список
            if ip_address in self._blocked_ips:
                result['is_safe'] = False
                result['warnings'].append("IP адрес находится в черном списке")
                return result
                
            # Проверяем страну
            country_code = await self._get_ip_country(ip_address)
            if country_code in self.suspicious_countries:
                result['is_safe'] = False
                result['warnings'].append(f"IP адрес из подозрительной страны: {country_code}")
                
            # Проверяем историю IP адресов пользователя
            ip_history = await self.get_ip_history(user_id)
            known_ips = {entry['ip_address'] for entry in ip_history}
            
            if ip_address not in known_ips:
                result['warnings'].append("Новый IP адрес для данного пользователя")
                
                # Проверяем временной паттерн
                if ip_history:
                    last_ip_change = datetime.fromisoformat(ip_history[0]['timestamp'])
                    if (datetime.utcnow() - last_ip_change).total_seconds() < 300:  # 5 минут
                        result['is_safe'] = False
                        result['warnings'].append("Слишком частая смена IP адреса")
                        
            # Проверяем на признаки прокси/VPN
            is_proxy = await self._check_proxy(ip_address)
            if is_proxy:
                result['warnings'].append("Обнаружены признаки использования прокси/VPN")
                
            # Если есть серьезные предупреждения, отправляем уведомление
            if not result['is_safe']:
                await self.notification_service.send_security_alert(
                    user_id,
                    "suspicious_ip",
                    "Обнаружен подозрительный IP адрес",
                    "\n".join(result['warnings']),
                    is_important=True
                )
                
            # Логируем результат проверки
            await self.log_security_event(
                user_id=user_id,
                event_type="ip_verification",
                ip_address=ip_address,
                details={
                    'is_safe': result['is_safe'],
                    'warnings': result['warnings'],
                    'country_code': country_code
                }
            )
            
            return result
            
        except ValueError as e:
            self.logger.error(f"Ошибка валидации при проверке IP: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Ошибка при проверке IP: {str(e)}")
            raise

    async def _get_ip_country(self, ip_address: str) -> str:
        """Получает код страны по IP адресу."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"https://ipapi.co/{ip_address}/country/") as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        raise Exception(f"Ошибка API: {response.status}")
        except Exception as e:
            self.logger.error(f"Ошибка при определении страны по IP: {str(e)}")
            return "XX"  # Возвращаем неизвестный код страны в случае ошибки

    async def _check_proxy(self, ip_address: str) -> bool:
        """Проверяет IP на признаки прокси/VPN."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get(f"https://proxycheck.io/v2/{ip_address}") as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get(ip_address, {}).get('proxy', 'no') == 'yes'
                    else:
                        raise Exception(f"Ошибка API: {response.status}")
        except Exception as e:
            self.logger.error(f"Ошибка при проверке прокси: {str(e)}")
            return False  # В случае ошибки считаем, что это не прокси

    async def mark_ip_as_suspicious(
        self,
        user_id: int,
        ip_address: str,
        is_suspicious: bool = True
    ) -> Dict:
        """Отмечает IP адрес как подозрительный."""
        try:
            if not isinstance(user_id, int) or user_id <= 0:
                raise ValueError("Некорректный ID пользователя")
            if not isinstance(ip_address, str) or not ip_address:
                raise ValueError("Некорректный IP адрес")

            # Добавляем или удаляем из списка подозрительных
            if is_suspicious:
                self._suspicious_addresses.add(ip_address)
            else:
                self._suspicious_addresses.discard(ip_address)
                
            # Сохраняем в базу данных
            async with self.db.session() as session:
                ip_record = await session.query(IPAddress)\
                    .filter(IPAddress.address == ip_address)\
                    .first()
                    
                if not ip_record:
                    ip_record = IPAddress(
                        address=ip_address,
                        is_suspicious=is_suspicious,
                        last_updated=datetime.utcnow()
                    )
                    session.add(ip_record)
                else:
                    ip_record.is_suspicious = is_suspicious
                    ip_record.last_updated = datetime.utcnow()
                    
                await session.commit()
                
            # Логируем изменение
            await self.log_security_event(
                user_id=user_id,
                event_type="ip_status_change",
                ip_address=ip_address,
                details={'is_suspicious': is_suspicious}
            )
            
            # Отправляем уведомление
            if is_suspicious:
                await self.notification_service.send_security_alert(
                    user_id,
                    "ip_marked_suspicious",
                    f"IP адрес {ip_address} отмечен как подозрительный",
                    "Рекомендуется проверить недавнюю активность.",
                    is_important=True
                )
            
            return {
                'success': True,
                'ip_address': ip_address,
                'is_suspicious': is_suspicious,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except ValueError as e:
            self.logger.error(f"Ошибка валидации при изменении статуса IP: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Ошибка при изменении статуса IP: {str(e)}")
            raise

    async def check_transaction_security(
        self,
        user_id: int,
        transaction_type: str,
        amount: float,
        destination: str
    ) -> Dict:
        """Проверяет безопасность транзакции."""
        try:
            # Проверяем историю транзакций
            recent_transactions = await SecurityLog.filter(
                user_id=user_id,
                event_type='transaction',
                created_at__gte=datetime.utcnow() - timedelta(hours=24)
            ).all()

            total_amount = sum(
                float(t.details.get('amount', 0))
                for t in recent_transactions
                if t.details
            )

            # Проверяем на подозрительные признаки
            is_suspicious = False
            reasons = []

            # Проверка на крупную сумму
            if amount > 1000:
                is_suspicious = True
                reasons.append("Крупная сумма транзакции")

            # Проверка на частые транзакции
            if len(recent_transactions) > 10:
                is_suspicious = True
                reasons.append("Слишком много транзакций за 24 часа")

            # Проверка на превышение дневного лимита
            if total_amount + amount > 5000:
                is_suspicious = True
                reasons.append("Превышен дневной лимит")

            if is_suspicious:
                await self.notification_service.send_notification(
                    user_id=user_id,
                    message=(
                        f"Подозрительная транзакция!\n"
                        f"Тип: {transaction_type}\n"
                        f"Сумма: {amount}\n"
                        f"Причины:\n" + "\n".join(reasons)
                    ),
                    notification_type='security_alert',
                    is_important=True
                )

            return {
                'success': True,
                'is_suspicious': is_suspicious,
                'reasons': reasons
            }

        except Exception as e:
            logger.error(f"Ошибка при проверке безопасности транзакции: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_security_logs(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> list:
        """Получает логи безопасности пользователя."""
        try:
            logs = await SecurityLog.filter(
                user_id=user_id
            ).order_by('-created_at').offset(offset).limit(limit).all()

            result = []
            for log in logs:
                result.append({
                    'id': log.id,
                    'event_type': log.event_type,
                    'ip_address': log.ip_address,
                    'details': log.details,
                    'created_at': log.created_at.isoformat()
                })

            return result

        except Exception as e:
            logger.error(f"Ошибка при получении логов безопасности: {str(e)}")
            return []

    async def get_login_history(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> list:
        """Получает историю входов пользователя."""
        try:
            attempts = await LoginAttempt.filter(
                user_id=user_id
            ).order_by('-created_at').offset(offset).limit(limit).all()

            result = []
            for attempt in attempts:
                result.append({
                    'id': attempt.id,
                    'ip_address': attempt.ip_address,
                    'country_code': attempt.country_code,
                    'is_successful': attempt.is_successful,
                    'created_at': attempt.created_at.isoformat()
                })

            return result

        except Exception as e:
            logger.error(f"Ошибка при получении истории входов: {str(e)}")
            return []

    async def get_ip_history(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> list:
        """Получает историю IP-адресов пользователя."""
        try:
            ips = await IPAddress.filter(
                user_id=user_id
            ).order_by('-last_seen').offset(offset).limit(limit).all()

            result = []
            for ip in ips:
                result.append({
                    'ip_address': ip.ip_address,
                    'first_seen': ip.first_seen.isoformat(),
                    'last_seen': ip.last_seen.isoformat(),
                    'is_suspicious': ip.is_suspicious
                })

            return result

        except Exception as e:
            logger.error(f"Ошибка при получении истории IP-адресов: {str(e)}")
            return []

    async def _check_suspicious_activity(
        self,
        user_id: int,
        event_type: str,
        ip_address: str
    ) -> bool:
        """Проверяет подозрительную активность."""
        try:
            # Проверяем частоту событий
            recent_events = await SecurityLog.filter(
                user_id=user_id,
                event_type=event_type,
                created_at__gte=datetime.utcnow() - timedelta(minutes=5)
            ).count()

            if recent_events > 10:
                return True

            # Проверяем разные IP-адреса
            unique_ips = await SecurityLog.filter(
                user_id=user_id,
                created_at__gte=datetime.utcnow() - timedelta(hours=1)
            ).distinct().values_list('ip_address', flat=True)

            if len(unique_ips) > 3:
                return True

            return False

        except Exception as e:
            logger.error(f"Ошибка при проверке подозрительной активности: {str(e)}")
            return False 

    async def update_risk_score(
        self,
        user_id: int,
        event_type: str,
        details: Dict = None
    ) -> None:
        """Обновляет оценку риска для пользователя."""
        try:
            if user_id not in self.risk_scores:
                self.risk_scores[user_id] = 0
                
            # Увеличиваем оценку риска
            if event_type in self.risk_weights:
                self.risk_scores[user_id] += self.risk_weights[event_type]
                
            # Проверяем превышение порогов
            if self.risk_scores[user_id] >= self.risk_thresholds['high']:
                await self._handle_high_risk(user_id, details)
            elif self.risk_scores[user_id] >= self.risk_thresholds['medium']:
                await self._handle_medium_risk(user_id, details)
                
            # Постепенно снижаем оценку риска со временем
            asyncio.create_task(self._decay_risk_score(user_id))
            
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении оценки риска: {str(e)}")
            
    async def _handle_high_risk(self, user_id: int, details: Dict = None) -> None:
        """Обрабатывает ситуацию высокого риска."""
        try:
            # Блокируем пользователя
            await self._block_user(user_id)
            
            # Отправляем уведомление администратору
            await self.notification_service.send_notification(
                user_id=0,  # ID администратора
                message=f"Пользователь {user_id} заблокирован из-за высокого риска",
                notification_type='security_alert',
                is_important=True,
                details=details
            )
            
            # Логируем событие
            await self.log_security_event(
                user_id=user_id,
                event_type="high_risk_block",
                details=details
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка при обработке высокого риска: {str(e)}")
            
    async def _handle_medium_risk(self, user_id: int, details: Dict = None) -> None:
        """Обрабатывает ситуацию среднего риска."""
        try:
            # Включаем усиленную проверку
            await self._enable_enhanced_verification(user_id)
            
            # Отправляем предупреждение пользователю
            await self.notification_service.send_notification(
                user_id=user_id,
                message="Обнаружена подозрительная активность. Включена дополнительная проверка.",
                notification_type='security_warning',
                is_important=True,
                details=details
            )
            
        except Exception as e:
            self.logger.error(f"Ошибка при обработке среднего риска: {str(e)}")
            
    async def _decay_risk_score(self, user_id: int) -> None:
        """Постепенно снижает оценку риска."""
        try:
            while self.risk_scores[user_id] > 0:
                await asyncio.sleep(3600)  # Каждый час
                self.risk_scores[user_id] = max(0, self.risk_scores[user_id] - 5)
                
        except Exception as e:
            self.logger.error(f"Ошибка при снижении оценки риска: {str(e)}")
            
    async def _block_user(self, user_id: int) -> None:
        """Блокирует пользователя."""
        try:
            async with self.db.session() as session:
                user = await session.query(User).filter_by(id=user_id).first()
                if user:
                    user.is_blocked = True
                    user.blocked_at = datetime.utcnow()
                    await session.commit()
                    
        except Exception as e:
            self.logger.error(f"Ошибка при блокировке пользователя: {str(e)}")
            
    async def _enable_enhanced_verification(self, user_id: int) -> None:
        """Включает усиленную проверку для пользователя."""
        try:
            async with self.db.session() as session:
                user = await session.query(User).filter_by(id=user_id).first()
                if user:
                    user.enhanced_security = True
                    await session.commit()
                    
        except Exception as e:
            self.logger.error(f"Ошибка при включении усиленной проверки: {str(e)}") 
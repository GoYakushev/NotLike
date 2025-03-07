import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
from services.security.security_service import SecurityService
from services.notifications.notification_service import NotificationService
from core.database.models import User, SecurityLog, LoginAttempt, IPAddress

@pytest.fixture
def notification_service():
    return AsyncMock(spec=NotificationService)

@pytest.fixture
def security_service(notification_service):
    return SecurityService(notification_service)

@pytest.mark.asyncio
async def test_verify_transaction_valid():
    """Тест проверки валидной транзакции"""
    notification_service = AsyncMock(spec=NotificationService)
    security_service = SecurityService(notification_service)
    
    # Подготавливаем моки
    security_service._check_address_blacklist = MagicMock(return_value=(True, ""))
    security_service._check_transaction_limits = MagicMock(return_value=(True, ""))
    security_service._check_address_reputation = AsyncMock(return_value=(True, ""))
    security_service._check_unusual_activity = MagicMock(return_value=(True, ""))
    security_service.log_security_event = AsyncMock()
    
    # Выполняем проверку
    result, message = await security_service.verify_transaction(
        user_id=1,
        network="solana",
        from_address="0x123",
        to_address="0x456",
        amount=Decimal("100"),
        token_symbol="SOL"
    )
    
    assert result is True
    assert "прошла проверку" in message
    assert notification_service.send_security_alert.call_count == 0

@pytest.mark.asyncio
async def test_verify_transaction_invalid():
    """Тест проверки невалидной транзакции"""
    notification_service = AsyncMock(spec=NotificationService)
    security_service = SecurityService(notification_service)
    
    # Подготавливаем моки
    security_service._check_address_blacklist = MagicMock(return_value=(False, "Адрес в черном списке"))
    security_service._check_transaction_limits = MagicMock(return_value=(True, ""))
    security_service._check_address_reputation = AsyncMock(return_value=(True, ""))
    security_service._check_unusual_activity = MagicMock(return_value=(True, ""))
    security_service.log_security_event = AsyncMock()
    
    # Выполняем проверку
    result, message = await security_service.verify_transaction(
        user_id=1,
        network="solana",
        from_address="0x123",
        to_address="0x456",
        amount=Decimal("100"),
        token_symbol="SOL"
    )
    
    assert result is False
    assert "черном списке" in message
    assert notification_service.send_security_alert.call_count == 1

@pytest.mark.asyncio
async def test_verify_user_session_valid():
    """Тест проверки валидной сессии"""
    notification_service = AsyncMock(spec=NotificationService)
    security_service = SecurityService(notification_service)
    
    # Подготавливаем моки
    security_service._is_suspicious_login = AsyncMock(return_value=False)
    security_service.log_security_event = AsyncMock()
    
    # Выполняем проверку
    result, message = await security_service.verify_user_session(
        user_id=1,
        session_id="test_session",
        ip_address="127.0.0.1",
        user_agent="Mozilla/5.0"
    )
    
    assert result is True
    assert "успешно проверена" in message
    assert notification_service.send_security_alert.call_count == 0

@pytest.mark.asyncio
async def test_verify_user_session_blocked_ip():
    """Тест проверки сессии с заблокированным IP"""
    notification_service = AsyncMock(spec=NotificationService)
    security_service = SecurityService(notification_service)
    
    # Добавляем IP в черный список
    security_service._blocked_ips.add("127.0.0.1")
    security_service.log_security_event = AsyncMock()
    
    # Выполняем проверку
    result, message = await security_service.verify_user_session(
        user_id=1,
        session_id="test_session",
        ip_address="127.0.0.1",
        user_agent="Mozilla/5.0"
    )
    
    assert result is False
    assert "заблокирован" in message
    assert security_service.log_security_event.call_count == 1

@pytest.mark.asyncio
async def test_check_rate_limit():
    """Тест проверки ограничения частоты запросов"""
    notification_service = AsyncMock(spec=NotificationService)
    security_service = SecurityService(notification_service)
    
    # Первый запрос должен пройти
    result = await security_service.check_rate_limit(
        user_id=1,
        action="test_action",
        limit=2,
        window=60
    )
    assert result is True
    
    # Второй запрос должен пройти
    result = await security_service.check_rate_limit(
        user_id=1,
        action="test_action",
        limit=2,
        window=60
    )
    assert result is True
    
    # Третий запрос должен быть отклонен
    result = await security_service.check_rate_limit(
        user_id=1,
        action="test_action",
        limit=2,
        window=60
    )
    assert result is False
    assert notification_service.send_security_alert.call_count == 1

@pytest.mark.asyncio
async def test_verify_ip_address():
    """Тест проверки IP адреса"""
    notification_service = AsyncMock(spec=NotificationService)
    security_service = SecurityService(notification_service)
    
    # Подготавливаем моки
    security_service._get_ip_country = AsyncMock(return_value="US")
    security_service._check_proxy = AsyncMock(return_value=False)
    security_service.get_ip_history = AsyncMock(return_value=[])
    security_service.log_security_event = AsyncMock()
    
    # Проверяем обычный IP
    result = await security_service.verify_ip_address(
        user_id=1,
        ip_address="192.168.1.1"
    )
    
    assert result['is_safe'] is True
    assert len(result['warnings']) == 1  # Только предупреждение о новом IP
    assert notification_service.send_security_alert.call_count == 0
    
    # Проверяем подозрительный IP
    security_service._get_ip_country = AsyncMock(return_value="CN")
    result = await security_service.verify_ip_address(
        user_id=1,
        ip_address="192.168.1.2"
    )
    
    assert result['is_safe'] is False
    assert len(result['warnings']) > 1
    assert notification_service.send_security_alert.call_count == 1

@pytest.mark.asyncio
async def test_mark_ip_as_suspicious():
    """Тест отметки IP как подозрительного"""
    notification_service = AsyncMock(spec=NotificationService)
    security_service = SecurityService(notification_service)
    
    # Подготавливаем моки
    security_service.log_security_event = AsyncMock()
    
    # Отмечаем IP как подозрительный
    result = await security_service.mark_ip_as_suspicious(
        user_id=1,
        ip_address="192.168.1.1",
        is_suspicious=True
    )
    
    assert result['success'] is True
    assert result['is_suspicious'] is True
    assert "192.168.1.1" in security_service._suspicious_addresses
    assert notification_service.send_security_alert.call_count == 1
    
    # Снимаем отметку подозрительности
    result = await security_service.mark_ip_as_suspicious(
        user_id=1,
        ip_address="192.168.1.1",
        is_suspicious=False
    )
    
    assert result['success'] is True
    assert result['is_suspicious'] is False
    assert "192.168.1.1" not in security_service._suspicious_addresses

@pytest.mark.asyncio
async def test_sanitize_input():
    """Тест очистки пользовательского ввода"""
    notification_service = AsyncMock(spec=NotificationService)
    security_service = SecurityService(notification_service)
    
    # Проверяем базовую очистку
    result = security_service.sanitize_input("<script>alert('test')</script>")
    assert "<script>" not in result
    assert "alert" in result
    
    # Проверяем обработку None
    result = security_service.sanitize_input(None)
    assert result == ""
    
    # Проверяем обработку не строк
    result = security_service.sanitize_input(123)
    assert result == "123"
    
    # Проверяем ограничение длины
    long_input = "a" * 20000
    result = security_service.sanitize_input(long_input)
    assert len(result) == 10000

@pytest.mark.asyncio
async def test_detect_sql_injection():
    """Тест обнаружения SQL-инъекций"""
    notification_service = AsyncMock(spec=NotificationService)
    security_service = SecurityService(notification_service)
    
    # Проверяем валидные запросы
    assert not security_service._detect_sql_injection("SELECT * FROM users WHERE id = 1")
    assert not security_service._detect_sql_injection("UPDATE users SET name = 'John' WHERE id = 1")
    
    # Проверяем инъекции
    assert security_service._detect_sql_injection("SELECT * FROM users; DROP TABLE users")
    assert security_service._detect_sql_injection("SELECT * FROM users -- comment")
    assert security_service._detect_sql_injection("SELECT * FROM users WHERE id = 1; DELETE FROM users")
    assert security_service._detect_sql_injection("SELECT * FROM users /* comment */ WHERE id = 1") 
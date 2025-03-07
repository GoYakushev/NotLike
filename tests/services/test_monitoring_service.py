import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.monitoring.monitoring_service import MonitoringService
from core.database.database import Database

@pytest.fixture
def monitoring_service():
    with patch('prometheus_client.start_http_server'):
        service = MonitoringService(port=8000)
        return service

@pytest.mark.asyncio
async def test_track_swap():
    """Тест отслеживания метрик свопа"""
    monitoring_service = MonitoringService(port=8000)
    
    # Отслеживаем успешный своп
    await monitoring_service.track_swap(
        dex="ston.fi",
        network="solana",
        token_pair="SOL/USDC",
        duration=1.5,
        volume=100.0,
        success=True
    )
    
    # Проверяем метрики
    assert monitoring_service.swap_duration._metrics == {
        ('ston.fi', 'solana'): [(1.5, 1)]
    }
    assert monitoring_service.swap_volume._metrics == {
        ('ston.fi', 'solana', 'SOL/USDC'): 100.0
    }
    assert monitoring_service.swap_success._metrics == {
        ('ston.fi', 'solana'): 1
    }
    
    # Отслеживаем неудачный своп
    await monitoring_service.track_swap(
        dex="ston.fi",
        network="solana",
        token_pair="SOL/USDC",
        duration=0.5,
        volume=50.0,
        success=False,
        error_type="insufficient_liquidity"
    )
    
    # Проверяем метрики ошибок
    assert monitoring_service.swap_failure._metrics == {
        ('ston.fi', 'solana', 'insufficient_liquidity'): 1
    }

@pytest.mark.asyncio
async def test_track_api_request():
    """Тест отслеживания метрик API"""
    monitoring_service = MonitoringService(port=8000)
    
    # Отслеживаем успешный запрос
    await monitoring_service.track_api_request(
        endpoint="/api/v1/swap",
        method="POST",
        duration=0.1,
        success=True
    )
    
    # Проверяем метрики
    assert monitoring_service.api_latency._metrics == {
        ('/api/v1/swap', 'POST'): [(0.1, 1)]
    }
    
    # Отслеживаем неудачный запрос
    await monitoring_service.track_api_request(
        endpoint="/api/v1/swap",
        method="POST",
        duration=0.2,
        success=False,
        error_type="validation_error"
    )
    
    # Проверяем метрики ошибок
    assert monitoring_service.api_errors._metrics == {
        ('/api/v1/swap', 'validation_error'): 1
    }

@pytest.mark.asyncio
async def test_track_user_operation():
    """Тест отслеживания операций пользователей"""
    monitoring_service = MonitoringService(port=8000)
    
    # Отслеживаем операцию
    await monitoring_service.track_user_operation(
        operation_type="swap"
    )
    
    # Проверяем метрики
    assert monitoring_service.user_operations._metrics == {
        ('swap',): 1
    }

@pytest.mark.asyncio
async def test_collect_system_metrics():
    """Тест сбора системных метрик"""
    monitoring_service = MonitoringService(port=8000)
    
    with patch('psutil.cpu_percent', return_value=50.0), \
         patch('psutil.virtual_memory', return_value=MagicMock(percent=60.0)), \
         patch('psutil.disk_usage', return_value=MagicMock(percent=70.0)):
        
        # Запускаем сбор метрик
        await monitoring_service._collect_system_metrics()
        
        # Проверяем метрики
        assert monitoring_service.cpu_usage._value == 50.0
        assert monitoring_service.memory_usage._value == 60.0
        assert monitoring_service.disk_usage._value == 70.0

@pytest.mark.asyncio
async def test_collect_user_metrics():
    """Тест сбора метрик пользователей"""
    db_mock = AsyncMock(spec=Database)
    session_mock = AsyncMock()
    session_mock.query.return_value.scalar.return_value = 10
    db_mock.session.return_value.__aenter__.return_value = session_mock
    
    monitoring_service = MonitoringService(port=8000)
    monitoring_service.db = db_mock
    
    # Запускаем сбор метрик
    await monitoring_service._collect_user_metrics()
    
    # Проверяем метрики
    assert monitoring_service.active_users._value == 10 
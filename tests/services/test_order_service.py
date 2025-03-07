import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from services.orders.order_service import OrderService
from core.database.models import Order, OrderType, OrderStatus

@pytest.fixture
def dex_service():
    return Mock(
        execute_swap=AsyncMock(),
        get_best_price=AsyncMock()
    )

@pytest.fixture
def monitoring_service():
    return Mock(track_swap=AsyncMock())

@pytest.fixture
def cache_service():
    return Mock(
        hash_set=AsyncMock(),
        hash_get=AsyncMock(),
        hash_delete=AsyncMock(),
        list_range=AsyncMock()
    )

@pytest.fixture
def order_service(dex_service, monitoring_service, cache_service):
    return OrderService(dex_service, monitoring_service, cache_service)

@pytest.mark.asyncio
async def test_create_market_order(order_service):
    """Тест создания рыночного ордера."""
    # Подготавливаем моки
    swap_result = {
        'dex_used': 'uniswap',
        'output_amount': '100',
        'transaction_hash': '0x123'
    }
    order_service.dex_service.execute_swap.return_value = swap_result
    
    # Создаем ордер
    result = await order_service.create_order(
        user_id=1,
        order_type=OrderType.MARKET,
        network='ethereum',
        from_token='ETH',
        to_token='USDT',
        amount=Decimal('1')
    )
    
    # Проверяем результат
    assert result['status'] == OrderStatus.COMPLETED
    assert 'execution_details' in result
    assert result['execution_details'] == swap_result
    
    # Проверяем вызовы методов
    order_service.dex_service.execute_swap.assert_called_once()
    order_service.monitoring_service.track_swap.assert_called_once()

@pytest.mark.asyncio
async def test_create_stop_loss_order(order_service):
    """Тест создания стоп-лосс ордера."""
    conditions = {
        'type': 'stop_loss',
        'price': '1900'
    }
    
    # Создаем ордер
    result = await order_service.create_order(
        user_id=1,
        order_type=OrderType.STOP_LOSS,
        network='ethereum',
        from_token='ETH',
        to_token='USDT',
        amount=Decimal('1'),
        conditions=conditions
    )
    
    # Проверяем результат
    assert result['status'] == OrderStatus.PENDING
    
    # Проверяем добавление в отслеживание
    order_service.cache_service.hash_set.assert_called_once()

@pytest.mark.asyncio
async def test_execute_order(order_service):
    """Тест выполнения ордера."""
    # Подготавливаем моки
    swap_result = {
        'dex_used': 'uniswap',
        'output_amount': '100',
        'transaction_hash': '0x123'
    }
    order_service.dex_service.execute_swap.return_value = swap_result
    
    # Выполняем ордер
    result = await order_service.execute_order(1)
    
    # Проверяем результат
    assert result['status'] == OrderStatus.COMPLETED
    assert result['execution_details'] == swap_result
    
    # Проверяем вызовы методов
    order_service.dex_service.execute_swap.assert_called_once()
    order_service.monitoring_service.track_swap.assert_called_once()

@pytest.mark.asyncio
async def test_cancel_order(order_service):
    """Тест отмены ордера."""
    # Отменяем ордер
    result = await order_service.cancel_order(1)
    
    # Проверяем результат
    assert result['status'] == OrderStatus.CANCELLED
    assert 'cancelled_at' in result

@pytest.mark.asyncio
async def test_get_order(order_service):
    """Тест получения информации об ордере."""
    # Получаем ордер
    result = await order_service.get_order(1)
    
    # Проверяем наличие всех полей
    assert 'order_id' in result
    assert 'user_id' in result
    assert 'order_type' in result
    assert 'network' in result
    assert 'from_token' in result
    assert 'to_token' in result
    assert 'amount' in result
    assert 'conditions' in result
    assert 'status' in result
    assert 'created_at' in result

@pytest.mark.asyncio
async def test_get_user_orders(order_service):
    """Тест получения списка ордеров пользователя."""
    # Получаем ордера
    result = await order_service.get_user_orders(
        user_id=1,
        status=OrderStatus.PENDING
    )
    
    # Проверяем что получили список
    assert isinstance(result, list)
    
    # Если есть ордера, проверяем поля
    if result:
        order = result[0]
        assert 'order_id' in order
        assert 'order_type' in order
        assert 'network' in order
        assert 'from_token' in order
        assert 'to_token' in order
        assert 'amount' in order
        assert 'status' in order
        assert 'created_at' in order

@pytest.mark.asyncio
async def test_process_conditional_orders(order_service):
    """Тест обработки условных ордеров."""
    # Подготавливаем моки
    tracking_keys = ['ethereum:ETH']
    orders = {
        '1': {
            'order_id': 1,
            'conditions': {
                'type': 'stop_loss',
                'price': '1900'
            },
            'amount': '1'
        }
    }
    price_info = {
        'output_amount': '1800'  # Цена ниже стоп-лосса
    }
    
    order_service.cache_service.list_range.return_value = tracking_keys
    order_service.cache_service.hash_get.return_value = orders
    order_service.dex_service.get_best_price.return_value = price_info
    
    # Запускаем один цикл обработки
    await order_service._process_conditional_orders()
    
    # Проверяем что ордер был выполнен
    order_service.dex_service.execute_swap.assert_called_once()

@pytest.mark.asyncio
async def test_create_order_invalid_input(order_service):
    """Тест создания ордера с некорректными входными данными."""
    # Проверяем некорректный user_id
    with pytest.raises(ValueError, match="Некорректный ID пользователя"):
        await order_service.create_order(
            user_id=0,
            order_type=OrderType.MARKET,
            network='ethereum',
            from_token='ETH',
            to_token='USDT',
            amount=Decimal('1')
        )
    
    # Проверяем некорректную сумму
    with pytest.raises(ValueError, match="Некорректная сумма"):
        await order_service.create_order(
            user_id=1,
            order_type=OrderType.MARKET,
            network='ethereum',
            from_token='ETH',
            to_token='USDT',
            amount=Decimal('0')
        )

@pytest.mark.asyncio
async def test_execute_order_not_found(order_service):
    """Тест выполнения несуществующего ордера."""
    with pytest.raises(ValueError, match="Ордер .* не найден"):
        await order_service.execute_order(999)

@pytest.mark.asyncio
async def test_cancel_order_already_executed(order_service):
    """Тест отмены уже выполненного ордера."""
    # Мокаем получение ордера со статусом COMPLETED
    with patch('services.orders.order_service.Order') as mock_order:
        mock_order.status = OrderStatus.COMPLETED
        
        with pytest.raises(ValueError, match="Ордер .* уже обработан"):
            await order_service.cancel_order(1) 
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.cache.cache_service import CacheService

@pytest.fixture
def redis_mock():
    return AsyncMock()

@pytest.fixture
def cache_service(redis_mock):
    with patch('aioredis.from_url', return_value=redis_mock):
        service = CacheService(url="redis://localhost")
        service.redis = redis_mock
        return service

@pytest.mark.asyncio
async def test_get(cache_service, redis_mock):
    """Тест получения значения из кэша"""
    # Подготавливаем мок
    redis_mock.get.return_value = b'{"key": "value"}'
    
    # Получаем значение
    result = await cache_service.get("test_key")
    
    # Проверяем результат
    assert result == {"key": "value"}
    redis_mock.get.assert_called_once_with("test_key")
    
    # Тест с отсутствующим значением
    redis_mock.get.return_value = None
    result = await cache_service.get("missing_key")
    assert result is None

@pytest.mark.asyncio
async def test_set(cache_service, redis_mock):
    """Тест сохранения значения в кэш"""
    # Сохраняем значение
    result = await cache_service.set("test_key", {"key": "value"}, expire=60)
    
    # Проверяем результат
    assert result is True
    redis_mock.set.assert_called_once_with(
        "test_key",
        '{"key": "value"}',
        ex=60
    )
    
    # Тест с ошибкой
    redis_mock.set.side_effect = Exception("Redis error")
    result = await cache_service.set("test_key", {"key": "value"})
    assert result is False

@pytest.mark.asyncio
async def test_delete(cache_service, redis_mock):
    """Тест удаления значения из кэша"""
    # Удаляем значение
    result = await cache_service.delete("test_key")
    
    # Проверяем результат
    assert result is True
    redis_mock.delete.assert_called_once_with("test_key")
    
    # Тест с ошибкой
    redis_mock.delete.side_effect = Exception("Redis error")
    result = await cache_service.delete("test_key")
    assert result is False

@pytest.mark.asyncio
async def test_exists(cache_service, redis_mock):
    """Тест проверки существования ключа"""
    # Подготавливаем мок
    redis_mock.exists.return_value = 1
    
    # Проверяем существование
    result = await cache_service.exists("test_key")
    
    # Проверяем результат
    assert result is True
    redis_mock.exists.assert_called_once_with("test_key")
    
    # Тест с отсутствующим ключом
    redis_mock.exists.return_value = 0
    result = await cache_service.exists("missing_key")
    assert result is False

@pytest.mark.asyncio
async def test_increment(cache_service, redis_mock):
    """Тест увеличения счетчика"""
    # Подготавливаем мок
    redis_mock.incrby.return_value = 1
    
    # Увеличиваем счетчик
    result = await cache_service.increment("counter_key")
    
    # Проверяем результат
    assert result == 1
    redis_mock.incrby.assert_called_once_with("counter_key", 1)
    
    # Тест с указанным значением
    result = await cache_service.increment("counter_key", 5)
    assert result == 1
    redis_mock.incrby.assert_called_with("counter_key", 5)

@pytest.mark.asyncio
async def test_decrement(cache_service, redis_mock):
    """Тест уменьшения счетчика"""
    # Подготавливаем мок
    redis_mock.decrby.return_value = 0
    
    # Уменьшаем счетчик
    result = await cache_service.decrement("counter_key")
    
    # Проверяем результат
    assert result == 0
    redis_mock.decrby.assert_called_once_with("counter_key", 1)
    
    # Тест с указанным значением
    result = await cache_service.decrement("counter_key", 5)
    assert result == 0
    redis_mock.decrby.assert_called_with("counter_key", 5)

@pytest.mark.asyncio
async def test_set_operations(cache_service, redis_mock):
    """Тест операций с множествами"""
    # Тест добавления в множество
    result = await cache_service.set_add("set_key", "value1", "value2")
    assert result is True
    redis_mock.sadd.assert_called_once_with(
        "set_key",
        '"value1"',
        '"value2"'
    )
    
    # Тест удаления из множества
    result = await cache_service.set_remove("set_key", "value1")
    assert result is True
    redis_mock.srem.assert_called_once_with("set_key", '"value1"')
    
    # Тест получения всех значений
    redis_mock.smembers.return_value = {b'"value1"', b'"value2"'}
    result = await cache_service.set_members("set_key")
    assert result == ["value1", "value2"]
    redis_mock.smembers.assert_called_once_with("set_key")

@pytest.mark.asyncio
async def test_list_operations(cache_service, redis_mock):
    """Тест операций со списками"""
    # Тест добавления в список
    result = await cache_service.list_push("list_key", "value1", "value2")
    assert result is True
    redis_mock.rpush.assert_called_once_with(
        "list_key",
        '"value1"',
        '"value2"'
    )
    
    # Тест извлечения из списка
    redis_mock.lpop.return_value = b'"value1"'
    result = await cache_service.list_pop("list_key")
    assert result == "value1"
    redis_mock.lpop.assert_called_once_with("list_key")
    
    # Тест получения диапазона
    redis_mock.lrange.return_value = [b'"value1"', b'"value2"']
    result = await cache_service.list_range("list_key", 0, -1)
    assert result == ["value1", "value2"]
    redis_mock.lrange.assert_called_once_with("list_key", 0, -1)

@pytest.mark.asyncio
async def test_hash_operations(cache_service, redis_mock):
    """Тест операций с хэшами"""
    # Тест установки значения
    result = await cache_service.hash_set("hash_key", "field", "value")
    assert result is True
    redis_mock.hset.assert_called_once_with(
        "hash_key",
        "field",
        '"value"'
    )
    
    # Тест получения значения
    redis_mock.hget.return_value = b'"value"'
    result = await cache_service.hash_get("hash_key", "field")
    assert result == "value"
    redis_mock.hget.assert_called_once_with("hash_key", "field")
    
    # Тест удаления поля
    result = await cache_service.hash_delete("hash_key", "field")
    assert result is True
    redis_mock.hdel.assert_called_once_with("hash_key", "field")

@pytest.mark.asyncio
async def test_clear_cache(cache_service, redis_mock):
    """Тест очистки кэша"""
    # Очищаем кэш
    result = await cache_service.clear_cache()
    
    # Проверяем результат
    assert result is True
    redis_mock.flushdb.assert_called_once() 
from typing import Any, Optional, Union
import json
import logging
from datetime import datetime, timedelta
import aioredis
from core.config import REDIS_URL

class CacheService:
    def __init__(self, url: str = REDIS_URL):
        self.logger = logging.getLogger(__name__)
        self.redis = aioredis.from_url(url)
        
    async def get(self, key: str) -> Optional[Any]:
        """Получает значение из кэша."""
        try:
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            self.logger.error(f"Ошибка при получении из кэша: {str(e)}")
            return None
            
    async def set(
        self,
        key: str,
        value: Any,
        expire: int = 60  # время жизни в секундах
    ) -> bool:
        """Сохраняет значение в кэш."""
        try:
            await self.redis.set(
                key,
                json.dumps(value),
                ex=expire
            )
            return True
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении в кэш: {str(e)}")
            return False
            
    async def delete(self, key: str) -> bool:
        """Удаляет значение из кэша."""
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            self.logger.error(f"Ошибка при удалении из кэша: {str(e)}")
            return False
            
    async def exists(self, key: str) -> bool:
        """Проверяет существование ключа в кэше."""
        try:
            return await self.redis.exists(key) > 0
        except Exception as e:
            self.logger.error(f"Ошибка при проверке существования в кэше: {str(e)}")
            return False
            
    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Увеличивает значение счетчика."""
        try:
            return await self.redis.incrby(key, amount)
        except Exception as e:
            self.logger.error(f"Ошибка при увеличении счетчика: {str(e)}")
            return None
            
    async def decrement(self, key: str, amount: int = 1) -> Optional[int]:
        """Уменьшает значение счетчика."""
        try:
            return await self.redis.decrby(key, amount)
        except Exception as e:
            self.logger.error(f"Ошибка при уменьшении счетчика: {str(e)}")
            return None
            
    async def set_add(self, key: str, *values: Any) -> bool:
        """Добавляет значения в множество."""
        try:
            values_json = [json.dumps(v) for v in values]
            await self.redis.sadd(key, *values_json)
            return True
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении в множество: {str(e)}")
            return False
            
    async def set_remove(self, key: str, *values: Any) -> bool:
        """Удаляет значения из множества."""
        try:
            values_json = [json.dumps(v) for v in values]
            await self.redis.srem(key, *values_json)
            return True
        except Exception as e:
            self.logger.error(f"Ошибка при удалении из множества: {str(e)}")
            return False
            
    async def set_members(self, key: str) -> list:
        """Получает все значения множества."""
        try:
            values = await self.redis.smembers(key)
            return [json.loads(v) for v in values]
        except Exception as e:
            self.logger.error(f"Ошибка при получении значений множества: {str(e)}")
            return []
            
    async def list_push(self, key: str, *values: Any) -> bool:
        """Добавляет значения в список."""
        try:
            values_json = [json.dumps(v) for v in values]
            await self.redis.rpush(key, *values_json)
            return True
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении в список: {str(e)}")
            return False
            
    async def list_pop(self, key: str) -> Optional[Any]:
        """Извлекает значение из списка."""
        try:
            value = await self.redis.lpop(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            self.logger.error(f"Ошибка при извлечении из списка: {str(e)}")
            return None
            
    async def list_range(
        self,
        key: str,
        start: int = 0,
        end: int = -1
    ) -> list:
        """Получает диапазон значений из списка."""
        try:
            values = await self.redis.lrange(key, start, end)
            return [json.loads(v) for v in values]
        except Exception as e:
            self.logger.error(f"Ошибка при получении диапазона списка: {str(e)}")
            return []
            
    async def hash_set(self, key: str, field: str, value: Any) -> bool:
        """Устанавливает значение поля хэша."""
        try:
            await self.redis.hset(key, field, json.dumps(value))
            return True
        except Exception as e:
            self.logger.error(f"Ошибка при установке значения хэша: {str(e)}")
            return False
            
    async def hash_get(self, key: str, field: str) -> Optional[Any]:
        """Получает значение поля хэша."""
        try:
            value = await self.redis.hget(key, field)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            self.logger.error(f"Ошибка при получении значения хэша: {str(e)}")
            return None
            
    async def hash_delete(self, key: str, field: str) -> bool:
        """Удаляет поле хэша."""
        try:
            await self.redis.hdel(key, field)
            return True
        except Exception as e:
            self.logger.error(f"Ошибка при удалении поля хэша: {str(e)}")
            return False
            
    async def clear_cache(self) -> bool:
        """Очищает весь кэш."""
        try:
            await self.redis.flushdb()
            return True
        except Exception as e:
            self.logger.error(f"Ошибка при очистке кэша: {str(e)}")
            return False 
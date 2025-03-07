import pytest
from utils.security import rate_limit, rate_limit_storage, hash_password, verify_password
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta
from aiogram.utils.exceptions import Throttled
import asyncio
import unittest
from NotLike3.utils.security import check_password

pytest_plugins = ('pytest_asyncio',)

@pytest.fixture
def message_mock():
    mock = AsyncMock()
    mock.from_user.id = 123
    return mock

@pytest.mark.asyncio
async def test_rate_limit_not_exceeded(message_mock):
    """Тест rate_limit: лимит не превышен."""
    rate_limit_storage.clear()  #  
    @rate_limit(limit=3, interval=60)
    async def test_func(message):
        return "OK"

    result = await test_func(message_mock)
    assert result == "OK"
    assert len(rate_limit_storage[123]) == 1

@pytest.mark.asyncio
async def test_rate_limit_exceeded(message_mock):
    """Тест rate_limit: лимит превышен."""
    rate_limit_storage.clear()
    @rate_limit(limit=3, interval=60)
    async def test_func(message):
        return "OK"

    #   
    for _ in range(3):
        await test_func(message_mock)

    #  
    result = await test_func(message_mock)
    assert result is None  #   ,    
    assert len(rate_limit_storage[123]) == 4 #  ,     

@pytest.mark.asyncio
async def test_rate_limit_time_window(message_mock):
    """Тест rate_limit: временное окно."""
    rate_limit_storage.clear()
    @rate_limit(limit=3, interval=1)  #  1 
    async def test_func(message):
        return "OK"

    #   
    for _ in range(3):
        await test_func(message_mock)

    #   1 
    await asyncio.sleep(1.1)

    #   
    result = await test_func(message_mock)
    assert result == "OK"
    assert len(rate_limit_storage[123]) == 1 #   

@pytest.mark.asyncio
async def test_rate_limit_multiple_users(message_mock):
    """Тест rate_limit: несколько пользователей."""
    rate_limit_storage.clear()
    @rate_limit(limit=2, interval=60)
    async def test_func(message):
        return "OK"

    #  1
    message_mock.from_user.id = 111
    await test_func(message_mock)
    await test_func(message_mock)
    result = await test_func(message_mock) #  
    assert result is None

    #  2
    message_mock.from_user.id = 222
    result = await test_func(message_mock)
    assert result == "OK"
    assert len(rate_limit_storage[222]) == 1

class TestSecurityUtils(unittest.TestCase):

    def test_hash_password(self):
        password = "test_password"
        hashed_password = hash_password(password)
        self.assertNotEqual(password, hashed_password) # Хеш должен отличаться от исходного пароля
        self.assertTrue(hashed_password.startswith('$2b$')) # Проверка, что это bcrypt хеш (может отличаться в зависимости от библиотеки)

    def test_check_password(self):
        password = "test_password"
        hashed_password = hash_password(password)
        self.assertTrue(check_password(password, hashed_password)) # Проверка правильного пароля
        self.assertFalse(check_password("wrong_password", hashed_password)) # Проверка неправильного пароля

def test_hash_password():
    """Тест функции hash_password."""
    password = "test_password"
    hashed_password = hash_password(password)
    assert isinstance(hashed_password, str) # Проверяем, что хеш - строка
    assert hashed_password != password # Проверяем, что хеш отличается от исходного пароля

def test_verify_password_valid():
    """Тест функции verify_password с правильным паролем."""
    password = "test_password"
    hashed_password = hash_password(password)
    assert verify_password(password, hashed_password) # Проверяем, что verify_password возвращает True для правильного пароля

def test_verify_password_invalid():
    """Тест функции verify_password с неправильным паролем."""
    password = "test_password"
    hashed_password = hash_password(password)
    wrong_password = "wrong_password"
    assert not verify_password(wrong_password, hashed_password) # Проверяем, что verify_password возвращает False для неправильного пароля

def test_verify_password_different_hashes():
    """Тест функции verify_password с разными хешами."""
    password = "test_password"
    hashed_password1 = hash_password(password)
    hashed_password2 = hash_password(password) # Генерируем второй хеш, bcrypt каждый раз генерирует новый salt
    assert not verify_password(hashed_password2, hashed_password1) # Проверяем, что verify_password возвращает False для разных хешей, даже если пароли одинаковые (из-за salt)

# ... другие тесты для функций безопасности ... 
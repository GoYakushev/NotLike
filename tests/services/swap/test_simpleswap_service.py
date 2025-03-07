import pytest
from services.swap.simpleswap_service import SimpleSwapService
import aiohttp
from unittest.mock import AsyncMock, patch

pytest_plugins = ('pytest_asyncio',)

@pytest.fixture
def simpleswap_service():
    return SimpleSwapService(api_key="test_api_key")

@pytest.mark.asyncio
async def test_get_currencies(simpleswap_service):
    """Тест get_currencies."""
    mock_response = AsyncMock()
    mock_response.json.return_value = [{"currency": "BTC"}, {"currency": "ETH"}]

    with patch('aiohttp.ClientSession.get', return_value=mock_response) as mock_get:
        currencies = await simpleswap_service.get_currencies()

    assert len(currencies) == 2
    assert currencies[0]['currency'] == "BTC"
    assert currencies[1]['currency'] == "ETH"
    mock_get.assert_called_once_with(
        "https://api.simpleswap.io/v1/get_currencies",
        headers={"api-key": "test_api_key"}
    )

@pytest.mark.asyncio
async def test_get_pairs(simpleswap_service):
    """Тест get_pairs."""
    mock_response = AsyncMock()
    mock_response.json.return_value = ["ETH", "TON"]

    with patch('aiohttp.ClientSession.get', return_value=mock_response) as mock_get:
        pairs = await simpleswap_service.get_pairs("BTC")

    assert len(pairs) == 2
    assert pairs[0] == "ETH"
    assert pairs[1] == "TON"
    mock_get.assert_called_once_with(
        "https://api.simpleswap.io/v1/get_pairs",
        params={"fixed": 1, "currency_from": "BTC"},
        headers={"api-key": "test_api_key"}
    )

@pytest.mark.asyncio
async def test_get_estimated_amount(simpleswap_service):
    """Тест get_estimated_amount."""
    mock_response = AsyncMock()
    mock_response.json.return_value = {"estimated_amount": "10.5"}

    with patch('aiohttp.ClientSession.get', return_value=mock_response) as mock_get:
        amount = await simpleswap_service.get_estimated_amount("BTC", "ETH", 1.0)

    assert amount == 10.5
    mock_get.assert_called_once_with(
        "https://api.simpleswap.io/v1/get_estimated",
        params={"currency_from": "BTC", "currency_to": "ETH", "amount": 1.0, "fixed": 1},
        headers={"api-key": "test_api_key"}
    )

@pytest.mark.asyncio
async def test_create_exchange(simpleswap_service):
    """Тест create_exchange."""
    mock_response = AsyncMock()
    mock_response.json.return_value = {"id": "exchange_id"}

    with patch('aiohttp.ClientSession.post', return_value=mock_response) as mock_post:
        result = await simpleswap_service.create_exchange("BTC", "ETH", 1.0, "address_to")

    assert result['id'] == "exchange_id"
    mock_post.assert_called_once_with(
        "https://api.simpleswap.io/v1/create_exchange",
        json={"currency_from": "BTC", "currency_to": "ETH", "amount": 1.0, "address_to": "address_to", "fixed": 1},
        headers={"api-key": "test_api_key"}
    )

@pytest.mark.asyncio
async def test_create_exchange_with_extra_id(simpleswap_service):
    """Тест create_exchange (с extra_id)."""
    mock_response = AsyncMock()
    mock_response.json.return_value = {"id": "exchange_id"}

    with patch('aiohttp.ClientSession.post', return_value=mock_response) as mock_post:
        result = await simpleswap_service.create_exchange("BTC", "ETH", 1.0, "address_to", "extra_id")

    assert result['id'] == "exchange_id"
    mock_post.assert_called_once_with(
        "https://api.simpleswap.io/v1/create_exchange",
        json={"currency_from": "BTC", "currency_to": "ETH", "amount": 1.0, "address_to": "address_to", "fixed": 1, "extra_id": "extra_id"},
        headers={"api-key": "test_api_key"}
    )

@pytest.mark.asyncio
async def test_get_exchange_status(simpleswap_service):
    """Тест get_exchange_status."""
    mock_response = AsyncMock()
    mock_response.json.return_value = {"status": "completed"}

    with patch('aiohttp.ClientSession.get', return_value=mock_response) as mock_get:
        status = await simpleswap_service.get_exchange_status("exchange_id")

    assert status['status'] == "completed"
    mock_get.assert_called_once_with(
        "https://api.simpleswap.io/v1/get_exchange",
        params={"id": "exchange_id"},
        headers={"api-key": "test_api_key"}
    ) 
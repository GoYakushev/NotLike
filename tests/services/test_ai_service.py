import pytest
from datetime import datetime, timedelta
from decimal import Decimal
import pandas as pd
import numpy as np
from unittest.mock import AsyncMock, patch, MagicMock
from services.ai.ai_service import AIService
from core.database.database import Database
from core.database.models import MarketData

@pytest.fixture
def db():
    return AsyncMock(spec=Database)

@pytest.fixture
def ai_service(db):
    return AIService(db, "test_api_key")

@pytest.mark.asyncio
async def test_analyze_market_valid():
    """Тест анализа рынка с валидными данными"""
    db = AsyncMock(spec=Database)
    ai_service = AIService(db, "test_api_key")
    
    # Подготавливаем тестовые данные
    market_data = [
        {
            'timestamp': datetime.utcnow().isoformat(),
            'price': "100.0",
            'volume': "1000.0",
            'high': "105.0",
            'low': "95.0",
            'open': "98.0",
            'close': "102.0"
        }
    ]
    
    # Подготавливаем моки
    ai_service._get_market_data = AsyncMock(return_value=market_data)
    ai_service._get_technical_analysis = AsyncMock(return_value={
        'trend': 'bullish',
        'strength': 7,
        'support': [95.0],
        'resistance': [105.0],
        'indicators': {}
    })
    ai_service._analyze_news_sentiment = AsyncMock(return_value={
        'score': 0.7,
        'summary': 'Positive news'
    })
    ai_service._get_ai_prediction = AsyncMock(return_value={
        'price_change': 5.0,
        'confidence': 0.8,
        'timeframe': '24h',
        'factors': ['strong_trend']
    })
    
    # Выполняем анализ
    result = await ai_service.analyze_market(
        token_symbol="BTC",
        network="ethereum",
        timeframe="1d"
    )
    
    assert result['token_symbol'] == "BTC"
    assert result['network'] == "ethereum"
    assert 'technical_analysis' in result
    assert 'news_sentiment' in result
    assert 'prediction' in result

@pytest.mark.asyncio
async def test_analyze_market_invalid_timeframe():
    """Тест анализа рынка с невалидным timeframe"""
    db = AsyncMock(spec=Database)
    ai_service = AIService(db, "test_api_key")
    
    with pytest.raises(ValueError) as exc_info:
        await ai_service.analyze_market(
            token_symbol="BTC",
            network="ethereum",
            timeframe="invalid"
        )
    assert "Неподдерживаемый timeframe" in str(exc_info.value)

@pytest.mark.asyncio
async def test_get_market_data():
    """Тест получения рыночных данных"""
    db = AsyncMock(spec=Database)
    ai_service = AIService(db, "test_api_key")
    
    # Подготавливаем тестовые данные
    test_data = [
        MarketData(
            token_symbol="BTC",
            network="ethereum",
            timestamp=datetime.utcnow(),
            price=Decimal("100.0"),
            volume=Decimal("1000.0"),
            high=Decimal("105.0"),
            low=Decimal("95.0"),
            open=Decimal("98.0"),
            close=Decimal("102.0")
        )
    ]
    
    # Настраиваем мок сессии
    mock_session = AsyncMock()
    mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = test_data
    db.session.return_value.__aenter__.return_value = mock_session
    
    # Получаем данные
    result = await ai_service._get_market_data(
        token_symbol="BTC",
        network="ethereum",
        timeframe="1d"
    )
    
    assert len(result) == 1
    assert result[0]['token_symbol'] == "BTC"
    assert result[0]['network'] == "ethereum"
    assert Decimal(result[0]['price']) == Decimal("100.0")

def test_prepare_analysis_data():
    """Тест подготовки данных для анализа"""
    db = AsyncMock(spec=Database)
    ai_service = AIService(db, "test_api_key")
    
    # Подготавливаем тестовые данные
    market_data = [
        {
            'timestamp': datetime.utcnow().isoformat(),
            'price': "100.0",
            'volume': "1000.0",
            'high': "105.0",
            'low': "95.0",
            'open': "98.0",
            'close': "102.0"
        }
    ]
    
    result = ai_service._prepare_analysis_data(market_data)
    
    assert 'data' in result
    assert 'indicators' in result
    assert all(key in result['indicators'] for key in ['current_price', 'sma_20', 'sma_50', 'rsi', 'macd', 'macd_signal'])

def test_calculate_rsi():
    """Тест расчета RSI"""
    db = AsyncMock(spec=Database)
    ai_service = AIService(db, "test_api_key")
    
    # Создаем тестовые данные
    prices = pd.Series([100.0, 102.0, 101.0, 103.0, 102.0])
    
    result = ai_service._calculate_rsi(prices)
    
    assert isinstance(result, pd.Series)
    assert not result.isna().any()  # Проверяем отсутствие NaN
    assert all(0 <= x <= 100 for x in result)  # Проверяем диапазон значений

def test_calculate_macd():
    """Тест расчета MACD"""
    db = AsyncMock(spec=Database)
    ai_service = AIService(db, "test_api_key")
    
    # Создаем тестовые данные
    prices = pd.Series([100.0, 102.0, 101.0, 103.0, 102.0])
    
    macd, signal = ai_service._calculate_macd(prices)
    
    assert isinstance(macd, pd.Series)
    assert isinstance(signal, pd.Series)
    assert not macd.isna().any()  # Проверяем отсутствие NaN
    assert not signal.isna().any()  # Проверяем отсутствие NaN

@pytest.mark.asyncio
async def test_get_technical_analysis():
    """Тест получения технического анализа"""
    db = AsyncMock(spec=Database)
    ai_service = AIService(db, "test_api_key")
    
    # Подготавливаем тестовые данные
    analysis_data = {
        'indicators': {
            'current_price': 100.0,
            'sma_20': 98.0,
            'sma_50': 95.0,
            'rsi': 60.0,
            'macd': 2.0,
            'macd_signal': 1.0
        }
    }
    
    # Настраиваем мок API ответа
    mock_response = {
        'choices': [{
            'message': {
                'content': '{"trend": "bullish", "strength": 7, "support": [95.0], "resistance": [105.0], "indicators": {}}'
            }
        }]
    }
    
    with patch('aiohttp.ClientSession') as mock_session:
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value.status = 200
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value.json.return_value = mock_response
        
        result = await ai_service._get_technical_analysis(analysis_data)
        
        assert result['trend'] == 'bullish'
        assert result['strength'] == 7
        assert len(result['support']) == 1
        assert len(result['resistance']) == 1

@pytest.mark.asyncio
async def test_analyze_news_sentiment():
    """Тест анализа новостного сентимента"""
    db = AsyncMock(spec=Database)
    ai_service = AIService(db, "test_api_key")
    
    # Настраиваем мок API ответа
    mock_response = {
        'choices': [{
            'message': {
                'content': 'sentiment_score: 0.7\nPositive market sentiment due to recent developments.'
            }
        }]
    }
    
    with patch('aiohttp.ClientSession') as mock_session:
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value.status = 200
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value.json.return_value = mock_response
        
        result = await ai_service._analyze_news_sentiment("BTC", "ethereum")
        
        assert 'score' in result
        assert 'summary' in result
        assert -1 <= result['score'] <= 1 
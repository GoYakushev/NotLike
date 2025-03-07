from core.database.models import Token, MarketAnalysis
from core.database.database import Database
import openai
import json
import aiohttp
from datetime import datetime, timedelta

class MarketAnalyzer:
    def __init__(self):
        self.db = Database()
        self.openai = openai
        self.openai.api_key = "YOUR_OPENAI_API_KEY"
        
    async def analyze_token(self, token_symbol: str) -> dict:
        """Анализирует токен с помощью ИИ"""
        session = self.db.get_session()
        token = session.query(Token).filter_by(symbol=token_symbol).first()
        
        if not token:
            return {
                'success': False,
                'error': 'Токен не найден'
            }
            
        try:
            # Получаем исторические данные
            historical_data = await self.get_historical_data(token_symbol)
            
            # Получаем новости и сентимент
            news_data = await self.get_news_sentiment(token_symbol)
            
            # Формируем промпт для GPT
            prompt = self.create_analysis_prompt(historical_data, news_data)
            
            # Получаем анализ от GPT
            response = await self.openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a professional crypto market analyst."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            analysis = self.parse_gpt_response(response.choices[0].message.content)
            
            # Сохраняем анализ
            market_analysis = MarketAnalysis(
                token_id=token.id,
                analysis_type='AI_COMBINED',
                prediction=analysis['prediction'],
                confidence=analysis['confidence'],
                details=json.dumps(analysis['details'])
            )
            
            session.add(market_analysis)
            session.commit()
            
            return {
                'success': True,
                'analysis': analysis
            }
        except Exception as e:
            session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
            
    async def get_historical_data(self, symbol: str) -> dict:
        """Получает исторические данные цены"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.binance.com/api/v3/klines",
                params={
                    'symbol': f"{symbol}USDT",
                    'interval': '1d',
                    'limit': 30
                }
            ) as response:
                data = await response.json()
                return {
                    'prices': [float(x[4]) for x in data],
                    'volumes': [float(x[5]) for x in data]
                }
                
    def create_analysis_prompt(self, historical_data: dict, news_data: dict) -> str:
        """Создает промпт для GPT"""
        return f"""
        Please analyze this cryptocurrency based on the following data:
        
        Price History (30 days):
        {historical_data['prices']}
        
        Trading Volumes:
        {historical_data['volumes']}
        
        Recent News Sentiment:
        {news_data['sentiment']}
        
        Key News Headlines:
        {news_data['headlines']}
        
        Please provide:
        1. Technical Analysis
        2. Market Sentiment Analysis
        3. Price Prediction
        4. Key Risks and Opportunities
        5. Recommended Trading Strategy
        """ 
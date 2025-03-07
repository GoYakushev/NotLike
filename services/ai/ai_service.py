from typing import Dict, List, Optional, Tuple, Union
import logging
import json
import aiohttp
from datetime import datetime, timedelta
from decimal import Decimal
import pandas as pd
import numpy as np
from core.database.database import Database
from core.database.models import Transaction, Token, MarketData
from contextlib import asynccontextmanager

class AIService:
    SUPPORTED_TIMEFRAMES = ['1h', '4h', '1d', '7d', '30d']
    RISK_LEVELS = ['low', 'medium', 'high']
    
    def __init__(
        self,
        db: Database,
        openrouter_api_key: str,
        model: str = "qwen/qwq-32b:free"
    ):
        if not isinstance(db, Database):
            raise ValueError("db должен быть экземпляром Database")
        if not isinstance(openrouter_api_key, str) or not openrouter_api_key:
            raise ValueError("Некорректный API ключ")
            
        self.logger = logging.getLogger(__name__)
        self.db = db
        self.openrouter_api_key = openrouter_api_key
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1"
        self.headers = {
            "Authorization": f"Bearer {openrouter_api_key}",
            "HTTP-Referer": "https://notlike3.bot",
            "Content-Type": "application/json"
        }
        self.timeout = aiohttp.ClientTimeout(total=30)
        
        # Метрики точности предсказаний
        self.prediction_metrics = {
            'total': 0,
            'correct': 0,
            'incorrect': 0,
            'accuracy': 0.0,
            'predictions': []  # Последние N предсказаний для анализа
        }
        
        # Параметры для адаптивной настройки
        self.adaptive_params = {
            'rsi_period': 14,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'learning_rate': 0.01
        }

    def _validate_timeframe(self, timeframe: str) -> str:
        """Проверяет корректность временного интервала."""
        if timeframe not in self.SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Неподдерживаемый timeframe: {timeframe}. Поддерживаемые значения: {self.SUPPORTED_TIMEFRAMES}")
        return timeframe
        
    def _validate_risk_level(self, risk_level: str) -> str:
        """Проверяет корректность уровня риска."""
        if risk_level not in self.RISK_LEVELS:
            raise ValueError(f"Неподдерживаемый уровень риска: {risk_level}. Поддерживаемые значения: {self.RISK_LEVELS}")
        return risk_level
        
    def _validate_token(self, token_symbol: str, network: str) -> None:
        """Проверяет существование токена."""
        if not isinstance(token_symbol, str) or not token_symbol:
            raise ValueError("Некорректный символ токена")
        if not isinstance(network, str) or not network:
            raise ValueError("Некорректная сеть")
            
    @asynccontextmanager
    async def _api_request(self, endpoint: str, data: Dict) -> Dict:
        """Выполняет запрос к API с обработкой ошибок."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(
                    f"{self.base_url}/{endpoint}",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status == 200:
                        yield await response.json()
                    elif response.status == 401:
                        raise ValueError("Неверный API ключ")
                    elif response.status == 429:
                        raise Exception("Превышен лимит запросов к API")
                    else:
                        error_text = await response.text()
                        raise Exception(f"Ошибка API: {response.status}, {error_text}")
        except aiohttp.ClientError as e:
            raise Exception(f"Ошибка сети при запросе к API: {str(e)}")
        except Exception as e:
            raise Exception(f"Ошибка при запросе к API: {str(e)}")

    async def analyze_market(
        self,
        token_symbol: str,
        network: str,
        timeframe: str = '1d'
    ) -> Dict:
        """Анализирует рыночные данные с помощью AI."""
        try:
            # Валидация входных данных
            self._validate_token(token_symbol, network)
            timeframe = self._validate_timeframe(timeframe)
            
            # Получаем исторические данные
            market_data = await self._get_market_data(
                token_symbol,
                network,
                timeframe
            )
            
            if not market_data:
                raise ValueError("Нет данных для анализа")

            # Подготавливаем данные для анализа
            analysis_data = self._prepare_analysis_data(market_data)

            # Получаем технический анализ
            technical_analysis = await self._get_technical_analysis(analysis_data)

            # Получаем сентимент-анализ новостей
            news_sentiment = await self._analyze_news_sentiment(
                token_symbol,
                network
            )

            # Получаем прогноз от AI
            ai_prediction = await self._get_ai_prediction(
                analysis_data,
                technical_analysis,
                news_sentiment
            )

            return {
                'timestamp': datetime.utcnow().isoformat(),
                'token_symbol': token_symbol,
                'network': network,
                'technical_analysis': technical_analysis,
                'news_sentiment': news_sentiment,
                'prediction': ai_prediction
            }

        except ValueError as e:
            self.logger.error(f"Ошибка валидации при анализе рынка: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Ошибка при анализе рынка: {str(e)}")
            raise

    async def get_trading_signals(
        self,
        token_symbol: str,
        network: str
    ) -> Dict:
        """Получает торговые сигналы."""
        try:
            # Получаем анализ рынка
            market_analysis = await self.analyze_market(token_symbol, network)

            # Генерируем сигналы на основе анализа
            signals = await self._generate_trading_signals(market_analysis)

            return {
                'timestamp': datetime.utcnow().isoformat(),
                'token_symbol': token_symbol,
                'network': network,
                'signals': signals
            }

        except Exception as e:
            self.logger.error(f"Ошибка при получении торговых сигналов: {str(e)}")
            raise

    async def predict_price(
        self,
        token_symbol: str,
        network: str,
        timeframe: str = '24h'
    ) -> Dict:
        """Предсказывает цену токена."""
        try:
            # Получаем исторические данные
            market_data = await self._get_market_data(
                token_symbol,
                network,
                timeframe
            )

            # Подготавливаем данные для предсказания
            prediction_data = self._prepare_prediction_data(market_data)

            # Получаем предсказание от AI
            prediction = await self._get_price_prediction(prediction_data)

            return {
                'timestamp': datetime.utcnow().isoformat(),
                'token_symbol': token_symbol,
                'network': network,
                'timeframe': timeframe,
                'current_price': float(market_data[-1]['price']),
                'predicted_price': prediction['price'],
                'confidence': prediction['confidence'],
                'factors': prediction['factors']
            }

        except Exception as e:
            self.logger.error(f"Ошибка при предсказании цены: {str(e)}")
            raise

    async def analyze_portfolio(
        self,
        user_id: int,
        risk_level: str = 'medium'
    ) -> Dict:
        """Анализирует портфель пользователя."""
        try:
            session = self.db.get_session()
            try:
                # Получаем транзакции пользователя
                transactions = session.query(Transaction).filter_by(
                    user_id=user_id
                ).all()

                # Подготавливаем данные портфеля
                portfolio_data = self._prepare_portfolio_data(transactions)

                # Получаем анализ от AI
                analysis = await self._get_portfolio_analysis(
                    portfolio_data,
                    risk_level
                )

                return {
                    'timestamp': datetime.utcnow().isoformat(),
                    'user_id': user_id,
                    'risk_level': risk_level,
                    'analysis': analysis
                }

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при анализе портфеля: {str(e)}")
            raise

    async def _get_market_data(
        self,
        token_symbol: str,
        network: str,
        timeframe: str
    ) -> List[Dict]:
        """Получает исторические данные рынка."""
        try:
            # Определяем временной интервал
            end_date = datetime.utcnow()
            if timeframe == '1h':
                start_date = end_date - timedelta(hours=1)
            elif timeframe == '4h':
                start_date = end_date - timedelta(hours=4)
            elif timeframe == '1d':
                start_date = end_date - timedelta(days=1)
            elif timeframe == '7d':
                start_date = end_date - timedelta(days=7)
            elif timeframe == '30d':
                start_date = end_date - timedelta(days=30)
            else:
                raise ValueError(f"Неподдерживаемый timeframe: {timeframe}")

            async with self.db.session() as session:
                # Получаем данные из базы
                market_data = await session.query(MarketData).filter(
                    MarketData.token_symbol == token_symbol,
                    MarketData.network == network,
                    MarketData.timestamp.between(start_date, end_date)
                ).order_by(MarketData.timestamp.asc()).all()

                if not market_data:
                    return []

                return [{
                    'timestamp': data.timestamp.isoformat(),
                    'price': str(data.price),  # Используем строки для Decimal
                    'volume': str(data.volume),
                    'high': str(data.high),
                    'low': str(data.low),
                    'open': str(data.open),
                    'close': str(data.close)
                } for data in market_data]

        except Exception as e:
            self.logger.error(f"Ошибка при получении рыночных данных: {str(e)}")
            raise

    def _prepare_analysis_data(self, market_data: List[Dict]) -> Dict:
        """Подготавливает данные для анализа."""
        try:
            if not market_data:
                raise ValueError("Нет данных для анализа")
                
            df = pd.DataFrame(market_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Преобразуем строковые значения в float
            numeric_columns = ['price', 'volume', 'high', 'low', 'open', 'close']
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            # Проверяем на наличие NaN
            if df[numeric_columns].isna().any().any():
                self.logger.warning("Обнаружены пропущенные значения в данных")
                # Заполняем пропуски предыдущими значениями
                df[numeric_columns] = df[numeric_columns].fillna(method='ffill')
                
            df.set_index('timestamp', inplace=True)

            # Рассчитываем технические индикаторы
            df['SMA_20'] = df['close'].rolling(window=20, min_periods=1).mean()
            df['SMA_50'] = df['close'].rolling(window=50, min_periods=1).mean()
            df['RSI'] = self._calculate_rsi(df['close'])
            df['MACD'], df['Signal'] = self._calculate_macd(df['close'])
            
            # Проверяем результаты
            for col in df.columns:
                if df[col].isna().any():
                    df[col] = df[col].fillna(method='ffill').fillna(method='bfill')

            return {
                'data': df.to_dict(orient='records'),
                'indicators': {
                    'current_price': float(df['close'].iloc[-1]),
                    'sma_20': float(df['SMA_20'].iloc[-1]),
                    'sma_50': float(df['SMA_50'].iloc[-1]),
                    'rsi': float(df['RSI'].iloc[-1]),
                    'macd': float(df['MACD'].iloc[-1]),
                    'macd_signal': float(df['Signal'].iloc[-1])
                }
            }

        except Exception as e:
            self.logger.error(f"Ошибка при подготовке данных для анализа: {str(e)}")
            raise

    async def _get_technical_analysis(self, analysis_data: Dict) -> Dict:
        """Получает технический анализ от AI."""
        try:
            if not isinstance(analysis_data, dict):
                raise ValueError("Некорректные данные для анализа")
                
            if 'indicators' not in analysis_data:
                raise ValueError("Отсутствуют индикаторы в данных")
                
            prompt = self._create_technical_analysis_prompt(analysis_data)
            
            async with self._api_request("chat", {
                "model": self.model,
                "messages": [{
                    "role": "user",
                    "content": prompt
                }]
            }) as response:
                analysis = self._parse_technical_analysis(response['choices'][0]['message']['content'])
                
                # Валидация результатов
                required_fields = ['trend', 'strength', 'support', 'resistance', 'indicators']
                if not all(field in analysis for field in required_fields):
                    raise ValueError("Неполный анализ от AI")
                    
                return analysis

        except ValueError as e:
            self.logger.error(f"Ошибка валидации при получении технического анализа: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Ошибка при получении технического анализа: {str(e)}")
            raise

    async def _analyze_news_sentiment(
        self,
        token_symbol: str,
        network: str
    ) -> Dict:
        """Анализирует новостной сентимент."""
        try:
            self._validate_token(token_symbol, network)
            
            async with self._api_request("chat", {
                "model": self.model,
                "messages": [{
                    "role": "user",
                    "content": f"Проанализируй последние новости о {token_symbol} в сети {network}"
                }]
            }) as response:
                sentiment = {
                    'score': float(response['choices'][0]['message']['content'].split(':')[1].strip()),
                    'summary': response['choices'][0]['message']['content']
                }
                
                # Валидация результатов
                if not -1 <= sentiment['score'] <= 1:
                    raise ValueError("Некорректная оценка сентимента")
                    
                return sentiment

        except ValueError as e:
            self.logger.error(f"Ошибка валидации при анализе новостей: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Ошибка при анализе новостей: {str(e)}")
            raise

    async def _get_ai_prediction(
        self,
        analysis_data: Dict,
        technical_analysis: Dict,
        news_sentiment: Dict
    ) -> Dict:
        """Получает прогноз от AI."""
        try:
            if not all(isinstance(data, dict) for data in [analysis_data, technical_analysis, news_sentiment]):
                raise ValueError("Некорректные входные данные для прогноза")
                
            prompt = self._create_prediction_prompt(
                analysis_data,
                technical_analysis,
                news_sentiment
            )
            
            async with self._api_request("chat", {
                "model": self.model,
                "messages": [{
                    "role": "user",
                    "content": prompt
                }]
            }) as response:
                prediction = self._parse_prediction(response['choices'][0]['message']['content'])
                
                # Валидация результатов
                required_fields = ['price_change', 'confidence', 'timeframe', 'factors']
                if not all(field in prediction for field in required_fields):
                    raise ValueError("Неполный прогноз от AI")
                    
                # Проверяем значения
                if not 0 <= prediction['confidence'] <= 1:
                    raise ValueError("Некорректное значение уверенности")
                    
                if not isinstance(prediction['factors'], list):
                    raise ValueError("Некорректный формат факторов")
                    
                return prediction

        except ValueError as e:
            self.logger.error(f"Ошибка валидации при получении прогноза: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Ошибка при получении прогноза: {str(e)}")
            raise

    async def track_prediction_accuracy(
        self,
        prediction: Dict,
        actual_outcome: Dict
    ) -> None:
        """Отслеживает точность предсказаний."""
        try:
            self.prediction_metrics['total'] += 1
            
            # Проверяем точность предсказания
            predicted_change = prediction['price_change']
            actual_change = actual_outcome['price_change']
            
            # Считаем предсказание правильным, если направление движения совпало
            # и разница в процентах не превышает 20% от предсказанного значения
            is_correct = (
                (predicted_change > 0 and actual_change > 0 or
                 predicted_change < 0 and actual_change < 0) and
                abs(predicted_change - actual_change) <= abs(predicted_change) * 0.2
            )
            
            if is_correct:
                self.prediction_metrics['correct'] += 1
            else:
                self.prediction_metrics['incorrect'] += 1
                
            # Обновляем общую точность
            self.prediction_metrics['accuracy'] = (
                self.prediction_metrics['correct'] /
                self.prediction_metrics['total']
            )
            
            # Сохраняем предсказание для анализа
            self.prediction_metrics['predictions'].append({
                'timestamp': datetime.utcnow().isoformat(),
                'prediction': prediction,
                'actual': actual_outcome,
                'is_correct': is_correct
            })
            
            # Ограничиваем историю предсказаний
            if len(self.prediction_metrics['predictions']) > 1000:
                self.prediction_metrics['predictions'] = self.prediction_metrics['predictions'][-1000:]
                
            # Адаптируем параметры на основе точности
            await self._adapt_parameters()
            
        except Exception as e:
            self.logger.error(f"Ошибка при отслеживании точности предсказаний: {str(e)}")
            
    async def _adapt_parameters(self) -> None:
        """Адаптирует параметры на основе точности предсказаний."""
        try:
            # Анализируем последние предсказания
            recent_predictions = self.prediction_metrics['predictions'][-100:]
            if not recent_predictions:
                return
                
            recent_accuracy = sum(
                1 for p in recent_predictions if p['is_correct']
            ) / len(recent_predictions)
            
            # Если точность падает, корректируем параметры
            if recent_accuracy < self.prediction_metrics['accuracy']:
                # Анализируем ошибки
                errors = [
                    abs(p['prediction']['price_change'] - p['actual']['price_change'])
                    for p in recent_predictions if not p['is_correct']
                ]
                avg_error = sum(errors) / len(errors) if errors else 0
                
                # Корректируем параметры на основе ошибок
                if avg_error > 10:  # Если средняя ошибка больше 10%
                    # Увеличиваем периоды индикаторов
                    self.adaptive_params['rsi_period'] = min(
                        30,
                        self.adaptive_params['rsi_period'] + 1
                    )
                    self.adaptive_params['macd_slow'] = min(
                        40,
                        self.adaptive_params['macd_slow'] + 2
                    )
                else:
                    # Уменьшаем периоды
                    self.adaptive_params['rsi_period'] = max(
                        7,
                        self.adaptive_params['rsi_period'] - 1
                    )
                    self.adaptive_params['macd_slow'] = max(
                        20,
                        self.adaptive_params['macd_slow'] - 2
                    )
                    
        except Exception as e:
            self.logger.error(f"Ошибка при адаптации параметров: {str(e)}")
            
    def _calculate_rsi(
        self,
        prices: pd.Series,
        period: Optional[int] = None
    ) -> pd.Series:
        """Рассчитывает индикатор RSI с адаптивным периодом."""
        try:
            if period is None:
                period = self.adaptive_params['rsi_period']
                
            if not isinstance(prices, pd.Series):
                raise ValueError("prices должен быть pandas Series")
            if not isinstance(period, int) or period <= 0:
                raise ValueError("period должен быть положительным целым числом")
                
            # Рассчитываем изменения цен
            delta = prices.diff()
            
            # Разделяем положительные и отрицательные изменения
            gain = (delta.where(delta > 0, 0)).fillna(0)
            loss = (-delta.where(delta < 0, 0)).fillna(0)
            
            # Рассчитываем средние значения
            avg_gain = gain.rolling(window=period, min_periods=1).mean()
            avg_loss = loss.rolling(window=period, min_periods=1).mean()
            
            # Рассчитываем RS и RSI
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi.fillna(50)  # Заполняем NaN значением 50 (нейтральный уровень)
            
        except Exception as e:
            self.logger.error(f"Ошибка при расчете RSI: {str(e)}")
            raise

    def _calculate_macd(
        self,
        prices: pd.Series,
        fast: Optional[int] = None,
        slow: Optional[int] = None,
        signal: Optional[int] = None
    ) -> Tuple[pd.Series, pd.Series]:
        """Рассчитывает индикатор MACD с адаптивными периодами."""
        try:
            if fast is None:
                fast = self.adaptive_params['macd_fast']
            if slow is None:
                slow = self.adaptive_params['macd_slow']
            if signal is None:
                signal = self.adaptive_params['macd_signal']
                
            if not isinstance(prices, pd.Series):
                raise ValueError("prices должен быть pandas Series")
            if not all(isinstance(x, int) and x > 0 for x in [fast, slow, signal]):
                raise ValueError("Периоды должны быть положительными целыми числами")
            if fast >= slow:
                raise ValueError("Быстрый период должен быть меньше медленного")
                
            # Рассчитываем экспоненциальные скользящие средние
            exp1 = prices.ewm(span=fast, adjust=False).mean()
            exp2 = prices.ewm(span=slow, adjust=False).mean()
            
            # Рассчитываем MACD и сигнальную линию
            macd = exp1 - exp2
            signal_line = macd.ewm(span=signal, adjust=False).mean()
            
            # Заполняем пропущенные значения
            macd = macd.fillna(method='ffill').fillna(0)
            signal_line = signal_line.fillna(method='ffill').fillna(0)
            
            return macd, signal_line
            
        except Exception as e:
            self.logger.error(f"Ошибка при расчете MACD: {str(e)}")
            raise

    def _create_technical_analysis_prompt(self, analysis_data: Dict) -> str:
        """Создает промпт для технического анализа."""
        try:
            if not isinstance(analysis_data, dict) or 'indicators' not in analysis_data:
                raise ValueError("Некорректные данные для создания промпта")
                
            indicators = analysis_data['indicators']
            
            return f"""Проведи технический анализ на основе следующих индикаторов:
1. Текущая цена: {indicators['current_price']}
2. SMA 20: {indicators['sma_20']}
3. SMA 50: {indicators['sma_50']}
4. RSI: {indicators['rsi']}
5. MACD: {indicators['macd']}
6. Сигнальная линия MACD: {indicators['macd_signal']}

Ответ должен содержать:
- Тренд (восходящий/нисходящий/боковой)
- Силу тренда (1-10)
- Уровни поддержки
- Уровни сопротивления
- Анализ индикаторов"""
            
        except Exception as e:
            self.logger.error(f"Ошибка при создании промпта для технического анализа: {str(e)}")
            raise

    def _create_prediction_prompt(
        self,
        analysis_data: Dict,
        technical_analysis: Dict,
        news_sentiment: Dict
    ) -> str:
        """Создает промпт для прогноза."""
        try:
            if not all(isinstance(data, dict) for data in [analysis_data, technical_analysis, news_sentiment]):
                raise ValueError("Некорректные данные для создания промпта")
                
            return f"""На основе следующих данных сделай прогноз движения цены:

Технический анализ:
{json.dumps(technical_analysis, indent=2)}

Новостной сентимент:
{json.dumps(news_sentiment, indent=2)}

Текущие индикаторы:
{json.dumps(analysis_data['indicators'], indent=2)}

Ответ должен содержать:
- Ожидаемое изменение цены (в процентах)
- Уверенность в прогнозе (0-1)
- Временной горизонт
- Ключевые факторы влияния"""
            
        except Exception as e:
            self.logger.error(f"Ошибка при создании промпта для прогноза: {str(e)}")
            raise

    def _parse_technical_analysis(self, response: str) -> Dict:
        """Разбирает ответ технического анализа."""
        try:
            if not isinstance(response, str) or not response:
                raise ValueError("Некорректный ответ для парсинга")
                
            # Пытаемся найти JSON в ответе
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                # Если не получилось, парсим текстовый формат
                lines = response.split('\n')
                result = {
                    'trend': None,
                    'strength': None,
                    'support': [],
                    'resistance': [],
                    'indicators': {}
                }
                
                for line in lines:
                    if 'тренд' in line.lower():
                        result['trend'] = line.split(':')[1].strip()
                    elif 'сила' in line.lower():
                        result['strength'] = int(line.split(':')[1].strip())
                    elif 'поддержка' in line.lower():
                        result['support'] = [float(x) for x in line.split(':')[1].strip().split(',')]
                    elif 'сопротивление' in line.lower():
                        result['resistance'] = [float(x) for x in line.split(':')[1].strip().split(',')]
                        
                return result
                
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге технического анализа: {str(e)}")
            raise

    def _parse_prediction(self, response: str) -> Dict:
        """Разбирает ответ прогноза."""
        try:
            if not isinstance(response, str) or not response:
                raise ValueError("Некорректный ответ для парсинга")
                
            # Пытаемся найти JSON в ответе
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                # Если не получилось, парсим текстовый формат
                lines = response.split('\n')
                result = {
                    'price_change': None,
                    'confidence': None,
                    'timeframe': None,
                    'factors': []
                }
                
                for line in lines:
                    if 'изменение' in line.lower():
                        result['price_change'] = float(line.split(':')[1].strip().rstrip('%'))
                    elif 'уверенность' in line.lower():
                        result['confidence'] = float(line.split(':')[1].strip())
                    elif 'горизонт' in line.lower():
                        result['timeframe'] = line.split(':')[1].strip()
                    elif 'фактор' in line.lower():
                        result['factors'].append(line.split(':')[1].strip())
                        
                return result
                
        except Exception as e:
            self.logger.error(f"Ошибка при парсинге прогноза: {str(e)}")
            raise 
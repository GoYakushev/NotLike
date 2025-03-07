from core.database.models import User, ExchangeAccount
from core.database.database import Database
import ccxt
import json

class ExchangeService:
    def __init__(self):
        self.db = Database()
        self.exchanges = {
            'binance': ccxt.binance(),
            'bybit': ccxt.bybit()
        }
        
    async def add_exchange_account(self, user_id: int, exchange: str, api_key: str, api_secret: str) -> dict:
        """Добавляет аккаунт биржи"""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        
        try:
            # Проверяем ключи
            exchange_instance = self.exchanges[exchange.lower()]
            exchange_instance.apiKey = api_key
            exchange_instance.secret = api_secret
            
            # Пробуем получить баланс для проверки
            await exchange_instance.fetch_balance()
            
            # Сохраняем аккаунт
            account = ExchangeAccount(
                user_id=user.id,
                exchange=exchange.upper(),
                api_key=api_key,
                api_secret=api_secret
            )
            
            session.add(account)
            session.commit()
            
            return {
                'success': True,
                'account_id': account.id
            }
        except Exception as e:
            session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
            
    async def get_exchange_balance(self, user_id: int, exchange: str) -> dict:
        """Получает баланс с биржи"""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        account = session.query(ExchangeAccount).filter_by(
            user_id=user.id,
            exchange=exchange.upper(),
            is_active=True
        ).first()
        
        if not account:
            return {
                'success': False,
                'error': 'Аккаунт не найден'
            }
            
        try:
            exchange_instance = self.exchanges[exchange.lower()]
            exchange_instance.apiKey = account.api_key
            exchange_instance.secret = account.api_secret
            
            balance = await exchange_instance.fetch_balance()
            
            return {
                'success': True,
                'balance': balance['total']
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            } 
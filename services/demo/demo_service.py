from core.database.models import User, DemoOrder, Token
from core.database.database import Database
from decimal import Decimal
import json

class DemoService:
    def __init__(self):
        self.db = Database()
        
    async def toggle_demo_mode(self, user_id: int) -> dict:
        """Переключает режим демо-торговли"""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        
        if not user:
            return {
                'success': False,
                'error': 'Пользователь не найден'
            }
            
        try:
            user.demo_mode = not user.demo_mode
            session.commit()
            
            return {
                'success': True,
                'demo_mode': user.demo_mode,
                'balance': user.demo_balance
            }
        except Exception as e:
            session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
            
    async def create_demo_order(self, user_id: int, token_symbol: str, 
                              order_type: str, side: str, amount: float, price: float = None) -> dict:
        """Создает демо-ордер"""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        token = session.query(Token).filter_by(symbol=token_symbol).first()
        
        if not user.demo_mode:
            return {
                'success': False,
                'error': 'Включите демо-режим'
            }
            
        # Проверяем баланс
        if side == 'BUY':
            total_cost = amount * (price or token.current_price)
            if total_cost > user.demo_balance:
                return {
                    'success': False,
                    'error': 'Недостаточно демо-баланса'
                }
                
        try:
            order = DemoOrder(
                user_id=user.id,
                token_id=token.id,
                order_type=order_type,
                side=side,
                amount=amount,
                price=price or token.current_price,
                status='OPEN'
            )
            
            session.add(order)
            
            # Обновляем демо-баланс
            if side == 'BUY':
                user.demo_balance -= total_cost
            
            session.commit()
            return {
                'success': True,
                'order_id': order.id
            }
        except Exception as e:
            session.rollback()
            return {
                'success': False,
                'error': str(e)
            } 
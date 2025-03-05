from core.database.models import User, CopyTrader, CopyTraderFollower, SpotOrder
from core.database.database import Database
from utils.security import Security
from datetime import datetime
import json
from services.fees.fee_service import FeeService
from services.notifications.notification_service import NotificationService, NotificationType
from typing import Optional

class CopyTradingService:
    def __init__(self, db: Optional[Database] = None, notification_service: Optional[NotificationService] = None):
        self.db = db or Database()
        self.security = Security()
        self.fee_service = FeeService(self.db)
        self.notification_service = notification_service
        
    async def register_as_trader(self, user_id: int) -> dict:
        """Регистрирует пользователя как копитрейдера"""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        
        # Проверяем требования
        wallets = user.wallets
        total_balance = sum(wallet.balance for wallet in wallets)
        
        if total_balance < 300:  # Минимальный баланс 300$
            return {
                'success': False,
                'error': 'Недостаточный баланс для регистрации копитрейдером'
            }
            
        # Проверяем объем торгов
        total_volume = sum(order.amount * order.price for order in user.spot_orders)
        if total_volume < 500:  # Минимальный объем торгов 500$
            return {
                'success': False,
                'error': 'Недостаточный объем торгов для регистрации копитрейдером'
            }
            
        try:
            trader = CopyTrader(
                user_id=user.id,
                monthly_profit=0,
                total_trades=0,
                successful_trades=0,
                followers_count=0,
                is_active=True
            )
            session.add(trader)
            session.commit()
            
            return {
                'success': True,
                'trader_id': trader.id
            }
        except Exception as e:
            session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
            
    async def follow_trader(self, follower_id: int, trader_id: int, copy_amount: float) -> dict:
        """Подписывает пользователя на копитрейдера"""
        session = self.db.get_session()
        follower = session.query(User).filter_by(telegram_id=follower_id).first()
        trader = session.query(CopyTrader).filter_by(user_id=trader_id).first()
        
        if not follower or not trader:
            return {
                'success': False,
                'error': 'Пользователь или трейдер не найден'
            }
            
        try:
            # Проверяем, не подписан ли уже пользователь
            existing_subscription = session.query(CopyTraderFollower).filter_by(
                follower_id=follower.id,
                trader_id=trader.id
            ).first()
            
            if existing_subscription:
                return {'success': False, 'error': 'Вы уже подписаны на этого трейдера'}
            
            subscription = CopyTraderFollower(
                follower_id=follower.id,
                trader_id=trader.id,
                copy_amount=copy_amount,
                active=True
            )
            session.add(subscription)
            
            # Увеличиваем счетчик подписчиков у трейдера
            trader.followers_count += 1
            
            session.commit()
            return {'success': True}
        except Exception as e:
            session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
            
    async def unfollow_trader(self, follower_id: int, trader_id: int) -> dict:
        """Отписывает пользователя от копитрейдера"""
        session = self.db.get_session()
        follower = session.query(User).filter_by(telegram_id=follower_id).first()
        trader = session.query(CopyTrader).filter_by(user_id=trader_id).first()
        
        if not follower or not trader:
            return {
                'success': False,
                'error': 'Пользователь или трейдер не найден'
            }
            
        try:
            subscription = session.query(CopyTraderFollower).filter_by(
                follower_id=follower.id,
                trader_id=trader.id
            ).first()
            
            if not subscription:
                return {'success': False, 'error': 'Вы не подписаны на этого трейдера'}
            
            session.delete(subscription)
            
            # Уменьшаем счетчик подписчиков у трейдера
            trader.followers_count -= 1
            
            session.commit()
            return {'success': True}
        except Exception as e:
            session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
            
    async def copy_trade(self, order: SpotOrder) -> None:
        """Копирует сделку для всех подписчиков"""
        session = self.db.get_session()
        trader = session.query(CopyTrader).filter_by(user_id=order.user_id).first()
        
        if not trader:
            return
            
        for follower_rel in trader.followers:
            follower = follower_rel.follower
            if not follower_rel.active:
                continue
                
            # Рассчитываем пропорциональную сумму для копирования
            proportion = follower_rel.copy_amount / order.quantity
            copy_amount = order.quantity * proportion
            
            # Создаем копию ордера для подписчика
            copy_order = SpotOrder(
                user_id=follower.id,
                base_currency=order.base_currency,
                quote_currency=order.quote_currency,
                order_type=order.order_type,
                side=order.side,
                price=order.price,
                quantity=copy_amount,
                status='OPEN'
            )
            
            session.add(copy_order)
            
            # Применяем комиссию
            fee_result = await self.fee_service.apply_fee(follower.telegram_id, 'copytrading', copy_amount * order.price if order.price else 0)
            if not fee_result['success']:
                session.rollback()
                print(f"Error applying fee for copy trade: {fee_result['error']}")
                continue
            
            # Отправляем уведомление
            if self.notification_service:
                await self.notification_service.notify(
                    user_id=follower.telegram_id,
                    notification_type=NotificationType.ORDER_UPDATE,
                    message=f"Скопирована сделка трейдера @{trader.user.username}: {order.side} {order.base_currency}/{order.quote_currency} x {copy_amount} @ {order.price}",
                    data={'order_id': copy_order.id}
                )
        
        session.commit() 
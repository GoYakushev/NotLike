from core.database.models import User, ReferralProgram, ReferralEarning
from core.database.database import Database
from utils.notifications import NotificationManager
from datetime import datetime
import json
from typing import Optional

class ReferralService:
    def __init__(self, notification_manager: NotificationManager, db: Optional[Database] = None):
        self.db = db or Database()
        self.notifications = notification_manager
        
    async def create_referral_link(self, user_id: int) -> str:
        """Создает реферальную ссылку"""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        
        if not user:
            return None
            
        # Генерируем уникальный код
        ref_code = f"ref_{user.id}_{hash(datetime.now())}"[:20]
        
        return f"https://t.me/your_bot_username?start={ref_code}"
        
    async def process_referral(self, referral_code: str, new_user_id: int) -> bool:
        """Обрабатывает реферальный код при регистрации"""
        session = self.db.get_session()
        
        try:
            # Извлекаем ID реферера из кода
            referrer_id = int(referral_code.split('_')[1])
            referrer = session.query(User).get(referrer_id)
            
            if not referrer:
                return False
                
            # Привязываем нового пользователя
            new_user = session.query(User).filter_by(telegram_id=new_user_id).first()
            new_user.referrer_id = referrer.id
            
            # Уведомляем реферера
            await self.notifications.send_notification(
                referrer.telegram_id,
                "👥 Новый реферал",
                f"По вашей ссылке зарегистрировался новый пользователь!"
            )
            
            session.commit()
            return True
        except:
            session.rollback()
            return False
            
    async def calculate_commission(self, order_id: int, amount: float) -> dict:
        """Рассчитывает реферальную комиссию"""
        session = self.db.get_session()
        order = session.query(SpotOrder).get(order_id)
        
        if not order:
            return None
            
        user = order.user
        if not user.referrer_id:
            return None
            
        # Получаем активную программу
        program = session.query(ReferralProgram).filter_by(is_active=True).first()
        
        # Рассчитываем комиссию
        commission = amount * (program.commission_rate / 100)
        
        # Создаем запись о начислении
        earning = ReferralEarning(
            referrer_id=user.referrer_id,
            referred_id=user.id,
            order_id=order_id,
            amount=commission,
            currency='USDT'
        )
        
        session.add(earning)
        session.commit()
        
        return {
            'amount': commission,
            'currency': 'USDT'
        }

    async def get_referral_link(self, user_id: int) -> str:
        """Генерирует реферальную ссылку для пользователя."""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        session.close()

        if not user:
            return "Ошибка: пользователь не найден"

        #  username,   ID
        return f"https://t.me/your_bot?start={user.username or user.telegram_id}"

    async def get_referral_stats(self, user_id: int) -> dict:
        """Возвращает статистику по рефералам пользователя."""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()

        if not user:
            return {'success': False, 'error': 'Пользователь не найден'}

        referrals = session.query(User).filter_by(referral_id=user.id).all()
        total_referrals = len(referrals)
        active_referrals = sum(1 for ref in referrals if ref.last_login_date)  #  last_login_date
        total_earned = 0  #  

        session.close()
        return {
            'total_referrals': total_referrals,
            'active_referrals': active_referrals,
            'total_earned': total_earned
        }

    async def process_referral(self, referrer_id: int, referred_user_id: int):
        """Обрабатывает реферала при регистрации."""
        session = self.db.get_session()
        referrer = session.query(User).filter_by(telegram_id=referrer_id).first()
        referred_user = session.query(User).filter_by(telegram_id=referred_user_id).first()

        if not referrer or not referred_user:
            return

        if referred_user.referral_id:
            return  #  

        referred_user.referral_id = referrer.id
        session.commit()
        session.close() 
from aiogram import Bot
from core.database.models import User, Notification, PriceAlert
from core.database.database import Database
from typing import Optional
import asyncio

class NotificationManager:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.db = Database()
        
    async def send_notification(self, user_id: int, title: str, message: str, notification_type: str = "SYSTEM") -> bool:
        """Отправляет уведомление пользователю"""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        
        if not user:
            return False
            
        try:
            # Сохраняем в базу
            notification = Notification(
                user_id=user.id,
                type=notification_type,
                title=title,
                message=message
            )
            session.add(notification)
            
            # Отправляем в Telegram
            await self.bot.send_message(
                user_id,
                f"📢 {title}\n\n{message}",
                parse_mode="HTML"
            )
            
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"Error sending notification: {e}")
            return False
            
    async def send_mass_notification(self, title: str, message: str, user_filter: Optional[dict] = None):
        """Отправляет массовое уведомление"""
        session = self.db.get_session()
        query = session.query(User)
        
        if user_filter:
            for key, value in user_filter.items():
                query = query.filter(getattr(User, key) == value)
                
        users = query.all()
        
        for user in users:
            await self.send_notification(user.telegram_id, title, message)
            await asyncio.sleep(0.1)  # Избегаем флуда
            
    async def check_price_alerts(self):
        """Проверяет и отправляет уведомления о ценах"""
        session = self.db.get_session()
        alerts = session.query(PriceAlert).filter_by(is_triggered=False).all()
        
        for alert in alerts:
            current_price = await self.get_current_price(alert.token.symbol)
            
            if (alert.condition == "ABOVE" and current_price >= alert.price) or \
               (alert.condition == "BELOW" and current_price <= alert.price):
                
                await self.send_notification(
                    alert.user.telegram_id,
                    "🔔 Ценовой алерт",
                    f"Цена {alert.token.symbol} {'достигла' if alert.condition == 'ABOVE' else 'упала до'} "
                    f"${current_price:.2f}",
                    "PRICE_ALERT"
                )
                
                alert.is_triggered = True
                
        session.commit() 
from core.database.models import User, SupportTicket, SupportMessage
from core.database.database import Database
from utils.notifications import NotificationManager
from datetime import datetime
import json

class SupportService:
    def __init__(self, notification_manager: NotificationManager):
        self.db = Database()
        self.notifications = notification_manager
        
    async def create_ticket(self, user_id: int, subject: str, message: str) -> dict:
        """Создает новый тикет поддержки"""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        
        try:
            ticket = SupportTicket(
                user_id=user.id,
                subject=subject,
                status='OPEN',
                priority='MEDIUM'
            )
            session.add(ticket)
            session.flush()
            
            # Добавляем первое сообщение
            message = SupportMessage(
                ticket_id=ticket.id,
                sender_id=user.id,
                message=message
            )
            session.add(message)
            
            # Уведомляем администраторов
            admins = session.query(Admin).filter(Admin.permissions.contains('support')).all()
            for admin in admins:
                await self.notifications.send_notification(
                    admin.user.telegram_id,
                    "🎫 Новый тикет поддержки",
                    f"Тема: {subject}\nОт: @{user.username}"
                )
            
            session.commit()
            return {
                'success': True,
                'ticket_id': ticket.id
            }
        except Exception as e:
            session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
            
    async def reply_to_ticket(self, ticket_id: int, user_id: int, message: str, is_support: bool = False) -> dict:
        """Отвечает на тикет"""
        session = self.db.get_session()
        ticket = session.query(SupportTicket).get(ticket_id)
        user = session.query(User).filter_by(telegram_id=user_id).first()
        
        if not ticket or not user:
            return {
                'success': False,
                'error': 'Тикет не найден'
            }
            
        try:
            reply = SupportMessage(
                ticket_id=ticket.id,
                sender_id=user.id,
                message=message,
                is_from_support=is_support
            )
            session.add(reply)
            
            # Уведомляем получателя
            recipient_id = ticket.user.telegram_id if is_support else \
                          session.query(Admin).filter(Admin.permissions.contains('support')).first().user.telegram_id
                          
            await self.notifications.send_notification(
                recipient_id,
                "💬 Новый ответ в тикете",
                f"Тикет #{ticket.id}\n\n{message}"
            )
            
            session.commit()
            return {'success': True}
        except Exception as e:
            session.rollback()
            return {
                'success': False,
                'error': str(e)
            } 
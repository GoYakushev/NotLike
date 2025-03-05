from core.database.models import User, Admin, AdminLog
from core.database.database import Database
from utils.notifications import NotificationManager
import json

class AdminService:
    def __init__(self, notification_manager: NotificationManager):
        self.db = Database()
        self.notifications = notification_manager
        
    async def check_admin(self, user_id: int) -> dict:
        """Проверяет права администратора"""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        
        if not user:
            return {'is_admin': False}
            
        admin = session.query(Admin).filter_by(user_id=user.id).first()
        
        if not admin:
            return {'is_admin': False}
            
        return {
            'is_admin': True,
            'role': admin.role,
            'permissions': json.loads(admin.permissions)
        }
        
    async def get_statistics(self) -> dict:
        """Получает общую статистику"""
        session = self.db.get_session()
        
        total_users = session.query(User).count()
        total_orders = session.query(SpotOrder).count()
        total_p2p = session.query(P2POrder).count()
        total_volume = session.query(func.sum(SpotOrder.amount * SpotOrder.price)).scalar() or 0
        
        return {
            'total_users': total_users,
            'total_orders': total_orders,
            'total_p2p': total_p2p,
            'total_volume': total_volume,
            'active_users_24h': self.get_active_users_24h()
        }
        
    async def ban_user(self, admin_id: int, user_id: int, reason: str) -> bool:
        """Банит пользователя"""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        admin = session.query(Admin).filter_by(user_id=admin_id).first()
        
        if not user or not admin:
            return False
            
        try:
            # Логируем действие
            log = AdminLog(
                admin_id=admin.id,
                action="BAN_USER",
                details=json.dumps({
                    'user_id': user_id,
                    'reason': reason
                })
            )
            session.add(log)
            
            # Баним пользователя
            user.is_banned = True
            user.ban_reason = reason
            
            # Уведомляем пользователя
            await self.notifications.send_notification(
                user_id,
                "🚫 Аккаунт заблокирован",
                f"Причина: {reason}\n\nДля обжалования обратитесь в поддержку."
            )
            
            session.commit()
            return True
        except:
            session.rollback()
            return False 
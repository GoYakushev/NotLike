from core.database.models import User, SpotOrder, P2POrder, SwapOrder, Token
from core.database.database import Database
from datetime import datetime, timedelta
from sqlalchemy import func
import json

class StatsService:
    def __init__(self):
        self.db = Database()
        
    async def get_global_stats(self) -> dict:
        """Получает общую статистику бота за 24 часа"""
        session = self.db.get_session()
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        
        try:
            # Объем торгов за 24 часа
            spot_volume = session.query(func.sum(SpotOrder.amount * SpotOrder.price))\
                .filter(SpotOrder.created_at >= day_ago).scalar() or 0
                
            p2p_volume = session.query(func.sum(P2POrder.crypto_amount))\
                .filter(P2POrder.created_at >= day_ago).scalar() or 0
                
            swap_volume = session.query(func.sum(SwapOrder.amount))\
                .filter(SwapOrder.created_at >= day_ago).scalar() or 0
                
            # Количество транзакций
            spot_count = session.query(SpotOrder)\
                .filter(SpotOrder.created_at >= day_ago).count()
                
            p2p_count = session.query(P2POrder)\
                .filter(P2POrder.created_at >= day_ago).count()
                
            swap_count = session.query(SwapOrder)\
                .filter(SwapOrder.created_at >= day_ago).count()
                
            # Активные пользователи
            active_users = session.query(func.count(func.distinct(User.id)))\
                .filter(
                    (User.id == SpotOrder.user_id) & (SpotOrder.created_at >= day_ago) |
                    (User.id == P2POrder.user_id) & (P2POrder.created_at >= day_ago) |
                    (User.id == SwapOrder.user_id) & (SwapOrder.created_at >= day_ago)
                ).scalar()
                
            return {
                'total_volume_24h': spot_volume + p2p_volume + swap_volume,
                'transactions_24h': spot_count + p2p_count + swap_count,
                'active_users_24h': active_users,
                'details': {
                    'spot': {'volume': spot_volume, 'count': spot_count},
                    'p2p': {'volume': p2p_volume, 'count': p2p_count},
                    'swap': {'volume': swap_volume, 'count': swap_count}
                }
            }
        except Exception as e:
            print(f"Error getting global stats: {e}")
            return None
            
    async def get_user_stats(self, username: str) -> dict:
        """Получает статистику пользователя"""
        session = self.db.get_session()
        user = session.query(User).filter_by(username=username).first()
        
        if not user:
            return None
            
        try:
            # Общий объем торгов
            total_volume = session.query(
                func.sum(SpotOrder.amount * SpotOrder.price)
            ).filter_by(user_id=user.id).scalar() or 0
            
            # Открытые ордера
            open_orders = session.query(func.count(SpotOrder.id))\
                .filter_by(user_id=user.id, status='OPEN').scalar()
                
            # Успешные P2P сделки
            successful_p2p = session.query(func.count(P2POrder.id))\
                .filter_by(user_id=user.id, status='COMPLETED').scalar()
            total_p2p = session.query(func.count(P2POrder.id))\
                .filter_by(user_id=user.id).scalar()
                
            p2p_success_rate = (successful_p2p / total_p2p * 100) if total_p2p > 0 else 0
            
            return {
                'username': user.username,
                'registration_date': user.registration_date.strftime('%Y-%m-%d'),
                'total_volume': total_volume,
                'open_orders': open_orders,
                'wallet_addresses': [w.address for w in user.wallets],
                'total_transactions': len(user.orders) + len(user.p2p_orders) + len(user.spot_orders),
                'p2p_success_rate': p2p_success_rate,
                'is_premium': user.is_premium
            }
        except Exception as e:
            print(f"Error getting user stats: {e}")
            return None 
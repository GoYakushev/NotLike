from typing import Dict, List, Optional
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from core.database.models import User, P2PDeal, P2POrder, UserRating, Transaction

logger = logging.getLogger(__name__)

class StatisticsService:
    def __init__(self):
        pass

    async def get_user_stats(self, user_id: int) -> Dict:
        """Получает статистику пользователя."""
        try:
            # Получаем все сделки пользователя
            deals = await P2PDeal.filter(
                Q(seller_id=user_id) | Q(buyer_id=user_id)
            ).all()

            # Получаем рейтинг пользователя
            rating = await UserRating.get(user_id=user_id)

            # Рассчитываем статистику
            total_deals = len(deals)
            successful_deals = len([d for d in deals if d.status == 'completed'])
            total_volume = sum(
                d.amount * d.price
                for d in deals
                if d.status == 'completed'
            )
            avg_deal_volume = total_volume / successful_deals if successful_deals > 0 else 0

            # Получаем транзакции
            transactions = await Transaction.filter(
                user_id=user_id
            ).all()

            # Рассчитываем P&L
            profit_loss = sum(
                t.amount
                for t in transactions
                if t.type == 'profit'
            )
            loss = sum(
                t.amount
                for t in transactions
                if t.type == 'loss'
            )
            net_pnl = profit_loss - loss

            return {
                'success': True,
                'stats': {
                    'total_deals': total_deals,
                    'successful_deals': successful_deals,
                    'success_rate': successful_deals / total_deals if total_deals > 0 else 0,
                    'total_volume': float(total_volume),
                    'average_deal_volume': float(avg_deal_volume),
                    'rating': float(rating.rating) if rating else 0,
                    'profit_loss': float(net_pnl),
                    'total_transactions': len(transactions)
                }
            }

        except Exception as e:
            logger.error(f"Ошибка при получении статистики пользователя: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_trading_history(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict]:
        """Получает историю торговли пользователя."""
        try:
            query = Transaction.filter(user_id=user_id)
            if start_date:
                query = query.filter(created_at__gte=start_date)
            if end_date:
                query = query.filter(created_at__lte=end_date)

            transactions = await query.order_by('-created_at').offset(offset).limit(limit).all()
            result = []

            for tx in transactions:
                result.append({
                    'id': tx.id,
                    'type': tx.type,
                    'amount': float(tx.amount),
                    'currency': tx.currency,
                    'status': tx.status,
                    'created_at': tx.created_at.isoformat()
                })

            return result

        except Exception as e:
            logger.error(f"Ошибка при получении истории торговли: {str(e)}")
            return []

    async def get_volume_stats(
        self,
        user_id: int,
        period: str = 'day'
    ) -> Dict:
        """Получает статистику объемов торговли."""
        try:
            now = datetime.utcnow()
            if period == 'day':
                start_date = now - timedelta(days=1)
                interval = timedelta(hours=1)
                format_str = '%H:00'
            elif period == 'week':
                start_date = now - timedelta(weeks=1)
                interval = timedelta(days=1)
                format_str = '%Y-%m-%d'
            elif period == 'month':
                start_date = now - timedelta(days=30)
                interval = timedelta(days=1)
                format_str = '%Y-%m-%d'
            else:
                return {
                    'success': False,
                    'error': 'Неверный период'
                }

            # Получаем все сделки за период
            deals = await P2PDeal.filter(
                Q(seller_id=user_id) | Q(buyer_id=user_id),
                created_at__gte=start_date,
                status='completed'
            ).all()

            # Группируем по интервалам
            volumes = {}
            current = start_date
            while current <= now:
                key = current.strftime(format_str)
                volumes[key] = 0
                current += interval

            for deal in deals:
                key = deal.created_at.strftime(format_str)
                if key in volumes:
                    volumes[key] += float(deal.amount * deal.price)

            return {
                'success': True,
                'period': period,
                'volumes': volumes
            }

        except Exception as e:
            logger.error(f"Ошибка при получении статистики объемов: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_profit_loss_stats(
        self,
        user_id: int,
        period: str = 'day'
    ) -> Dict:
        """Получает статистику прибыли и убытков."""
        try:
            now = datetime.utcnow()
            if period == 'day':
                start_date = now - timedelta(days=1)
                interval = timedelta(hours=1)
                format_str = '%H:00'
            elif period == 'week':
                start_date = now - timedelta(weeks=1)
                interval = timedelta(days=1)
                format_str = '%Y-%m-%d'
            elif period == 'month':
                start_date = now - timedelta(days=30)
                interval = timedelta(days=1)
                format_str = '%Y-%m-%d'
            else:
                return {
                    'success': False,
                    'error': 'Неверный период'
                }

            # Получаем все транзакции за период
            transactions = await Transaction.filter(
                user_id=user_id,
                created_at__gte=start_date
            ).all()

            # Группируем по интервалам
            pnl = {}
            current = start_date
            while current <= now:
                key = current.strftime(format_str)
                pnl[key] = {
                    'profit': 0,
                    'loss': 0,
                    'net': 0
                }
                current += interval

            for tx in transactions:
                key = tx.created_at.strftime(format_str)
                if key in pnl:
                    if tx.type == 'profit':
                        pnl[key]['profit'] += float(tx.amount)
                    elif tx.type == 'loss':
                        pnl[key]['loss'] += float(tx.amount)
                    pnl[key]['net'] = pnl[key]['profit'] - pnl[key]['loss']

            return {
                'success': True,
                'period': period,
                'pnl': pnl
            }

        except Exception as e:
            logger.error(f"Ошибка при получении статистики P&L: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_top_traders(
        self,
        period: str = 'all',
        limit: int = 10
    ) -> List[Dict]:
        """Получает список топ трейдеров."""
        try:
            now = datetime.utcnow()
            if period == 'day':
                start_date = now - timedelta(days=1)
            elif period == 'week':
                start_date = now - timedelta(weeks=1)
            elif period == 'month':
                start_date = now - timedelta(days=30)
            elif period == 'all':
                start_date = None
            else:
                return []

            # Получаем рейтинги пользователей
            query = UserRating.all()
            if start_date:
                query = query.filter(last_updated__gte=start_date)

            ratings = await query.order_by('-rating').limit(limit).all()
            result = []

            for rating in ratings:
                user = await User.get(id=rating.user_id)
                if user:
                    # Получаем статистику сделок
                    deals_query = P2PDeal.filter(
                        Q(seller_id=user.id) | Q(buyer_id=user.id),
                        status='completed'
                    )
                    if start_date:
                        deals_query = deals_query.filter(created_at__gte=start_date)
                    deals = await deals_query.all()

                    total_volume = sum(d.amount * d.price for d in deals)
                    success_rate = len(deals) / rating.total_deals if rating.total_deals > 0 else 0

                    result.append({
                        'user_id': user.id,
                        'username': user.username,
                        'rating': float(rating.rating),
                        'total_deals': rating.total_deals,
                        'successful_deals': rating.successful_deals,
                        'total_volume': float(total_volume),
                        'success_rate': float(success_rate)
                    })

            return result

        except Exception as e:
            logger.error(f"Ошибка при получении топ трейдеров: {str(e)}")
            return []

    async def get_market_stats(self) -> Dict:
        """Получает статистику рынка."""
        try:
            now = datetime.utcnow()
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)

            # Получаем статистику за сегодня
            today_deals = await P2PDeal.filter(
                created_at__gte=today,
                status='completed'
            ).all()

            today_volume = sum(d.amount * d.price for d in today_deals)
            today_count = len(today_deals)

            # Получаем статистику за все время
            all_deals = await P2PDeal.filter(
                status='completed'
            ).all()

            total_volume = sum(d.amount * d.price for d in all_deals)
            total_count = len(all_deals)

            # Получаем активные ордера
            active_orders = await P2POrder.filter(
                status='active'
            ).count()

            # Получаем количество пользователей
            total_users = await User.all().count()
            active_users = await User.filter(
                last_active__gte=now - timedelta(days=7)
            ).count()

            return {
                'success': True,
                'stats': {
                    'today': {
                        'volume': float(today_volume),
                        'deals_count': today_count,
                        'average_deal': float(today_volume / today_count) if today_count > 0 else 0
                    },
                    'total': {
                        'volume': float(total_volume),
                        'deals_count': total_count,
                        'average_deal': float(total_volume / total_count) if total_count > 0 else 0
                    },
                    'active_orders': active_orders,
                    'users': {
                        'total': total_users,
                        'active': active_users
                    }
                }
            }

        except Exception as e:
            logger.error(f"Ошибка при получении статистики рынка: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            } 
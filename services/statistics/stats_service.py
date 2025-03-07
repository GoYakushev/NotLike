from core.database.models import User, SpotOrder, P2POrder, SwapOrder, Token, Transaction, Wallet
from core.database.database import Database
from datetime import datetime, timedelta
from sqlalchemy import func
import json
from typing import Dict, List, Optional, Tuple
import logging
from decimal import Decimal

class StatsService:
    def __init__(self, db: Database):
        self.logger = logging.getLogger(__name__)
        self.db = db
        
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
            
    async def get_user_stats(self, user_id: int) -> Dict:
        """Получает статистику пользователя."""
        try:
            session = self.db.get_session()
            try:
                # Получаем все транзакции пользователя
                transactions = session.query(Transaction).filter_by(
                    user_id=user_id
                ).all()

                # Статистика по типам транзакций
                transaction_types = {}
                total_volume = Decimal('0')
                successful_trades = 0
                total_trades = 0

                for tx in transactions:
                    if tx.type not in transaction_types:
                        transaction_types[tx.type] = 0
                    transaction_types[tx.type] += 1

                    if tx.type in ['buy', 'sell']:
                        total_trades += 1
                        if tx.status == 'completed':
                            successful_trades += 1
                            total_volume += tx.amount

                # Вычисляем процент успешных сделок
                success_rate = (successful_trades / total_trades * 100) if total_trades > 0 else 0

                return {
                    'total_transactions': len(transactions),
                    'transaction_types': transaction_types,
                    'total_volume': float(total_volume),
                    'success_rate': float(success_rate),
                    'total_trades': total_trades,
                    'successful_trades': successful_trades
                }

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при получении статистики пользователя: {str(e)}")
            raise

    async def get_trading_history(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        token_symbol: Optional[str] = None
    ) -> List[Dict]:
        """Получает историю торговли с фильтрами."""
        try:
            session = self.db.get_session()
            try:
                query = session.query(Transaction).filter_by(user_id=user_id)

                if start_date:
                    query = query.filter(Transaction.created_at >= start_date)
                if end_date:
                    query = query.filter(Transaction.created_at <= end_date)
                if token_symbol:
                    query = query.join(Token).filter(Token.symbol == token_symbol)

                transactions = query.order_by(Transaction.created_at.desc()).all()

                return [{
                    'tx_hash': tx.tx_hash,
                    'type': tx.type,
                    'amount': float(tx.amount),
                    'token_symbol': tx.token.symbol if tx.token else None,
                    'price': float(tx.price) if tx.price else None,
                    'status': tx.status,
                    'timestamp': tx.created_at.isoformat()
                } for tx in transactions]

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при получении истории торговли: {str(e)}")
            raise

    async def get_portfolio_stats(self, user_id: int) -> Dict:
        """Получает статистику портфеля."""
        try:
            session = self.db.get_session()
            try:
                wallets = session.query(Wallet).filter_by(user_id=user_id).all()
                
                portfolio = {
                    'total_value_usd': Decimal('0'),
                    'assets': [],
                    'distribution': {}
                }

                for wallet in wallets:
                    # Получаем балансы токенов
                    token_balances = session.query(Token).filter_by(
                        wallet_id=wallet.id
                    ).all()

                    for token in token_balances:
                        if token.balance > 0:
                            # В реальном приложении здесь нужно получать
                            # актуальную цену токена через API
                            current_price = Decimal('1')  # Пример
                            value_usd = token.balance * current_price

                            portfolio['total_value_usd'] += value_usd
                            portfolio['assets'].append({
                                'token_symbol': token.symbol,
                                'balance': float(token.balance),
                                'value_usd': float(value_usd),
                                'network': wallet.network
                            })

                # Вычисляем распределение
                if portfolio['total_value_usd'] > 0:
                    for asset in portfolio['assets']:
                        percentage = (
                            Decimal(str(asset['value_usd'])) /
                            portfolio['total_value_usd'] * 100
                        )
                        portfolio['distribution'][asset['token_symbol']] = float(percentage)

                portfolio['total_value_usd'] = float(portfolio['total_value_usd'])
                return portfolio

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при получении статистики портфеля: {str(e)}")
            raise

    async def get_profit_loss_report(
        self,
        user_id: int,
        period: str = 'all'
    ) -> Dict:
        """Получает отчет о прибылях и убытках."""
        try:
            session = self.db.get_session()
            try:
                query = session.query(Transaction).filter_by(user_id=user_id)

                # Фильтруем по периоду
                if period != 'all':
                    start_date = datetime.utcnow()
                    if period == 'day':
                        start_date -= timedelta(days=1)
                    elif period == 'week':
                        start_date -= timedelta(weeks=1)
                    elif period == 'month':
                        start_date -= timedelta(days=30)
                    elif period == 'year':
                        start_date -= timedelta(days=365)
                    query = query.filter(Transaction.created_at >= start_date)

                transactions = query.all()

                report = {
                    'total_profit_loss': Decimal('0'),
                    'realized_profit_loss': Decimal('0'),
                    'unrealized_profit_loss': Decimal('0'),
                    'trades_count': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'average_profit_per_trade': Decimal('0'),
                    'largest_profit': Decimal('0'),
                    'largest_loss': Decimal('0'),
                    'profit_factor': Decimal('0')
                }

                total_profits = Decimal('0')
                total_losses = Decimal('0')

                for tx in transactions:
                    if tx.type in ['buy', 'sell'] and tx.status == 'completed':
                        report['trades_count'] += 1
                        profit_loss = tx.profit_loss if tx.profit_loss else Decimal('0')

                        if profit_loss > 0:
                            report['winning_trades'] += 1
                            total_profits += profit_loss
                            report['largest_profit'] = max(
                                report['largest_profit'],
                                profit_loss
                            )
                        elif profit_loss < 0:
                            report['losing_trades'] += 1
                            total_losses += abs(profit_loss)
                            report['largest_loss'] = max(
                                report['largest_loss'],
                                abs(profit_loss)
                            )

                        report['realized_profit_loss'] += profit_loss

                # Вычисляем метрики
                if report['trades_count'] > 0:
                    report['average_profit_per_trade'] = (
                        report['realized_profit_loss'] /
                        report['trades_count']
                    )

                if total_losses > 0:
                    report['profit_factor'] = total_profits / total_losses

                # Конвертируем Decimal в float для JSON
                return {
                    k: float(v) if isinstance(v, Decimal) else v
                    for k, v in report.items()
                }

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при получении отчета P&L: {str(e)}")
            raise

    async def get_network_stats(self, user_id: int) -> Dict:
        """Получает статистику по сетям."""
        try:
            session = self.db.get_session()
            try:
                wallets = session.query(Wallet).filter_by(user_id=user_id).all()
                
                stats = {}
                for wallet in wallets:
                    if wallet.network not in stats:
                        stats[wallet.network] = {
                            'transaction_count': 0,
                            'total_volume': Decimal('0'),
                            'active_tokens': 0
                        }

                    # Считаем транзакции
                    transactions = session.query(Transaction).filter_by(
                        wallet_id=wallet.id
                    ).all()
                    
                    stats[wallet.network]['transaction_count'] += len(transactions)
                    
                    # Считаем объем
                    for tx in transactions:
                        if tx.status == 'completed':
                            stats[wallet.network]['total_volume'] += tx.amount

                    # Считаем активные токены
                    active_tokens = session.query(Token).filter(
                        Token.wallet_id == wallet.id,
                        Token.balance > 0
                    ).count()
                    
                    stats[wallet.network]['active_tokens'] += active_tokens

                # Конвертируем Decimal в float
                return {
                    network: {
                        'transaction_count': data['transaction_count'],
                        'total_volume': float(data['total_volume']),
                        'active_tokens': data['active_tokens']
                    }
                    for network, data in stats.items()
                }

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при получении статистики по сетям: {str(e)}")
            raise 
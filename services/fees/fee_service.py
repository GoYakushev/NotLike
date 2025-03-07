from core.database.database import Database
from datetime import datetime, timedelta
from core.database.models import User, P2POrder, SpotOrder, SwapOrder, Transaction, FeeDiscount, FeeSettings, FeeTransaction, UserLevel
import json
from typing import Optional, Dict
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

class FeeService:
    def __init__(self, db: Database):
        self.logger = logging.getLogger(__name__)
        self.db = db
        self.base_fees = {
            'spot': {
                'maker': Decimal('0.001'),  # 0.1%
                'taker': Decimal('0.002')   # 0.2%
            },
            'p2p': {
                'maker': Decimal('0'),      # Бесплатно для мейкера
                'taker': Decimal('0.001')   # 0.1% для тейкера
            },
            'swap': {
                'standard': Decimal('0.003') # 0.3%
            }
        }
        self.volume_tiers = [
            {
                'min_volume': Decimal('0'),
                'max_volume': Decimal('10000'),
                'maker_discount': Decimal('0'),
                'taker_discount': Decimal('0')
            },
            {
                'min_volume': Decimal('10000'),
                'max_volume': Decimal('50000'),
                'maker_discount': Decimal('0.1'),  # 10% скидка
                'taker_discount': Decimal('0.05')  # 5% скидка
            },
            {
                'min_volume': Decimal('50000'),
                'max_volume': Decimal('100000'),
                'maker_discount': Decimal('0.2'),  # 20% скидка
                'taker_discount': Decimal('0.1')   # 10% скидка
            },
            {
                'min_volume': Decimal('100000'),
                'max_volume': None,
                'maker_discount': Decimal('0.3'),  # 30% скидка
                'taker_discount': Decimal('0.15')  # 15% скидка
            }
        ]
        self.default_fee_rate = Decimal('0.001')  # 0.1%
        self.min_fee = Decimal('0.1')  # Минимальная комиссия в USDT
        self.max_fee = Decimal('100')  # Максимальная комиссия в USDT
        
    def get_current_fees(self) -> dict:
        """Возвращает текущие комиссии с учетом дня недели"""
        now = datetime.utcnow()
        weekday = now.weekday()
        
        fees = self.base_fees.copy()
        
        # Пятница (4) и понедельник (0) - P2P без комиссии
        if weekday in [0, 4]:
            fees['p2p']['taker'] = Decimal('0')
            
        # Суббота (5) и воскресенье (6) - спот с пониженной комиссией
        if weekday in [5, 6]:
            fees['spot']['taker'] = Decimal('0.001')  # 0.1%
            
        return fees
        
    def get_fee_message(self) -> str:
        """Возвращает сообщение о текущих комиссиях"""
        now = datetime.utcnow()
        weekday = now.weekday()
        
        if weekday == 0:
            return "Понедельник день тяжелый... P2P торговля без комиссии! 🎉"
        elif weekday == 4:
            return "Трудный день... и на выходные! P2P торговля без комиссии! 🎉"
        elif weekday in [5, 6]:
            return "Хороших выходных! Комиссия на спотовую торговлю снижена до 0.1%! 🎉"
            
        return None 

    async def calculate_fee(
        self,
        user_id: int,
        amount: Decimal,
        operation_type: str,
        network: str
    ) -> Dict:
        """Рассчитывает комиссию для операции."""
        try:
            # Получаем настройки комиссий
            settings = await FeeSettings.get(network=network)
            if not settings:
                return {
                    'success': False,
                    'error': 'Настройки комиссий не найдены'
                }

            # Получаем уровень пользователя
            user_level = await UserLevel.get(user_id=user_id)
            if not user_level:
                user_level = await UserLevel(
                    user_id=user_id,
                    level=1,
                    created_at=datetime.utcnow()
                ).save()

            # Определяем базовую ставку комиссии
            base_rate = getattr(settings, f"{operation_type}_fee", self.default_fee_rate)

            # Применяем скидку в зависимости от уровня пользователя
            level_discount = Decimal('0.1') * (user_level.level - 1)  # 10% скидка за каждый уровень
            fee_rate = base_rate * (1 - level_discount)

            # Рассчитываем комиссию
            fee_amount = amount * fee_rate

            # Применяем ограничения
            fee_amount = max(min(fee_amount, self.max_fee), self.min_fee)

            return {
                'success': True,
                'fee_amount': float(fee_amount),
                'fee_rate': float(fee_rate),
                'base_rate': float(base_rate),
                'level_discount': float(level_discount)
            }

        except Exception as e:
            logger.error(f"Ошибка при расчете комиссии: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def apply_fee(
        self,
        user_id: int,
        amount: Decimal,
        operation_type: str,
        network: str,
        transaction_id: Optional[str] = None
    ) -> Dict:
        """Применяет комиссию к операции."""
        try:
            # Рассчитываем комиссию
            fee_result = await self.calculate_fee(
                user_id=user_id,
                amount=amount,
                operation_type=operation_type,
                network=network
            )

            if not fee_result['success']:
                return fee_result

            # Создаем запись о комиссии
            fee_tx = FeeTransaction(
                user_id=user_id,
                amount=Decimal(str(fee_result['fee_amount'])),
                operation_type=operation_type,
                network=network,
                transaction_id=transaction_id,
                fee_rate=Decimal(str(fee_result['fee_rate'])),
                created_at=datetime.utcnow()
            )
            await fee_tx.save()

            return {
                'success': True,
                'fee_transaction_id': fee_tx.id,
                'fee_amount': float(fee_tx.amount),
                'total_amount': float(amount + fee_tx.amount)
            }

        except Exception as e:
            logger.error(f"Ошибка при применении комиссии: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_fee_history(
        self,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict:
        """Получает историю комиссий пользователя."""
        try:
            query = FeeTransaction.filter(user_id=user_id)
            if start_date:
                query = query.filter(created_at__gte=start_date)
            if end_date:
                query = query.filter(created_at__lte=end_date)

            transactions = await query.order_by('-created_at').offset(offset).limit(limit).all()
            result = []

            for tx in transactions:
                result.append({
                    'id': tx.id,
                    'amount': float(tx.amount),
                    'operation_type': tx.operation_type,
                    'network': tx.network,
                    'transaction_id': tx.transaction_id,
                    'fee_rate': float(tx.fee_rate),
                    'created_at': tx.created_at.isoformat()
                })

            # Рассчитываем общую сумму комиссий
            total_fees = sum(tx.amount for tx in transactions)

            return {
                'success': True,
                'transactions': result,
                'total_fees': float(total_fees)
            }

        except Exception as e:
            logger.error(f"Ошибка при получении истории комиссий: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def update_fee_settings(
        self,
        network: str,
        settings: Dict
    ) -> Dict:
        """Обновляет настройки комиссий."""
        try:
            fee_settings = await FeeSettings.get(network=network)
            if not fee_settings:
                fee_settings = FeeSettings(network=network)

            # Обновляем настройки
            for key, value in settings.items():
                if hasattr(fee_settings, key):
                    setattr(fee_settings, key, Decimal(str(value)))

            await fee_settings.save()

            return {
                'success': True,
                'settings': {
                    'network': fee_settings.network,
                    'swap_fee': float(fee_settings.swap_fee),
                    'transfer_fee': float(fee_settings.transfer_fee),
                    'withdrawal_fee': float(fee_settings.withdrawal_fee)
                }
            }

        except Exception as e:
            logger.error(f"Ошибка при обновлении настроек комиссий: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_fee_settings(self, network: str) -> Dict:
        """Получает настройки комиссий."""
        try:
            settings = await FeeSettings.get(network=network)
            if not settings:
                return {
                    'success': False,
                    'error': 'Настройки не найдены'
                }

            return {
                'success': True,
                'settings': {
                    'network': settings.network,
                    'swap_fee': float(settings.swap_fee),
                    'transfer_fee': float(settings.transfer_fee),
                    'withdrawal_fee': float(settings.withdrawal_fee)
                }
            }

        except Exception as e:
            logger.error(f"Ошибка при получении настроек комиссий: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_fee_stats(
        self,
        period: str = 'day'
    ) -> Dict:
        """Получает статистику комиссий."""
        try:
            now = datetime.utcnow()
            if period == 'day':
                start_date = now - timedelta(days=1)
            elif period == 'week':
                start_date = now - timedelta(weeks=1)
            elif period == 'month':
                start_date = now - timedelta(days=30)
            else:
                return {
                    'success': False,
                    'error': 'Неверный период'
                }

            # Получаем все комиссии за период
            transactions = await FeeTransaction.filter(
                created_at__gte=start_date
            ).all()

            # Группируем по типам операций
            stats = {}
            for tx in transactions:
                if tx.operation_type not in stats:
                    stats[tx.operation_type] = {
                        'count': 0,
                        'total_amount': Decimal('0')
                    }
                stats[tx.operation_type]['count'] += 1
                stats[tx.operation_type]['total_amount'] += tx.amount

            # Форматируем результат
            result = {}
            for op_type, data in stats.items():
                result[op_type] = {
                    'count': data['count'],
                    'total_amount': float(data['total_amount']),
                    'average_amount': float(data['total_amount'] / data['count']) if data['count'] > 0 else 0
                }

            return {
                'success': True,
                'period': period,
                'stats': result,
                'total_fees': float(sum(tx.amount for tx in transactions))
            }

        except Exception as e:
            logger.error(f"Ошибка при получении статистики комиссий: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def _get_base_fee(self, operation_type: str, role: str) -> Decimal:
        """Возвращает базовую комиссию для операции."""
        if operation_type not in self.base_fees:
            raise ValueError(f"Неподдерживаемый тип операции: {operation_type}")
            
        if operation_type == 'swap':
            return self.base_fees[operation_type]['standard']
            
        if role not in ['maker', 'taker']:
            raise ValueError(f"Неподдерживаемая роль: {role}")
            
        return self.base_fees[operation_type][role]

    async def _get_volume_discount(
        self,
        session,
        user_id: int,
        role: str
    ) -> Decimal:
        """Рассчитывает скидку на основе объема торгов."""
        volume = await self._calculate_trading_volume(session, user_id)
        
        for tier in self.volume_tiers:
            if (tier['min_volume'] <= volume and
                (tier['max_volume'] is None or volume < tier['max_volume'])):
                return (
                    tier['maker_discount']
                    if role == 'maker'
                    else tier['taker_discount']
                )
        
        return Decimal('0')

    async def _get_user_discount(
        self,
        session,
        user_id: int
    ) -> Decimal:
        """Получает персональную скидку пользователя."""
        discounts = session.query(FeeDiscount).filter(
            FeeDiscount.user_id == user_id,
            (
                FeeDiscount.expiration_date.is_(None) |
                (FeeDiscount.expiration_date > datetime.utcnow())
            )
        ).all()
        
        total_discount = Decimal('0')
        for discount in discounts:
            total_discount += discount.discount_value
            
        return min(total_discount, Decimal('0.8'))  # Максимум 80% скидки

    async def _calculate_trading_volume(
        self,
        session,
        user_id: int,
        days: int = 30
    ) -> Decimal:
        """Рассчитывает объем торгов за период."""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        transactions = session.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.created_at >= start_date,
            Transaction.status == 'completed',
            Transaction.type.in_(['buy', 'sell'])
        ).all()
        
        return sum(tx.amount for tx in transactions)

    async def apply_fee_discount(
        self,
        user_id: int,
        discount_type: str,
        discount_value: Decimal,
        expiration_days: Optional[int] = None
    ) -> bool:
        """Применяет скидку на комиссию для пользователя."""
        try:
            session = self.db.get_session()
            try:
                # Проверяем существующие скидки
                existing_discount = session.query(FeeDiscount).filter_by(
                    user_id=user_id,
                    discount_type=discount_type
                ).first()

                if existing_discount:
                    # Обновляем существующую скидку
                    existing_discount.discount_value = discount_value
                    if expiration_days:
                        existing_discount.expiration_date = (
                            datetime.utcnow() + timedelta(days=expiration_days)
                        )
                else:
                    # Создаем новую скидку
                    new_discount = FeeDiscount(
                        user_id=user_id,
                        discount_type=discount_type,
                        discount_value=discount_value,
                        expiration_date=(
                            datetime.utcnow() + timedelta(days=expiration_days)
                            if expiration_days else None
                        )
                    )
                    session.add(new_discount)

                session.commit()
                return True

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при применении скидки: {str(e)}")
            return False

    async def get_user_fee_info(self, user_id: int) -> Dict:
        """Получает информацию о комиссиях пользователя."""
        try:
            session = self.db.get_session()
            try:
                # Получаем объем торгов за последние 30 дней
                volume = await self._calculate_trading_volume(
                    session,
                    user_id,
                    days=30
                )
                
                # Определяем текущий тир
                current_tier = None
                for tier in self.volume_tiers:
                    if (tier['min_volume'] <= volume and
                        (tier['max_volume'] is None or volume < tier['max_volume'])):
                        current_tier = tier
                        break

                # Получаем активные скидки
                discounts = session.query(FeeDiscount).filter(
                    FeeDiscount.user_id == user_id,
                    (
                        FeeDiscount.expiration_date.is_(None) |
                        (FeeDiscount.expiration_date > datetime.utcnow())
                    )
                ).all()

                return {
                    'trading_volume_30d': float(volume),
                    'current_tier': {
                        'min_volume': float(current_tier['min_volume']),
                        'max_volume': float(current_tier['max_volume']) if current_tier['max_volume'] else None,
                        'maker_discount': float(current_tier['maker_discount']),
                        'taker_discount': float(current_tier['taker_discount'])
                    } if current_tier else None,
                    'active_discounts': [{
                        'type': d.discount_type,
                        'value': float(d.discount_value),
                        'expires_at': d.expiration_date.isoformat() if d.expiration_date else None
                    } for d in discounts],
                    'base_fees': {
                        k: {
                            sk: float(sv) for sk, sv in v.items()
                        } for k, v in self.base_fees.items()
                    }
                }

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при получении информации о комиссиях: {str(e)}")
            raise 
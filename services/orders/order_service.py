from typing import Dict, List, Optional
import logging
from decimal import Decimal
from datetime import datetime
import asyncio
from core.database.database import Database
from core.database.models import Order, OrderType, OrderStatus
from services.dex.dex_service import DEXService
from services.monitoring.monitoring_service import MonitoringService
from services.cache.cache_service import CacheService

class OrderService:
    def __init__(
        self,
        dex_service: DEXService,
        monitoring_service: MonitoringService,
        cache_service: CacheService
    ):
        self.logger = logging.getLogger(__name__)
        self.db = Database()
        self.dex_service = dex_service
        self.monitoring_service = monitoring_service
        self.cache_service = cache_service
        
        # Запускаем обработчик условных ордеров
        asyncio.create_task(self._process_conditional_orders())
        
    async def create_order(
        self,
        user_id: int,
        order_type: OrderType,
        network: str,
        from_token: str,
        to_token: str,
        amount: Decimal,
        conditions: Optional[Dict] = None
    ) -> Dict:
        """Создает новый ордер."""
        try:
            # Валидация входных данных
            if not isinstance(user_id, int) or user_id <= 0:
                raise ValueError("Некорректный ID пользователя")
            if not isinstance(amount, Decimal) or amount <= 0:
                raise ValueError("Некорректная сумма")
                
            # Создаем ордер
            order = Order(
                user_id=user_id,
                order_type=order_type,
                network=network,
                from_token=from_token,
                to_token=to_token,
                amount=amount,
                conditions=conditions,
                status=OrderStatus.PENDING,
                created_at=datetime.utcnow()
            )
            
            async with self.db.session() as session:
                session.add(order)
                await session.commit()
                
            # Если это обычный ордер, выполняем его сразу
            if order_type == OrderType.MARKET:
                return await self.execute_order(order.id)
                
            # Для условных ордеров добавляем в кэш для отслеживания
            if order_type in [OrderType.STOP_LOSS, OrderType.TAKE_PROFIT]:
                await self._add_to_tracking(order)
                
            return {
                'order_id': order.id,
                'status': order.status,
                'created_at': order.created_at.isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при создании ордера: {str(e)}")
            raise
            
    async def execute_order(self, order_id: int) -> Dict:
        """Выполняет ордер."""
        try:
            async with self.db.session() as session:
                order = await session.query(Order).filter_by(id=order_id).first()
                if not order:
                    raise ValueError(f"Ордер {order_id} не найден")
                    
                # Проверяем статус
                if order.status != OrderStatus.PENDING:
                    raise ValueError(f"Ордер {order_id} уже обработан")
                    
                # Выполняем своп
                start_time = datetime.utcnow()
                swap_result = await self.dex_service.execute_swap(
                    network=order.network,
                    from_token=order.from_token,
                    to_token=order.to_token,
                    amount=order.amount
                )
                duration = (datetime.utcnow() - start_time).total_seconds()
                
                # Обновляем статус ордера
                order.status = OrderStatus.COMPLETED
                order.executed_at = datetime.utcnow()
                order.execution_details = swap_result
                await session.commit()
                
                # Записываем метрики
                await self.monitoring_service.track_swap(
                    dex=swap_result['dex_used'],
                    network=order.network,
                    token_pair=f"{order.from_token}/{order.to_token}",
                    duration=duration,
                    volume=float(order.amount),
                    success=True
                )
                
                return {
                    'order_id': order.id,
                    'status': order.status,
                    'execution_details': swap_result,
                    'executed_at': order.executed_at.isoformat()
                }
                
        except Exception as e:
            self.logger.error(f"Ошибка при выполнении ордера {order_id}: {str(e)}")
            
            # Обновляем статус на FAILED
            async with self.db.session() as session:
                order = await session.query(Order).filter_by(id=order_id).first()
                if order:
                    order.status = OrderStatus.FAILED
                    order.error = str(e)
                    await session.commit()
                    
            # Записываем метрики ошибки
            await self.monitoring_service.track_swap(
                dex="unknown",
                network=order.network,
                token_pair=f"{order.from_token}/{order.to_token}",
                duration=0,
                volume=float(order.amount),
                success=False,
                error_type=str(e)
            )
            
            raise
            
    async def cancel_order(self, order_id: int) -> Dict:
        """Отменяет ордер."""
        try:
            async with self.db.session() as session:
                order = await session.query(Order).filter_by(id=order_id).first()
                if not order:
                    raise ValueError(f"Ордер {order_id} не найден")
                    
                # Проверяем статус
                if order.status != OrderStatus.PENDING:
                    raise ValueError(f"Ордер {order_id} уже обработан")
                    
                # Обновляем статус
                order.status = OrderStatus.CANCELLED
                order.cancelled_at = datetime.utcnow()
                await session.commit()
                
                # Удаляем из отслеживания
                if order.order_type in [OrderType.STOP_LOSS, OrderType.TAKE_PROFIT]:
                    await self._remove_from_tracking(order)
                    
                return {
                    'order_id': order.id,
                    'status': order.status,
                    'cancelled_at': order.cancelled_at.isoformat()
                }
                
        except Exception as e:
            self.logger.error(f"Ошибка при отмене ордера {order_id}: {str(e)}")
            raise
            
    async def get_order(self, order_id: int) -> Dict:
        """Получает информацию об ордере."""
        try:
            async with self.db.session() as session:
                order = await session.query(Order).filter_by(id=order_id).first()
                if not order:
                    raise ValueError(f"Ордер {order_id} не найден")
                    
                return {
                    'order_id': order.id,
                    'user_id': order.user_id,
                    'order_type': order.order_type,
                    'network': order.network,
                    'from_token': order.from_token,
                    'to_token': order.to_token,
                    'amount': str(order.amount),
                    'conditions': order.conditions,
                    'status': order.status,
                    'created_at': order.created_at.isoformat(),
                    'executed_at': order.executed_at.isoformat() if order.executed_at else None,
                    'cancelled_at': order.cancelled_at.isoformat() if order.cancelled_at else None,
                    'execution_details': order.execution_details,
                    'error': order.error
                }
                
        except Exception as e:
            self.logger.error(f"Ошибка при получении ордера {order_id}: {str(e)}")
            raise
            
    async def get_user_orders(
        self,
        user_id: int,
        status: Optional[OrderStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict]:
        """Получает список ордеров пользователя."""
        try:
            async with self.db.session() as session:
                query = session.query(Order).filter_by(user_id=user_id)
                if status:
                    query = query.filter_by(status=status)
                    
                orders = await query.order_by(Order.created_at.desc())\
                    .offset(offset)\
                    .limit(limit)\
                    .all()
                    
                return [{
                    'order_id': order.id,
                    'order_type': order.order_type,
                    'network': order.network,
                    'from_token': order.from_token,
                    'to_token': order.to_token,
                    'amount': str(order.amount),
                    'conditions': order.conditions,
                    'status': order.status,
                    'created_at': order.created_at.isoformat(),
                    'executed_at': order.executed_at.isoformat() if order.executed_at else None,
                    'cancelled_at': order.cancelled_at.isoformat() if order.cancelled_at else None
                } for order in orders]
                
        except Exception as e:
            self.logger.error(f"Ошибка при получении ордеров пользователя {user_id}: {str(e)}")
            raise
            
    async def _add_to_tracking(self, order: Order) -> None:
        """Добавляет условный ордер в отслеживание."""
        try:
            key = f"tracking_orders:{order.network}:{order.from_token}"
            await self.cache_service.hash_set(
                key,
                str(order.id),
                {
                    'order_id': order.id,
                    'conditions': order.conditions,
                    'amount': str(order.amount)
                }
            )
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении ордера {order.id} в отслеживание: {str(e)}")
            
    async def _remove_from_tracking(self, order: Order) -> None:
        """Удаляет условный ордер из отслеживания."""
        try:
            key = f"tracking_orders:{order.network}:{order.from_token}"
            await self.cache_service.hash_delete(key, str(order.id))
        except Exception as e:
            self.logger.error(f"Ошибка при удалении ордера {order.id} из отслеживания: {str(e)}")
            
    async def _process_conditional_orders(self) -> None:
        """Обрабатывает условные ордера."""
        while True:
            try:
                # Получаем все отслеживаемые пары
                tracking_keys = await self.cache_service.list_range("tracking_pairs")
                
                for key in tracking_keys:
                    # Получаем текущую цену
                    network, from_token = key.split(":")
                    price_info = await self.dex_service.get_best_price(
                        network=network,
                        from_token=from_token,
                        to_token="USDT",  # Используем USDT как базовую валюту
                        amount=Decimal("1")
                    )
                    current_price = Decimal(price_info['output_amount'])
                    
                    # Получаем ордера для этой пары
                    orders = await self.cache_service.hash_get(f"tracking_orders:{key}")
                    
                    for order_id, order_data in orders.items():
                        conditions = order_data['conditions']
                        
                        # Проверяем условия
                        if (
                            (conditions['type'] == 'stop_loss' and
                             current_price <= Decimal(conditions['price'])) or
                            (conditions['type'] == 'take_profit' and
                             current_price >= Decimal(conditions['price']))
                        ):
                            # Выполняем ордер
                            await self.execute_order(int(order_id))
                            
                await asyncio.sleep(1)  # Проверяем каждую секунду
                
            except Exception as e:
                self.logger.error(f"Ошибка при обработке условных ордеров: {str(e)}")
                await asyncio.sleep(1) 
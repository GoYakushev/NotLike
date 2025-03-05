from core.database.models import User, P2POrder, P2PAdvertisement, PaymentMethod, P2PDispute, P2POrderStatus, P2PPaymentMethod, Wallet
from core.database.database import Database
from utils.security import Security
from datetime import datetime, timedelta
import json
from services.wallet.wallet_service import WalletService
from services.notifications.notification_service import NotificationService, NotificationType
from services.fees.fee_service import FeeService
from typing import List, Dict, Optional

class P2PService:
    def __init__(self, db: Database, wallet_service: WalletService, notification_service: NotificationService):
        self.db = db
        self.wallet_service = wallet_service
        self.notification_service = notification_service
        self.security = Security()
        self.fee_service = FeeService(db)
        
    async def create_advertisement(self, user_id: int, data: dict) -> dict:
        """Создает новое P2P объявление"""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        
        try:
            ad = P2PAdvertisement(
                user_id=user.id,
                type=data['type'],
                crypto_currency=data['crypto_currency'],
                fiat_currency=data['fiat_currency'],
                price=data['price'],
                min_amount=data['min_amount'],
                max_amount=data['max_amount'],
                payment_method_id=data['payment_method_id']
            )
            
            session.add(ad)
            session.commit()
            
            return {
                'success': True,
                'ad_id': ad.id
            }
        except Exception as e:
            session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
            
    async def create_order(self, user_id: int, side: str, base_currency: str, quote_currency: str,
                           amount: float, price: float, payment_method: str, limit_min: float = None,
                           limit_max: float = None, time_limit: int = None) -> dict:
        """Создает новый P2P ордер."""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()

        if not user:
            return {'success': False, 'error': 'Пользователь не найден'}

        try:
            order = P2POrder(
                user_id=user.id,
                side=side,
                base_currency=base_currency,
                quote_currency=quote_currency,
                crypto_amount=amount,
                fiat_amount=amount * price,
                price=price,
                payment_method=payment_method,
                limit_min=limit_min,
                limit_max=limit_max,
                time_limit=time_limit,
                status=P2POrderStatus.OPEN,
                expires_at=datetime.utcnow() + timedelta(minutes=30)  #  30
            )
            session.add(order)

            #  комиссию
            fee_result = await self.fee_service.apply_fee(user.telegram_id, 'p2p', order.fiat_amount, {'order_id': order.id})
            if not fee_result['success']:
                session.rollback()
                return fee_result #  ошибку

            session.commit()

            #  уведомление
            await self.notification_service.notify(
                user_id=user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"Создан новый P2P ордер #{order.id} ({side})",
                data={
                    'order_id': order.id,
                    'actions': [
                        {'text': '👁 Посмотреть', 'callback': f'p2p_view_{order.id}'},
                        {'text': '❌ Отменить', 'callback': f'p2p_cancel_{order.id}'}
                    ]
                }
            )

            return {'success': True, 'order_id': order.id}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': str(e)}

    async def get_open_orders(self, base_currency: Optional[str] = None, quote_currency: Optional[str] = None,
                              side: Optional[str] = None, payment_method: Optional[str] = None) -> List[P2POrder]:
        """Возвращает список открытых P2P ордеров с фильтрацией."""
        session = self.db.get_session()
        query = session.query(P2POrder).filter(P2POrder.status == P2POrderStatus.OPEN)

        if base_currency:
            query = query.filter(P2POrder.base_currency == base_currency)
        if quote_currency:
            query = query.filter(P2POrder.quote_currency == quote_currency)
        if side:
            query = query.filter(P2POrder.side == side)
        if payment_method:
            query = query.filter(P2POrder.payment_method == payment_method)

        orders = query.all()
        session.close()
        return orders

    async def get_order_by_id(self, order_id: int) -> Optional[P2POrder]:
        """Возвращает P2P ордер по ID."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)
        session.close()  #  
        return order

    async def take_order(self, order_id: int, taker_id: int) -> Dict:
        """Пользователь принимает (покупает/продает) P2P ордер."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)
        taker = session.query(User).filter_by(telegram_id=taker_id).first()

        if not order or not taker:
            return {'success': False, 'error': 'Ордер или пользователь не найдены'}

        if order.status != P2POrderStatus.OPEN:
            return {'success': False, 'error': 'Ордер неактивен'}

        if order.user_id == taker.id:
            return {'success': False, 'error': 'Нельзя принять собственный ордер'}

        try:
            order.taker_id = taker.id
            order.status = P2POrderStatus.IN_PROGRESS  #  

            #  комиссию
            fee_result = await self.fee_service.apply_fee(taker.telegram_id, 'p2p', order.fiat_amount, {'order_id': order.id})
            if not fee_result['success']:
                session.rollback()
                return fee_result

            session.commit()

            #  уведомления
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"Ваш P2P ордер #{order.id} принят пользователем @{taker.username}!",
                data={'order_id': order.id, 'taker_username': taker.username}
            )
            await self.notification_service.notify(
                user_id=taker.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"Вы приняли P2P ордер #{order.id} пользователя @{order.user.username}!",
                data={'order_id': order.id, 'owner_username': order.user.username}
            )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при принятии P2P ордера: {str(e)}'}
        finally:
            session.close()  #

    async def cancel_order(self, order_id: int, user_id: int) -> dict:
        """Отменяет P2P ордер."""
        session = self.db.get_session()
        try:
            order = session.query(P2POrder).filter(P2POrder.id == order_id).first()
            if not order:
                return {'success': False, 'error': 'Ордер не найден'}
            #  отменить  создатель,  админ
            if order.user_id != user_id and not session.query(User).filter(User.id == user_id).first().is_admin:
                return {'success': False, 'error': 'Нет прав для отмены ордера'}
            if order.status not in (P2POrderStatus.OPEN, P2POrderStatus.IN_PROGRESS):  #  отменять  OPEN  IN_PROGRESS
                return {'success': False, 'error': 'Ордер нельзя отменить'}

            #  токен
            token_address = None if order.base_currency in ("SOL", "TON") else "address_" + order.base_currency

            #  средств
            if order.status == P2POrderStatus.OPEN:
                if order.side == "SELL":
                    unlocked = await self.wallet_service.unlock_funds(order.user_id, "TON" if order.base_currency == "TON" else "SOL", order.amount, token_address)
                    if not unlocked:
                        return {'success': False, 'error': 'Не удалось разблокировать средства'}
            elif order.status == P2POrderStatus.IN_PROGRESS:
                if order.side == "BUY":
                    #  средства покупателю (taker)
                    unlocked = await self.wallet_service.unlock_funds(order.taker_id, "TON" if order.quote_currency == "TON" else "SOL", order.amount * order.price, None if order.quote_currency in ("SOL", "TON") else "address_" + order.quote_currency)
                    if not unlocked:
                        return {'success': False, 'error': 'Не удалось разблокировать средства'}
                else: #  SELL,  средства  уже разблокированы
                    pass

            order.status = P2POrderStatus.CANCELLED
            session.commit()
            return {'success': True}

        except Exception as e:
            session.rollback()
            print(f"Error canceling P2P order: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            session.close()

    async def get_user_p2p_orders(self, user_id: int) -> List[P2POrder]:
        """Возвращает список P2P ордеров пользователя."""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            return []
        return user.p2p_orders + user.taken_p2p_orders

    async def get_user_taken_p2p_orders(self, user_id: int, status: Optional[str] = None) -> List[P2POrder]:
        """Возвращает список P2P ордеров, которые принял пользователь."""
        session = self.db.get_session()
        query = session.query(P2POrder).filter(P2POrder.taker_id == user_id)
        if status:
            query = query.filter(P2POrder.status == P2POrderStatus[status.upper()])
        orders = query.all()
        session.close()
        return orders

    async def complete_order(self, order_id: int, user_id: int) -> Dict:
        """Завершает P2P ордер после подтверждения оплаты."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)

        if not order:
            return {'success': False, 'error': 'Ордер не найден'}

        #  ,   
        if order.user_id != user_id:
            return {'success': False, 'error': 'Вы не можете завершить этот ордер'}

        if order.status != P2POrderStatus.CONFIRMED:
            return {'success': False, 'error': 'Неверный статус ордера'}

        try:
            #  средства
            if order.side == "BUY":
                await self.wallet_service.transfer_funds(
                    from_user_id=order.taker.telegram_id,
                    to_user_id=order.user.telegram_id,
                    network="TON",
                    amount=order.crypto_amount,
                    token_address=None
                )
            else:  # SELL
                await self.wallet_service.transfer_funds(
                    from_user_id=order.user.telegram_id,
                    to_user_id=order.taker.telegram_id,
                    network="TON",
                    amount=order.crypto_amount,
                    token_address=None
                )

            order.status = P2POrderStatus.COMPLETED
            session.commit()

            # Уведомления
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"P2P ордер #{order.id} завершен!",
                data={'order_id': order.id}
            )
            await self.notification_service.notify(
                user_id=order.taker.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"P2P ордер #{order.id} завершен!",
                data={'order_id': order.id}
            )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при завершении P2P ордера: {str(e)}'}
        finally:
            session.close()  #

    async def open_dispute(self, order_id: int, user_id: int) -> Dict:
        """Открывает диспут по P2P ордеру."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)

        if not order:
            return {'success': False, 'error': 'Ордер не найден'}

        if order.user_id != user_id and order.taker_id != user_id:
            return {'success': False, 'error': 'Вы не участник этого ордера'}

        if order.status != P2POrderStatus.IN_PROGRESS:
            return {'success': False, 'error': 'Неверный статус ордера'}

        try:
            order.status = P2POrderStatus.DISPUTE
            session.commit()

            # Уведомление администрации (TODO)
            # ...
            #  уведомления участникам
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"Открыт диспут по P2P ордеру #{order.id}!",
                data={'order_id': order.id}
            )
            await self.notification_service.notify(
                user_id=order.taker.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"Открыт диспут по P2P ордеру #{order.id}!",
                data={'order_id': order.id}
            )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при открытии диспута: {str(e)}'}
        finally:
            session.close()  #

    async def resolve_dispute(self, order_id: int, admin_id: int, decision: str) -> Dict:
        """Разрешает диспут по P2P ордеру (администратором)."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)

        if not order:
            return {'success': False, 'error': 'Ордер не найден'}

        if order.status != P2POrderStatus.DISPUTE:
            return {'success': False, 'error': 'Ордер не находится в статусе диспута'}

        try:
            if decision == 'refund':
                #  средств покупателю
                if order.side == "BUY":
                    #  
                    pass
                else:  # SELL
                    #  
                    pass
                order.status = P2POrderStatus.CANCELLED
            elif decision == 'complete':
                #  в пользу продавца
                if order.side == "BUY":
                    #  
                    await self.wallet_service.transfer_funds(
                        from_user_id=order.taker.telegram_id,
                        to_user_id=order.user.telegram_id,
                        network="TON",
                        amount=order.crypto_amount,
                        token_address=None
                    )
                else:  # SELL
                    #  
                    await self.wallet_service.transfer_funds(
                        from_user_id=order.user.telegram_id,
                        to_user_id=order.taker.telegram_id,
                        network="TON",
                        amount=order.crypto_amount,
                        token_address=None
                    )
                order.status = P2POrderStatus.COMPLETED
            else:
                return {'success': False, 'error': 'Неверное решение'}

            session.commit()

            # Уведомления участникам
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"Диспут по P2P ордеру #{order.id} разрешен. Решение: {decision}",
                data={'order_id': order.id, 'decision': decision}
            )
            await self.notification_service.notify(
                user_id=order.taker.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"Диспут по P2P ордеру #{order.id} разрешен. Решение: {decision}",
                data={'order_id': order.id, 'decision': decision}
            )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при разрешении диспута: {str(e)}'}
        finally:
            session.close()  #

    async def get_advertisements(self, crypto: str, fiat: str, type: str) -> list:
        """Получает список объявлений"""
        session = self.db.get_session()
        ads = session.query(P2PAdvertisement).filter(
            P2PAdvertisement.crypto_currency == crypto,
            P2PAdvertisement.fiat_currency == fiat,
            P2PAdvertisement.type == type,
            P2PAdvertisement.available == True
        ).all()
        
        return [{
            'id': ad.id,
            'user': ad.user.username,
            'price': ad.price,
            'min_amount': ad.min_amount,
            'max_amount': ad.max_amount,
            'payment_method': ad.payment_method.name
        } for ad in ads]

    async def create_p2p_order(self,
                             user_id: int,
                             order_type: str,  # "BUY" or "SELL"
                             crypto_amount: float,
                             fiat_amount: float,
                             fiat_currency: str,
                             payment_method: str,
                             limit_min: Optional[float] = None,
                             limit_max: Optional[float] = None,
                             time_limit: Optional[int] = None,
                             crypto_currency: str = "SOL") -> Dict:
        """Создает P2P ордер."""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()

        if not user:
            return {'success': False, 'error': 'Пользователь не найден'}

        if limit_min is not None and limit_max is not None and limit_min > limit_max:
            return {'success': False, 'error': 'Минимальный лимит не может быть больше максимального'}

        if crypto_currency not in ("SOL", "TON", "USDT", "NOT"):
            return {'success': False, 'error': 'Неподдерживаемая криптовалюта'}

        try:
            order = P2POrder(
                user_id=user.id,
                type=order_type,
                crypto_amount=crypto_amount,
                fiat_amount=fiat_amount,
                fiat_currency=fiat_currency,
                payment_method=payment_method,
                limit_min=limit_min,
                limit_max=limit_max,
                time_limit=time_limit,
                status='OPEN',
                crypto_currency=crypto_currency
            )
            session.add(order)
            session.commit()

            # Уведомление
            await self.notification_service.notify(
                user_id=user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"Создан новый P2P ордер #{order.id} ({order_type})",
                data={
                    'order_id': order.id,
                    'actions': [
                        {'text': '👁 Посмотреть', 'callback': f'p2p_view_{order.id}'},
                        {'text': '❌ Отменить', 'callback': f'p2p_cancel_{order.id}'}
                    ]
                }
            )

            return {'success': True, 'order_id': order.id}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при создании P2P ордера: {str(e)}'}

    async def find_matching_p2p_orders(self, side: str, base_currency: str, quote_currency: str,
                                       amount: float, payment_method: str) -> List[P2POrder]:
        """Ищет подходящие P2P ордера."""
        session = self.db.get_session()
        opposite_side = "BUY" if side == "SELL" else "SELL"

        orders = session.query(P2POrder).filter(
            P2POrder.side == opposite_side,
            P2POrder.base_currency == base_currency,
            P2POrder.quote_currency == quote_currency,
            P2POrder.status == P2POrderStatus.OPEN,
            P2POrder.payment_method == payment_method,
            P2POrder.crypto_amount >= amount,  #  
            P2POrder.price <= amount  #  цену
        ).all()
        return orders

    async def confirm_p2p_order(self, order_id: int, counterparty_order_id: int) -> Dict:
        """Подтверждает P2P ордер."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)
        counterparty_order = session.query(P2POrder).get(counterparty_order_id)

        if not order or not counterparty_order:
            return {'success': False, 'error': 'Ордер не найден'}

        if order.status != 'OPEN' or counterparty_order.status != 'OPEN':
            return {'success': False, 'error': 'Один из ордеров неактивен'}
            
        if order.type == counterparty_order.type:
            return {'success': False, 'error': "Нельзя подтвердить ордер того же типа"}

        try:
            # Блокируем средства (TODO: реализовать через WalletService)
            # ...

            order.status = 'CONFIRMED'
            counterparty_order.status = 'CONFIRMED'
            session.commit()

            # Уведомления
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"P2P ордер #{order.id} подтвержден!",
                data={'order_id': order.id}
            )
            await self.notification_service.notify(
                user_id=counterparty_order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"P2P ордер #{counterparty_order.id} подтвержден!",
                data={'order_id': counterparty_order.id}
            )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при подтверждении P2P ордера: {str(e)}'}

    async def complete_p2p_order(self, order_id: int) -> Dict:
        """Завершает P2P ордер после подтверждения оплаты."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)

        if not order:
            return {'success': False, 'error': 'Ордер не найден'}

        if order.status != 'CONFIRMED':
            return {'success': False, 'error': 'Ордер не подтвержден'}

        try:
            # Переводим средства (TODO: реализовать через WalletService)
            # ...

            order.status = 'COMPLETED'
            session.commit()

            # Уведомление
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"P2P ордер #{order.id} завершен!",
                data={'order_id': order.id}
            )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при завершении P2P ордера: {str(e)}'}

    async def cancel_p2p_order(self, order_id: int, user_id: int) -> Dict:
        """Отменяет P2P ордер."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)

        if not order:
            return {'success': False, 'error': 'Ордер не найден'}

        #   
        if order.user_id != user_id and order.taker_id != user_id:
            return {'success': False, 'error': 'Вы не участник этого ордера'}

        if order.status not in ['OPEN', 'CONFIRMED']:
            return {'success': False, 'error': 'Нельзя отменить ордер в данном статусе'}

        try:
            # Разблокируем средства, если ордер был подтвержден (TODO)
            # ...

            order.status = 'CANCELLED'
            session.commit()

            # Уведомление
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"P2P ордер #{order.id} отменен",
                data={'order_id': order.id}
            )
            if order.taker_id:  #  ,   
                await self.notification_service.notify(
                    user_id=order.taker.telegram_id,
                    notification_type=NotificationType.P2P_UPDATE,
                    message=f"P2P ордер #{order.id} отменен",
                    data={'order_id': order.id}
                )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при отмене P2P ордера: {str(e)}'}
        finally:
            session.close()  #

    async def confirm_payment(self, order_id: int, user_id: int) -> Dict:
        """Подтверждает получение оплаты."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)

        if not order:
            return {'success': False, 'error': 'Ордер не найден'}

        if order.taker_id != user_id:
            return {'success': False, 'error': 'Вы не можете подтвердить этот ордер'}

        if order.status != P2POrderStatus.IN_PROGRESS:
            return {'success': False, 'error': 'Неверный статус ордера'}

        try:
            order.status = P2POrderStatus.CONFIRMED
            session.commit()

            #  уведомление
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"Пользователь @{order.taker.username} подтвердил оплату по ордеру #{order.id}!",
                data={'order_id': order.id}
            )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при подтверждении оплаты: {str(e)}'}
        finally:
            session.close()  #

    async def complete_order(self, order_id: int, user_id: int) -> Dict:
        """Завершает P2P ордер после подтверждения оплаты."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)

        if not order:
            return {'success': False, 'error': 'Ордер не найден'}

        #  ,   
        if order.user_id != user_id:
            return {'success': False, 'error': 'Вы не можете завершить этот ордер'}

        if order.status != P2POrderStatus.CONFIRMED:
            return {'success': False, 'error': 'Неверный статус ордера'}

        try:
            #  средства
            if order.side == "BUY":
                await self.wallet_service.transfer_funds(
                    from_user_id=order.taker.telegram_id,
                    to_user_id=order.user.telegram_id,
                    network="TON",
                    amount=order.crypto_amount,
                    token_address=None
                )
            else:  # SELL
                await self.wallet_service.transfer_funds(
                    from_user_id=order.user.telegram_id,
                    to_user_id=order.taker.telegram_id,
                    network="TON",
                    amount=order.crypto_amount,
                    token_address=None
                )

            order.status = P2POrderStatus.COMPLETED
            session.commit()

            # Уведомления
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"P2P ордер #{order.id} завершен!",
                data={'order_id': order.id}
            )
            await self.notification_service.notify(
                user_id=order.taker.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"P2P ордер #{order.id} завершен!",
                data={'order_id': order.id}
            )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при завершении P2P ордера: {str(e)}'}
        finally:
            session.close()  #

    async def cancel_p2p_order(self, order_id: int, user_id: int) -> Dict:
        """Отменяет P2P ордер."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)

        if not order:
            return {'success': False, 'error': 'Ордер не найден'}

        #   
        if order.user_id != user_id and order.taker_id != user_id:
            return {'success': False, 'error': 'Вы не участник этого ордера'}

        if order.status not in ['OPEN', 'CONFIRMED']:
            return {'success': False, 'error': 'Нельзя отменить ордер в данном статусе'}

        try:
            # Разблокируем средства, если ордер был подтвержден (TODO)
            # ...

            order.status = 'CANCELLED'
            session.commit()

            # Уведомление
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"P2P ордер #{order.id} отменен",
                data={'order_id': order.id}
            )
            if order.taker_id:  #  ,   
                await self.notification_service.notify(
                    user_id=order.taker.telegram_id,
                    notification_type=NotificationType.P2P_UPDATE,
                    message=f"P2P ордер #{order.id} отменен",
                    data={'order_id': order.id}
                )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при отмене P2P ордера: {str(e)}'}
        finally:
            session.close()  #

    async def open_dispute(self, order_id: int, user_id: int) -> Dict:
        """Открывает диспут по P2P ордеру."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)

        if not order:
            return {'success': False, 'error': 'Ордер не найден'}

        if order.user_id != user_id and order.taker_id != user_id:
            return {'success': False, 'error': 'Вы не участник этого ордера'}

        if order.status != P2POrderStatus.IN_PROGRESS:
            return {'success': False, 'error': 'Неверный статус ордера'}

        try:
            order.status = P2POrderStatus.DISPUTE
            session.commit()

            # Уведомление администрации (TODO)
            # ...
            #  уведомления участникам
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"Открыт диспут по P2P ордеру #{order.id}!",
                data={'order_id': order.id}
            )
            await self.notification_service.notify(
                user_id=order.taker.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"Открыт диспут по P2P ордеру #{order.id}!",
                data={'order_id': order.id}
            )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при открытии диспута: {str(e)}'}
        finally:
            session.close()  #

    async def resolve_dispute(self, order_id: int, admin_id: int, decision: str) -> Dict:
        """Разрешает диспут по P2P ордеру (администратором)."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)

        if not order:
            return {'success': False, 'error': 'Ордер не найден'}

        if order.status != P2POrderStatus.DISPUTE:
            return {'success': False, 'error': 'Ордер не находится в статусе диспута'}

        try:
            if decision == 'refund':
                #  средств покупателю
                if order.side == "BUY":
                    #  
                    pass
                else:  # SELL
                    #  
                    pass
                order.status = P2POrderStatus.CANCELLED
            elif decision == 'complete':
                #  в пользу продавца
                if order.side == "BUY":
                    #  
                    await self.wallet_service.transfer_funds(
                        from_user_id=order.taker.telegram_id,
                        to_user_id=order.user.telegram_id,
                        network="TON",
                        amount=order.crypto_amount,
                        token_address=None
                    )
                else:  # SELL
                    #  
                    await self.wallet_service.transfer_funds(
                        from_user_id=order.user.telegram_id,
                        to_user_id=order.taker.telegram_id,
                        network="TON",
                        amount=order.crypto_amount,
                        token_address=None
                    )
                order.status = P2POrderStatus.COMPLETED
            else:
                return {'success': False, 'error': 'Неверное решение'}

            session.commit()

            # Уведомления участникам
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"Диспут по P2P ордеру #{order.id} разрешен. Решение: {decision}",
                data={'order_id': order.id, 'decision': decision}
            )
            await self.notification_service.notify(
                user_id=order.taker.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"Диспут по P2P ордеру #{order.id} разрешен. Решение: {decision}",
                data={'order_id': order.id, 'decision': decision}
            )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при разрешении диспута: {str(e)}'}
        finally:
            session.close()  #

    async def get_advertisements(self, crypto: str, fiat: str, type: str) -> list:
        """Получает список объявлений"""
        session = self.db.get_session()
        ads = session.query(P2PAdvertisement).filter(
            P2PAdvertisement.crypto_currency == crypto,
            P2PAdvertisement.fiat_currency == fiat,
            P2PAdvertisement.type == type,
            P2PAdvertisement.available == True
        ).all()
        
        return [{
            'id': ad.id,
            'user': ad.user.username,
            'price': ad.price,
            'min_amount': ad.min_amount,
            'max_amount': ad.max_amount,
            'payment_method': ad.payment_method.name
        } for ad in ads]

    async def create_p2p_order(self,
                             user_id: int,
                             order_type: str,  # "BUY" or "SELL"
                             crypto_amount: float,
                             fiat_amount: float,
                             fiat_currency: str,
                             payment_method: str,
                             limit_min: Optional[float] = None,
                             limit_max: Optional[float] = None,
                             time_limit: Optional[int] = None,
                             crypto_currency: str = "SOL") -> Dict:
        """Создает P2P ордер."""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()

        if not user:
            return {'success': False, 'error': 'Пользователь не найден'}

        if limit_min is not None and limit_max is not None and limit_min > limit_max:
            return {'success': False, 'error': 'Минимальный лимит не может быть больше максимального'}

        if crypto_currency not in ("SOL", "TON", "USDT", "NOT"):
            return {'success': False, 'error': 'Неподдерживаемая криптовалюта'}

        try:
            order = P2POrder(
                user_id=user.id,
                type=order_type,
                crypto_amount=crypto_amount,
                fiat_amount=fiat_amount,
                fiat_currency=fiat_currency,
                payment_method=payment_method,
                limit_min=limit_min,
                limit_max=limit_max,
                time_limit=time_limit,
                status='OPEN',
                crypto_currency=crypto_currency
            )
            session.add(order)
            session.commit()

            # Уведомление
            await self.notification_service.notify(
                user_id=user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"Создан новый P2P ордер #{order.id} ({order_type})",
                data={
                    'order_id': order.id,
                    'actions': [
                        {'text': '👁 Посмотреть', 'callback': f'p2p_view_{order.id}'},
                        {'text': '❌ Отменить', 'callback': f'p2p_cancel_{order.id}'}
                    ]
                }
            )

            return {'success': True, 'order_id': order.id}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при создании P2P ордера: {str(e)}'}

    async def find_matching_p2p_orders(self, side: str, base_currency: str, quote_currency: str,
                                       amount: float, payment_method: str) -> List[P2POrder]:
        """Ищет подходящие P2P ордера."""
        session = self.db.get_session()
        opposite_side = "BUY" if side == "SELL" else "SELL"

        orders = session.query(P2POrder).filter(
            P2POrder.side == opposite_side,
            P2POrder.base_currency == base_currency,
            P2POrder.quote_currency == quote_currency,
            P2POrder.status == P2POrderStatus.OPEN,
            P2POrder.payment_method == payment_method,
            P2POrder.crypto_amount >= amount,  #  
            P2POrder.price <= amount  #  цену
        ).all()
        return orders

    async def confirm_p2p_order(self, order_id: int, counterparty_order_id: int) -> Dict:
        """Подтверждает P2P ордер."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)
        counterparty_order = session.query(P2POrder).get(counterparty_order_id)

        if not order or not counterparty_order:
            return {'success': False, 'error': 'Ордер не найден'}

        if order.status != 'OPEN' or counterparty_order.status != 'OPEN':
            return {'success': False, 'error': 'Один из ордеров неактивен'}
            
        if order.type == counterparty_order.type:
            return {'success': False, 'error': "Нельзя подтвердить ордер того же типа"}

        try:
            # Блокируем средства (TODO: реализовать через WalletService)
            # ...

            order.status = 'CONFIRMED'
            counterparty_order.status = 'CONFIRMED'
            session.commit()

            # Уведомления
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"P2P ордер #{order.id} подтвержден!",
                data={'order_id': order.id}
            )
            await self.notification_service.notify(
                user_id=counterparty_order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"P2P ордер #{counterparty_order.id} подтвержден!",
                data={'order_id': counterparty_order.id}
            )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при подтверждении P2P ордера: {str(e)}'}

    async def complete_p2p_order(self, order_id: int) -> Dict:
        """Завершает P2P ордер после подтверждения оплаты."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)

        if not order:
            return {'success': False, 'error': 'Ордер не найден'}

        if order.status != 'CONFIRMED':
            return {'success': False, 'error': 'Ордер не подтвержден'}

        try:
            # Переводим средства (TODO: реализовать через WalletService)
            # ...

            order.status = 'COMPLETED'
            session.commit()

            # Уведомление
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"P2P ордер #{order.id} завершен!",
                data={'order_id': order.id}
            )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при завершении P2P ордера: {str(e)}'}

    async def cancel_p2p_order(self, order_id: int, user_id: int) -> Dict:
        """Отменяет P2P ордер."""
        session = self.db.get_session()
        order = session.query(P2POrder).get(order_id)

        if not order:
            return {'success': False, 'error': 'Ордер не найден'}

        #   
        if order.user_id != user_id and order.taker_id != user_id:
            return {'success': False, 'error': 'Вы не участник этого ордера'}

        if order.status not in ['OPEN', 'CONFIRMED']:
            return {'success': False, 'error': 'Нельзя отменить ордер в данном статусе'}

        try:
            # Разблокируем средства, если ордер был подтвержден (TODO)
            # ...

            order.status = 'CANCELLED'
            session.commit()

            # Уведомление
            await self.notification_service.notify(
                user_id=order.user.telegram_id,
                notification_type=NotificationType.P2P_UPDATE,
                message=f"P2P ордер #{order.id} отменен",
                data={'order_id': order.id}
            )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при отмене P2P ордера: {str(e)}'} 
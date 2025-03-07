from services.dex.orca_service import OrcaService
from services.dex.stonfi_service import StonFiService
from services.wallet.wallet_service import WalletService
from core.database.models import User, SwapOrder
from core.database.database import Database
from decimal import Decimal
import json
from services.fees.fee_service import FeeService
from typing import Optional
from services.notifications.notification_service import NotificationService, NotificationType

class SwapService:
    def __init__(self, db: Optional[Database] = None, notification_service: Optional[NotificationService] = None):
        self.db = db or Database()
        self.orca = OrcaService()
        self.stonfi = StonFiService()
        self.wallet_service = WalletService()
        self.fee_service = FeeService(db)
        self.notification_service = notification_service
        
    async def get_swap_price(self, from_token: str, to_token: str, amount: float) -> dict:
        """Получает цену свопа с учетом комиссий"""
        try:
            # Определяем сеть и DEX
            if from_token.startswith('SOL'):
                price = await self.orca.get_price(from_token, to_token)
                dex = 'ORCA'
            else:
                price = await self.stonfi.get_price(from_token, to_token)
                dex = 'STONFI'
                
            if not price:
                return None
                
            # Рассчитываем комиссии
            dex_fee = amount * 0.003  # 0.3% комиссия DEX
            bot_fee = amount * 0.01   # 1% комиссия бота
            total_fee = dex_fee + bot_fee
            
            # Рассчитываем итоговую сумму
            estimated_amount = (amount - total_fee) * price
            
            return {
                'success': True,
                'price': price,
                'estimated_amount': estimated_amount,
                'dex_fee': dex_fee,
                'bot_fee': bot_fee,
                'total_fee': total_fee,
                'dex': dex
            }
        except Exception as e:
            print(f"Error getting swap price: {e}")
            return {
                'success': False,
                'error': str(e)
            }
            
    async def create_swap(self, user_id: int, from_token: str, 
                         to_token: str, amount: float) -> dict:
        """Создает свап"""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        
        if not user:
            return {'success': False, 'error': 'Пользователь не найден'}
        
        try:
            # Получаем цену
            price_data = await self.get_swap_price(from_token, to_token, amount)
            if not price_data['success']:
                return price_data
                
            # Создаем запись в базе
            order = SwapOrder(
                user_id=user.id,
                from_token=from_token,
                to_token=to_token,
                amount=amount,
                price=price_data['price'],
                status='PENDING'
            )
            
            session.add(order)
            
            # Применяем комиссию
            fee_result = await self.fee_service.apply_fee(user.telegram_id, 'swap', amount)
            if not fee_result['success']:
                session.rollback()
                return fee_result
            
            session.commit()
            
            # Создаем транзакцию свопа
            if price_data['dex'] == 'ORCA':
                tx = await self.orca.create_swap_transaction(
                    from_token, to_token, amount,
                    await self.wallet_service.get_wallet(user_id, 'SOL')
                )
            else:
                tx = await self.stonfi.create_swap_transaction(
                    from_token, to_token, amount,
                    await self.wallet_service.get_wallet(user_id, 'TON')
                )
                
            #  уведомление
            await self.notification_service.notify(
                user_id=user.telegram_id,
                notification_type=NotificationType.SWAP_STATUS,
                message=f"Создан запрос на своп #{order.id}: {from_token} -> {to_token}, количество: {amount}",
                data={'order_id': order.id}
            )

            return {
                'success': True,
                'order_id': order.id,
                'transaction': tx
            }
            
        except Exception as e:
            session.rollback()
            print(f"Error creating swap: {e}")
            return {
                'success': False,
                'error': str(e)
            } 
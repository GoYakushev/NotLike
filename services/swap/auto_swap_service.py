from services.swap.simpleswap_service import SimpleSwapService
from services.wallet.wallet_service import WalletService
from core.database.models import User, AutoSwap
from core.database.database import Database
from decimal import Decimal
import asyncio
import json

class AutoSwapService:
    def __init__(self, simpleswap_api_key: str):
        self.db = Database()
        self.simpleswap = SimpleSwapService(simpleswap_api_key)
        self.wallet_service = WalletService()
        
    async def handle_incoming_transfer(self, user_id: int, network: str, amount: float):
        """Обрабатывает входящий перевод USDT"""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        
        if not user:
            return
            
        try:
            # Определяем целевую сеть для свопа
            target_network = 'TON' if network == 'SOL' else 'SOL'
            
            # Получаем адрес кошелька пользователя в целевой сети
            target_wallet = await self.wallet_service.get_wallet(
                user_id, target_network
            )
            
            if not target_wallet:
                return
                
            # Создаем автоматический своп
            estimated_amount = await self.simpleswap.get_estimated_amount(
                f"USDT_{network}",
                f"USDT_{target_network}",
                amount
            )
            
            if not estimated_amount:
                return
                
            # Создаем обмен
            exchange = await self.simpleswap.create_exchange(
                f"USDT_{network}",
                f"USDT_{target_network}",
                amount,
                target_wallet.address
            )
            
            # Сохраняем информацию об автосвопе
            auto_swap = AutoSwap(
                user_id=user.id,
                from_network=network,
                to_network=target_network,
                amount=amount,
                estimated_amount=estimated_amount,
                exchange_id=exchange['id'],
                status='PENDING'
            )
            
            session.add(auto_swap)
            session.commit()
            
            # Запускаем мониторинг статуса
            asyncio.create_task(
                self._monitor_swap_status(exchange['id'], auto_swap.id)
            )
            
        except Exception as e:
            session.rollback()
            print(f"Error in auto swap: {e}")
            
    async def _monitor_swap_status(self, exchange_id: str, auto_swap_id: int):
        """Мониторит статус автоматического свопа"""
        session = self.db.get_session()
        auto_swap = session.query(AutoSwap).get(auto_swap_id)
        
        if not auto_swap:
            return
            
        while True:
            try:
                status = await self.simpleswap.get_exchange_status(exchange_id)
                
                if status['status'] != auto_swap.status:
                    auto_swap.status = status['status']
                    session.commit()
                    
                    # Уведомляем пользователя
                    if status['status'] == 'COMPLETED':
                        user = session.query(User).get(auto_swap.user_id)
                        await self.notify_swap_completed(
                            user.telegram_id,
                            auto_swap.amount,
                            auto_swap.from_network,
                            auto_swap.to_network
                        )
                        break
                        
                    elif status['status'] in ['FAILED', 'EXPIRED']:
                        user = session.query(User).get(auto_swap.user_id)
                        await self.notify_swap_failed(
                            user.telegram_id,
                            auto_swap.amount,
                            auto_swap.from_network,
                            auto_swap.to_network,
                            status['status']
                        )
                        break
                        
            except Exception as e:
                print(f"Error monitoring swap status: {e}")
                
            await asyncio.sleep(60)  # Проверяем каждую минуту
            
    async def notify_swap_completed(self, user_id: int, amount: float,
                                  from_network: str, to_network: str):
        """Уведомляет пользователя о завершении свопа"""
        # Здесь будет код отправки уведомления через бота
        pass
        
    async def notify_swap_failed(self, user_id: int, amount: float,
                               from_network: str, to_network: str, reason: str):
        """Уведомляет пользователя о неудачном свопе"""
        # Здесь будет код отправки уведомления через бота
        pass 
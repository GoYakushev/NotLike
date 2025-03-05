from core.blockchain.solana_client import SolanaClient
from core.blockchain.ton_client import TONClient
from core.database.database import Database
from core.database.models import User, Wallet, Token
from utils.security import Security
import aiohttp
from typing import Optional, Dict, Union
import random
import string
from services.notifications.notification_service import NotificationService, NotificationType

def random_string(length=10):
    """Генерирует случайную строку"""
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))

class WalletService:
    def __init__(self, db: Optional[Database] = None, notification_service: Optional[NotificationService] = None):
        self.solana = SolanaClient()
        self.ton = TONClient(api_key="YOUR_TON_API_KEY")
        self.db = db or Database()
        self.security = Security()
        self.notification_service = notification_service
        
    async def create_user_wallets(self, user_id: int) -> dict:
        """Создает кошельки для нового пользователя"""
        session = self.db.get_session()
        
        try:
            # Создаем кошельки
            sol_wallet = self.solana.create_wallet()
            ton_wallet = self.ton.create_wallet()
            
            # Сохраняем в базу
            user = session.query(User).filter_by(telegram_id=user_id).first()
            
            sol_db_wallet = Wallet(
                user_id=user.id,
                network="SOL",
                address=sol_wallet['address'],
                private_key=sol_wallet['private_key']
            )
            
            ton_db_wallet = Wallet(
                user_id=user.id,
                network="TON",
                address=ton_wallet['address'],
                private_key=ton_wallet['private_key']
            )
            
            session.add(sol_db_wallet)
            session.add(ton_db_wallet)
            session.commit()
            
            return {
                'success': True,
                'wallets': {
                    'SOL': sol_wallet['address'],
                    'TON': ton_wallet['address']
                }
            }
        except Exception as e:
            session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            session.close()
            
    async def get_balances(self, user_id: int) -> dict:
        """Возвращает балансы пользователя с учетом новых правил."""
        session = self.db.get_session()
        wallets = session.query(Wallet).filter_by(user_id=user_id).all()
        balances = {}

        for wallet in wallets:
            if wallet.network == "SOL":
                balance = self.solana.get_balance(wallet.address, wallet.token_address)
            elif wallet.network == "TON":
                balance = await self.ton.get_balance(wallet.address, wallet.token_address)
            else:
                balance = 0.0

            if wallet.token_address:
                #  токен
                token = session.query(Token).filter_by(address=wallet.token_address).first()
                if token:
                    balances[token.symbol] = balance
                else:
                    #  токен не в базе,  как "Unknown"
                    balances[f"Unknown ({wallet.token_address[:6]}...):"] = balance

                    #  токен в базу (  )
                    async with aiohttp.ClientSession() as session_aio:
                        async with session_aio.get(f"https://api.geckoterminal.com/api/v2/networks/solana/tokens/{wallet.token_address}") as response:
                            if response.status == 200:
                                data = await response.json()
                                try:
                                    token_name = data['data']['attributes']['name']
                                    token_symbol = data['data']['attributes']['symbol']
                                    token_decimals = int(data['data']['attributes']['decimals'])

                                    new_token = Token(
                                        symbol=token_symbol,
                                        name=token_name,
                                        network="SOL",
                                        address=wallet.token_address,
                                        decimals=token_decimals
                                    )
                                    session.add(new_token)
                                    session.commit()
                                    balances[token_symbol] = balance

                                except (KeyError, TypeError) as e:
                                    print(f"Error parsing GeckoTerminal response: {e}")
                            else:
                                print(f"GeckoTerminal API error: {response.status}")

            else:
                #  SOL  TON
                balances[wallet.network] = balance
        session.close()

        return balances 

    async def get_wallet(self, user_id: int, network: str, token_address: Optional[str] = None) -> Optional[Wallet]:
        """Возвращает кошелек пользователя в указанной сети."""
        session = self.db.get_session()
        try:
            wallet = session.query(Wallet).filter_by(
                user_id=user_id, network=network, token_address=token_address
            ).first()
            return wallet
        finally:
            session.close()

    async def get_balance(self, user_id: int, network: str, token_address: Optional[str] = None) -> float:
        """Возвращает баланс кошелька пользователя."""
        wallet = await self.get_wallet(user_id, network, token_address)
        if not wallet:
            return 0.0
        return wallet.balance

    async def update_balance(self, user_id: int, network: str, amount: float, token_address: Optional[str] = None) -> bool:
        """Обновляет баланс кошелька."""
        session = self.db.get_session()
        try:
            wallet = session.query(Wallet).filter_by(user_id=user_id, network=network, token_address=token_address).first()
            if not wallet:
                return False

            wallet.balance += amount
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"Error updating balance: {e}")
            return False
        finally:
            session.close()

    async def lock_funds(self, user_id: int, network: str, amount: float, token_address: Optional[str] = None) -> bool:
        """Блокирует средства на кошельке."""
        session = self.db.get_session()
        try:
            wallet = session.query(Wallet).filter_by(user_id=user_id, network=network, token_address=token_address).first()
            if not wallet:
                return False

            if wallet.balance < amount:
                return False  #  средств

            wallet.balance -= amount
            #  поле locked_balance (если  такого поля нет, добавьте  в модель Wallet)
            if hasattr(wallet, 'locked_balance'):
                wallet.locked_balance += amount
            else:
                print("Warning: Wallet model does not have 'locked_balance' field.") #  предупреждение
                #  логику,  у вас нет locked_balance
                return False
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"Error locking funds: {e}")
            return False
        finally:
            session.close()

    async def unlock_funds(self, user_id: int, network: str, amount: float, token_address: Optional[str] = None) -> bool:
        """Разблокирует средства на кошельке."""
        session = self.db.get_session()
        try:
            wallet = session.query(Wallet).filter_by(user_id=user_id, network=network, token_address=token_address).first()
            if not wallet:
                return False

            #  locked_balance
            if hasattr(wallet, 'locked_balance'):
                if wallet.locked_balance < amount:
                    return False
                wallet.locked_balance -= amount
                wallet.balance += amount
            else:
                print("Warning: Wallet model does not have 'locked_balance' field.")
                return False

            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"Error unlocking funds: {e}")
            return False
        finally:
            session.close()

    async def transfer_funds(self, from_user_id: int, to_user_id: int, network: str, amount: float, token_address: Optional[str] = None) -> bool:
        """Переводит средства между кошельками."""
        session = self.db.get_session()
        try:
            from_wallet = session.query(Wallet).filter_by(user_id=from_user_id, network=network, token_address=token_address).first()
            to_wallet = session.query(Wallet).filter_by(user_id=to_user_id, network=network, token_address=token_address).first()

            if not from_wallet or not to_wallet:
                return False
            if from_wallet.balance < amount:
                return False

            from_wallet.balance -= amount
            to_wallet.balance += amount
            session.commit()

            #  уведомление
            if self.notification_service:
                await self.notification_service.notify(
                    user_id=to_user_id,
                    notification_type=NotificationType.WALLET_TRANSFER,
                    message=f"Получен перевод от пользователя {from_user_id} на сумму {amount} {network}" + (f" ({token_address})" if token_address else ""),
                    data={'from_user_id': from_user_id, 'amount': amount, 'network': network, 'token_address': token_address}
                )
                await self.notification_service.notify(
                    user_id=from_user_id,
                    notification_type=NotificationType.WALLET_TRANSFER,
                    message=f"Вы перевели пользователю {to_user_id} сумму {amount} {network}" + (f" ({token_address})" if token_address else ""),
                    data={'to_user_id': to_user_id, 'amount': amount, 'network': network, 'token_address': token_address}
                )

            return True

        except Exception as e:
            session.rollback()
            print(f"Error during transfer: {e}")
            return False
        finally:
            session.close()

    async def deduct_fee(self, user_id: int, network: str, amount: float, token_address: Optional[str] = None) -> bool:
        """Списывает комиссию с баланса пользователя."""
        session = self.db.get_session()
        try:
            wallet = session.query(Wallet).filter_by(user_id=user_id, network=network, token_address=token_address).first()
            if not wallet:
                return False

            if wallet.balance < amount:
                return False

            wallet.balance -= amount
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            print(f"Error deducting fee: {e}")
            return False
        finally:
            session.close() 
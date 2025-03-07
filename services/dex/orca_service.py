from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.keypair import Keypair
import json
import base58
import requests

class OrcaService:
    def __init__(self):
        self.client = Client("https://api.mainnet-beta.solana.com")
        self.orca_api = "https://api.orca.so"
        self.pools = {}
        
    async def get_pools(self):
        """Получает список пулов Orca"""
        try:
            response = requests.get(f"{self.orca_api}/pools")
            self.pools = response.json()
            return self.pools
        except Exception as e:
            print(f"Error getting Orca pools: {e}")
            return None
            
    async def get_price(self, token_a: str, token_b: str) -> float:
        """Получает цену свопа между токенами"""
        try:
            pool_id = self._get_pool_id(token_a, token_b)
            response = requests.get(f"{self.orca_api}/price/{pool_id}")
            return float(response.json()['price'])
        except Exception as e:
            print(f"Error getting Orca price: {e}")
            return None
            
    async def create_swap_transaction(self, 
                                    from_token: str,
                                    to_token: str,
                                    amount: float,
                                    wallet: Keypair) -> Transaction:
        """Создает транзакцию свопа"""
        try:
            pool_id = self._get_pool_id(from_token, to_token)
            
            # Получаем данные для свопа
            swap_data = {
                'poolId': pool_id,
                'fromToken': from_token,
                'toToken': to_token,
                'amount': str(amount),
                'slippage': '0.5',  # 0.5% slippage
                'wallet': str(wallet.public_key)
            }
            
            response = requests.post(
                f"{self.orca_api}/swap/prepare",
                json=swap_data
            )
            
            # Создаем и подписываем транзакцию
            tx_data = response.json()
            transaction = Transaction.deserialize(
                base58.b58decode(tx_data['transaction'])
            )
            transaction.sign(wallet)
            
            return transaction
            
        except Exception as e:
            print(f"Error creating Orca swap transaction: {e}")
            return None
            
    def _get_pool_id(self, token_a: str, token_b: str) -> str:
        """Находит ID пула для пары токенов"""
        for pool in self.pools:
            if (pool['tokenA'] == token_a and pool['tokenB'] == token_b) or \
               (pool['tokenA'] == token_b and pool['tokenB'] == token_a):
                return pool['id']
        raise Exception(f"Pool not found for {token_a}/{token_b}") 
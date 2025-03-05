from tonsdk.client import TonClient
from tonsdk.utils import Address
import requests
import base64

class StonFiService:
    def __init__(self):
        self.client = TonClient("https://toncenter.com/api/v2/jsonRPC")
        self.stonfi_api = "https://api.ston.fi/v1"
        self.pools = {}
        
    async def get_pools(self):
        """Получает список пулов Ston.FI"""
        try:
            response = requests.get(f"{self.stonfi_api}/pools")
            self.pools = response.json()
            return self.pools
        except Exception as e:
            print(f"Error getting Ston.FI pools: {e}")
            return None
            
    async def get_price(self, token_a: str, token_b: str) -> float:
        """Получает цену свопа между токенами"""
        try:
            pool_address = self._get_pool_address(token_a, token_b)
            response = requests.get(
                f"{self.stonfi_api}/price",
                params={
                    'pool': pool_address,
                    'tokenA': token_a,
                    'tokenB': token_b
                }
            )
            return float(response.json()['price'])
        except Exception as e:
            print(f"Error getting Ston.FI price: {e}")
            return None
            
    async def create_swap_transaction(self,
                                    from_token: str,
                                    to_token: str,
                                    amount: float,
                                    wallet_address: str) -> dict:
        """Создает транзакцию свопа"""
        try:
            pool_address = self._get_pool_address(from_token, to_token)
            
            # Получаем данные для свопа
            swap_data = {
                'pool': pool_address,
                'fromToken': from_token,
                'toToken': to_token,
                'amount': str(amount),
                'slippage': '0.5',  # 0.5% slippage
                'wallet': wallet_address
            }
            
            response = requests.post(
                f"{self.stonfi_api}/swap/prepare",
                json=swap_data
            )
            
            return response.json()
            
        except Exception as e:
            print(f"Error creating Ston.FI swap transaction: {e}")
            return None
            
    def _get_pool_address(self, token_a: str, token_b: str) -> str:
        """Находит адрес пула для пары токенов"""
        for pool in self.pools:
            if (pool['tokenA'] == token_a and pool['tokenB'] == token_b) or \
               (pool['tokenA'] == token_b and pool['tokenB'] == token_a):
                return pool['address']
        raise Exception(f"Pool not found for {token_a}/{token_b}") 
import aiohttp
import json
from datetime import datetime
from typing import Optional, Dict, List

class SimpleSwapService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.simpleswap.io/v1"
        self.headers = {"api-key": api_key}
        
    async def get_currencies(self) -> List[Dict]:
        """Получает список доступных валют"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/get_currencies",
                headers=self.headers
            ) as response:
                return await response.json()
                
    async def get_pairs(self, from_currency: str) -> List[str]:
        """Получает список доступных пар для обмена"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/get_pairs",
                params={"fixed": 1, "currency_from": from_currency},
                headers=self.headers
            ) as response:
                return await response.json()
                
    async def get_estimated_amount(self, 
                                 from_currency: str,
                                 to_currency: str,
                                 amount: float) -> Optional[float]:
        """Получает оценочную сумму обмена"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/get_estimated",
                params={
                    "currency_from": from_currency,
                    "currency_to": to_currency,
                    "amount": amount,
                    "fixed": 1
                },
                headers=self.headers
            ) as response:
                data = await response.json()
                return float(data['estimated_amount'])
                
    async def create_exchange(self,
                            from_currency: str,
                            to_currency: str,
                            amount: float,
                            address_to: str,
                            extra_id: str = None) -> Dict:
        """Создает обмен"""
        params = {
            "currency_from": from_currency,
            "currency_to": to_currency,
            "amount": amount,
            "address_to": address_to,
            "fixed": 1
        }
        
        if extra_id:
            params["extra_id"] = extra_id
            
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/create_exchange",
                json=params,
                headers=self.headers
            ) as response:
                return await response.json()
                
    async def get_exchange_status(self, exchange_id: str) -> Dict:
        """Получает статус обмена"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/get_exchange",
                params={"id": exchange_id},
                headers=self.headers
            ) as response:
                return await response.json() 
from typing import Dict, List, Optional, Tuple
import aiohttp
import json
import logging
from decimal import Decimal
from datetime import datetime, timedelta
import asyncio
from functools import wraps
import random
from cachetools import TTLCache

def retry_on_failure(retries=3, delay=1):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < retries - 1:
                        await asyncio.sleep(delay * (attempt + 1))
            raise last_exception
        return wrapper
    return decorator

class DEXService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.supported_dexes = {
            'solana': {
                'ston.fi': 'https://api.ston.fi/v1',
                'orca': 'https://api.orca.so',
                'raydium': 'https://api.raydium.io'
            },
            'ton': {
                'ston.fi': 'https://api.ston.fi/v1',
                'dedust': 'https://api.dedust.io/v2'
            }
        }
        self.timeout = aiohttp.ClientTimeout(total=30)
        # Кэш для цен с временем жизни 60 секунд
        self.price_cache = TTLCache(maxsize=1000, ttl=60)
        # Статистика успешности DEX
        self.dex_stats = {
            dex: {'success': 0, 'fail': 0}
            for network in self.supported_dexes
            for dex in self.supported_dexes[network]
        }
        
    def _validate_network(self, network: str) -> str:
        network = network.lower()
        if network not in self.supported_dexes:
            raise ValueError(f"Неподдерживаемая сеть: {network}")
        return network
        
    def _validate_token_address(self, token_address: str) -> str:
        if not isinstance(token_address, str) or not token_address:
            raise ValueError("Некорректный адрес токена")
        return token_address
        
    def _validate_amount(self, amount: Decimal) -> Decimal:
        if not isinstance(amount, Decimal) or amount <= 0:
            raise ValueError("Сумма должна быть положительным числом")
        return amount

    @retry_on_failure(retries=3, delay=1)
    async def get_token_info(self, network: str, token_address: str) -> Dict:
        """Получает информацию о токене."""
        try:
            network = self._validate_network(network)
            token_address = self._validate_token_address(token_address)
            
            if network == 'solana':
                return await self._get_solana_token_info(token_address)
            elif network == 'ton':
                return await self._get_ton_token_info(token_address)
        except Exception as e:
            self.logger.error(f"Ошибка при получении информации о токене: {str(e)}")
            raise

    @retry_on_failure(retries=3, delay=1)
    async def get_best_price(self, network: str, from_token: str, to_token: str, amount: Decimal) -> Dict:
        """Находит лучшую цену среди всех поддерживаемых DEX."""
        try:
            # Проверяем кэш
            cache_key = f"{network}:{from_token}:{to_token}:{amount}"
            cached_result = self.price_cache.get(cache_key)
            if cached_result:
                return cached_result
                
            network = self._validate_network(network)
            from_token = self._validate_token_address(from_token)
            to_token = self._validate_token_address(to_token)
            amount = self._validate_amount(amount)
            
            best_price = None
            best_dex = None
            best_route = None
            errors = {}

            # Запрашиваем цены параллельно
            async def get_dex_price(dex_name: str, api_url: str):
                try:
                    price_info = await self._get_dex_price(
                        dex_name, 
                        api_url, 
                        network, 
                        from_token, 
                        to_token, 
                        amount
                    )
                    return dex_name, price_info
                except Exception as e:
                    errors[dex_name] = str(e)
                    return dex_name, None

            tasks = [
                get_dex_price(dex_name, api_url)
                for dex_name, api_url in self.supported_dexes[network].items()
            ]
            
            results = await asyncio.gather(*tasks)
            
            for dex_name, price_info in results:
                if price_info and (best_price is None or 
                                 price_info['output_amount'] > best_price):
                    best_price = price_info['output_amount']
                    best_dex = dex_name
                    best_route = price_info['route']

            if best_price is None:
                error_details = "\n".join([f"{dex}: {err}" for dex, err in errors.items()])
                raise Exception(f"Не удалось получить цены:\n{error_details}")

            result = {
                'dex': best_dex,
                'input_amount': str(amount),
                'output_amount': str(best_price),
                'route': best_route,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Сохраняем в кэш
            self.price_cache[cache_key] = result
            
            return result
            
        except Exception as e:
            self.logger.error(f"Ошибка при поиске лучшей цены: {str(e)}")
            raise

    async def execute_swap(
        self,
        network: str,
        from_token: str,
        to_token: str,
        amount: Decimal,
        slippage: float = 0.5
    ) -> Dict:
        """Выполняет своп на DEX с лучшей ценой."""
        try:
            # Получаем лучшее предложение
            best_price = await self.get_best_price(network, from_token, to_token, amount)
            
            # Проверяем, что цена не изменилась сильнее допустимого проскальзывания
            min_output = Decimal(best_price['output_amount']) * (1 - slippage/100)
            
            # Пытаемся выполнить своп на разных DEX в порядке их надежности
            for dex in self._get_best_dex(network):
                try:
                    # Выполняем своп
                    swap_result = await self._execute_dex_swap(
                        dex,
                        network,
                        from_token,
                        to_token,
                        amount,
                        min_output
                    )
                    
                    # Обновляем статистику
                    self.dex_stats[dex]['success'] += 1
                    
                    # Проверяем частичное исполнение
                    if Decimal(swap_result['output_amount']) < amount:
                        remaining_amount = amount - Decimal(swap_result['output_amount'])
                        if remaining_amount > 0:
                            # Пытаемся выполнить оставшуюся часть на другой DEX
                            remaining_swap = await self.execute_swap(
                                network,
                                from_token,
                                to_token,
                                remaining_amount,
                                slippage
                            )
                            # Объединяем результаты
                            swap_result['output_amount'] = str(
                                Decimal(swap_result['output_amount']) +
                                Decimal(remaining_swap['output_amount'])
                            )
                            swap_result['partial_execution'] = True
                            swap_result['additional_tx'] = remaining_swap['transaction_hash']
                    
                    return {
                        'success': True,
                        'transaction_hash': swap_result['tx_hash'],
                        'input_amount': str(amount),
                        'output_amount': swap_result['output_amount'],
                        'dex_used': dex,
                        'route': best_price['route'],
                        'partial_execution': swap_result.get('partial_execution', False),
                        'additional_tx': swap_result.get('additional_tx'),
                        'timestamp': datetime.utcnow().isoformat()
                    }
                except Exception as e:
                    self.logger.warning(f"Ошибка при свопе на {dex}: {str(e)}")
                    self.dex_stats[dex]['fail'] += 1
                    continue
            
            raise Exception("Не удалось выполнить своп ни на одной DEX")
            
        except Exception as e:
            self.logger.error(f"Ошибка при выполнении свопа: {str(e)}")
            raise

    @retry_on_failure(retries=3, delay=1)
    async def _get_solana_token_info(self, token_address: str) -> Dict:
        """Получает информацию о токене в сети Solana."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(
                    f"{self.supported_dexes['solana']['ston.fi']}/token/{token_address}"
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if not all(key in data for key in ['name', 'symbol', 'decimals']):
                            raise ValueError("Неполные данные токена")
                        return {
                            'address': token_address,
                            'name': data['name'],
                            'symbol': data['symbol'],
                            'decimals': data['decimals'],
                            'total_supply': data.get('total_supply'),
                            'network': 'solana'
                        }
                    elif response.status == 404:
                        raise ValueError(f"Токен не найден: {token_address}")
                    else:
                        error_text = await response.text()
                        raise Exception(f"Ошибка API: {response.status}, {error_text}")
        except asyncio.TimeoutError:
            raise Exception("Таймаут при получении информации о токене Solana")
        except aiohttp.ClientError as e:
            raise Exception(f"Ошибка сети при получении информации о токене Solana: {str(e)}")
        except Exception as e:
            self.logger.error(f"Ошибка при получении информации о токене Solana: {str(e)}")
            raise

    @retry_on_failure(retries=3, delay=1)
    async def _get_ton_token_info(self, token_address: str) -> Dict:
        """Получает информацию о токене в сети TON."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(
                    f"{self.supported_dexes['ton']['ston.fi']}/token/{token_address}"
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if not all(key in data for key in ['name', 'symbol', 'decimals']):
                            raise ValueError("Неполные данные токена")
                        return {
                            'address': token_address,
                            'name': data['name'],
                            'symbol': data['symbol'],
                            'decimals': data['decimals'],
                            'total_supply': data.get('total_supply'),
                            'network': 'ton'
                        }
                    elif response.status == 404:
                        raise ValueError(f"Токен не найден: {token_address}")
                    else:
                        error_text = await response.text()
                        raise Exception(f"Ошибка API: {response.status}, {error_text}")
        except asyncio.TimeoutError:
            raise Exception("Таймаут при получении информации о токене TON")
        except aiohttp.ClientError as e:
            raise Exception(f"Ошибка сети при получении информации о токене TON: {str(e)}")
        except Exception as e:
            self.logger.error(f"Ошибка при получении информации о токене TON: {str(e)}")
            raise

    @retry_on_failure(retries=3, delay=1)
    async def _get_dex_price(self, dex_name: str, api_url: str, network: str,
                            from_token: str, to_token: str, amount: Decimal) -> Dict:
        """Получает цену свопа с конкретной DEX."""
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                params = {
                    'fromToken': from_token,
                    'toToken': to_token,
                    'amount': str(amount)
                }
                
                async with session.get(
                    f"{api_url}/quote",
                    params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'outputAmount' not in data:
                            raise ValueError("Отсутствует информация о выходной сумме")
                        return {
                            'output_amount': Decimal(str(data['outputAmount'])),  # Безопасное преобразование
                            'route': data.get('route', []),
                            'price_impact': data.get('priceImpact')
                        }
                    elif response.status == 404:
                        raise ValueError(f"Пара токенов не найдена: {from_token}/{to_token}")
                    else:
                        error_text = await response.text()
                        raise Exception(f"Ошибка API DEX: {response.status}, {error_text}")
        except asyncio.TimeoutError:
            raise Exception(f"Таймаут при получении цены с {dex_name}")
        except aiohttp.ClientError as e:
            raise Exception(f"Ошибка сети при получении цены с {dex_name}: {str(e)}")
        except Exception as e:
            self.logger.error(f"Ошибка при получении цены с {dex_name}: {str(e)}")
            raise

    @retry_on_failure(retries=3, delay=1)
    async def _execute_dex_swap(self, dex_name: str, network: str, from_token: str,
                               to_token: str, amount: Decimal, min_output: Decimal) -> Dict:
        """Выполняет своп на конкретной DEX."""
        try:
            api_url = self.supported_dexes[network][dex_name]
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                swap_data = {
                    'fromToken': from_token,
                    'toToken': to_token,
                    'amount': str(amount),
                    'minOutput': str(min_output)
                }
                
                async with session.post(
                    f"{api_url}/swap",
                    json=swap_data
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if not all(key in data for key in ['txHash', 'outputAmount']):
                            raise ValueError("Неполные данные свопа")
                        return {
                            'tx_hash': data['txHash'],
                            'output_amount': Decimal(str(data['outputAmount']))  # Безопасное преобразование
                        }
                    elif response.status == 400:
                        error_data = await response.json()
                        raise ValueError(f"Ошибка валидации: {error_data.get('error', 'Unknown error')}")
                    else:
                        error_text = await response.text()
                        raise Exception(f"Ошибка при выполнении свопа: {response.status}, {error_text}")
        except asyncio.TimeoutError:
            raise Exception(f"Таймаут при выполнении свопа на {dex_name}")
        except aiohttp.ClientError as e:
            raise Exception(f"Ошибка сети при выполнении свопа на {dex_name}: {str(e)}")
        except Exception as e:
            self.logger.error(f"Ошибка при выполнении свопа на {dex_name}: {str(e)}")
            raise 

    def _get_best_dex(self, network: str) -> List[str]:
        """Возвращает список DEX в порядке их надежности"""
        dexes = list(self.supported_dexes[network].keys())
        # Сортируем DEX по соотношению успешных операций к общему количеству
        return sorted(dexes, key=lambda dex: (
            self.dex_stats[dex]['success'] / 
            (self.dex_stats[dex]['success'] + self.dex_stats[dex]['fail'] + 1)
        ), reverse=True) 
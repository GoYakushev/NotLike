from core.database.models import Token, SpotOrder, User, Wallet
from core.database.database import Database
from utils.security import Security
import aiohttp
import json
from services.wallet.wallet_service import WalletService
from core.blockchain.solana_client import SolanaClient  # Ваши классы
from core.blockchain.ton_client import TONClient
# from core.blockchain.ton_client import TONClient # Если будете делать spot для TON
from typing import Dict, Optional, Union, List
import asyncio
import bisect  #  bisect
from services.fees.fee_service import FeeService #  FeeService
from services.notifications.notification_service import NotificationService, NotificationType  #  

class StonfiAPI:
    """Вспомогательный класс для работы с API Ston.fi."""

    def __init__(self, api_key: str):
        self.base_url = "https://api.ston.fi"  #  URL
        self.api_key = api_key  #  API key

    async def get_price(self, base_token: str, quote_token: str) -> Optional[float]:
        """Получает текущую цену пары."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/v1/spot/price",  #  эндпоинт
                params={"base_asset": base_token, "quote_asset": quote_token},
                headers={"X-API-KEY": self.api_key}  #  API key
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data['price'])  #  цену
                else:
                    print(f"Ston.fi API error: {response.status} - {await response.text()}")
                    return None

    async def market_buy(self, base_token: str, quote_token: str, amount: float) -> dict:
        """Выполняет рыночную покупку."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/v1/spot/market_buy",  #  эндпоинт
                json={"base_asset": base_token, "quote_asset": quote_token, "amount": amount},
                headers={"X-API-KEY": self.api_key}  #  API key
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"Ston.fi API error: {response.status} - {await response.text()}")
                    return {'success': False, 'error': f'Ston.fi API error: {response.status} - {await response.text()}'}

    async def market_sell(self, base_token: str, quote_token: str, amount: float) -> dict:
        """Выполняет рыночную продажу."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/v1/spot/market_sell",  #  эндпоинт
                json={"base_asset": base_token, "quote_asset": quote_token, "amount": amount},
                headers={"X-API-KEY": self.api_key}  #  API key
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"Ston.fi API error: {response.status} - {await response.text()}")
                    return {'success': False, 'error': f'Ston.fi API error: {response.status} - {await response.text()}'}

class OrderBook:
    """
    Класс, представляющий стакан заявок (Order Book).
    """
    def __init__(self, base_currency: str, quote_currency: str):
        self.base_currency = base_currency
        self.quote_currency = quote_currency
        self.bids: List[SpotOrder] = []  #  BUY orders (отсортированы по убыванию цены)
        self.asks: List[SpotOrder] = []  #  SELL orders (отсортированы по возрастанию цены)

    def add_order(self, order: SpotOrder):
        """Добавляет ордер в стакан."""
        if order.side == "BUY":
            bisect.insort_left(self.bids, order, key=lambda x: -x.price)  #  по убыванию
        elif order.side == "SELL":
            bisect.insort_left(self.asks, order, key=lambda x: x.price)  #  по возрастанию
        else:
            raise ValueError("Invalid order side")

    def remove_order(self, order: SpotOrder):
        """Удаляет ордер из стакана."""
        if order.side == "BUY":
            if order in self.bids:
                self.bids.remove(order)
        elif order.side == "SELL":
            if order in self.asks:
                self.asks.remove(order)
        else:
            raise ValueError("Invalid order side")

    def match_orders(self) -> List[tuple[SpotOrder, SpotOrder]]:
        """
        Мэтчит ордера в стакане.

        Returns:
            List[tuple[SpotOrder, SpotOrder]]: Список пар (buy_order, sell_order), для которых произошел мэтчинг.
        """
        matches = []
        while self.bids and self.asks and self.bids[0].price >= self.asks[0].price:
            buy_order = self.bids[0]
            sell_order = self.asks[0]
            matches.append((buy_order, sell_order))

            if buy_order.quantity > sell_order.quantity:
                buy_order.quantity -= sell_order.quantity
                sell_order.quantity = 0
                self.asks.pop(0)
            elif buy_order.quantity < sell_order.quantity:
                sell_order.quantity -= buy_order.quantity
                buy_order.quantity = 0
                self.bids.pop(0)
            else:  # buy_order.quantity == sell_order.quantity
                buy_order.quantity = 0
                sell_order.quantity = 0
                self.bids.pop(0)
                self.asks.pop(0)
        return matches

class SpotService:
    def __init__(self, db: Database, wallet_service: WalletService, solana_client: SolanaClient, ton_client: TONClient, orca_api, stonfi_api: StonfiAPI, notification_service: NotificationService):
        self.db = db
        self.security = Security()
        self.wallet_service = wallet_service
        self.solana_client = solana_client
        self.ton_client = ton_client
        self.orca_api = orca_api  # Ваши классы для работы с биржами
        self.stonfi_api = stonfi_api
        self.order_books: Dict[str, OrderBook] = {}  #  стаканы заявок
        self.lock = asyncio.Lock()  #  asyncio lock
        self.fee_service = FeeService(db) #  FeeService
        self.notification_service = notification_service  #  
        
    async def get_token_info(self, symbol: str, network: str) -> dict:
        """Получает информацию о токене"""
        session = self.db.get_session()
        token = session.query(Token).filter_by(symbol=symbol, network=network).first()
        
        if not token:
            # Получаем информацию через API
            if network == "SOL":
                # Используем API ORCA
                async with aiohttp.ClientSession() as client:
                    async with client.get(f"https://api.orca.so/v1/token/{symbol}") as response:
                        data = await response.json()
                        
                token = Token(
                    network="SOL",
                    symbol=symbol,
                    contract_address=data['address'],
                    name=data['name'],
                    decimals=data['decimals'],
                    total_supply=data['total_supply'],
                    market_cap=data['market_cap'],
                    volume_24h=data['volume_24h']
                )
                session.add(token)
                session.commit()
                
        return {
            'symbol': token.symbol,
            'name': token.name,
            'price': await self.get_current_price(token.symbol, token.network),
            'market_cap': token.market_cap,
            'volume_24h': token.volume_24h,
            'total_supply': token.total_supply,
            'ath': token.ath,
            'atl': token.atl
        }
        
    async def create_order(self, user_id: int, data: dict) -> dict:
        """Создает новый ордер"""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()
        
        try:
            # Проверяем баланс
            if data['side'] == 'BUY':
                # Проверка USDT баланса
                pass
            else:
                # Проверка баланса токена
                pass
                
            order = SpotOrder(
                user_id=user.id,
                token_id=data['token_id'],
                order_type=data['type'],
                side=data['side'],
                amount=data['amount'],
                price=data['price'] if data['type'] == 'LIMIT' else await self.get_current_price(data['symbol'], data['network']),
                take_profit=data.get('take_profit'),
                stop_loss=data.get('stop_loss'),
                status='OPEN'
            )
            
            session.add(order)
            session.commit()
            
            # Если это рыночный ордер, сразу исполняем
            if data['type'] == 'MARKET':
                await self.execute_market_order(order)
                
            return {
                'success': True,
                'order_id': order.id
            }
            
        except Exception as e:
            session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
            
    async def execute_market_order(self, order: SpotOrder):
        """Исполняет рыночный ордер"""
        # Здесь будет интеграция с ORCA/Ston.fi
        pass 

    def get_order_book(self, base_currency: str, quote_currency: str) -> OrderBook:
        """Возвращает OrderBook для заданной пары."""
        pair = f"{base_currency}/{quote_currency}"
        if pair not in self.order_books:
            self.order_books[pair] = OrderBook(base_currency, quote_currency)
        return self.order_books[pair]

    async def create_limit_order(self,
                                 user_id: int,
                                 base_currency: str,
                                 quote_currency: str,
                                 side: str,
                                 quantity: float,
                                 price: float) -> dict:
        """Создает LIMIT ордер."""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()

        if not user:
            return {'success': False, 'error': 'Пользователь не найден'}

        try:
            order = SpotOrder(
                user_id=user.id,
                base_currency=base_currency,
                quote_currency=quote_currency,
                order_type="LIMIT",
                side=side,
                price=price,
                quantity=quantity,
                status="OPEN"
            )
            session.add(order)

            #  комиссию
            fee_result = await self.fee_service.apply_fee(user.telegram_id, 'spot', order.quantity * order.price if order.price else 0) #  0  MARKET
            if not fee_result['success']:
                session.rollback()
                return fee_result

            session.commit()

            #  ордер в стакан
            order_book = self.get_order_book(base_currency, quote_currency)
            order_book.add_order(order)

            #  уведомление
            await self.notification_service.notify(
                user_id=user.telegram_id,
                notification_type=NotificationType.ORDER_UPDATE,
                message=f"Создан LIMIT ордер #{order.id}: {side} {base_currency}/{quote_currency} x {quantity} @ {price}",
                data={'order_id': order.id}
            )

            #  мэтчинг
            async with self.lock:  #  lock
                self.match_and_execute_orders(order_book)

            return {'success': True, 'order_id': order.id}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при создании LIMIT ордера: {str(e)}'}

    async def create_market_order(self,
                                  user_id: int,
                                  base_currency: str,
                                  quote_currency: str,
                                  side: str,
                                  quantity: float) -> dict:
        """Создает MARKET ордер."""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()

        if not user:
            return {'success': False, 'error': 'Пользователь не найден'}

        try:
            order = SpotOrder(
                user_id=user.id,
                base_currency=base_currency,
                quote_currency=quote_currency,
                order_type="MARKET",
                side=side,
                quantity=quantity,
                status="OPEN"  #  сразу исполняем
            )
            session.add(order)

            #  комиссию
            fee_result = await self.fee_service.apply_fee(user.telegram_id, 'spot', order.quantity * order.price if order.price else 0) #  0  MARKET
            if not fee_result['success']:
                session.rollback()
                return fee_result

            session.commit()

            #  уведомление
            await self.notification_service.notify(
                user_id=user.telegram_id,
                notification_type=NotificationType.ORDER_UPDATE,
                message=f"Создан MARKET ордер #{order.id}: {side} {base_currency}/{quote_currency} x {quantity}",
                data={'order_id': order.id}
            )

            #  исполнение
            await self.process_order(order.id)

            return {'success': True, 'order_id': order.id}
        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при создании MARKET ордера: {str(e)}'}

    async def cancel_order(self, user_id: int, order_id: int) -> dict:
        """Отменяет ордер."""
        session = self.db.get_session()
        order = session.query(SpotOrder).get(order_id)

        if not order:
            return {'success': False, 'error': 'Ордер не найден'}
        if order.user_id != user_id:
            return {'success': False, 'error': 'Нельзя отменить чужой ордер'}
        if order.status != "OPEN":
            return {'success': False, 'error': 'Нельзя отменить ордер в статусе, отличном от OPEN'}

        try:
            #  из стакана
            order_book = self.get_order_book(order.base_currency, order.quote_currency)
            order_book.remove_order(order)

            order.status = "CANCELLED"
            session.commit()

            #  уведомление
            await self.notification_service.notify(
                user_id=order.user_id,
                notification_type=NotificationType.ORDER_UPDATE,
                message=f"Ордер #{order.id} отменен",
                data={'order_id': order.id}
            )

            return {'success': True}
        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при отмене ордера: {str(e)}'}

    def match_and_execute_orders(self, order_book: OrderBook):
        """Мэтчит и исполняет ордера в стакане."""
        matches = order_book.match_orders()
        for buy_order, sell_order in matches:
            #  исполнение
            asyncio.create_task(self.execute_matched_orders(buy_order, sell_order))

    async def execute_matched_orders(self, buy_order: SpotOrder, sell_order: SpotOrder):
        """Исполняет ордера, для которых произошел мэтчинг."""
        session = self.db.get_session()
        try:
            #  цену
            price = sell_order.price  #  SELL ордера

            #  количество
            executed_quantity = min(buy_order.quantity, sell_order.quantity)

            #  балансы
            buy_user_wallet_base = session.query(Wallet).filter_by(user_id=buy_order.user_id, network=buy_order.base_currency.split('_')[0], token_address=None if buy_order.base_currency.split('_')[0] in ('SOL', 'TON') else buy_order.base_currency).first()
            buy_user_wallet_quote = session.query(Wallet).filter_by(user_id=buy_order.user_id, network=buy_order.quote_currency.split('_')[0], token_address=None if buy_order.quote_currency.split('_')[0] in ('SOL', 'TON') else buy_order.quote_currency).first()

            sell_user_wallet_base = session.query(Wallet).filter_by(user_id=sell_order.user_id, network=sell_order.base_currency.split('_')[0], token_address=None if sell_order.base_currency.split('_')[0] in ('SOL', 'TON') else sell_order.base_currency).first()
            sell_user_wallet_quote = session.query(Wallet).filter_by(user_id=sell_order.user_id, network=sell_order.quote_currency.split('_')[0], token_address=None if sell_order.quote_currency.split('_')[0] in ('SOL', 'TON') else sell_order.quote_currency).first()

            if not all([buy_user_wallet_base, buy_user_wallet_quote, sell_user_wallet_base, sell_user_wallet_quote]):
                raise Exception("Один из кошельков не найден")

            #  балансы
            buy_user_wallet_base.balance += executed_quantity
            buy_user_wallet_quote.balance -= executed_quantity * price
            sell_user_wallet_base.balance -= executed_quantity
            sell_user_wallet_quote.balance += executed_quantity * price

            #  ордеров
            buy_order.filled_amount += executed_quantity
            sell_order.filled_amount += executed_quantity

            if buy_order.quantity == 0:
                buy_order.status = "FILLED"
            else:
                buy_order.status = "PARTIALLY_FILLED"

            if sell_order.quantity == 0:
                sell_order.status = "FILLED"
            else:
                sell_order.status = "PARTIALLY_FILLED"

            session.commit()

            #  уведомление
            await self.notification_service.notify(
                user_id=buy_order.user_id,
                notification_type=NotificationType.ORDER_UPDATE,
                message=f"Ордер #{buy_order.id} исполнен",
                data={'order_id': buy_order.id}
            )

        except Exception as e:
            session.rollback()
            print(f"Error executing matched orders: {e}")
            #  логирование
            #  уведомления

    async def process_order(self, order_id: int):
        """Обрабатывает (исполняет) ордер."""
        session = self.db.get_session()
        order = session.query(SpotOrder).get(order_id)

        if not order:
            return {'success': False, 'error': 'Ордер не найден'}

        if order.status != "OPEN":
            return {'success': False, 'error': 'Ордер не в статусе OPEN'}

        try:
            if order.base_currency == "SOL":
                if order.order_type == "MARKET":
                    if order.side == "BUY":
                        async with aiohttp.ClientSession() as client:
                            async with client.post("https://api.orca.so/v1/market/buy",
                                                  json={
                                                      "base": order.base_currency,
                                                      "quote": order.quote_currency,
                                                      "amount": order.quantity
                                                  }) as response:
                                result = await response.json()
                                if response.status != 200:
                                    raise Exception(f"Orca API error: {result}")

                    elif order.side == "SELL":
                        async with aiohttp.ClientSession() as client:
                            async with client.post("https://api.orca.so/v1/market/sell",
                                                  json={
                                                      "base": order.base_currency,
                                                      "quote": order.quote_currency,
                                                      "amount": order.quantity
                                                  }) as response:
                                result = await response.json()
                                if response.status != 200:
                                    raise Exception(f"Orca API error: {result}")
                    else:
                        raise ValueError(f"Invalid order side: {order.side}")

                    order.status = "FILLED"
                    order.filled_amount = order.quantity
                    order.price = result.get('price')

                    #  балансы
                    if order.side == "BUY":
                        buyer_wallet = session.query(Wallet).filter_by(user_id=order.user_id, network="SOL", token_address=None).first()
                        if not buyer_wallet:
                            raise Exception("Кошелек покупателя не найден")
                        buyer_wallet.balance += order.quantity

                        seller_wallet = session.query(Wallet).filter_by(user_id=order.user_id, network="SOL", token_address="usdt_address").first()  #  USDT
                        if not seller_wallet:
                            raise Exception("Кошелек продавца (USDT) не найден")
                        seller_wallet.balance -= order.quantity * result.get("price")

                    else:  # SELL
                        seller_wallet = session.query(Wallet).filter_by(user_id=order.user_id, network="SOL", token_address="usdt_address").first()
                        if not seller_wallet:
                            raise Exception("Кошелек продавца (USDT) не найден")
                        seller_wallet.balance += order.quantity * result.get("price")

                        buyer_wallet = session.query(Wallet).filter_by(user_id=order.user_id, network="SOL", token_address=None).first()
                        if not buyer_wallet:
                            raise Exception("Кошелек покупателя не найден")
                        buyer_wallet.balance -= order.quantity

                elif order.order_type == "LIMIT":
                    #  LIMIT ордеров
                    pass

            elif order.base_currency == "TON":
                if order.order_type == "MARKET":
                    if order.side == "BUY":
                        result = await self.stonfi_api.market_buy(order.base_currency.split("_")[1], order.quote_currency.split("_")[1], order.quantity)
                    elif order.side == "SELL":
                        result = await self.stonfi_api.market_sell(order.base_currency.split("_")[1], order.quote_currency.split("_")[1], order.quantity)
                    else:
                        raise ValueError(f"Invalid order side: {order.side}")

                    if result and result.get('success'):
                        order.status = "FILLED"
                        order.filled_amount = order.quantity
                        order.price = result.get('price')

                        #  балансы
                        if order.side == "BUY":
                            buyer_wallet_base = session.query(Wallet).filter_by(user_id=order.user_id, network="TON", token_address=None).first()
                            buyer_wallet_quote = session.query(Wallet).filter_by(user_id=order.user_id, network="TON", token_address="usdt_address").first()  #  USDT
                            if not buyer_wallet_base or not buyer_wallet_quote:
                                raise Exception("Кошелек покупателя не найден")
                            buyer_wallet_base.balance += order.quantity
                            buyer_wallet_quote.balance -= order.quantity * result.get("price")

                        else:  # SELL
                            seller_wallet_base = session.query(Wallet).filter_by(user_id=order.user_id, network="TON", token_address=None).first()
                            seller_wallet_quote = session.query(Wallet).filter_by(user_id=order.user_id, network="TON", token_address="usdt_address").first()
                            if not seller_wallet_base or not seller_wallet_quote:
                                raise Exception("Кошелек продавца не найден")
                            seller_wallet_base.balance -= order.quantity
                            seller_wallet_quote.balance += order.quantity * result.get("price")

                    else:
                        order.status = "FAILED"  #  не удалось исполнить
                        #  логирование
                elif order.order_type == "LIMIT":
                    pass

            else:
                return {'success': False, 'error': f'Неподдерживаемая валюта: {order.base_currency}'}

            session.commit()

            #  уведомление
            await self.notification_service.notify(
                user_id=order.user_id,
                notification_type=NotificationType.ORDER_UPDATE,
                message=f"Ордер #{order.id} исполнен",
                data={'order_id': order.id}
            )

            return {'success': True}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': f'Ошибка при обработке ордера: {str(e)}'}

    async def get_open_orders(self, user_id: int) -> list:
        """Возвращает список открытых ордеров пользователя."""
        session = self.db.get_session()
        orders = session.query(SpotOrder).filter_by(user_id=user_id, status="OPEN").all()
        return orders

    async def get_order_history(self, user_id: int) -> list:
        """Возвращает историю ордеров пользователя."""
        session = self.db.get_session()
        orders = session.query(SpotOrder).filter_by(user_id=user_id).all()  # Все ордера
        return orders 
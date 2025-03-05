from aiogram import Bot, types
from core.database.models import User, NotificationSettings
from core.database.database import Database
from typing import Optional, List, Dict
import asyncio
import json

class NotificationType:
    PRICE_ALERT = "price_alert"
    ORDER_UPDATE = "order_update"
    P2P_UPDATE = "p2p_update"
    WALLET_TRANSFER = "wallet_transfer"
    SWAP_STATUS = "swap_status"
    SECURITY_ALERT = "security_alert"
    SYSTEM_UPDATE = "system_update"
    PREMIUM_STATUS = "premium_status"

class NotificationService:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.db = Database()
        self._notification_queue = asyncio.Queue()
        self._is_running = False
        
    async def start(self):
        """Запускает обработчик очереди уведомлений"""
        self._is_running = True
        asyncio.create_task(self._process_queue())
        
    async def stop(self):
        """Останавливает обработчик"""
        self._is_running = False
        
    async def send_notification(self, user_id: int, title: str, message: str, notification_type: str = "SYSTEM", data: Optional[Dict] = None) -> bool:
        """Отправляет уведомление пользователю."""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()

        if not user:
            return False

        try:
            #  настройки уведомлений
            settings = session.query(NotificationSettings).filter_by(user_id=user.id).first()
            if not settings:
                #  настройки по умолчанию (  )
                settings = NotificationSettings(user_id=user.id, settings=json.dumps({
                    notification_type: {'enabled': True, 'channels': ['telegram']}  #  Telegram
                }))
                session.add(settings)
                session.commit()

            if not settings.is_enabled(notification_type):
                return True  #  

            channels = settings.get_channels(notification_type)

            #  уведомление
            formatted_message = self._format_notification(
                {'type': notification_type, 'message': message, 'data': data or {}}
            )
            keyboard = self._get_action_keyboard(
                {'type': notification_type, 'message': message, 'data': data or {}}
            )

            if 'telegram' in channels:
                try:
                    await self.bot.send_message(user.telegram_id, formatted_message, reply_markup=keyboard)
                except Exception as e:
                    print(f"Error sending Telegram notification: {e}")
                    #  другие каналы,  Telegram

            if 'email' in channels:
                #  email (  )
                pass

            return True

        except Exception as e:
            print(f"Error sending notification: {e}")
            return False
        finally:
            session.close()

    async def notify(self, user_id: int, notification_type: str, message: str, data: Optional[Dict] = None):
        """Публичный метод для отправки уведомлений."""
        #  send_notification,    
        await self.send_notification(user_id, "", message, notification_type, data)

    async def send_price_alerts(self):
        """Проверяет и отправляет ценовые алерты."""
        session = self.db.get_session()
        alerts = session.query(PriceAlert).filter_by(is_triggered=False).all()

        for alert in alerts:
            current_price = await self.get_current_price(alert.token.symbol)

            if (alert.condition == "ABOVE" and current_price >= alert.price) or \
               (alert.condition == "BELOW" and current_price <= alert.price):

                await self.send_notification(
                    alert.user.telegram_id,
                    "🔔 Ценовой алерт",
                    f"Цена {alert.token.symbol} {'достигла' if alert.condition == 'ABOVE' else 'упала до'} "
                    f"${current_price:.2f}",
                    "PRICE_ALERT"
                )

                alert.is_triggered = True

        session.commit()

    async def get_current_price(self, symbol: str) -> Optional[float]:
        """Получает текущую цену токена (заглушка)."""
        #  реальную логику получения цены (  API,  )
        return 10.0

    def _format_notification(self, notification: Dict) -> str:
        """Форматирует уведомление."""
        type_icons = {
            NotificationType.PRICE_ALERT: "🔔",
            NotificationType.ORDER_UPDATE: "🔄",
            NotificationType.P2P_UPDATE: "🤝",
            NotificationType.WALLET_TRANSFER: "💰",
            NotificationType.SWAP_STATUS: "🔄",
            NotificationType.SECURITY_ALERT: "🔒",
            NotificationType.SYSTEM_UPDATE: "⚙️",
            NotificationType.PREMIUM_STATUS: "⭐️"
        }

        icon = type_icons.get(notification['type'], "ℹ️")
        return f"{icon} {notification['message']}"

    def _get_action_keyboard(self, notification: Dict):
        """Создает клавиатуру с действиями"""
        if not notification.get('data', {}).get('actions'):
            return None

        keyboard = types.InlineKeyboardMarkup()

        for action in notification['data']['actions']:
            keyboard.add(types.InlineKeyboardButton(
                action['text'],
                callback_data=action['callback']
            ))

        return keyboard
        
    async def _process_queue(self):
        """Обрабатывает очередь уведомлений"""
        while self._is_running:
            try:
                notification = await self._notification_queue.get()
                
                # Отправляем по всем выбранным каналам
                for channel in notification['channels']:
                    if channel == 'telegram':
                        await self._send_telegram(notification)
                    elif channel == 'email':
                        await self._send_email(notification)
                        
                self._notification_queue.task_done()
                
            except Exception as e:
                print(f"Error processing notification: {e}")
                await asyncio.sleep(1)
                
    async def _send_telegram(self, notification: Dict):
        """Отправляет уведомление в Telegram"""
        try:
            # Форматируем сообщение в зависимости от типа
            message = self._format_message(notification)
            
            # Добавляем кнопки действий если есть
            keyboard = self._get_action_keyboard(notification)
            
            await self.bot.send_message(
                notification['user_id'],
                message,
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"Error sending Telegram notification: {e}")
            
    async def _send_email(self, notification: Dict):
        """Отправляет уведомление на email"""
        # TODO: Реализовать отправку email
        pass
        
    def _format_message(self, notification: Dict) -> str:
        """Форматирует сообщение уведомления"""
        type_icons = {
            NotificationType.PRICE_ALERT: "📈",
            NotificationType.ORDER_UPDATE: "📊",
            NotificationType.P2P_UPDATE: "👥",
            NotificationType.WALLET_TRANSFER: "💳",
            NotificationType.SWAP_STATUS: "🔄",
            NotificationType.SECURITY_ALERT: "🔒",
            NotificationType.SYSTEM_UPDATE: "⚙️",
            NotificationType.PREMIUM_STATUS: "⭐️"
        }
        
        icon = type_icons.get(notification['type'], "ℹ️")
        return f"{icon} {notification['message']}"
        
    def _get_action_keyboard(self, notification: Dict):
        """Создает клавиатуру с действиями"""
        if not notification.get('data', {}).get('actions'):
            return None
            
        keyboard = types.InlineKeyboardMarkup()
        
        for action in notification['data']['actions']:
            keyboard.add(types.InlineKeyboardButton(
                action['text'],
                callback_data=action['callback']
            ))
            
        return keyboard 
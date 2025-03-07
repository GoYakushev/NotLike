from aiogram import Bot, types
from core.database.models import User, NotificationSettings, Notification
from core.database.database import Database
from typing import Optional, List, Dict
import asyncio
import json
from datetime import datetime
from enum import Enum
import logging
from services.telegram.telegram_service import TelegramService

class NotificationType(Enum):
    TRADE = "trade"
    PRICE_ALERT = "price_alert"
    SYSTEM = "system"
    SECURITY = "security"
    WALLET = "wallet"

class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self, telegram_service: TelegramService):
        self.telegram_service = telegram_service
        self.db = Database()
        self._notification_queue = asyncio.Queue()
        self._is_running = False
        self._price_alerts = {}  # user_id -> List[alert_config]
        self._notification_history = {}  # user_id -> List[notification]
        
    async def start(self):
        """Запускает обработчик очереди уведомлений"""
        self._is_running = True
        asyncio.create_task(self._process_queue())
        
    async def stop(self):
        """Останавливает обработчик"""
        self._is_running = False
        
    async def send_notification(
        self,
        user_id: int,
        message: str,
        notification_type: str = 'info',
        data: Optional[Dict] = None,
        is_important: bool = False
    ) -> Dict:
        """Отправляет уведомление пользователю."""
        try:
            # Проверяем настройки уведомлений пользователя
            settings = await NotificationSettings.get(user_id=user_id)
            if not settings:
                settings = NotificationSettings(
                    user_id=user_id,
                    enabled=True,
                    trade_notifications=True,
                    price_alerts=True,
                    security_alerts=True,
                    news_updates=True,
                    sound_enabled=True,
                    quiet_hours_start=23,
                    quiet_hours_end=7
                )
                await settings.save()

            # Проверяем, включены ли уведомления
            if not settings.enabled and not is_important:
                return {
                    'success': False,
                    'error': 'Уведомления отключены пользователем'
                }

            # Проверяем тихие часы
            current_hour = datetime.utcnow().hour
            is_quiet_time = (
                current_hour >= settings.quiet_hours_start or
                current_hour < settings.quiet_hours_end
            )
            if is_quiet_time and not is_important:
                return {
                    'success': False,
                    'error': 'Тихие часы'
                }

            # Создаем запись о уведомлении
            notification = Notification(
                user_id=user_id,
                type=notification_type,
                message=message,
                data=data,
                is_important=is_important,
                created_at=datetime.utcnow(),
                is_read=False
            )
            await notification.save()

            # Отправляем уведомление через Telegram
            await self.telegram_service.send_message(
                chat_id=user_id,
                text=message,
                disable_notification=is_quiet_time and not is_important
            )

            return {
                'success': True,
                'notification_id': notification.id
            }

        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def send_trade_notification(
        self,
        user_id: int,
        trade_type: str,
        amount: float,
        token_symbol: str,
        price: float,
        tx_hash: str
    ) -> bool:
        """Отправляет уведомление о сделке."""
        data = {
            "trade_type": trade_type,
            "amount": amount,
            "token_symbol": token_symbol,
            "price": price,
            "tx_hash": tx_hash,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        message = (
            f"{'🟢 Покупка' if trade_type == 'buy' else '🔴 Продажа'}\n\n"
            f"Количество: {amount} {token_symbol}\n"
            f"Цена: ${price:.4f}\n"
            f"Хэш: {tx_hash[:8]}...{tx_hash[-8:]}"
        )
        
        return await self.send_notification(
            user_id,
            message,
            NotificationType.TRADE.value,
            NotificationPriority.HIGH.value,
            data
        )

    async def send_price_alert(
        self,
        user_id: int,
        token_symbol: str,
        current_price: float,
        target_price: float,
        condition: str
    ) -> bool:
        """Отправляет уведомление о достижении целевой цены."""
        data = {
            "token_symbol": token_symbol,
            "current_price": current_price,
            "target_price": target_price,
            "condition": condition,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        message = (
            f"⚠️ Ценовой алерт - {token_symbol}\n\n"
            f"Текущая цена: ${current_price:.4f}\n"
            f"Целевая цена: ${target_price:.4f}\n"
            f"Условие: {'выше' if condition == 'above' else 'ниже'}"
        )
        
        return await self.send_notification(
            user_id,
            message,
            NotificationType.PRICE_ALERT.value,
            NotificationPriority.HIGH.value,
            data
        )

    async def send_security_alert(
        self,
        user_id: int,
        alert_type: str,
        details: str,
        recommendation: Optional[str] = None
    ) -> bool:
        """Отправляет уведомление безопасности."""
        data = {
            "alert_type": alert_type,
            "details": details,
            "recommendation": recommendation,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        message = (
            f"🚨 Предупреждение безопасности\n\n"
            f"Тип: {alert_type}\n"
            f"Детали: {details}\n"
            f"{f'Рекомендация: {recommendation}' if recommendation else ''}"
        )
        
        return await self.send_notification(
            user_id,
            message,
            NotificationType.SECURITY.value,
            NotificationPriority.CRITICAL.value,
            data
        )

    async def send_wallet_notification(
        self,
        user_id: int,
        operation_type: str,
        amount: float,
        token_symbol: str,
        status: str,
        tx_hash: Optional[str] = None
    ) -> bool:
        """Отправляет уведомление о операциях с кошельком."""
        data = {
            "operation_type": operation_type,
            "amount": amount,
            "token_symbol": token_symbol,
            "status": status,
            "tx_hash": tx_hash,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        message = (
            f"💼 Операция с кошельком\n\n"
            f"Тип: {operation_type}\n"
            f"Количество: {amount} {token_symbol}\n"
            f"Статус: {status}\n"
            f"{f'Хэш: {tx_hash[:8]}...{tx_hash[-8:]}' if tx_hash else ''}"
        )
        
        return await self.send_notification(
            user_id,
            message,
            NotificationType.WALLET.value,
            NotificationPriority.HIGH.value,
            data
        )

    async def set_price_alert(
        self,
        user_id: int,
        token_symbol: str,
        target_price: float,
        condition: str
    ) -> bool:
        """Устанавливает оповещение о цене."""
        try:
            if user_id not in self._price_alerts:
                self._price_alerts[user_id] = []
                
            alert_config = {
                "token_symbol": token_symbol,
                "target_price": target_price,
                "condition": condition,
                "created_at": datetime.utcnow().isoformat()
            }
            
            self._price_alerts[user_id].append(alert_config)
            
            await self.send_notification(
                user_id,
                f"✅ Установлен ценовой алерт для {token_symbol}\n"
                f"Цель: ${target_price:.4f}\n"
                f"Условие: {'выше' if condition == 'above' else 'ниже'}",
                NotificationType.SYSTEM.value,
                NotificationPriority.LOW.value
            )
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при установке ценового алерта: {str(e)}")
            return False

    def get_user_alerts(self, user_id: int) -> List[Dict]:
        """Возвращает все активные алерты пользователя."""
        return self._price_alerts.get(user_id, [])

    def get_notification_history(
        self,
        user_id: int,
        notification_type: Optional[NotificationType] = None,
        limit: int = 50
    ) -> List[Dict]:
        """Возвращает историю уведомлений пользователя."""
        history = self._notification_history.get(user_id, [])
        
        if notification_type:
            history = [
                n for n in history 
                if n['type'] == notification_type.value
            ]
            
        return sorted(
            history,
            key=lambda x: x['timestamp'],
            reverse=True
        )[:limit]

    def _format_notification(
        self,
        message: str,
        notification_type: NotificationType,
        priority: NotificationPriority,
        data: Optional[Dict]
    ) -> str:
        """Форматирует уведомление в зависимости от типа и приоритета."""
        priority_icons = {
            NotificationPriority.LOW: "ℹ️",
            NotificationPriority.MEDIUM: "⚠️",
            NotificationPriority.HIGH: "❗️",
            NotificationPriority.CRITICAL: "🚨"
        }
        
        type_headers = {
            NotificationType.TRADE: "📊 Торговля",
            NotificationType.PRICE_ALERT: "💰 Ценовой алерт",
            NotificationType.SYSTEM: "🤖 Система",
            NotificationType.SECURITY: "🔒 Безопасность",
            NotificationType.WALLET: "💼 Кошелек"
        }
        
        formatted_message = (
            f"{priority_icons[priority]} {type_headers[notification_type]}\n\n"
            f"{message}\n\n"
            f"🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        
        return formatted_message

    def _save_to_history(
        self,
        user_id: int,
        notification_type: NotificationType,
        priority: NotificationPriority,
        message: str,
        data: Optional[Dict]
    ) -> None:
        """Сохраняет уведомление в историю."""
        if user_id not in self._notification_history:
            self._notification_history[user_id] = []
            
        notification = {
            "type": notification_type.value,
            "priority": priority.value,
            "message": message,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self._notification_history[user_id].append(notification)
        
        # Ограничиваем историю последними 1000 уведомлениями
        if len(self._notification_history[user_id]) > 1000:
            self._notification_history[user_id] = self._notification_history[user_id][-1000:]
        
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
            
            await self.telegram_service.send_message(
                chat_id=notification['user_id'],
                text=message,
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

    async def mark_as_read(
        self,
        notification_id: int,
        user_id: int
    ) -> Dict:
        """Отмечает уведомление как прочитанное."""
        try:
            notification = await Notification.get(id=notification_id)
            if not notification:
                return {
                    'success': False,
                    'error': 'Уведомление не найдено'
                }

            if notification.user_id != user_id:
                return {
                    'success': False,
                    'error': 'Нет доступа к этому уведомлению'
                }

            notification.is_read = True
            notification.read_at = datetime.utcnow()
            await notification.save()

            return {
                'success': True
            }

        except Exception as e:
            logger.error(f"Ошибка при отметке уведомления: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_user_notifications(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False
    ) -> List[Dict]:
        """Получает список уведомлений пользователя."""
        try:
            query = Notification.filter(user_id=user_id)
            if unread_only:
                query = query.filter(is_read=False)

            notifications = await query.order_by('-created_at').offset(offset).limit(limit).all()
            result = []

            for notification in notifications:
                result.append({
                    'id': notification.id,
                    'type': notification.type,
                    'message': notification.message,
                    'data': notification.data,
                    'is_important': notification.is_important,
                    'is_read': notification.is_read,
                    'created_at': notification.created_at.isoformat(),
                    'read_at': notification.read_at.isoformat() if notification.read_at else None
                })

            return result

        except Exception as e:
            logger.error(f"Ошибка при получении уведомлений: {str(e)}")
            return []

    async def update_notification_settings(
        self,
        user_id: int,
        settings: Dict
    ) -> Dict:
        """Обновляет настройки уведомлений пользователя."""
        try:
            user_settings = await NotificationSettings.get(user_id=user_id)
            if not user_settings:
                user_settings = NotificationSettings(user_id=user_id)

            # Обновляем настройки
            for key, value in settings.items():
                if hasattr(user_settings, key):
                    setattr(user_settings, key, value)

            await user_settings.save()

            return {
                'success': True,
                'settings': {
                    'enabled': user_settings.enabled,
                    'trade_notifications': user_settings.trade_notifications,
                    'price_alerts': user_settings.price_alerts,
                    'security_alerts': user_settings.security_alerts,
                    'news_updates': user_settings.news_updates,
                    'sound_enabled': user_settings.sound_enabled,
                    'quiet_hours_start': user_settings.quiet_hours_start,
                    'quiet_hours_end': user_settings.quiet_hours_end
                }
            }

        except Exception as e:
            logger.error(f"Ошибка при обновлении настроек уведомлений: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_notification_settings(self, user_id: int) -> Dict:
        """Получает настройки уведомлений пользователя."""
        try:
            settings = await NotificationSettings.get(user_id=user_id)
            if not settings:
                return {
                    'success': True,
                    'settings': {
                        'enabled': True,
                        'trade_notifications': True,
                        'price_alerts': True,
                        'security_alerts': True,
                        'news_updates': True,
                        'sound_enabled': True,
                        'quiet_hours_start': 23,
                        'quiet_hours_end': 7
                    }
                }

            return {
                'success': True,
                'settings': {
                    'enabled': settings.enabled,
                    'trade_notifications': settings.trade_notifications,
                    'price_alerts': settings.price_alerts,
                    'security_alerts': settings.security_alerts,
                    'news_updates': settings.news_updates,
                    'sound_enabled': settings.sound_enabled,
                    'quiet_hours_start': settings.quiet_hours_start,
                    'quiet_hours_end': settings.quiet_hours_end
                }
            }

        except Exception as e:
            logger.error(f"Ошибка при получении настроек уведомлений: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def delete_notification(
        self,
        notification_id: int,
        user_id: int
    ) -> Dict:
        """Удаляет уведомление."""
        try:
            notification = await Notification.get(id=notification_id)
            if not notification:
                return {
                    'success': False,
                    'error': 'Уведомление не найдено'
                }

            if notification.user_id != user_id:
                return {
                    'success': False,
                    'error': 'Нет доступа к этому уведомлению'
                }

            await notification.delete()

            return {
                'success': True
            }

        except Exception as e:
            logger.error(f"Ошибка при удалении уведомления: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def clear_notifications(
        self,
        user_id: int,
        older_than: Optional[datetime] = None
    ) -> Dict:
        """Очищает уведомления пользователя."""
        try:
            query = Notification.filter(user_id=user_id)
            if older_than:
                query = query.filter(created_at__lt=older_than)

            await query.delete()

            return {
                'success': True
            }

        except Exception as e:
            logger.error(f"Ошибка при очистке уведомлений: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def send_broadcast(
        self,
        message: str,
        user_ids: Optional[List[int]] = None,
        notification_type: str = 'broadcast',
        data: Optional[Dict] = None,
        is_important: bool = False
    ) -> Dict:
        """Отправляет массовое уведомление."""
        try:
            if user_ids is None:
                # Получаем всех пользователей
                users = await User.all()
                user_ids = [user.id for user in users]

            success_count = 0
            failed_count = 0

            for user_id in user_ids:
                result = await self.send_notification(
                    user_id=user_id,
                    message=message,
                    notification_type=notification_type,
                    data=data,
                    is_important=is_important
                )
                if result['success']:
                    success_count += 1
                else:
                    failed_count += 1

            return {
                'success': True,
                'total': len(user_ids),
                'success_count': success_count,
                'failed_count': failed_count
            }

        except Exception as e:
            logger.error(f"Ошибка при отправке массового уведомления: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_unread_count(self, user_id: int) -> Dict:
        """Получает количество непрочитанных уведомлений."""
        try:
            count = await Notification.filter(
                user_id=user_id,
                is_read=False
            ).count()

            return {
                'success': True,
                'count': count
            }

        except Exception as e:
            logger.error(f"Ошибка при получении количества непрочитанных уведомлений: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            } 
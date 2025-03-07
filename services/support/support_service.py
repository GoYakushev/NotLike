from typing import Dict, List, Optional
import logging
from datetime import datetime, timedelta
import json
import aiohttp
from core.database.database import Database
from core.database.models import User, SupportTicket, TicketMessage
from services.notifications.notification_service import NotificationService
from services.ai.ai_service import AIService

class TicketStatus:
    NEW = "new"
    IN_PROGRESS = "in_progress"
    WAITING_USER = "waiting_user"
    WAITING_ADMIN = "waiting_admin"
    RESOLVED = "resolved"
    CLOSED = "closed"

class TicketPriority:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class TicketCategory:
    GENERAL = "general"
    TECHNICAL = "technical"
    FINANCIAL = "financial"
    SECURITY = "security"
    FEATURE_REQUEST = "feature_request"

class SupportService:
    def __init__(
        self,
        db: Database,
        notification_service: NotificationService,
        ai_service: AIService
    ):
        self.logger = logging.getLogger(__name__)
        self.db = db
        self.notification_service = notification_service
        self.ai_service = ai_service
        self.auto_response_enabled = True
        self.auto_close_days = 7

    async def create_ticket(
        self,
        user_id: int,
        subject: str,
        message: str,
        category: str = TicketCategory.GENERAL,
        priority: str = TicketPriority.MEDIUM
    ) -> Dict:
        """Создает новый тикет поддержки."""
        try:
            session = self.db.get_session()
            try:
                # Создаем тикет
                ticket = SupportTicket(
                    user_id=user_id,
                    subject=subject,
                    category=category,
                    priority=priority,
                    status=TicketStatus.NEW,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                session.add(ticket)
                session.flush()

                # Добавляем первое сообщение
                ticket_message = TicketMessage(
                    ticket_id=ticket.id,
                    user_id=user_id,
                    message=message,
                    is_from_user=True,
                    created_at=datetime.utcnow()
                )
                session.add(ticket_message)
                session.commit()

                # Отправляем уведомление администраторам
                await self._notify_admins_new_ticket(ticket)

                # Пытаемся автоматически ответить
                if self.auto_response_enabled:
                    auto_response = await self._generate_auto_response(
                        ticket.id,
                        message,
                        category
                    )
                    if auto_response:
                        await self.add_message(
                            ticket.id,
                            None,  # system message
                            auto_response,
                            is_auto_response=True
                        )

                return {
                    'ticket_id': ticket.id,
                    'status': ticket.status,
                    'created_at': ticket.created_at.isoformat()
                }

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при создании тикета: {str(e)}")
            raise

    async def get_ticket(self, ticket_id: int) -> Dict:
        """Получает информацию о тикете."""
        try:
            session = self.db.get_session()
            try:
                ticket = session.query(SupportTicket).filter_by(
                    id=ticket_id
                ).first()

                if not ticket:
                    raise ValueError(f"Тикет {ticket_id} не найден")

                messages = session.query(TicketMessage).filter_by(
                    ticket_id=ticket_id
                ).order_by(TicketMessage.created_at.asc()).all()

                return {
                    'id': ticket.id,
                    'user_id': ticket.user_id,
                    'subject': ticket.subject,
                    'category': ticket.category,
                    'priority': ticket.priority,
                    'status': ticket.status,
                    'created_at': ticket.created_at.isoformat(),
                    'updated_at': ticket.updated_at.isoformat(),
                    'messages': [{
                        'id': msg.id,
                        'user_id': msg.user_id,
                        'message': msg.message,
                        'is_from_user': msg.is_from_user,
                        'is_auto_response': msg.is_auto_response,
                        'created_at': msg.created_at.isoformat()
                    } for msg in messages]
                }

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при получении тикета: {str(e)}")
            raise

    async def get_user_tickets(
        self,
        user_id: int,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """Получает список тикетов пользователя."""
        try:
            session = self.db.get_session()
            try:
                query = session.query(SupportTicket).filter_by(user_id=user_id)
                
                if status:
                    query = query.filter_by(status=status)

                tickets = query.order_by(
                    SupportTicket.created_at.desc()
                ).limit(limit).all()

                return [{
                    'id': ticket.id,
                    'subject': ticket.subject,
                    'category': ticket.category,
                    'priority': ticket.priority,
                    'status': ticket.status,
                    'created_at': ticket.created_at.isoformat(),
                    'updated_at': ticket.updated_at.isoformat(),
                    'last_message': await self._get_last_message(session, ticket.id)
                } for ticket in tickets]

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при получении тикетов пользователя: {str(e)}")
            raise

    async def add_message(
        self,
        ticket_id: int,
        user_id: Optional[int],
        message: str,
        is_auto_response: bool = False
    ) -> Dict:
        """Добавляет сообщение в тикет."""
        try:
            session = self.db.get_session()
            try:
                ticket = session.query(SupportTicket).filter_by(
                    id=ticket_id
                ).first()

                if not ticket:
                    raise ValueError(f"Тикет {ticket_id} не найден")

                # Добавляем сообщение
                ticket_message = TicketMessage(
                    ticket_id=ticket_id,
                    user_id=user_id,
                    message=message,
                    is_from_user=bool(user_id == ticket.user_id),
                    is_auto_response=is_auto_response,
                    created_at=datetime.utcnow()
                )
                session.add(ticket_message)

                # Обновляем статус тикета
                if user_id == ticket.user_id:
                    ticket.status = TicketStatus.WAITING_ADMIN
                elif user_id:  # admin response
                    ticket.status = TicketStatus.WAITING_USER
                ticket.updated_at = datetime.utcnow()

                session.commit()

                # Отправляем уведомление
                if user_id == ticket.user_id:
                    await self._notify_admins_new_message(ticket, message)
                else:
                    await self._notify_user_new_message(ticket, message)

                return {
                    'message_id': ticket_message.id,
                    'ticket_id': ticket_id,
                    'user_id': user_id,
                    'message': message,
                    'created_at': ticket_message.created_at.isoformat()
                }

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при добавлении сообщения: {str(e)}")
            raise

    async def update_ticket_status(
        self,
        ticket_id: int,
        status: str,
        admin_id: Optional[int] = None
    ) -> Dict:
        """Обновляет статус тикета."""
        try:
            session = self.db.get_session()
            try:
                ticket = session.query(SupportTicket).filter_by(
                    id=ticket_id
                ).first()

                if not ticket:
                    raise ValueError(f"Тикет {ticket_id} не найден")

                old_status = ticket.status
                ticket.status = status
                ticket.updated_at = datetime.utcnow()

                if admin_id:
                    ticket_message = TicketMessage(
                        ticket_id=ticket_id,
                        user_id=admin_id,
                        message=f"Статус тикета изменен с {old_status} на {status}",
                        is_from_user=False,
                        created_at=datetime.utcnow()
                    )
                    session.add(ticket_message)

                session.commit()

                # Отправляем уведомление пользователю
                await self._notify_user_status_change(ticket, old_status, status)

                return {
                    'ticket_id': ticket_id,
                    'status': status,
                    'updated_at': ticket.updated_at.isoformat()
                }

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при обновлении статуса тикета: {str(e)}")
            raise

    async def close_ticket(
        self,
        ticket_id: int,
        user_id: int,
        reason: Optional[str] = None
    ) -> Dict:
        """Закрывает тикет."""
        try:
            session = self.db.get_session()
            try:
                ticket = session.query(SupportTicket).filter_by(
                    id=ticket_id
                ).first()

                if not ticket:
                    raise ValueError(f"Тикет {ticket_id} не найден")

                ticket.status = TicketStatus.CLOSED
                ticket.updated_at = datetime.utcnow()

                close_message = (
                    f"Тикет закрыт пользователем {user_id}.\n"
                    f"Причина: {reason if reason else 'Не указана'}"
                )

                ticket_message = TicketMessage(
                    ticket_id=ticket_id,
                    user_id=user_id,
                    message=close_message,
                    is_from_user=user_id == ticket.user_id,
                    created_at=datetime.utcnow()
                )
                session.add(ticket_message)
                session.commit()

                # Отправляем уведомления
                if user_id == ticket.user_id:
                    await self._notify_admins_ticket_closed(ticket, reason)
                else:
                    await self._notify_user_ticket_closed(ticket, reason)

                return {
                    'ticket_id': ticket_id,
                    'status': TicketStatus.CLOSED,
                    'closed_by': user_id,
                    'reason': reason,
                    'closed_at': ticket.updated_at.isoformat()
                }

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при закрытии тикета: {str(e)}")
            raise

    async def get_ticket_statistics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """Получает статистику тикетов."""
        try:
            session = self.db.get_session()
            try:
                query = session.query(SupportTicket)

                if start_date:
                    query = query.filter(SupportTicket.created_at >= start_date)
                if end_date:
                    query = query.filter(SupportTicket.created_at <= end_date)

                tickets = query.all()

                stats = {
                    'total_tickets': len(tickets),
                    'status_distribution': {},
                    'category_distribution': {},
                    'priority_distribution': {},
                    'average_response_time': timedelta(0),
                    'average_resolution_time': timedelta(0)
                }

                for ticket in tickets:
                    # Считаем распределение по статусам
                    if ticket.status not in stats['status_distribution']:
                        stats['status_distribution'][ticket.status] = 0
                    stats['status_distribution'][ticket.status] += 1

                    # Считаем распределение по категориям
                    if ticket.category not in stats['category_distribution']:
                        stats['category_distribution'][ticket.category] = 0
                    stats['category_distribution'][ticket.category] += 1

                    # Считаем распределение по приоритетам
                    if ticket.priority not in stats['priority_distribution']:
                        stats['priority_distribution'][ticket.priority] = 0
                    stats['priority_distribution'][ticket.priority] += 1

                    # Считаем время ответа и решения
                    messages = session.query(TicketMessage).filter_by(
                        ticket_id=ticket.id
                    ).order_by(TicketMessage.created_at.asc()).all()

                    if len(messages) > 1:
                        first_response = next(
                            (msg for msg in messages[1:]
                             if not msg.is_from_user and not msg.is_auto_response),
                            None
                        )
                        if first_response:
                            response_time = (
                                first_response.created_at - ticket.created_at
                            )
                            stats['average_response_time'] += response_time

                    if ticket.status == TicketStatus.RESOLVED:
                        resolution_time = ticket.updated_at - ticket.created_at
                        stats['average_resolution_time'] += resolution_time

                # Вычисляем средние значения
                if stats['total_tickets'] > 0:
                    stats['average_response_time'] /= stats['total_tickets']
                    stats['average_resolution_time'] /= stats['total_tickets']

                # Конвертируем timedelta в секунды для JSON
                stats['average_response_time'] = stats['average_response_time'].total_seconds()
                stats['average_resolution_time'] = stats['average_resolution_time'].total_seconds()

                return stats

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при получении статистики: {str(e)}")
            raise

    async def _get_last_message(
        self,
        session,
        ticket_id: int
    ) -> Optional[Dict]:
        """Получает последнее сообщение тикета."""
        try:
            message = session.query(TicketMessage).filter_by(
                ticket_id=ticket_id
            ).order_by(TicketMessage.created_at.desc()).first()

            if message:
                return {
                    'id': message.id,
                    'user_id': message.user_id,
                    'message': message.message,
                    'is_from_user': message.is_from_user,
                    'created_at': message.created_at.isoformat()
                }
            return None

        except Exception as e:
            self.logger.error(f"Ошибка при получении последнего сообщения: {str(e)}")
            return None

    async def _generate_auto_response(
        self,
        ticket_id: int,
        message: str,
        category: str
    ) -> Optional[str]:
        """Генерирует автоматический ответ с помощью AI."""
        try:
            prompt = self._create_auto_response_prompt(message, category)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ai_service.base_url}/chat/completions",
                    headers=self.ai_service.headers,
                    json={
                        "model": self.ai_service.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a helpful support assistant."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ]
                    }
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['choices'][0]['message']['content']
                    else:
                        self.logger.error(
                            f"Ошибка API при генерации автоответа: {response.status}"
                        )
                        return None

        except Exception as e:
            self.logger.error(f"Ошибка при генерации автоответа: {str(e)}")
            return None

    def _create_auto_response_prompt(self, message: str, category: str) -> str:
        """Создает промпт для генерации автоответа."""
        return f"""
Please analyze the following support ticket and generate a helpful response:

Category: {category}
User Message: {message}

Requirements for the response:
1. Be polite and professional
2. Address the user's concern directly
3. Provide specific and actionable information
4. Keep the response concise but informative
5. Include a clear next step or resolution path

Please generate an appropriate response:
"""

    async def _notify_admins_new_ticket(self, ticket: SupportTicket) -> None:
        """Уведомляет администраторов о новом тикете."""
        try:
            message = (
                f"📝 Новый тикет #{ticket.id}\n"
                f"Тема: {ticket.subject}\n"
                f"Категория: {ticket.category}\n"
                f"Приоритет: {ticket.priority}"
            )
            
            # В реальном приложении здесь должна быть
            # логика получения списка администраторов
            admin_ids = [1]  # Пример
            
            for admin_id in admin_ids:
                await self.notification_service.send_notification(
                    admin_id,
                    message,
                    "support_ticket",
                    "high" if ticket.priority == TicketPriority.URGENT else "medium"
                )

        except Exception as e:
            self.logger.error(f"Ошибка при уведомлении администраторов: {str(e)}")

    async def _notify_admins_new_message(
        self,
        ticket: SupportTicket,
        message: str
    ) -> None:
        """Уведомляет администраторов о новом сообщении."""
        try:
            notification = (
                f"💬 Новое сообщение в тикете #{ticket.id}\n"
                f"Тема: {ticket.subject}\n"
                f"Сообщение: {message[:100]}..."
            )
            
            admin_ids = [1]  # Пример
            
            for admin_id in admin_ids:
                await self.notification_service.send_notification(
                    admin_id,
                    notification,
                    "support_message",
                    "medium"
                )

        except Exception as e:
            self.logger.error(
                f"Ошибка при уведомлении администраторов о сообщении: {str(e)}"
            )

    async def _notify_user_new_message(
        self,
        ticket: SupportTicket,
        message: str
    ) -> None:
        """Уведомляет пользователя о новом сообщении."""
        try:
            notification = (
                f"💬 Новый ответ в тикете #{ticket.id}\n"
                f"Тема: {ticket.subject}\n"
                f"Сообщение: {message[:100]}..."
            )
            
            await self.notification_service.send_notification(
                ticket.user_id,
                notification,
                "support_message",
                "medium"
            )

        except Exception as e:
            self.logger.error(
                f"Ошибка при уведомлении пользователя о сообщении: {str(e)}"
            )

    async def _notify_user_status_change(
        self,
        ticket: SupportTicket,
        old_status: str,
        new_status: str
    ) -> None:
        """Уведомляет пользователя об изменении статуса тикета."""
        try:
            notification = (
                f"📋 Статус тикета #{ticket.id} изменен\n"
                f"Тема: {ticket.subject}\n"
                f"Старый статус: {old_status}\n"
                f"Новый статус: {new_status}"
            )
            
            await self.notification_service.send_notification(
                ticket.user_id,
                notification,
                "support_status",
                "medium"
            )

        except Exception as e:
            self.logger.error(
                f"Ошибка при уведомлении об изменении статуса: {str(e)}"
            )

    async def _notify_admins_ticket_closed(
        self,
        ticket: SupportTicket,
        reason: Optional[str]
    ) -> None:
        """Уведомляет администраторов о закрытии тикета."""
        try:
            notification = (
                f"🔒 Тикет #{ticket.id} закрыт пользователем\n"
                f"Тема: {ticket.subject}\n"
                f"Причина: {reason if reason else 'Не указана'}"
            )
            
            admin_ids = [1]  # Пример
            
            for admin_id in admin_ids:
                await self.notification_service.send_notification(
                    admin_id,
                    notification,
                    "support_closed",
                    "low"
                )

        except Exception as e:
            self.logger.error(
                f"Ошибка при уведомлении администраторов о закрытии: {str(e)}"
            )

    async def _notify_user_ticket_closed(
        self,
        ticket: SupportTicket,
        reason: Optional[str]
    ) -> None:
        """Уведомляет пользователя о закрытии тикета."""
        try:
            notification = (
                f"🔒 Ваш тикет #{ticket.id} закрыт\n"
                f"Тема: {ticket.subject}\n"
                f"Причина: {reason if reason else 'Не указана'}"
            )
            
            await self.notification_service.send_notification(
                ticket.user_id,
                notification,
                "support_closed",
                "medium"
            )

        except Exception as e:
            self.logger.error(
                f"Ошибка при уведомлении пользователя о закрытии: {str(e)}"
            ) 
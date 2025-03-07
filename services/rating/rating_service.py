from core.database.models import User, Review, Transaction, Rating, RatingHistory, P2PDeal, UserRating, VerificationRequest
from core.database.database import Database
from typing import Optional, List, Dict, Tuple
import logging
from datetime import datetime, timedelta
from decimal import Decimal
import json

logger = logging.getLogger(__name__)

class RatingService:
    def __init__(self, db: Database):
        self.logger = logging.getLogger(__name__)
        self.db = db
        self.rating_weights = {
            'trade_volume': 0.4,      # 40% - объем торгов
            'success_rate': 0.3,      # 30% - успешность сделок
            'activity': 0.2,          # 20% - активность
            'reputation': 0.1         # 10% - репутация
        }
        self.activity_points = {
            'trade': 10,              # Очки за торговлю
            'p2p_deal': 15,          # Очки за P2P сделку
            'referral': 5,           # Очки за реферала
            'deposit': 3,            # Очки за депозит
            'withdrawal': 2          # Очки за вывод
        }

    async def get_user_rating(self, user_id: int) -> float:
        """Получает рейтинг пользователя."""
        try:
            rating = await UserRating.get(user_id=user_id)
            if not rating:
                return 0.0
            return float(rating.rating)
        except Exception as e:
            logger.error(f"Ошибка при получении рейтинга: {str(e)}")
            return 0.0

    async def add_review(self, reviewer_id: int, reviewee_id: int, order_id: Optional[int], rating: int, comment: Optional[str]) -> Dict:
        """Добавляет отзыв."""
        if not 1 <= rating <= 5:
            return {'success': False, 'error': 'Рейтинг должен быть от 1 до 5'}

        session = self.db.get_session()
        try:
            reviewer = session.query(User).filter(User.telegram_id == reviewer_id).first()
            reviewee = session.query(User).filter(User.telegram_id == reviewee_id).first()

            if not reviewer or not reviewee:
                return {'success': False, 'error': 'Пользователь не найден'}

            review = Review(
                reviewer_id=reviewer.id,
                reviewee_id=reviewee.id,
                order_id=order_id,
                rating=rating,
                comment=comment
            )
            session.add(review)
            session.commit()
            await self.update_user_rating(reviewee.telegram_id)  #  рейтинг
            return {'success': True}
        except Exception as e:
            session.rollback()
            return {'success': False, 'error': str(e)}
        finally:
            session.close()

    async def update_user_rating(
        self,
        user_id: int,
        deal_id: int,
        is_successful: bool
    ) -> Dict:
        """Обновляет рейтинг пользователя после сделки."""
        try:
            # Получаем текущий рейтинг
            rating = await UserRating.get(user_id=user_id)
            if not rating:
                rating = UserRating(
                    user_id=user_id,
                    rating=Decimal('5.0'),
                    total_deals=0,
                    successful_deals=0,
                    total_volume=Decimal('0'),
                    last_updated=datetime.utcnow()
                )

            # Получаем информацию о сделке
            deal = await P2PDeal.get(id=deal_id)
            if not deal:
                raise ValueError("Сделка не найдена")

            # Обновляем статистику
            rating.total_deals += 1
            if is_successful:
                rating.successful_deals += 1
                rating.total_volume += deal.amount * deal.price

            # Рассчитываем новый рейтинг
            success_rate = rating.successful_deals / rating.total_deals
            volume_weight = min(rating.total_volume / 1000, 1)  # Максимальный вес по объему - 1
            time_weight = min((datetime.utcnow() - rating.last_updated).days / 30, 1)  # Вес по времени

            new_rating = (
                5.0 * success_rate +  # Базовый рейтинг на основе успешности
                0.5 * volume_weight +  # Бонус за объем
                0.5 * time_weight  # Бонус за активность
            )

            # Ограничиваем рейтинг диапазоном 0-5
            rating.rating = Decimal(str(max(0.0, min(5.0, new_rating))))
            rating.last_updated = datetime.utcnow()
            await rating.save()

            return {
                'success': True,
                'new_rating': float(rating.rating),
                'total_deals': rating.total_deals,
                'successful_deals': rating.successful_deals
            }

        except Exception as e:
            logger.error(f"Ошибка при обновлении рейтинга: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def is_user_verified(self, user_id: int) -> bool:
        """Проверяет, верифицирован ли пользователь."""
        try:
            user = await User.get(id=user_id)
            if not user:
                return False
            return user.is_verified
        except Exception as e:
            logger.error(f"Ошибка при проверке верификации: {str(e)}")
            return False

    async def request_verification(
        self,
        user_id: int,
        document_type: str,
        document_data: Dict
    ) -> Dict:
        """Создает запрос на верификацию пользователя."""
        try:
            # Проверяем, нет ли уже активного запроса
            existing_request = await VerificationRequest.filter(
                user_id=user_id,
                status='pending'
            ).first()
            if existing_request:
                return {
                    'success': False,
                    'error': 'У вас уже есть активный запрос на верификацию'
                }

            # Создаем новый запрос
            request = VerificationRequest(
                user_id=user_id,
                document_type=document_type,
                document_data=document_data,
                status='pending',
                created_at=datetime.utcnow()
            )
            await request.save()

            return {
                'success': True,
                'request_id': request.id,
                'status': request.status
            }

        except Exception as e:
            logger.error(f"Ошибка при создании запроса на верификацию: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def process_verification(
        self,
        request_id: int,
        admin_id: int,
        is_approved: bool,
        comment: Optional[str] = None
    ) -> Dict:
        """Обрабатывает запрос на верификацию."""
        try:
            request = await VerificationRequest.get(id=request_id)
            if not request:
                return {
                    'success': False,
                    'error': 'Запрос не найден'
                }

            if request.status != 'pending':
                return {
                    'success': False,
                    'error': 'Запрос уже обработан'
                }

            # Обновляем статус запроса
            request.status = 'approved' if is_approved else 'rejected'
            request.processed_by = admin_id
            request.processed_at = datetime.utcnow()
            request.comment = comment
            await request.save()

            if is_approved:
                # Обновляем статус верификации пользователя
                user = await User.get(id=request.user_id)
                user.is_verified = True
                user.verified_at = datetime.utcnow()
                await user.save()

            return {
                'success': True,
                'status': request.status,
                'processed_at': request.processed_at.isoformat()
            }

        except Exception as e:
            logger.error(f"Ошибка при обработке запроса на верификацию: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_user_verification_status(self, user_id: int) -> Dict:
        """Получает статус верификации пользователя."""
        try:
            user = await User.get(id=user_id)
            if not user:
                return {
                    'success': False,
                    'error': 'Пользователь не найден'
                }

            # Получаем последний запрос на верификацию
            last_request = await VerificationRequest.filter(
                user_id=user_id
            ).order_by('-created_at').first()

            return {
                'success': True,
                'is_verified': user.is_verified,
                'verified_at': user.verified_at.isoformat() if user.verified_at else None,
                'last_request': {
                    'id': last_request.id,
                    'status': last_request.status,
                    'created_at': last_request.created_at.isoformat(),
                    'processed_at': last_request.processed_at.isoformat() if last_request.processed_at else None,
                    'comment': last_request.comment
                } if last_request else None
            }

        except Exception as e:
            logger.error(f"Ошибка при получении статуса верификации: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_user_stats(self, user_id: int) -> Dict:
        """Получает статистику пользователя."""
        try:
            rating = await UserRating.get(user_id=user_id)
            if not rating:
                return {
                    'success': True,
                    'rating': 0.0,
                    'total_deals': 0,
                    'successful_deals': 0,
                    'total_volume': 0.0,
                    'success_rate': 0.0
                }

            return {
                'success': True,
                'rating': float(rating.rating),
                'total_deals': rating.total_deals,
                'successful_deals': rating.successful_deals,
                'total_volume': float(rating.total_volume),
                'success_rate': rating.successful_deals / rating.total_deals if rating.total_deals > 0 else 0.0
            }

        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_top_traders(
        self,
        limit: int = 10,
        min_deals: int = 5
    ) -> list:
        """Получает список топ трейдеров."""
        try:
            ratings = await UserRating.filter(
                total_deals__gte=min_deals
            ).order_by('-rating').limit(limit).all()

            result = []
            for rating in ratings:
                user = await User.get(id=rating.user_id)
                result.append({
                    'user_id': user.id,
                    'username': user.username,
                    'rating': float(rating.rating),
                    'total_deals': rating.total_deals,
                    'successful_deals': rating.successful_deals,
                    'total_volume': float(rating.total_volume),
                    'success_rate': rating.successful_deals / rating.total_deals
                })

            return result

        except Exception as e:
            logger.error(f"Ошибка при получении топ трейдеров: {str(e)}")
            return []

    async def calculate_user_level(self, user_id: int) -> Dict:
        """Рассчитывает уровень пользователя на основе его активности."""
        try:
            rating = await UserRating.get(user_id=user_id)
            if not rating:
                return {
                    'success': True,
                    'level': 1,
                    'title': "Новичок",
                    'progress': 0,
                    'next_level_deals': 5
                }

            # Определяем уровень на основе количества сделок
            if rating.total_deals < 5:
                level = 1
                title = "Новичок"
                next_level_deals = 5
                progress = rating.total_deals / 5
            elif rating.total_deals < 20:
                level = 2
                title = "Начинающий"
                next_level_deals = 20
                progress = (rating.total_deals - 5) / 15
            elif rating.total_deals < 50:
                level = 3
                title = "Опытный"
                next_level_deals = 50
                progress = (rating.total_deals - 20) / 30
            elif rating.total_deals < 100:
                level = 4
                title = "Профессионал"
                next_level_deals = 100
                progress = (rating.total_deals - 50) / 50
            else:
                level = 5
                title = "Эксперт"
                next_level_deals = None
                progress = 1

            return {
                'success': True,
                'level': level,
                'title': title,
                'total_deals': rating.total_deals,
                'progress': progress,
                'next_level_deals': next_level_deals
            }

        except Exception as e:
            logger.error(f"Ошибка при расчете уровня пользователя: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_verification_requests(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> list:
        """Получает список запросов на верификацию."""
        try:
            query = VerificationRequest.all()
            if status:
                query = query.filter(status=status)

            requests = await query.order_by('-created_at').offset(offset).limit(limit).all()
            result = []

            for request in requests:
                user = await User.get(id=request.user_id)
                result.append({
                    'id': request.id,
                    'user_id': user.id,
                    'username': user.username,
                    'document_type': request.document_type,
                    'status': request.status,
                    'created_at': request.created_at.isoformat(),
                    'processed_at': request.processed_at.isoformat() if request.processed_at else None,
                    'processed_by': request.processed_by,
                    'comment': request.comment
                })

            return result

        except Exception as e:
            logger.error(f"Ошибка при получении списка запросов на верификацию: {str(e)}")
            return []

    async def get_user_reviews(self, user_id: int) -> List[Dict]:
        """Возвращает отзывы о пользователе."""
        session = self.db.get_session()
        reviews = session.query(Review).filter(Review.reviewee_id == user_id).all()
        session.close()

        return [
            {
                'reviewer_id': review.reviewer.telegram_id,  #  telegram_id
                'rating': review.rating,
                'comment': review.comment,
                'created_at': review.created_at.isoformat()
            }
            for review in reviews
        ]

    async def calculate_user_rating(self, user_id: int) -> Dict:
        """Рассчитывает рейтинг пользователя."""
        try:
            session = self.db.get_session()
            try:
                # Получаем метрики пользователя
                volume_score = await self._calculate_volume_score(session, user_id)
                success_score = await self._calculate_success_score(session, user_id)
                activity_score = await self._calculate_activity_score(session, user_id)
                reputation_score = await self._calculate_reputation_score(session, user_id)

                # Вычисляем итоговый рейтинг
                total_rating = (
                    volume_score * self.rating_weights['trade_volume'] +
                    success_score * self.rating_weights['success_rate'] +
                    activity_score * self.rating_weights['activity'] +
                    reputation_score * self.rating_weights['reputation']
                )

                # Сохраняем рейтинг
                await self._save_rating(
                    session,
                    user_id,
                    total_rating,
                    {
                        'volume_score': volume_score,
                        'success_score': success_score,
                        'activity_score': activity_score,
                        'reputation_score': reputation_score
                    }
                )

                return {
                    'total_rating': float(total_rating),
                    'components': {
                        'trade_volume': float(volume_score),
                        'success_rate': float(success_score),
                        'activity': float(activity_score),
                        'reputation': float(reputation_score)
                    },
                    'updated_at': datetime.utcnow().isoformat()
                }

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при расчете рейтинга: {str(e)}")
            raise

    async def get_user_rank(self, user_id: int) -> Dict:
        """Получает ранг пользователя среди всех трейдеров."""
        try:
            session = self.db.get_session()
            try:
                # Получаем рейтинг пользователя
                user_rating = session.query(Rating).filter_by(
                    user_id=user_id
                ).first()

                if not user_rating:
                    return {
                        'rank': None,
                        'total_users': 0,
                        'percentile': None
                    }

                # Считаем количество пользователей с более высоким рейтингом
                higher_ratings = session.query(Rating).filter(
                    Rating.total_rating > user_rating.total_rating
                ).count()

                # Общее количество пользователей с рейтингом
                total_users = session.query(Rating).count()

                # Вычисляем процентиль
                percentile = ((total_users - higher_ratings) / total_users) * 100

                return {
                    'rank': higher_ratings + 1,
                    'total_users': total_users,
                    'percentile': float(percentile)
                }

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при получении ранга пользователя: {str(e)}")
            raise

    async def get_rating_history(
        self,
        user_id: int,
        days: int = 30
    ) -> List[Dict]:
        """Получает историю изменения рейтинга."""
        try:
            session = self.db.get_session()
            try:
                start_date = datetime.utcnow() - timedelta(days=days)
                
                history = session.query(RatingHistory).filter(
                    RatingHistory.user_id == user_id,
                    RatingHistory.created_at >= start_date
                ).order_by(RatingHistory.created_at.asc()).all()

                return [{
                    'rating': float(h.rating),
                    'components': json.loads(h.components),
                    'created_at': h.created_at.isoformat()
                } for h in history]

            finally:
                session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при получении истории рейтинга: {str(e)}")
            raise

    async def _calculate_volume_score(self, session, user_id: int) -> Decimal:
        """Рассчитывает скор на основе объема торгов."""
        try:
            # Получаем объем торгов за последние 30 дней
            start_date = datetime.utcnow() - timedelta(days=30)
            
            transactions = session.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.created_at >= start_date,
                Transaction.status == 'completed'
            ).all()

            total_volume = sum(tx.amount for tx in transactions)
            
            # Нормализуем объем (пример: максимальный скор 100 при объеме $100,000)
            max_volume = Decimal('100000')
            return min(total_volume / max_volume * 100, Decimal('100'))

        except Exception as e:
            self.logger.error(f"Ошибка при расчете объема: {str(e)}")
            return Decimal('0')

    async def _calculate_success_score(self, session, user_id: int) -> Decimal:
        """Рассчитывает скор на основе успешности сделок."""
        try:
            # Получаем все сделки за последние 30 дней
            start_date = datetime.utcnow() - timedelta(days=30)
            
            transactions = session.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.created_at >= start_date
            ).all()

            if not transactions:
                return Decimal('0')

            successful = sum(1 for tx in transactions if tx.status == 'completed')
            total = len(transactions)

            return Decimal(successful) / Decimal(total) * 100

        except Exception as e:
            self.logger.error(f"Ошибка при расчете успешности: {str(e)}")
            return Decimal('0')

    async def _calculate_activity_score(self, session, user_id: int) -> Decimal:
        """Рассчитывает скор на основе активности."""
        try:
            # Получаем все действия за последние 30 дней
            start_date = datetime.utcnow() - timedelta(days=30)
            
            total_points = Decimal('0')

            # Считаем очки за торговлю
            trades = session.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.created_at >= start_date,
                Transaction.type.in_(['buy', 'sell'])
            ).count()
            total_points += trades * self.activity_points['trade']

            # Считаем очки за P2P сделки
            p2p_deals = session.query(Transaction).filter(
                Transaction.user_id == user_id,
                Transaction.created_at >= start_date,
                Transaction.type == 'p2p'
            ).count()
            total_points += p2p_deals * self.activity_points['p2p_deal']

            # Нормализуем активность (пример: максимальный скор 100 при 1000 очках)
            max_points = Decimal('1000')
            return min(total_points / max_points * 100, Decimal('100'))

        except Exception as e:
            self.logger.error(f"Ошибка при расчете активности: {str(e)}")
            return Decimal('0')

    async def _calculate_reputation_score(self, session, user_id: int) -> Decimal:
        """Рассчитывает скор репутации."""
        try:
            # В реальном приложении здесь должна быть логика расчета репутации
            # на основе отзывов, жалоб и т.д.
            return Decimal('100')

        except Exception as e:
            self.logger.error(f"Ошибка при расчете репутации: {str(e)}")
            return Decimal('0')

    async def _save_rating(
        self,
        session,
        user_id: int,
        total_rating: Decimal,
        components: Dict
    ) -> None:
        """Сохраняет рейтинг пользователя."""
        try:
            # Обновляем текущий рейтинг
            rating = session.query(Rating).filter_by(user_id=user_id).first()
            
            if rating:
                rating.total_rating = total_rating
                rating.components = json.dumps(components)
                rating.updated_at = datetime.utcnow()
            else:
                rating = Rating(
                    user_id=user_id,
                    total_rating=total_rating,
                    components=json.dumps(components),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                session.add(rating)

            # Сохраняем в историю
            history = RatingHistory(
                user_id=user_id,
                rating=total_rating,
                components=json.dumps(components),
                created_at=datetime.utcnow()
            )
            session.add(history)

            session.commit()

        except Exception as e:
            self.logger.error(f"Ошибка при сохранении рейтинга: {str(e)}")
            session.rollback()
            raise 
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from services.rating.rating_service import RatingService
from core.database.models import User, Review
from core.database.database import Database
from datetime import datetime


class TestRatingService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.db_mock = AsyncMock(spec=Database)
        self.session_mock = AsyncMock()
        self.db_mock.get_session.return_value = self.session_mock
        self.rating_service = RatingService(self.db_mock)
        self.user1 = User(id=1, telegram_id=123, username="user1")
        self.user2 = User(id=2, telegram_id=456, username="user2")

    async def test_get_user_rating_exists(self):
        """Тест get_user_rating: пользователь существует."""
        user = User(id=1, rating=4.5)
        self.session_mock.query.return_value.filter.return_value.first.return_value = user
        result = await self.rating_service.get_user_rating(1)
        self.assertEqual(result, 4.5)
        self.session_mock.close.assert_called_once()

    async def test_get_user_rating_not_exists(self):
        """Тест get_user_rating: пользователь не существует."""
        self.session_mock.query.return_value.filter.return_value.first.return_value = None
        result = await self.rating_service.get_user_rating(1)
        self.assertIsNone(result)
        self.session_mock.close.assert_called_once()

    async def test_add_review_success(self):
        """Тест add_review: успех."""
        self.session_mock.query.return_value.filter.return_value.first.side_effect = [self.user1, self.user2]
        result = await self.rating_service.add_review(1, 2, None, 5, "Great!")
        self.assertTrue(result['success'])
        self.session_mock.add.assert_called_once()
        self.session_mock.commit.assert_called()
        self.session_mock.close.assert_called_once()

    async def test_add_review_invalid_rating(self):
        """Тест add_review: неверный рейтинг."""
        result = await self.rating_service.add_review(1, 2, None, 6, "Great!")
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Рейтинг должен быть от 1 до 5')
        self.session_mock.add.assert_not_called()
        self.session_mock.commit.assert_not_called()

    async def test_add_review_reviewer_not_found(self):
        """Тест add_review: reviewer не найден."""
        self.session_mock.query.return_value.filter.return_value.first.side_effect = [None, self.user2]
        result = await self.rating_service.add_review(1, 2, None, 5, "Great!")
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Пользователь не найден')
        self.session_mock.add.assert_not_called()
        self.session_mock.commit.assert_not_called()

    async def test_add_review_reviewee_not_found(self):
        """Тест add_review: reviewee не найден."""
        self.session_mock.query.return_value.filter.return_value.first.side_effect = [self.user1, None]
        result = await self.rating_service.add_review(1, 2, None, 5, "Great!")
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], 'Пользователь не найден')
        self.session_mock.add.assert_not_called()
        self.session_mock.commit.assert_not_called()

    async def test_add_review_exception(self):
        """Тест add_review: исключение."""
        self.session_mock.query.return_value.filter.return_value.first.side_effect = Exception("Some error")
        result = await self.rating_service.add_review(1, 2, None, 5, "Great!")
        self.assertFalse(result['success'])
        self.session_mock.rollback.assert_called_once()
        self.session_mock.close.assert_called_once()

    async def test_update_user_rating(self):
        """Тест update_user_rating."""
        review1 = Review(reviewer_id=1, reviewee_id=2, rating=4)
        review2 = Review(reviewer_id=3, reviewee_id=2, rating=5)
        self.session_mock.query.return_value.filter.return_value.all.return_value = [review1, review2]
        self.session_mock.query.return_value.filter.return_value.first.return_value = self.user2 #  юзера

        await self.rating_service.update_user_rating(2)
        self.assertEqual(self.user2.rating, 4.5)  #  рейтинг
        self.assertEqual(self.user2.review_count, 2) #  отзывов
        self.session_mock.commit.assert_called_once()
        self.session_mock.close.assert_called_once()

    async def test_update_user_rating_no_reviews(self):
        """Тест update_user_rating: нет отзывов."""
        self.session_mock.query.return_value.filter.return_value.all.return_value = []
        await self.rating_service.update_user_rating(2)
        self.session_mock.commit.assert_not_called() #  вызываем
        self.session_mock.close.assert_called_once()

    async def test_get_user_reviews(self):
        """Тест get_user_reviews."""
        review1 = Review(reviewer_id=1, reviewee_id=2, rating=4, comment="Good", created_at=datetime(2023, 1, 1))
        review2 = Review(reviewer_id=3, reviewee_id=2, rating=5, comment="Excellent", created_at=datetime(2023, 1, 2))
        self.session_mock.query.return_value.filter.return_value.all.return_value = [review1, review2]

        reviews = await self.rating_service.get_user_reviews(2)
        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0]['reviewer_id'], 1)
        self.assertEqual(reviews[0]['rating'], 4)
        self.assertEqual(reviews[0]['comment'], "Good")
        self.assertEqual(reviews[1]['reviewer_id'], 3)
        self.assertEqual(reviews[1]['rating'], 5)
        self.assertEqual(reviews[1]['comment'], "Excellent")
        self.session_mock.close.assert_called_once()

    async def test_get_user_reviews_no_reviews(self):
        """Тест get_user_reviews: нет отзывов."""
        self.session_mock.query.return_value.filter.return_value.all.return_value = []
        reviews = await self.rating_service.get_user_reviews(2)
        self.assertEqual(len(reviews), 0)
        self.session_mock.close.assert_called_once() 
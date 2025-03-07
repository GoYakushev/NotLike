import pytest
from services.rating.rating_service import RatingService
from core.database.database import Database
from core.database.models import User, Rating, Review
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database.models import Base

pytest_plugins = ('pytest_asyncio',)

#  in-memory SQLite
@pytest.fixture(scope="session")
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Database()
    db.SessionLocal = SessionLocal #  
    yield db
    Base.metadata.drop_all(engine)

@pytest.fixture
def rating_service(in_memory_db):
    return RatingService(db=in_memory_db)

@pytest.fixture
async def create_test_users(in_memory_db):
    session = in_memory_db.SessionLocal()
    user1 = User(telegram_id=12345, username="reviewer")
    user2 = User(telegram_id=67890, username="reviewee")
    session.add_all([user1, user2])
    session.commit()
    session.refresh(user1)
    session.refresh(user2)
    yield user1, user2
    session.delete(user1)
    session.delete(user2)
    session.commit()
    session.close()

@pytest.mark.asyncio
async def test_add_review_success(rating_service, create_test_users, in_memory_db):
    """Тест add_review: успех."""
    reviewer, reviewee = create_test_users
    result = await rating_service.add_review(reviewer.telegram_id, reviewee.telegram_id, 5, "Excellent service!")
    assert result['success'] is True

    session = in_memory_db.SessionLocal()
    review = session.query(Review).filter_by(reviewer_id=reviewer.id, reviewee_id=reviewee.id).first()
    assert review is not None
    assert review.rating == 5
    assert review.comment == "Excellent service!"

    #   
    rating = session.query(Rating).filter_by(user_id=reviewee.id).first()
    assert rating is not None
    assert rating.rating_value == 5.0
    assert rating.total_reviews == 1
    session.close()

@pytest.mark.asyncio
async def test_add_review_reviewer_not_found(rating_service, create_test_users):
    """Тест add_review: reviewer не найден."""
    _, reviewee = create_test_users
    result = await rating_service.add_review(99999, reviewee.telegram_id, 5, "Excellent service!")  #  ID
    assert result['success'] is False
    assert result['error'] == 'Reviewer не найден'

@pytest.mark.asyncio
async def test_add_review_reviewee_not_found(rating_service, create_test_users):
    """Тест add_review: reviewee не найден."""
    reviewer, _ = create_test_users
    result = await rating_service.add_review(reviewer.telegram_id, 99999, 5, "Excellent service!")  #  ID
    assert result['success'] is False
    assert result['error'] == 'Reviewee не найден'

@pytest.mark.asyncio
async def test_add_review_already_reviewed(rating_service, create_test_users, in_memory_db):
    """Тест add_review: уже оставил отзыв."""
    reviewer, reviewee = create_test_users
    #  
    session = in_memory_db.SessionLocal()
    review = Review(reviewer_id=reviewer.id, reviewee_id=reviewee.id, rating=5, comment="Good")
    session.add(review)
    session.commit()

    result = await rating_service.add_review(reviewer.telegram_id, reviewee.telegram_id, 4, "Another review")
    assert result['success'] is False
    assert result['error'] == 'Вы уже оставили отзыв этому пользователю'
    session.close()

@pytest.mark.asyncio
async def test_add_review_exception(rating_service, create_test_users, monkeypatch):
    """Тест add_review: исключение."""
    reviewer, reviewee = create_test_users
    #  ,   
    async def mock_add(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(rating_service.db.SessionLocal, 'add', mock_add)

    result = await rating_service.add_review(reviewer.telegram_id, reviewee.telegram_id, 5, "Excellent service!")
    assert result['success'] is False
    assert "Some error" in result['error']

@pytest.mark.asyncio
async def test_update_rating(rating_service, create_test_users, in_memory_db):
    """Тест update_rating."""
    _, reviewee = create_test_users
    session = in_memory_db.SessionLocal()
    #   
    rating = Rating(user_id=reviewee.id, rating_value=4.0, total_reviews=2)
    session.add(rating)
    session.commit()

    await rating_service.update_rating(reviewee.telegram_id)

    updated_rating = session.query(Rating).filter_by(user_id=reviewee.id).first()
    #   ,    
    assert updated_rating.total_reviews == 2 #  ,   
    session.close()

@pytest.mark.asyncio
async def test_update_rating_no_reviews(rating_service, create_test_users, in_memory_db):
    """Тест update_rating: нет отзывов."""
    _, reviewee = create_test_users
    #   
    session = in_memory_db.SessionLocal()
    rating = Rating(user_id=reviewee.id, rating_value=4.0, total_reviews=0)
    session.add(rating)
    session.commit()

    await rating_service.update_rating(reviewee.telegram_id)

    updated_rating = session.query(Rating).filter_by(user_id=reviewee.id).first()
    assert updated_rating.rating_value == 0.0  #   
    assert updated_rating.total_reviews == 0
    session.close()

@pytest.mark.asyncio
async def test_update_rating_user_not_found(rating_service):
    """Тест update_rating: пользователь не найден."""
    #   ,    
    await rating_service.update_rating(99999)

@pytest.mark.asyncio
async def test_get_rating_and_reviews(rating_service, create_test_users, in_memory_db):
    """Тест get_rating_and_reviews."""
    reviewer, reviewee = create_test_users
    session = in_memory_db.SessionLocal()
    rating = Rating(user_id=reviewee.id, rating_value=4.5, total_reviews=2)
    review1 = Review(reviewer_id=reviewer.id, reviewee_id=reviewee.id, rating=5, comment="Excellent!")
    review2 = Review(reviewer_id=reviewer.id + 1, reviewee_id=reviewee.id, rating=4, comment="Good")  #  reviewer
    session.add_all([rating, review1, review2])
    session.commit()

    result = await rating_service.get_rating_and_reviews(reviewee.telegram_id)
    assert result['rating'] == 4.5
    assert result['total_reviews'] == 2
    assert len(result['reviews']) == 2
    assert result['reviews'][0]['rating'] == 5
    assert result['reviews'][1]['rating'] == 4
    session.close()

@pytest.mark.asyncio
async def test_get_rating_and_reviews_user_not_found(rating_service):
    """Тест get_rating_and_reviews: пользователь не найден."""
    result = await rating_service.get_rating_and_reviews(99999)  #  ID
    assert result is None 
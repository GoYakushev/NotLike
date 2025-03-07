import pytest
import os
from services.backup.backup_service import BackupService
from core.database.database import Database
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database.models import Base

pytest_plugins = ('pytest_asyncio',)

#  in-memory SQLite  
#   ,    
@pytest.fixture(scope="session")
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Database()
    db.SessionLocal = SessionLocal
    yield db
    Base.metadata.drop_all(engine)

@pytest.fixture
def backup_service(in_memory_db):
    yadisk_service_mock = AsyncMock() #  
    return BackupService(db=in_memory_db, yadisk_service=yadisk_service_mock)

@pytest.mark.asyncio
async def test_create_backup_success(backup_service, in_memory_db):
    """Тест create_backup: успех."""
    result = await backup_service.create_backup()
    assert result['success'] is True
    assert 'backup_path' in result
    #  ,    
    assert os.path.exists(result['backup_path'])
    #   ( ,    )
    os.remove(result['backup_path'])

@pytest.mark.asyncio
async def test_create_backup_exception(backup_service, monkeypatch):
    """Тест create_backup: исключение."""
    #  ,   
    async def mock_execute(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(backup_service.db.engine, 'execute', mock_execute)

    result = await backup_service.create_backup()
    assert result['success'] is False
    assert "Some error" in result['error']

@pytest.mark.asyncio
async def test_upload_backup_success(backup_service):
    """Тест upload_backup: успех."""
    backup_service.yadisk_service.upload_file.return_value = {'success': True}
    result = await backup_service.upload_backup("test_backup.dump")
    assert result['success'] is True
    backup_service.yadisk_service.upload_file.assert_awaited_once_with("test_backup.dump", ANY)

@pytest.mark.asyncio
async def test_upload_backup_failure(backup_service):
    """Тест upload_backup: ошибка."""
    backup_service.yadisk_service.upload_file.return_value = {'success': False, 'error': 'Upload error'}
    result = await backup_service.upload_backup("test_backup.dump")
    assert result['success'] is False
    assert result['error'] == 'Upload error' 
import pytest
from services.backup.yadisk_service import YandexDiskService
from unittest.mock import AsyncMock, patch, MagicMock
import yadisk

pytest_plugins = ('pytest_asyncio',)

@pytest.fixture
def yadisk_service():
    return YandexDiskService(token="test_token")

@pytest.mark.asyncio
async def test_upload_file_success(yadisk_service):
    """Тест upload_file: успех."""
    #  yadisk.YaDisk.upload
    with patch('yadisk.YaDisk.upload', new_callable=AsyncMock) as mock_upload:
        result = await yadisk_service.upload_file("test_file.txt", "/backups/test_file.txt")

    assert result['success'] is True
    mock_upload.assert_called_once_with("test_file.txt", "/backups/test_file.txt", overwrite=True)

@pytest.mark.asyncio
async def test_upload_file_exception(yadisk_service, monkeypatch):
    """Тест upload_file: исключение."""
    #  ,   
    async def mock_upload(*args, **kwargs):
        raise Exception("Some error")

    monkeypatch.setattr(yadisk.YaDisk, 'upload', mock_upload)

    result = await yadisk_service.upload_file("test_file.txt", "/backups/test_file.txt")
    assert result['success'] is False
    assert "Some error" in result['error'] 
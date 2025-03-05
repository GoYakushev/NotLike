import yadisk
import os
import time
from datetime import datetime

class YandexDiskService:
    def __init__(self, token: str, backup_folder: str = "/not_like_backups"):
        self.yandex = yadisk.YaDisk(token=token)
        self.backup_folder = backup_folder
        
        # Проверяем токен и создаем папку если нужно
        if not self.yandex.check_token():
            raise Exception("Неверный токен Яндекс.Диска")
            
        if not self.yandex.exists(self.backup_folder):
            self.yandex.mkdir(self.backup_folder)
            
    def upload_backup(self, file_path: str, overwrite: bool = True) -> bool:
        """Загружает файл на Яндекс.Диск"""
        try:
            # Формируем имя файла на Диске
            filename = os.path.basename(file_path)
            remote_path = f"{self.backup_folder}/{filename}"
            
            self.yandex.upload(file_path, remote_path, overwrite=overwrite)
            return True
        except Exception as e:
            print(f"Ошибка загрузки на Яндекс.Диск: {e}")
            return False
            
    def get_backups_list(self) -> list:
        """Получает список резервных копий на Диске"""
        try:
            return list(self.yandex.listdir(self.backup_folder))
        except Exception as e:
            print(f"Ошибка получения списка бэкапов: {e}")
            return []
            
    def delete_old_backups(self, keep_last: int = 10):
        """Удаляет старые резервные копии, оставляя keep_last штук"""
        try:
            backups = self.get_backups_list()
            
            # Сортируем по дате создания (предполагаем формат имени файла)
            backups.sort(key=lambda x: x['created'], reverse=True)
            
            for backup in backups[keep_last:]:
                self.yandex.remove(f"{self.backup_folder}/{backup['name']}")
                
        except Exception as e:
            print(f"Ошибка удаления старых бэкапов: {e}") 
from aiogram import Bot
from datetime import datetime
import sqlite3
import json
import os
import asyncio
from services.backup.yadisk_service import YandexDiskService

class BackupService:
    def __init__(self, bot: Bot, yandex_token: str):
        self.bot = bot
        self.yandex_service = YandexDiskService(yandex_token)
        self.backup_interval = 3 * 60  # 3 минуты
        
    async def start_backup_scheduler(self):
        """Запускает планировщик резервного копирования"""
        while True:
            await self.create_backup()
            await asyncio.sleep(self.backup_interval)
            
    async def create_backup(self):
        """Создает резервную копию базы данных и загружает на Яндекс.Диск"""
        try:
            # Создаем временную копию базы
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f'backup_{timestamp}.db'
            
            # Копируем базу данных
            connection = sqlite3.connect('not_like.db')
            backup = sqlite3.connect(backup_path)
            with backup:
                connection.backup(backup)
            backup.close()
            connection.close()
            
            # Загружаем на Яндекс.Диск
            if self.yandex_service.upload_backup(backup_path):
                await self.bot.send_message(
                    config.ADMIN_ID,  # Используем config
                    f"✅ Резервная копия базы данных создана и загружена на Яндекс.Диск: {backup_path}"
                )
                
                # Удаляем старые бэкапы
                self.yandex_service.delete_old_backups()
            else:
                await self.bot.send_message(
                    config.ADMIN_ID,
                    f"❌ Ошибка при загрузке резервной копии на Яндекс.Диск"
                )
            
            # Удаляем временный файл
            os.remove(backup_path)
            
        except Exception as e:
            await self.bot.send_message(
                config.ADMIN_ID,
                f"❌ Ошибка при создании резервной копии:\n{str(e)}"
            )
            
    async def backup_critical_data(self):
        """Создает резервную копию критичных данных в JSON"""
        try:
            connection = sqlite3.connect('not_like.db')
            cursor = connection.cursor()
            
            # Получаем данные пользователей и кошельков
            cursor.execute("""
                SELECT users.*, wallets.address, wallets.private_key 
                FROM users 
                LEFT JOIN wallets ON users.id = wallets.user_id
            """)
            
            data = {
                'users': [],
                'timestamp': datetime.now().isoformat()
            }
            
            for row in cursor.fetchall():
                user_data = {
                    'telegram_id': row[1],
                    'username': row[2],
                    'wallets': [{
                        'address': row[-2],
                        'private_key': row[-1]
                    }] if row[-2] else []
                }
                data['users'].append(user_data)
                
            connection.close()
            
            # Сохраняем в файл
            backup_file = f'critical_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            with open(backup_file, 'w') as f:
                json.dump(data, f, indent=2)
                
            # Отправляем файл
            with open(backup_file, 'rb') as f:
                await self.bot.send_document(
                    config.ADMIN_ID,
                    f,
                    caption="🔐 Резервная копия критичных данных"
                )
                
            os.remove(backup_file)
            
        except Exception as e:
            await self.bot.send_message(
                config.ADMIN_ID,
                f"❌ Ошибка при резервном копировании критичных данных:\n{str(e)}"
            ) 
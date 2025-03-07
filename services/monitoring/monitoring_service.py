from typing import Dict, List, Optional
import logging
import time
from datetime import datetime, timedelta
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import psutil
import asyncio
from core.database.database import Database

class MonitoringService:
    def __init__(self, port: int = 8000):
        self.logger = logging.getLogger(__name__)
        self.db = Database()
        
        # Метрики Prometheus
        # DEX метрики
        self.swap_duration = Histogram(
            'swap_duration_seconds',
            'Время выполнения свопа',
            ['dex', 'network']
        )
        self.swap_volume = Counter(
            'swap_volume_total',
            'Общий объем свопов',
            ['dex', 'network', 'token_pair']
        )
        self.swap_success = Counter(
            'swap_success_total',
            'Успешные свопы',
            ['dex', 'network']
        )
        self.swap_failure = Counter(
            'swap_failure_total',
            'Неудачные свопы',
            ['dex', 'network', 'error_type']
        )
        
        # API метрики
        self.api_latency = Histogram(
            'api_latency_seconds',
            'Латентность API запросов',
            ['endpoint', 'method']
        )
        self.api_errors = Counter(
            'api_errors_total',
            'Ошибки API',
            ['endpoint', 'error_type']
        )
        
        # Системные метрики
        self.cpu_usage = Gauge(
            'cpu_usage_percent',
            'Использование CPU'
        )
        self.memory_usage = Gauge(
            'memory_usage_percent',
            'Использование памяти'
        )
        self.disk_usage = Gauge(
            'disk_usage_percent',
            'Использование диска'
        )
        
        # Метрики пользователей
        self.active_users = Gauge(
            'active_users',
            'Активные пользователи'
        )
        self.user_operations = Counter(
            'user_operations_total',
            'Операции пользователей',
            ['operation_type']
        )
        
        # Запускаем HTTP сервер для Prometheus
        start_http_server(port)
        
        # Запускаем фоновые задачи
        asyncio.create_task(self._collect_system_metrics())
        asyncio.create_task(self._collect_user_metrics())
        
    async def track_swap(
        self,
        dex: str,
        network: str,
        token_pair: str,
        duration: float,
        volume: float,
        success: bool,
        error_type: Optional[str] = None
    ) -> None:
        """Отслеживает метрики свопа."""
        try:
            # Записываем длительность
            self.swap_duration.labels(dex=dex, network=network).observe(duration)
            
            # Записываем объем
            self.swap_volume.labels(
                dex=dex,
                network=network,
                token_pair=token_pair
            ).inc(volume)
            
            # Записываем результат
            if success:
                self.swap_success.labels(dex=dex, network=network).inc()
            else:
                self.swap_failure.labels(
                    dex=dex,
                    network=network,
                    error_type=error_type or 'unknown'
                ).inc()
                
        except Exception as e:
            self.logger.error(f"Ошибка при отслеживании метрик свопа: {str(e)}")
            
    async def track_api_request(
        self,
        endpoint: str,
        method: str,
        duration: float,
        success: bool,
        error_type: Optional[str] = None
    ) -> None:
        """Отслеживает метрики API запросов."""
        try:
            # Записываем латентность
            self.api_latency.labels(endpoint=endpoint, method=method).observe(duration)
            
            # Записываем ошибки
            if not success:
                self.api_errors.labels(
                    endpoint=endpoint,
                    error_type=error_type or 'unknown'
                ).inc()
                
        except Exception as e:
            self.logger.error(f"Ошибка при отслеживании метрик API: {str(e)}")
            
    async def track_user_operation(
        self,
        operation_type: str
    ) -> None:
        """Отслеживает операции пользователей."""
        try:
            self.user_operations.labels(operation_type=operation_type).inc()
        except Exception as e:
            self.logger.error(f"Ошибка при отслеживании операций пользователей: {str(e)}")
            
    async def _collect_system_metrics(self) -> None:
        """Собирает системные метрики."""
        while True:
            try:
                # CPU
                self.cpu_usage.set(psutil.cpu_percent())
                
                # Память
                memory = psutil.virtual_memory()
                self.memory_usage.set(memory.percent)
                
                # Диск
                disk = psutil.disk_usage('/')
                self.disk_usage.set(disk.percent)
                
                await asyncio.sleep(60)  # Обновляем каждую минуту
                
            except Exception as e:
                self.logger.error(f"Ошибка при сборе системных метрик: {str(e)}")
                await asyncio.sleep(60)
                
    async def _collect_user_metrics(self) -> None:
        """Собирает метрики пользователей."""
        while True:
            try:
                # Подсчитываем активных пользователей за последний час
                async with self.db.session() as session:
                    active_count = await session.query(
                        "SELECT COUNT(DISTINCT user_id) FROM user_sessions "
                        "WHERE last_activity >= NOW() - INTERVAL '1 hour'"
                    ).scalar()
                    
                    self.active_users.set(active_count or 0)
                    
                await asyncio.sleep(300)  # Обновляем каждые 5 минут
                
            except Exception as e:
                self.logger.error(f"Ошибка при сборе метрик пользователей: {str(e)}")
                await asyncio.sleep(300) 
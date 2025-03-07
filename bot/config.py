from dataclasses import dataclass
from typing import Dict

@dataclass
class Config:
    # Telegram
    BOT_TOKEN: str = "YOUR_BOT_TOKEN"
    SUPPORT_BOT_TOKEN: str = "YOUR_SUPPORT_BOT_TOKEN"
    CREATOR_ID: int = 123456789  # @goyakushev
    
    # Комиссии
    FEES = {
        "p2p": 0.015,        # 1.5%
        "transfer": 0.01,     # 1%
        "internal": 0.002,    # 0.2%
        "spot": 0.01,         # 1%
        "swap": 0.01,         # 1%
        "copy_trading": 0.03  # 3%
    }
    
    # Кошельки
    COMMISSION_WALLET_SOL = "66Ghgnkq4miBLc9HVhsKyLqYAeYFndn73MAtwhvgoGG"
    
    # API ключи
    OPENROUTER_API_KEY: str = "YOUR_OPENROUTER_API_KEY"
    
    # Минимальные требования для копитрейдинга
    MIN_BALANCE_COPYTRADING = 300
    MIN_TRADING_VOLUME = 500

    # Ссылки
    TELEGRAM_CHANNEL = "t.me/n0tlikee"
    GITHUB_REPO = "https://github.com/GoYakushev/NotLike"

    # Яндекс.Диск
    YANDEX_DISK_TOKEN = "YOUR_YANDEX_DISK_TOKEN"

config = Config() 
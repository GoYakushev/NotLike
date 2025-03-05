from core.database.database import Database
from datetime import datetime, timedelta
from core.database.models import User, P2POrder, SpotOrder, SwapOrder
import json
from typing import Optional, Dict

class FeeService:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.default_fees = {
            'p2p': 0.015,  # 1.5%
            'transfer_address': 0.01,  # 1%
            'transfer_username': 0.002,  # 0.2%
            'spot': 0.01,  # 1%
            'swap': 0.01,  # 1%
            'copytrading': 0.03  # 3%
        }
        
    def get_current_fees(self) -> dict:
        """Возвращает текущие комиссии с учетом дня недели"""
        now = datetime.utcnow()
        weekday = now.weekday()
        
        fees = self.default_fees.copy()
        
        # Пятница (4) и понедельник (0) - P2P без комиссии
        if weekday in [0, 4]:
            fees['p2p'] = 0
            
        # Суббота (5) и воскресенье (6) - спот с пониженной комиссией
        if weekday in [5, 6]:
            fees['spot'] = 0.005  # 0.5%
            
        return fees
        
    def get_fee_message(self) -> str:
        """Возвращает сообщение о текущих комиссиях"""
        now = datetime.utcnow()
        weekday = now.weekday()
        
        if weekday == 0:
            return "Понедельник день тяжелый... P2P торговля без комиссии! 🎉"
        elif weekday == 4:
            return "Трудный день... и на выходные! P2P торговля без комиссии! 🎉"
        elif weekday in [5, 6]:
            return "Хороших выходных! Комиссия на спотовую торговлю снижена до 0.5%! 🎉"
            
        return None 

    def calculate_fee(self, operation_type: str, amount: float) -> float:
        """Вычисляет комиссию для заданной операции."""
        fees = self.get_current_fees()
        fee_rate = fees.get(operation_type, 0)  #  0,   
        return amount * fee_rate

    async def apply_fee(self, user_id: int, operation_type: str, amount: float, details: Optional[Dict] = None) -> Dict:
        """Применяет комиссию: списывает с баланса и записывает в историю."""
        session = self.db.get_session()
        user = session.query(User).filter_by(telegram_id=user_id).first()

        if not user:
            return {'success': False, 'error': 'Пользователь не найден'}

        try:
            fee_amount = self.calculate_fee(operation_type, amount)

            #  баланс (  WalletService)
            #  списание с баланса пользователя
            # ...

            #  в историю комиссий (  FeeTransaction)
            # ...

            session.commit()
            return {'success': True, 'fee_amount': fee_amount}

        except Exception as e:
            session.rollback()
            return {'success': False, 'error': str(e)}

    async def get_user_fee_stats(self, user_id: int, period: str = "day") -> Dict:
      """Возвращает статистику по комиссиям пользователя за период (day, week, month)."""
      session = self.db.get_session()
      user = session.query(User).filter_by(telegram_id=user_id).first()

      if not user:
          return {'success': False, 'error': 'Пользователь не найден'}

      try:
          now = datetime.utcnow()
          if period == "day":
              start_time = now - timedelta(days=1)
          elif period == "week":
              start_time = now - timedelta(weeks=1)
          elif period == "month":
              start_time = now - timedelta(days=30)  #  30
          else:
              return {'success': False, 'error': 'Неверный период'}

          #  комиссии по P2P
          p2p_fees = session.query(func.sum(P2POrder.amount * P2POrder.price * self.default_fees['p2p']))\
              .filter(P2POrder.user_id == user.id, P2POrder.created_at >= start_time).scalar() or 0

          #  комиссии по Spot
          spot_fees = session.query(func.sum(SpotOrder.amount * SpotOrder.price * self.default_fees['spot']))\
              .filter(SpotOrder.user_id == user.id, SpotOrder.created_at >= start_time).scalar() or 0

          #  комиссии по Swap
          swap_fees = session.query(func.sum(SwapOrder.amount * self.default_fees['swap']))\
              .filter(SwapOrder.user_id == user.id, SwapOrder.created_at >= start_time).scalar() or 0

          total_fees = p2p_fees + spot_fees + swap_fees

          return {
              'success': True,
              'total_fees': total_fees,
              'p2p_fees': p2p_fees,
              'spot_fees': spot_fees,
              'swap_fees': swap_fees
          }

      except Exception as e:
          return {'success': False, 'error': str(e)}
      finally:
          session.close() 
from AlgorithmImports import *
import datetime
from datetime import timedelta
from zoneinfo import ZoneInfo

from config import TradingConfig
from indicators import IndicatorManager
from trading_logic import TradingLogic

class SupertrendSarAlgorithm(QCAlgorithm):
    def initialize(self) -> None:
        # === Launch Settings ===
        self.set_start_date(2024, 9, 1)
        self.set_end_date(2025, 11, 1)
        self.set_cash(100000)

        # === Initializing modules ===
        self.config = TradingConfig(timeframe=5)
        self.indicators = IndicatorManager(self, self.config)
        self.trading_logic = TradingLogic(self, self.config, self.indicators)

        #=== Futures Subscription ===
        future = self.add_future(
            Futures.Indices.SP_500_E_MINI,
            Resolution.MINUTE,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            data_mapping_mode=DataMappingMode.OPEN_INTEREST,
            contract_depth_offset=0,
            extended_market_hours=True
        )
        future.set_filter(0, 90)
        
        self.future = future
        self._future_symbol = future.symbol
        self.ct = ZoneInfo("America/Chicago")

        # === Состояние ===
        self.current_contract_symbol = None
        self._contract_just_changed = False
        self.bar_index = 0
        self._last_trade_date = None
        self.pre_volume = 0
        self.volume_high = False
        self.consolidated_bars = {}
        
        # Прогрев
        max_len = max(self.config.atr_len, self.config.adx_len, self.config.supertrend_atr2, 
                     self.config.atr_stop_len, self.config.bb_len, self.config.rsi_len)
        warmup_period = max_len * (self.config.timeframe if self.config.timeframe > 1 else 1) * 3
        self.set_warm_up(warmup_period, Resolution.MINUTE)

        # === Initializing portfolio value for tracking ===
        self.trading_logic.last_portfolio_value = self.portfolio.total_portfolio_value

    def setup_consolidator(self):
        """Настройка консолидатора для выбранного таймфрейма"""
        self.indicators.setup_consolidator(self._future_symbol)
        self.indicators.consolidator.data_consolidated += self.on_consolidated_data

    def on_consolidated_data(self, sender, consolidated_bar):
        """Обработка консолидированных данных"""
        self.consolidated_bars[consolidated_bar.symbol] = consolidated_bar
        
        if self.is_warming_up:
            return
        
        if not self.indicators.indicators_ready:
            self.indicators.setup_consolidated_indicators(self._future_symbol)
        
        self.bar_index += 1
        
        bar_time = consolidated_bar.end_time.astimezone(self.ct).time()
        if not self.is_time_in_session(consolidated_bar.end_time):
            return
        
        if not self.indicators.all_indicators_ready():
            return
        
        if self.config.debug_flags:
            self.debug(f"ОБРАБОТКА КОНСОЛИДИРОВАННОГО БАРА: {bar_time:%H:%M} | Цена: {consolidated_bar.close}")
        
        self.process_trading_logic(consolidated_bar)

    def is_time_in_session(self, timestamp):
        """Проверяет, попадает ли время в торговую сессию"""
        time = timestamp.astimezone(self.ct).time()
        
        if self.config.timeframe > 1:
            bar_start = (timestamp - timedelta(minutes=self.config.timeframe-1)).astimezone(self.ct).time()
            if bar_start < self.config.session_start <= time:
                return True
            if self.config.session_start <= bar_start and time <= self.config.session_end:
                return True
            return False
        else:
            return self.config.session_start <= time <= self.config.session_end

    def can_trade_symbol(self, symbol):
        """Проверяет, можно ли торговать символом"""
        if symbol is None:
            return False
        if not self.securities.contains_key(symbol):
            return False
        security = self.securities[symbol]
        if not security.has_data or security.price == 0:
            return False
        return True

    def on_data(self, data: Slice) -> None:
        # Сброс при смене даты
        current_date = self.time.date()
        if self._last_trade_date is None or current_date != self._last_trade_date:
            self.pre_volume = 0
            self.volume_high = False
            self._last_trade_date = current_date
            if self.config.debug_flags:
                self.debug(f"НОВЫЙ ТОРГОВЫЙ ДЕНЬ: {current_date}")

        # Проверяем изменения портфеля
        self.trading_logic.debug_portfolio_change()

        if self.is_warming_up:
            return

        # Получение активного контракта
        contract = self.future.mapped
        if contract is None:
            if self.config.debug_flags:
                self.debug("NO ACTIVE CONTRACT")
            return
            
        if self.current_contract_symbol != contract:
            self.current_contract_symbol = contract
            self._contract_just_changed = True
            if self.config.debug_flags:
                self.debug(f"NEW ACTIVE CONTRACT: {contract} - ждем один тик")
            return
        
        if self._contract_just_changed:
            self._contract_just_changed = False
            if self.config.debug_flags:
                self.debug(f"Skip the first tick after rollover for {contract}")
            return
        
        # Pre-market объем
        now = self.time.astimezone(self.ct).time()
        if self.config.pre_start <= now <= self.config.pre_end:
            if data.bars.contains_key(contract):
                bar = data.bars[contract]
                self.pre_volume += bar.volume
                if self.config.debug_flags:
                    self.debug(f"PRE-MARKET VOLUME: {self.pre_volume} | Current bar: {bar.volume}")
        elif now > self.config.pre_end and not self.volume_high:
            self.volume_high = (self.pre_volume >= self.config.volume_requirement)
            if self.config.debug_flags:
                self.debug(f"VOLUME CHECK: {self.pre_volume} >= {self.config.volume_requirement} = {self.volume_high}")
        
        # Настройка консолидаторов или индикаторов
        if self.config.timeframe > 1:
            if self.indicators.consolidator is None:
                self.setup_consolidator()
            return
        
        if not self.indicators.indicators_ready:
            self.indicators.setup_minute_indicators(self._future_symbol)
        
        self.bar_index += 1
        
        if not (self.config.session_start <= now <= self.config.session_end):
            return
        
        if not data.bars.contains_key(contract):
            if self.config.debug_flags:
                self.debug(f"NO DATA FOR CONTRACT: {contract}")
            return
        
        if not self.can_trade_symbol(contract):
            if self.config.debug_flags:
                self.debug(f"SYMBOL NOT READY FOR TRADING: {contract}")
            return
        
        bar = data.bars[contract]
        
        if not self.indicators.all_indicators_ready():
            return
        
        self.process_trading_logic(bar)

    def process_trading_logic(self, bar):
        """Основная торговая логика"""
        if bar.close == 0:
            if self.config.debug_flags:
                self.debug(f"THE BAR IS NOT CORRECTLY PRICED: {bar.close}")
            return
        
        if not self.can_trade_symbol(self.current_contract_symbol):
            if self.config.debug_flags:
                self.debug(f"CONTRACT NOT READY FOR TRADE: {self.current_contract_symbol}")
            return
        
        # Проверка волатильности
        if not self.indicators.check_atr_condition():
            if self.config.debug_flags:
                self.debug("ATR condition not met - skip trading")
            return
        
        if not self.indicators.all_indicators_ready():
            if self.config.debug_flags:
                self.debug("INDICATORS NOT READY")
            return

        now = bar.end_time.astimezone(self.ct).time()
        price = bar.close
        adx_val = self.indicators._adx.current.value
        is_trending = adx_val > self.config.adx_thresh

        # Получение сигналов
        current_qty = self.portfolio[self.current_contract_symbol].quantity if self.current_contract_symbol else 0
        signals = self.trading_logic.calculate_signals(bar, current_qty, self.volume_high, adx_val, is_trending)
        
        if self.config.debug_flags:
            self.debug(f"ТОРГОВЫЙ БАР: {now:%H:%M} | Цена: {price:.2f} | ADX: {adx_val:.2f} | "
                      f"Trending: {is_trending} | Vol: {self.volume_high} | Pos: {current_qty}")

        # Выполнение сделок
        self.trading_logic.execute_entries(signals, current_qty, self.volume_high, self.bar_index, self.current_contract_symbol)
        self.trading_logic.execute_exits(signals, current_qty, self.bar_index, self.current_contract_symbol)

        # Статистика каждые 30 минут/баров
        if (self.config.timeframe == 1 and bar.end_time.minute % 30 == 0) or \
           (self.config.timeframe > 1 and self.bar_index % max(1, 30 // self.config.timeframe) == 0):
            self.trading_logic.debug_trade_stats()

    def on_symbol_changed_events(self, symbol_changed_events):
        """Обработка событий смены символа фьючерса"""
        for symbol, changed_event in symbol_changed_events.items():
            old_symbol = changed_event.old_symbol
            new_symbol = changed_event.new_symbol
            
            if self.config.debug_flags:
                self.debug(f"FUTURES ROLLOVER: {old_symbol} -> {new_symbol}")
            
            # Переносим позицию со старого контракта на новый
            old_quantity = self.portfolio[old_symbol].quantity
            if old_quantity != 0:
                if self.can_trade_symbol(old_symbol):
                    self.liquidate(old_symbol, "Rollover - закрытие старого контракта")
                
                if self.can_trade_symbol(new_symbol):
                    self.market_order(new_symbol, old_quantity, tag="Rollover - открытие нового контракта")
                else:
                    if self.config.debug_flags:
                        self.debug(f"ROLLOVER: Новый символ {new_symbol} не готов к торговле")
            
            self.current_contract_symbol = new_symbol
            self._contract_just_changed = True

from AlgorithmImports import *
from QuantConnect.Indicators import SimpleMovingAverage
from datetime import timedelta

class IndicatorManager:
    def __init__(self, algorithm, config):
        self.algo = algorithm
        self.config = config
        self.indicators_ready = False
        
        # Индикаторы
        self._atr = None
        self._avg_atr = None
        self._adx = None
        self._str_low = None
        self._str_high = None
        self._sar_low = None
        self._sar_high = None
        self._rsi = None
        self._bb = None
        
        # Консолидатор
        self.consolidator = None

    def setup_minute_indicators(self, symbol):
        """Настройка индикаторов для минутного таймфрейма"""
        if self.config.debug_flags:
            self.algo.debug(f"SETTING MINUTE INDICATORS for symbol {symbol}")
        
        # Инициализация индикаторов для базового таймфрейма (1 минута)
        self._atr = self.algo.atr(symbol, self.config.atr_len, MovingAverageType.WILDERS, Resolution.MINUTE)
        self._avg_atr = SimpleMovingAverage("avg_atr", self.config.atr_len)
        
        def atr_updated_handler(sender, updated):
            self._avg_atr.update(updated.end_time, updated.value)
        self._atr.updated += atr_updated_handler

        self._adx = self.algo.adx(symbol, self.config.adx_len, Resolution.MINUTE)
        self._str_low = self.algo.str(symbol, self.config.supertrend_atr, self.config.supertrend_factor, resolution=Resolution.MINUTE)
        self._str_high = self.algo.str(symbol, self.config.supertrend_atr2, self.config.supertrend_factor2, resolution=Resolution.MINUTE)
        self._sar_low = self.algo.psar(symbol, self.config.sar_start, self.config.sar_increment, self.config.sar_max, Resolution.MINUTE)
        self._sar_high = self.algo.psar(symbol, self.config.sar_start2, self.config.sar_increment2, self.config.sar_max2, Resolution.MINUTE)
        self._rsi = self.algo.rsi(symbol, self.config.rsi_len, MovingAverageType.WILDERS, Resolution.MINUTE)
        self._bb = self.algo.bb(symbol, self.config.bb_len, self.config.bb_mult, MovingAverageType.SIMPLE, Resolution.MINUTE)
        
        self.indicators_ready = True

    def setup_consolidator(self, symbol):
        """Настройка консолидатора для выбранного таймфрейма"""
        if self.config.debug_flags:
            self.algo.debug(f"CONFIGURING THE CONSOLIDATOR: {self.config.timeframe} минут для символа {symbol}")
        
        # Создаем консолидатор для выбранного таймфрейма
        self.consolidator = TradeBarConsolidator(timedelta(minutes=self.config.timeframe))
        
        # Регистрируем консолидатор для непрерывного контракта
        self.algo.subscription_manager.add_consolidator(symbol, self.consolidator)
        
        if self.config.debug_flags:
            self.algo.debug(f"CONSOLIDATOR SET UP: {symbol} | Таймфрейм: {self.config.timeframe} минут")

    def setup_consolidated_indicators(self, symbol):
        """Настройка индикаторов для консолидированных данных"""
        if self.config.debug_flags:
            self.algo.debug(f"SETTING UP CONSOLIDATED INDICATORS")
        
        # Создаем индикаторы для консолидированных данных
        self._atr = self.algo.atr(symbol, self.config.atr_len, MovingAverageType.WILDERS)
        self.algo.register_indicator(symbol, self._atr, self.consolidator)
        
        self._avg_atr = SimpleMovingAverage(f"avg_atr", self.config.atr_len)
        
        # Привязка ATR к AVG_ATR
        def atr_updated_handler(sender, updated):
            self._avg_atr.update(updated.end_time, updated.value)
        
        self._atr.updated += atr_updated_handler
        
        self._adx = self.algo.adx(symbol, self.config.adx_len)
        self.algo.register_indicator(symbol, self._adx, self.consolidator)
        
        self._str_low = self.algo.str(symbol, self.config.supertrend_atr, self.config.supertrend_factor)
        self.algo.register_indicator(symbol, self._str_low, self.consolidator)
        
        self._str_high = self.algo.str(symbol, self.config.supertrend_atr2, self.config.supertrend_factor2)
        self.algo.register_indicator(symbol, self._str_high, self.consolidator)
        
        self._sar_low = self.algo.psar(symbol, self.config.sar_start, self.config.sar_increment, self.config.sar_max)
        self.algo.register_indicator(symbol, self._sar_low, self.consolidator)
        
        self._sar_high = self.algo.psar(symbol, self.config.sar_start2, self.config.sar_increment2, self.config.sar_max2)
        self.algo.register_indicator(symbol, self._sar_high, self.consolidator)
        
        self._rsi = self.algo.rsi(symbol, self.config.rsi_len, MovingAverageType.WILDERS)
        self.algo.register_indicator(symbol, self._rsi, self.consolidator)
        
        self._bb = self.algo.bb(symbol, self.config.bb_len, self.config.bb_mult, MovingAverageType.SIMPLE)
        self.algo.register_indicator(symbol, self._bb, self.consolidator)
        
        self.indicators_ready = True
        
        if self.config.debug_flags:
            self.algo.debug(f"INDICATORS ARE CONFIGURED for the timeframe {self.config.timeframe}m")

    def all_indicators_ready(self):
        """Проверяет готовность всех индикаторов"""
        if not self.indicators_ready:
            return False
        
        # Проверяем индикаторы с is_ready и отдельно avg_atr
        indicators_with_is_ready = [
            self._atr, self._adx, self._str_low, 
            self._str_high, self._sar_low, self._sar_high,
            self._rsi, self._bb
        ]
        
        # Для SimpleMovingAverage проверяем samples >= period
        avg_atr_ready = self._avg_atr.samples >= self._avg_atr.period
        
        return all(ind.is_ready for ind in indicators_with_is_ready) and avg_atr_ready

    def check_atr_condition(self):
        """Проверка волатильности ATR"""
        if not (self._atr.is_ready and self._avg_atr.is_ready):
            return False
        
        return self._atr.current.value > self._avg_atr.current.value * self.config.atr_threshold_mult
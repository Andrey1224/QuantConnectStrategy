from AlgorithmImports import *

class TradingLogic:
    def __init__(self, algorithm, config, indicators):
        self.algo = algorithm
        self.config = config
        self.indicators = indicators
        
        # === Strategy State ===
        self._long_mr_bar_index = None
        self._short_mr_bar_index = None
        self._previous_bar = None
        
        # === Trade Statistics ===
        self.trade_counter = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0
        self.last_portfolio_value = None
        
        # Statistics by transaction types
        self.trend_trades = 0
        self.mr_trades = 0
        self.trend_pnl = 0
        self.mr_pnl = 0
        
       # === For tracking positions ===
        self.active_orders = {}
        self.position_entry_price = None
        self.position_entry_time = None
        self.position_type = None
        
        # === Order IDs ===
        self._trend_tickets = {}
        self._mr_entry_tickets = {}
        self._stop_ticket = None
        self._entry_ticket_id = None

    def calculate_signals(self, bar, current_qty, volume_high, adx_val, is_trending):
        """Рассчитывает все торговые сигналы"""
        price = bar.close
        
        # SuperTrend флаги
        st_low_val = self.indicators._str_low.current.value
        st_high_val = self.indicators._str_high.current.value
        isSTRbullish_low = price > st_low_val
        isSTRbearish_low = price < st_low_val
        isSTRbullish_high = price > st_high_val
        isSTRbearish_high = price < st_high_val

        # PSAR флаги
        sar_low_val = self.indicators._sar_low.current.value
        sar_high_val = self.indicators._sar_high.current.value
        isSARbullish_low = price > sar_low_val
        isSARbearish_low = price < sar_low_val
        isSARbullish_high = price > sar_high_val
        isSARbearish_high = price < sar_high_val

        # Рассчитываем свечной разворот (Candle Reversal)
        if self._previous_bar is not None:
            bullish_reversal = bar.close > bar.open and self._previous_bar.close < self._previous_bar.open
            bearish_reversal = bar.close < bar.open and self._previous_bar.close > self._previous_bar.open
        else:
            bullish_reversal = False
            bearish_reversal = False
        self._previous_bar = bar

        # Тренд сигналы
        if is_trending:
            if not volume_high:
                trend_long = isSTRbullish_low and isSARbullish_low
                trend_short = isSTRbearish_low and isSARbearish_low
            else:
                trend_long = isSTRbullish_high and isSARbullish_high
                trend_short = isSTRbearish_high and isSARbearish_high
        else:
            trend_long = False
            trend_short = False

        # Mean Reversion сигналы
        rsi_val = self.indicators._rsi.current.value
        bb_lower = self.indicators._bb.lower_band.current.value
        bb_upper = self.indicators._bb.upper_band.current.value

        mean_rev_long = (not is_trending) and (price < bb_lower) and (rsi_val < self.config.rsi_os) and bullish_reversal
        mean_rev_short = (not is_trending) and (price > bb_upper) and (rsi_val > self.config.rsi_ob) and bearish_reversal

        return {
            'trend_long': trend_long,
            'trend_short': trend_short,
            'mean_rev_long': mean_rev_long,
            'mean_rev_short': mean_rev_short,
            'bullish_reversal': bullish_reversal,
            'bearish_reversal': bearish_reversal,
            'rsi_val': rsi_val,
            'bb_lower': bb_lower,
            'bb_upper': bb_upper,
            'price': price
        }

    def execute_entries(self, signals, current_qty, volume_high, bar_index, contract_symbol):
        """Выполняет входы в позицию"""
        # Размеры позиций
        qty = self.config.high_volume_qty if volume_high else self.config.low_volume_qty
        mean_rev_qty = qty

        # ВХОДЫ В ПОЗИЦИЮ - LONG
        if (signals['trend_long'] or signals['mean_rev_long']) and current_qty == 0:
            # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА перед входом
            if not self.algo.can_trade_symbol(contract_symbol):
                if self.config.debug_trades:
                    self.algo.debug(f"ОТМЕНА ВХОДА - СИМВОЛ НЕ ГОТОВ: {contract_symbol}")
                return
                
            if signals['mean_rev_long']:
                self._long_mr_bar_index = bar_index
                self.position_entry_price = signals['price']
                self.position_type = 'mr_long'
                
                if self.config.debug_trades:
                    self.algo.debug(f"ENTERING MR LONG | Price={signals['price']:.2f} | Qty={mean_rev_qty} | ADX={self.indicators._adx.current.value:.2f}")
                
                ticket = self.algo.market_order(contract_symbol, mean_rev_qty)
                if ticket:
                    self._entry_ticket_id = ticket.order_id
                    self._mr_entry_tickets[ticket.order_id] = True
                    self.active_orders[ticket.order_id] = f"MR_LONG_ENTRY_{mean_rev_qty}"

            else:  # trend_long
                self.position_entry_price = signals['price']
                self.position_type = 'trend_long'
                
                if self.config.debug_trades:
                    self.algo.debug(f"ENTERING TREND LONG | Price={signals['price']:.2f} | Qty={qty} | ADX={self.indicators._adx.current.value:.2f}")
                
                ticket = self.algo.market_order(contract_symbol, qty)
                if ticket:
                    self._entry_ticket_id = ticket.order_id
                    self._trend_tickets[ticket.order_id] = True
                    self.active_orders[ticket.order_id] = f"TREND_LONG_ENTRY_{qty}"

        # ВХОДЫ В ПОЗИЦИЮ - SHORT
        elif (signals['trend_short'] or signals['mean_rev_short']) and current_qty == 0:
            # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА перед входом
            if not self.algo.can_trade_symbol(contract_symbol):
                if self.config.debug_trades:
                    self.algo.debug(f"ОТМЕНА ВХОДА - СИМВОЛ НЕ ГОТОВ: {contract_symbol}")
                return
                
            if signals['mean_rev_short']:
                self._short_mr_bar_index = bar_index
                self.position_entry_price = signals['price']
                self.position_type = 'mr_short'
                
                if self.config.debug_trades:
                    self.algo.debug(f"ENTERING MR SHORT | Price={signals['price']:.2f} | Qty={-mean_rev_qty} | ADX={self.indicators._adx.current.value:.2f}")
                
                ticket = self.algo.market_order(contract_symbol, -mean_rev_qty)
                if ticket:
                    self._entry_ticket_id = ticket.order_id
                    self._mr_entry_tickets[ticket.order_id] = True
                    self.active_orders[ticket.order_id] = f"MR_SHORT_ENTRY_{-mean_rev_qty}"
                
            else:  # trend_short
                self.position_entry_price = signals['price']
                self.position_type = 'trend_short'
                
                if self.config.debug_trades:
                    self.algo.debug(f"ENTERING TREND SHORT | Price={signals['price']:.2f} | Qty={-qty} | ADX={self.indicators._adx.current.value:.2f}")
                
                ticket = self.algo.market_order(contract_symbol, -qty)
                if ticket:
                    self._entry_ticket_id = ticket.order_id
                    self._trend_tickets[ticket.order_id] = True
                    self.active_orders[ticket.order_id] = f"TREND_SHORT_ENTRY_{-qty}"

    def execute_exits(self, signals, current_qty, bar_index, contract_symbol):
        """Выполняет выходы из позиции"""
        # ВЫХОДЫ ИЗ ПОЗИЦИИ
        if current_qty > 0:
            should_exit = not signals['trend_long'] and not signals['mean_rev_long']
            if should_exit and self.config.debug_trades:
                self.algo.debug(f"EXITING LONG | Reason: TrendLong={signals['trend_long']}, MRLong={signals['mean_rev_long']}")
            if should_exit and self.algo.can_trade_symbol(contract_symbol):
                self.algo.liquidate(contract_symbol)
                self._long_mr_bar_index = None

        if current_qty < 0:
            should_exit = not signals['trend_short'] and not signals['mean_rev_short']
            if should_exit and self.config.debug_trades:
                self.algo.debug(f"EXITING SHORT | Reason: TrendShort={signals['trend_short']}, MRShort={signals['mean_rev_short']}")
            if should_exit and self.algo.can_trade_symbol(contract_symbol):
                self.algo.liquidate(contract_symbol)
                self._short_mr_bar_index = None

        # Таймауты для MR (bar-based)
        if self._long_mr_bar_index is not None and current_qty > 0:
            elapsed_bars = bar_index - self._long_mr_bar_index
            if elapsed_bars >= self.config.max_bars_in_trade:
                if self.config.debug_trades:
                    self.algo.debug(f"MR LONG TIMEOUT | Elapsed bars: {elapsed_bars}")
                if self.algo.can_trade_symbol(contract_symbol):
                    self.algo.liquidate(contract_symbol)
                self._long_mr_bar_index = None

        if self._short_mr_bar_index is not None and current_qty < 0:
            elapsed_bars = bar_index - self._short_mr_bar_index
            if elapsed_bars >= self.config.max_bars_in_trade:
                if self.config.debug_trades:
                    self.algo.debug(f"MR SHORT TIMEOUT | Elapsed bars: {elapsed_bars}")
                if self.algo.can_trade_symbol(contract_symbol):
                    self.algo.liquidate(contract_symbol)
                self._short_mr_bar_index = None

    def debug_trade_stats(self):
        """Выводит статистику сделок"""
        if self.config.debug_trades and self.trade_counter > 0:
            win_rate = (self.winning_trades / self.trade_counter) * 100
            avg_trade = self.total_pnl / self.trade_counter
            
            self.algo.debug(f"=== TRADE STATS ===")
            self.algo.debug(f"Total Trades: {self.trade_counter} | Win Rate: {win_rate:.1f}%")
            self.algo.debug(f"Winners: {self.winning_trades} | Losers: {self.losing_trades}")
            self.algo.debug(f"Total PnL: {self.total_pnl:.2f} | Avg Trade: {avg_trade:.2f}")
            self.algo.debug(f"Trend Trades: {self.trend_trades} | Trend PnL: {self.trend_pnl:.2f}")
            self.algo.debug(f"MR Trades: {self.mr_trades} | MR PnL: {self.mr_pnl:.2f}")

    def debug_portfolio_change(self):
        """Отслеживает изменения в портфеле"""
        if self.config.debug_pnl:
            current_value = self.algo.portfolio.total_portfolio_value
            if self.last_portfolio_value is None:
                self.last_portfolio_value = current_value
            
            change = current_value - self.last_portfolio_value
            if abs(change) > 1:  # Если изменение больше $1
                self.algo.debug(f"PORTFOLIO CHANGE: {change:+.2f} | Total: {current_value:.2f} | Cash: {self.algo.portfolio.cash:.2f}")
                self.last_portfolio_value = current_value
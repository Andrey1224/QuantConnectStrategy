# region imports
from AlgorithmImports import *
# endregion
import math
from datetime import time

class TradingConfig:
    def __init__(self, timeframe=5): # here you can change TimeFrame (1 min 5 min 15min 30 min 45min 60min probably any minutes 1 , 2 ,3 4, 5)
        # === Basic settings ===
        self.timeframe = timeframe
        self.resolution = "Resolution.MINUTE"
        
        # === DEBUG FLAGS ===
        self.debug_indicators = True
        self.debug_flags = True
        self.debug_trades = True
        self.debug_orders = True
        self.debug_pnl = True
        
        # === Strategy Parameters === Here you can chabge parametrs
        self.volume_requirement = 90000
        self.low_volume_qty = 1
        self.high_volume_qty = 2

        self.supertrend_atr = 3
        self.supertrend_factor = 1.7
        self.supertrend_atr2 = 5
        self.supertrend_factor2 = 2.1

        self.sar_start = 0.008
        self.sar_increment = 0.004
        self.sar_max = 0.1
        self.sar_start2 = 0.01
        self.sar_increment2 = 0.006
        self.sar_max2 = 0.1

        self.low_vol_sl = 10
        self.high_vol_sl = 15
        self.mean_rev_tp = 10
        self.mean_rev_sl = 6
        self.max_bars_in_trade = 5

        self.atr_stop_len = 23
        self.atr_stop_mult = 1.5
        self.adx_len = 13
        self.adx_thresh = 18

        self.atr_len = 14
        self.atr_threshold_mult = 0.8
        self.rsi_len = 14
        self.rsi_ob = 70
        self.rsi_os = 30
        self.bb_len = 20
        self.bb_mult = 2.0
        
        # === Time windows ===
        self.pre_start = time(6, 30)
        self.pre_end = time(6, 45)
        self.session_start = time(6, 45)
        self.session_end = time(8, 0)
        
        # === Debug settings ===
        self.debug_every_n_minutes = 5
        self.debug_on_changes_only = False
        self.significant_change_threshold = 0.0005

        # We scale the parameters to the timeframe if it is greater than 1
        if self.timeframe > 1:
            scaling_factor = math.sqrt(self.timeframe)
            
            # Scaling stops and takes
            self.mean_rev_tp *= scaling_factor
            self.mean_rev_sl *= scaling_factor
            
            # Adjusting the ATR multiplier for larger timeframes
            self.atr_stop_mult *= scaling_factor / math.sqrt(5)
            
            # Adjusting the timeout by bars
            self.max_bars_in_trade = max(2, int(self.max_bars_in_trade / scaling_factor))
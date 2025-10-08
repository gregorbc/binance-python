def calculate_indicators(self, df: pd.DataFrame):
    """Calcular indicadores técnicos con manejo robusto de errores"""
    if df is None or len(df) < 5:
        return          
    try:
        df['fast_ema'] = df['close'].ewm(span=config.FAST_EMA, adjust=False).mean()
        df['slow_ema'] = df['close'].ewm(span=config.SLOW_EMA, adjust=False).mean()
        
        delta = df['close'].diff()
        up, down = delta.copy(), delta.copy()
        up[up < 0] = 0
        down[down > 0] = 0
        roll_up = up.ewm(span=config.RSI_PERIOD, adjust=False).mean()
        roll_down = down.abs().ewm(span=config.RSI_PERIOD, adjust=False).mean()
        rs = roll_up / roll_down.replace(0, np.nan)
        df['rsi'] = 100.0 - (100.0 / (1.0 + rs)).fillna(50)

        exp1 = df['close'].ewm(span=config.MACD_FAST, adjust=False).mean()
        exp2 = df['close'].ewm(span=config.MACD_SLOW, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=config.MACD_SIGNAL, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        stoch_rsi = (df['rsi'] - df['rsi'].rolling(config.STOCH_PERIOD).min()) / (df['rsi'].rolling(config.STOCH_PERIOD).max() - df['rsi'].rolling(config.STOCH_PERIOD).min())
        df['stoch_rsi'] = stoch_rsi * 100

        df['bb_middle'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']

        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(20).std() * np.sqrt(365) * 100
        
    except Exception as e:
        log.error(f"Error calculando indicadores: {e}")
        # Establecer valores por defecto para evitar que falle el análisis
        df['fast_ema'] = df['close']
        df['slow_ema'] = df['close']
        df['rsi'] = 50
        df['macd'] = 0
        df['macd_signal'] = 0
        df['macd_hist'] = 0
        df['stoch_rsi'] = 50
        df['bb_middle'] = df['close']
        df['bb_upper'] = df['close']
        df['bb_lower'] = df['close']
        df['bb_width'] = 0
        df['returns'] = 0
        df['volatility'] = 0
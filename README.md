# Binance Futures Trading Bot - Web Application v10.4

A professional web-based trading bot for Binance Futures with real-time monitoring, configuration management, and automated trading strategies.

## Features

- **Real-time Trading Dashboard**: Monitor positions, P&L, and trading activity
- **Automated Strategy Execution**: EMA crossover with RSI confirmation
- **Live Configuration Management**: Adjust settings without restarting
- **WebSocket Integration**: Real-time updates and notifications
- **Production-Ready**: Docker, Nginx, and Gunicorn support
- **Security**: Rate limiting, SSL support, and secure API handling

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/gregorbc/binance-python.git
cd binance-python
```

### 2. Environment Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit with your credentials
nano .env
```

Required environment variables:
```env
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_TESTNET=true  # Set to false for live trading
SECRET_KEY=your-flask-secret-key
```

### 3. Development Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run development server
python app.py
```

The application will be available at `http://localhost:5000`

## Production Deployment

### Option 1: Docker (Recommended)

```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Option 2: Direct Server Deployment

```bash
# Install dependencies
pip install -r requirements.txt

# Create required directories
mkdir -p logs static templates

# Run with Gunicorn
gunicorn -c gunicorn.conf.py wsgi:application
```

### Option 3: Systemd Service

Create `/etc/systemd/system/binance-bot.service`:

```ini
[Unit]
Description=Binance Futures Bot
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/opt/binance-bot
Environment=PATH=/opt/binance-bot/venv/bin
ExecStart=/opt/binance-bot/venv/bin/gunicorn -c gunicorn.conf.py wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable binance-bot
sudo systemctl start binance-bot
sudo systemctl status binance-bot
```

## Nginx Configuration

For production, use Nginx as a reverse proxy:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Security Considerations

1. **API Keys**: Never commit API keys to version control
2. **HTTPS**: Always use SSL/TLS in production
3. **Rate Limiting**: Implemented via Nginx configuration
4. **Firewall**: Restrict access to necessary ports only
5. **Updates**: Keep dependencies updated regularly

## Configuration

### Bot Settings

- **LEVERAGE**: Trading leverage (1-100)
- **MAX_CONCURRENT_POS**: Maximum simultaneous positions
- **FIXED_MARGIN_PER_TRADE_USDT**: Capital per trade
- **NUM_SYMBOLS_TO_SCAN**: Number of symbols to analyze

### Strategy Parameters

- **ATR_MULT_SL**: Stop-loss multiplier
- **ATR_MULT_TP**: Take-profit multiplier
- **FAST_EMA**: Fast EMA period
- **SLOW_EMA**: Slow EMA period

## Monitoring and Logs

### Log Files
- Application logs: `logs/bot_v10.log`
- Gunicorn access: `logs/gunicorn_access.log`
- Gunicorn errors: `logs/gunicorn_error.log`

### Health Checks
- Endpoint: `GET /health`
- Docker health check included
- Returns JSON status and timestamp

### Real-time Monitoring
- WebSocket connection status
- Live P&L updates
- Position changes
- Trade execution logs

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main dashboard |
| `/api/status` | GET | Bot status and metrics |
| `/api/start` | POST | Start trading bot |
| `/api/stop` | POST | Stop trading bot |
| `/api/update_config` | POST | Update configuration |
| `/api/close_position` | POST | Close specific position |
| `/api/manual_trade` | POST | Execute manual trade |
| `/api/history` | GET | Trading history |
| `/health` | GET | Health check |

## Troubleshooting

### Common Issues

1. **Connection Failed**: Check API keys and network connectivity
2. **Permission Denied**: Ensure proper file permissions
3. **Port Already in Use**: Change PORT in .env file
4. **WebSocket Issues**: Check firewall and proxy configuration

### Debug Mode

Enable debug logging:
```bash
export DEBUG=true
export LOG_LEVEL=DEBUG
python app.py
```

### Docker Issues

```bash
# Check container logs
docker-compose logs binance-bot

# Access container shell
docker-compose exec binance-bot bash

# Rebuild containers
docker-compose build --no-cache
```

## License

This project is for educational purposes. Use at your own risk. Trading involves financial risk.

## Support

- Check logs for error details
- Verify API connectivity and permissions
- Ensure sufficient balance for trading
- Review Binance API documentation
- Test with small amounts first

---

**Warning**: This bot involves real money trading. Always test thoroughly with small amounts and understand the risks involved. The developers are not responsible for any financial losses.

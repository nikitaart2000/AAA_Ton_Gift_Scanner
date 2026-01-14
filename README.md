# 🎯 AAA TON GIFTS SCANNER

High-performance TON Gifts market scanner with real-time alerts.

## 🚀 Quick Start

### 1. Start Database & Redis

```bash
docker-compose up -d
```

### 2. Install Dependencies

```bash
pip install poetry
poetry install
```

### 3. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials.

### 4. Test Collectors

```bash
python test_collectors.py
```

This will:
- Connect to TimescaleDB
- Start Swift Gifts event collector
- Start Tonnel listings collector
- Display events in real-time

## 📊 Architecture

```
collectors → scanner_service → database
                             ↓
                         analytics → alert_engine → telegram_bot
```

## 🗄️ Database Schema

- `market_events` - Time-series event data (buy, listing, change_price)
- `active_listings` - Current market listings
- `asset_analytics` - Cached analytics (floors, liquidity, confidence)
- `user_settings` - User preferences and filters
- `watchlist` - Watched assets
- `muted_assets` - Temporarily muted assets
- `sent_alerts` - Alert history for cooldown

## 📝 TODO

- [x] Setup project structure
- [x] TimescaleDB schema
- [x] Swift Gifts collector
- [x] Tonnel collector
- [ ] Analytics engine (ARP, liquidity, confidence)
- [ ] Alert engine (filtering, ranking)
- [ ] Telegram bot
- [ ] Telegram Mini App

## 🔧 Tech Stack

- **Python 3.11+**
- **TimescaleDB** (PostgreSQL + time-series)
- **Redis** (cache)
- **FastAPI** (API)
- **aiogram** (Telegram bot)
- **curl_cffi** (HTTP client with browser impersonation)

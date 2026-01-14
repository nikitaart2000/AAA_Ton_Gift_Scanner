# 🚀 Деплой Telegram Mini App

## Быстрый тест с ngrok (5 минут)

### 1. Установи ngrok
```bash
# Скачай: https://ngrok.com/download
# Или через chocolatey:
choco install ngrok
```

### 2. Запусти туннель
```bash
# В папке проекта
cd C:\Users\PC\Documents\Projects\AAA_Ton_Gift_Scanner

# Убедись что фронтенд работает на :5173
# Если нет - запусти: npm run dev в папке webapp

# Открой новый терминал и запусти ngrok
ngrok http 5173
```

Ты получишь URL типа: `https://abc123.ngrok-free.app`

### 3. Настрой бота в BotFather

Открой Telegram → @BotFather:

```
/mybots
→ Выбери @tongiftsbarygabot
→ Bot Settings
→ Menu Button
→ Configure Menu Button
→ Отправь URL: https://твой-ngrok-url.ngrok-free.app
→ Отправь название: Барыга Дилов 🦝💰
```

### 4. Тестируй!

Открой бота → увидишь кнопку Menu внизу → нажми → откроется твой Mini App! 🎉

---

## Продакшн деплой на Vercel (бесплатно, 10 минут)

### 1. Подготовь проект

```bash
cd webapp

# Создай production build
npm run build
```

### 2. Установи Vercel CLI

```bash
npm i -g vercel
```

### 3. Задеплой

```bash
# В папке webapp
vercel

# Следуй инструкциям:
# - Login через GitHub
# - Set up project: Yes
# - Which scope: твой аккаунт
# - Link to existing: No
# - Project name: ton-gifts-scanner
# - Directory: ./
# - Want to override settings: No

# После успешного деплоя получишь URL
```

### 4. Настрой environment variables на Vercel

В dashboard Vercel → Settings → Environment Variables:
```
VITE_API_URL=https://твой-api-url.com
```

### 5. Обнови API URL в коде

Если API тоже задеплоен, обнови URL в `webapp/src/api/client.ts`:
```typescript
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
```

### 6. Настрой бота (как в шаге 3 выше)

---

## API тоже нужно задеплоить!

Если хочешь чтобы все работало продакшн:

### Вариант 1: Railway (самый простой)
1. Зарегистрируйся на railway.app
2. New Project → Deploy from GitHub
3. Выбери свой репо
4. Railway автоматически определит Python и запустит

### Вариант 2: Render (бесплатный tier)
1. Зарегистрируйся на render.com
2. New → Web Service
3. Выбери репо
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `uvicorn src.api.app:app --host 0.0.0.0 --port $PORT`

### Вариант 3: VPS (для опытных)
- DigitalOcean, Linode, Hetzner
- Установи Docker, запусти через docker-compose

---

## Для локального теста БЕЗ деплоя

Можно протестировать через Telegram Web:
1. Открой https://web.telegram.org
2. Открой своего бота
3. Mini App должен открыться (но может не работать из-за localhost)

**Важно**: Для полноценной работы нужен HTTPS URL!

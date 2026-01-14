@echo off
echo ========================================
echo   TON GIFTS SCANNER - Mini App Test
echo ========================================
echo.
echo Этот скрипт запустит фронтенд и ngrok туннель
echo.

echo [1/3] Проверяем что фронтенд запущен...
curl -s http://localhost:5173 >nul 2>&1
if errorlevel 1 (
    echo ОШИБКА: Фронтенд не запущен на :5173
    echo Сначала запусти: cd webapp ^&^& npm run dev
    pause
    exit /b 1
)
echo ✓ Фронтенд работает!
echo.

echo [2/3] Запускаем ngrok туннель...
echo.
start cmd /k "ngrok http 5173"
echo.
echo Подожди 3 секунды...
timeout /t 3 >nul
echo.

echo [3/3] Настрой бота в @BotFather:
echo.
echo 1. Открой Telegram → @BotFather
echo 2. Отправь: /mybots
echo 3. Выбери: @tongiftsbarygabot
echo 4. Bot Settings → Menu Button → Configure Menu Button
echo 5. Скопируй URL из окна ngrok (начинается с https://)
echo 6. Отправь этот URL в BotFather
echo 7. Отправь название: Барыга Дилов 🦝💰
echo.
echo Готово! Теперь открой бота и нажми кнопку Menu!
echo.
pause

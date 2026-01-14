import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { initTelegramApp } from './telegram'

console.log('🚀 Starting TON Gifts Terminal...');

// Инициализация Telegram Mini App
initTelegramApp();

console.log('🎨 Rendering App component...');
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
console.log('✅ App rendered');

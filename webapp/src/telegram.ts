/**
 * Telegram Mini App integration
 */

// TODO: Update to latest @telegram-apps/sdk or use vanilla Telegram WebApp API
// import { initMiniApp, miniApp, themeParams, viewport } from '@telegram-apps/sdk';

export function initTelegramApp() {
  try {
    // Use vanilla Telegram WebApp API
    // @ts-ignore
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      tg.setHeaderColor('#0a0a15');
      console.log('✅ Telegram Mini App initialized');
      return true;
    }

    console.warn('⚠️ Not running in Telegram, using web fallback');
    return false;
  } catch (error) {
    console.warn('⚠️ Not running in Telegram, using web fallback');
    return false;
  }
}

export function getTelegramUserId(): number | null {
  try {
    // @ts-ignore
    const initData = window.Telegram?.WebApp?.initDataUnsafe;
    return initData?.user?.id || null;
  } catch {
    return null;
  }
}

export function openTelegramLink(url: string) {
  try {
    // @ts-ignore
    const tg = window.Telegram?.WebApp;
    if (tg && tg.openTelegramLink) {
      tg.openTelegramLink(url);
    } else {
      window.open(url, '_blank');
    }
  } catch {
    window.open(url, '_blank');
  }
}

export function openExternalLink(url: string) {
  try {
    // @ts-ignore
    const tg = window.Telegram?.WebApp;
    if (tg && tg.openLink) {
      tg.openLink(url);
    } else {
      window.open(url, '_blank');
    }
  } catch {
    window.open(url, '_blank');
  }
}

export function hapticFeedback(type: 'light' | 'medium' | 'heavy' | 'success' | 'warning' | 'error' = 'light') {
  try {
    // @ts-ignore
    const haptic = window.Telegram?.WebApp?.HapticFeedback;
    if (haptic) {
      if (type === 'success' || type === 'warning' || type === 'error') {
        haptic.notificationOccurred(type);
      } else {
        haptic.impactOccurred(type);
      }
    }
  } catch {
    // Fallback: nothing
  }
}

/**
 * ЖЕСТКАЯ ВИБРАЦИЯ для ЖИРНЫХ ДИЛОВ! 🔥
 * Вибрирует 5 секунд с интервалом
 */
export function hapticFeedbackIntense(durationMs: number = 5000) {
  try {
    // @ts-ignore
    const haptic = window.Telegram?.WebApp?.HapticFeedback;
    if (!haptic) {
      // Fallback: используем Web Vibration API
      if ('vibrate' in navigator) {
        // Паттерн: 200ms вибро, 100ms пауза, повторять
        const pattern: number[] = [];
        for (let i = 0; i < durationMs / 300; i++) {
          pattern.push(200, 100);
        }
        navigator.vibrate(pattern);
      }
      return;
    }

    // Telegram вибро - повторять heavy каждые 300ms
    let elapsed = 0;
    const interval = setInterval(() => {
      if (elapsed >= durationMs) {
        clearInterval(interval);
        return;
      }
      haptic.impactOccurred('heavy');
      elapsed += 300;
    }, 300);
  } catch (error) {
    console.warn('Vibration failed:', error);
  }
}

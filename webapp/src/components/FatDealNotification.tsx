/**
 * ЖИРНЫЙ ДИЛ NOTIFICATION - ТРЯСЕТ ЭКРАН! 🔥💰
 */

import { useEffect } from 'react';
import { type Deal } from '../types';
import { hapticFeedbackIntense } from '../telegram';

interface Props {
  deal: Deal;
  onClose: () => void;
}

export const FatDealNotification = ({ deal, onClose }: Props) => {
  useEffect(() => {
    // ЖЕСТКАЯ ВИБРАЦИЯ 5 секунд!
    hapticFeedbackIntense(5000);

    // Автоматически закрыть через 7 секунд
    const timeout = setTimeout(() => {
      onClose();
    }, 7000);

    return () => clearTimeout(timeout);
  }, [onClose]);

  return (
    <div
      className="fat-deal-notification"
      style={{
        position: 'fixed',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        zIndex: 9999,
        background: 'linear-gradient(135deg, #ff4444 0%, #ff0000 100%)',
        border: '4px solid #ffaa00',
        borderRadius: '24px',
        padding: '32px',
        maxWidth: '90%',
        boxShadow: '0 0 100px rgba(255, 68, 68, 0.8), 0 0 200px rgba(255, 170, 0, 0.6)',
        animation: 'shake 0.5s infinite, glow-pulse 1s ease-in-out infinite',
        textAlign: 'center',
      }}
      onClick={onClose}
    >
      {/* Emoji */}
      <div
        style={{
          fontSize: '80px',
          marginBottom: '16px',
          animation: 'spin 2s linear infinite',
        }}
      >
        💰🔥💎
      </div>

      {/* Title */}
      <div
        style={{
          fontSize: '32px',
          fontWeight: 'bold',
          color: '#fff',
          marginBottom: '12px',
          textShadow: '0 0 20px rgba(255, 255, 0, 0.8)',
        }}
      >
        ЖИРНЕЙШИЙ ДИЛ НАХУЙ!!!
      </div>

      {/* Deal info */}
      <div style={{ fontSize: '24px', color: '#fff', marginBottom: '8px' }}>
        {deal.gift_name}
      </div>
      <div
        style={{
          fontSize: '48px',
          fontWeight: 'bold',
          color: '#ffff00',
          marginBottom: '16px',
          textShadow: '0 0 30px rgba(255, 255, 0, 1)',
        }}
      >
        +{deal.profit_pct}% ПРОФИТА!
      </div>

      {/* Tap to close */}
      <div style={{ fontSize: '14px', color: 'rgba(255, 255, 255, 0.7)' }}>
        Тапни чтобы закрыть
      </div>
    </div>
  );
};

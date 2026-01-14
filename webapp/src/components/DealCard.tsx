/**
 * Карточка сделки - ГЛАВНЫЙ КОМПОНЕНТ
 */

import { type Deal } from '../types';
import { hapticFeedback, openTelegramLink } from '../telegram';

interface Props {
  deal: Deal;
  onClick?: () => void;
}

export const DealCard = ({ deal, onClick }: Props) => {
  // Badge mapping
  const badgeConfig = {
    GEM: { emoji: '💎', text: 'САМОЦВЕТ', color: '#00ff88' },
    HOT: { emoji: '🔥', text: 'ГОРЯЧ НАХУЙ', color: '#ff4444' },
    BLACK_PACK: { emoji: '🖤', text: 'BLACK PACK', color: '#000' },
    SNIPER: { emoji: '⚡', text: 'СНАЙПЕР', color: '#ffaa00' },
  };

  const badge = deal.quality_badge ? badgeConfig[deal.quality_badge] : null;

  // Confidence stars
  const confidenceStars = {
    very_high: '⭐⭐⭐⭐',
    high: '⭐⭐⭐',
    medium: '⭐⭐',
    low: '⭐',
  };

  // Format time in Calgary timezone (MST/MDT)
  const formatCalgaryTime = (timestamp: string) => {
    const date = new Date(timestamp);
    // Convert to Calgary timezone (America/Edmonton)
    const calgaryTime = date.toLocaleString('en-US', {
      timeZone: 'America/Edmonton',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
    return calgaryTime;
  };

  const handleClick = () => {
    hapticFeedback('light');
    if (onClick) onClick();
  };

  const handleOpenGift = (e: React.MouseEvent) => {
    e.stopPropagation();
    hapticFeedback('medium');
    // Открываем Fragment.com через встроенный браузер Telegram
    const tg = window.Telegram?.WebApp;
    if (tg && tg.openLink) {
      // openLink открывает во встроенном браузере Telegram
      tg.openLink(`https://fragment.com/gift/${deal.gift_id}`, { try_instant_view: true });
    } else {
      // Fallback для браузера вне Telegram
      window.open(`https://fragment.com/gift/${deal.gift_id}`, '_blank');
    }
  };

  const handleOpenTonnel = (e: React.MouseEvent) => {
    e.stopPropagation();
    hapticFeedback('medium');
    // Открываем Telegram Mini App Tonnel через openTelegramLink
    // Правильный формат: t.me/botname/appname?startapp=param
    openTelegramLink(`https://t.me/TonnelMarketBot/market?startapp=${deal.gift_id}`);
  };

  return (
    <div
      onClick={handleClick}
      className="deal-card"
      style={{
        background: 'rgba(20, 20, 30, 0.8)',
        backdropFilter: 'blur(20px)',
        border: deal.is_priority ? '2px solid #ff4444' : '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: '16px',
        padding: '16px',
        marginBottom: '12px',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        boxShadow: deal.is_priority
          ? '0 0 20px rgba(255, 68, 68, 0.3)'
          : '0 4px 12px rgba(0, 0, 0, 0.3)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = 'translateY(-2px)';
        e.currentTarget.style.boxShadow = deal.is_priority
          ? '0 4px 24px rgba(255, 68, 68, 0.5)'
          : '0 6px 16px rgba(0, 0, 0, 0.4)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.boxShadow = deal.is_priority
          ? '0 0 20px rgba(255, 68, 68, 0.3)'
          : '0 4px 12px rgba(0, 0, 0, 0.3)';
      }}
    >
      {/* Badge */}
      {badge && (
        <div
          style={{
            display: 'inline-block',
            padding: '4px 12px',
            borderRadius: '8px',
            background: badge.color,
            color: badge.color === '#000' ? '#fff' : '#000',
            fontSize: '12px',
            fontWeight: 'bold',
            marginBottom: '12px',
          }}
        >
          {badge.emoji} {badge.text}
        </div>
      )}

      {/* Photo + Info */}
      <div style={{ display: 'flex', gap: '12px' }}>
        {/* Photo */}
        {deal.photo_url && (
          <img
            src={deal.photo_url}
            alt={deal.gift_name}
            style={{
              width: '80px',
              height: '80px',
              borderRadius: '12px',
              objectFit: 'cover',
              border: '1px solid rgba(255, 255, 255, 0.1)',
            }}
          />
        )}

        {/* Info */}
        <div style={{ flex: 1 }}>
          {/* Name */}
          <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#fff', marginBottom: '4px' }}>
            {deal.gift_name}
            {deal.is_black_pack && ' 🖤'}
          </div>

          {/* Model + Backdrop */}
          <div style={{ fontSize: '13px', color: '#888', marginBottom: '8px' }}>
            {deal.model} • {deal.backdrop || 'без фона'}
            {deal.number && ` • #${deal.number}`}
          </div>

          {/* Price */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <span style={{ fontSize: '20px', fontWeight: 'bold', color: '#00ff88' }}>
              {deal.price} TON
            </span>
            {deal.reference_price && (
              <>
                <span style={{ fontSize: '14px', color: '#666' }}>→</span>
                <span style={{ fontSize: '14px', color: '#888', textDecoration: 'line-through' }}>
                  {deal.reference_price} TON
                </span>
              </>
            )}
          </div>

          {/* Profit */}
          {deal.profit_pct !== null && deal.profit_pct !== 0 && (
            <div
              style={{
                fontSize: '16px',
                fontWeight: 'bold',
                color: deal.profit_pct > 0 ? '#00ff88' : '#ff4444',
                marginBottom: '8px',
              }}
            >
              {deal.profit_pct > 0 ? '+' : ''}{deal.profit_pct.toFixed(1)}% {deal.profit_pct > 0 ? 'ПРОФИТА 💸' : 'УБЫТОК 📉'}
            </div>
          )}
          {(deal.profit_pct === null || deal.profit_pct === 0) && (
            <div style={{ fontSize: '14px', color: '#666', marginBottom: '8px' }}>
              ⏳ Профит рассчитывается...
            </div>
          )}

          {/* Stats */}
          <div
            style={{
              display: 'flex',
              gap: '16px',
              fontSize: '12px',
              color: '#aaa',
            }}
          >
            <div>
              {confidenceStars[deal.confidence_level]} {deal.confidence_level.toUpperCase()}
            </div>
            <div>💧 {deal.liquidity_score.toFixed(1)}/10</div>
            <div>🔥 {deal.hotness.toFixed(1)}/10</div>
            <div>📊 {deal.sales_48h} продаж</div>
          </div>

          {/* Time */}
          <div style={{ fontSize: '11px', color: '#666', marginTop: '8px' }}>
            ⏱️ {formatCalgaryTime(deal.event_time)}
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          marginTop: '12px',
          paddingTop: '12px',
          borderTop: '1px solid rgba(255, 255, 255, 0.05)',
        }}
      >
        <button
          onClick={handleOpenGift}
          style={{
            flex: 1,
            padding: '10px',
            background: 'linear-gradient(135deg, #00ff88 0%, #00cc66 100%)',
            border: 'none',
            borderRadius: '10px',
            color: '#000',
            fontWeight: 'bold',
            fontSize: '13px',
            cursor: 'pointer',
            transition: 'transform 0.1s ease',
          }}
          onMouseDown={(e) => {
            e.currentTarget.style.transform = 'scale(0.95)';
          }}
          onMouseUp={(e) => {
            e.currentTarget.style.transform = 'scale(1)';
          }}
        >
          🎁 ОТКРЫТЬ
        </button>
        <button
          onClick={handleOpenTonnel}
          style={{
            flex: 1,
            padding: '10px',
            background: 'rgba(255, 255, 255, 0.1)',
            border: '1px solid rgba(255, 255, 255, 0.2)',
            borderRadius: '10px',
            color: '#fff',
            fontWeight: 'bold',
            fontSize: '13px',
            cursor: 'pointer',
            transition: 'transform 0.1s ease',
          }}
          onMouseDown={(e) => {
            e.currentTarget.style.transform = 'scale(0.95)';
          }}
          onMouseUp={(e) => {
            e.currentTarget.style.transform = 'scale(1)';
          }}
        >
          🔍 TONNEL
        </button>
      </div>
    </div>
  );
};

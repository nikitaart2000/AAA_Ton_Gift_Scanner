/**
 * ЕНОТ-БАРЫГА LOADER 🦝💰
 * Милый енот ловит зелёные баксы!
 */

import './RaccoonLoader.css';

export const RaccoonLoader = () => {
  return (
    <div className="raccoon-loader">
      {/* Падающие баксы - БОЛЬШЕ! */}
      <div className="money-rain">
        {[...Array(35)].map((_, i) => (
          <div
            key={i}
            className="money"
            style={{
              left: `${Math.random() * 100}%`,
              animationDelay: `${Math.random() * 3}s`,
              animationDuration: `${1.5 + Math.random() * 2}s`,
            }}
          >
            💵
          </div>
        ))}
      </div>

      {/* Просто милый енот */}
      <div className="raccoon-container">
        <div className="raccoon-emoji">🦝</div>
      </div>

      {/* Текст */}
      <div className="loader-text">
        <div className="loader-title">ЛОВИМ ЖИРНЫЕ ДИЛЫ...</div>
        <div className="loader-subtitle">Барыжим нахуй! 🔥</div>
      </div>
    </div>
  );
};

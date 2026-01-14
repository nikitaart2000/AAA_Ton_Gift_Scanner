import React, { useState } from 'react';
import { hapticFeedback } from '../telegram';

interface FiltersSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onApply: (filters: Filters) => void;
  currentFilters: Filters;
}

export interface Filters {
  minProfit: number;
  maxPrice: number | null;
  blackPackOnly: boolean;
  sortBy: 'smart' | 'profit' | 'hotness' | 'liquidity' | 'time';
}

export const FiltersSidebar: React.FC<FiltersSidebarProps> = ({
  isOpen,
  onClose,
  onApply,
  currentFilters,
}) => {
  const [filters, setFilters] = useState<Filters>(currentFilters);

  const handleApply = () => {
    hapticFeedback('medium');
    onApply(filters);
    onClose();
  };

  const handleReset = () => {
    hapticFeedback('light');
    const defaultFilters: Filters = {
      minProfit: 0,
      maxPrice: null,
      blackPackOnly: false,
      sortBy: 'smart',
    };
    setFilters(defaultFilters);
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.7)',
          backdropFilter: 'blur(4px)',
          zIndex: 1000,
          animation: 'fadeIn 0.2s ease',
        }}
      />

      {/* Sidebar */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          bottom: 0,
          width: '320px',
          maxWidth: '85vw',
          background: 'linear-gradient(135deg, #0a0a15 0%, #1a1a2e 100%)',
          backdropFilter: 'blur(20px)',
          borderLeft: '1px solid rgba(0, 255, 136, 0.2)',
          boxShadow: '-4px 0 20px rgba(0, 0, 0, 0.5)',
          padding: '24px',
          zIndex: 1001,
          animation: 'slideInRight 0.3s ease',
          overflowY: 'auto',
        }}
      >
        {/* Header */}
        <div style={{ marginBottom: '32px' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '8px',
            }}
          >
            <h2
              style={{
                fontSize: '24px',
                fontWeight: 'bold',
                color: '#00ff88',
                margin: 0,
              }}
            >
              ФИЛЬТРЫ 🎯
            </h2>
            <button
              onClick={onClose}
              style={{
                background: 'none',
                border: 'none',
                color: '#888',
                fontSize: '28px',
                cursor: 'pointer',
                padding: 0,
                lineHeight: 1,
              }}
            >
              ×
            </button>
          </div>
          <p style={{ color: '#666', fontSize: '13px', margin: 0 }}>
            Настрой поиск жирных дилов нахуй
          </p>
        </div>

        {/* Min Profit */}
        <div style={{ marginBottom: '28px' }}>
          <label
            style={{
              display: 'block',
              color: '#00ff88',
              fontSize: '14px',
              fontWeight: 'bold',
              marginBottom: '12px',
            }}
          >
            💰 МИН. ПРОФИТ: {filters.minProfit}%
          </label>
          <input
            type="range"
            min="0"
            max="100"
            step="5"
            value={filters.minProfit}
            onChange={(e) => {
              hapticFeedback('light');
              setFilters({ ...filters, minProfit: Number(e.target.value) });
            }}
            style={{
              width: '100%',
              height: '6px',
              background: 'linear-gradient(90deg, #00ff88 0%, #00aa55 100%)',
              borderRadius: '3px',
              outline: 'none',
              cursor: 'pointer',
            }}
          />
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              color: '#666',
              fontSize: '11px',
              marginTop: '4px',
            }}
          >
            <span>0%</span>
            <span>50%</span>
            <span>100%</span>
          </div>
        </div>

        {/* Max Price */}
        <div style={{ marginBottom: '28px' }}>
          <label
            style={{
              display: 'block',
              color: '#00ff88',
              fontSize: '14px',
              fontWeight: 'bold',
              marginBottom: '12px',
            }}
          >
            💎 МАКС. ЦЕНА: {filters.maxPrice || '∞'} TON
          </label>
          <input
            type="number"
            placeholder="Без лимита"
            value={filters.maxPrice || ''}
            onChange={(e) => {
              hapticFeedback('light');
              setFilters({
                ...filters,
                maxPrice: e.target.value ? Number(e.target.value) : null,
              });
            }}
            style={{
              width: '100%',
              padding: '12px',
              background: 'rgba(20, 20, 30, 0.8)',
              border: '1px solid rgba(0, 255, 136, 0.3)',
              borderRadius: '8px',
              color: '#fff',
              fontSize: '16px',
              outline: 'none',
            }}
          />
        </div>

        {/* Black Pack Only */}
        <div style={{ marginBottom: '28px' }}>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              cursor: 'pointer',
              padding: '16px',
              background: filters.blackPackOnly
                ? 'rgba(0, 255, 136, 0.1)'
                : 'rgba(20, 20, 30, 0.8)',
              border: filters.blackPackOnly
                ? '2px solid #00ff88'
                : '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '12px',
              transition: 'all 0.2s ease',
            }}
            onClick={() => {
              hapticFeedback('medium');
              setFilters({ ...filters, blackPackOnly: !filters.blackPackOnly });
            }}
          >
            <input
              type="checkbox"
              checked={filters.blackPackOnly}
              onChange={() => {}}
              style={{ display: 'none' }}
            />
            <div
              style={{
                width: '24px',
                height: '24px',
                borderRadius: '6px',
                background: filters.blackPackOnly ? '#00ff88' : 'rgba(255, 255, 255, 0.1)',
                marginRight: '12px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '16px',
                transition: 'all 0.2s ease',
              }}
            >
              {filters.blackPackOnly && '✓'}
            </div>
            <div>
              <div
                style={{
                  color: '#fff',
                  fontSize: '15px',
                  fontWeight: 'bold',
                  marginBottom: '2px',
                }}
              >
                🖤 ТОЛЬКО BLACK PACK
              </div>
              <div style={{ color: '#666', fontSize: '12px' }}>
                Самые дорогие фоны
              </div>
            </div>
          </label>
        </div>

        {/* Sort By */}
        <div style={{ marginBottom: '32px' }}>
          <label
            style={{
              display: 'block',
              color: '#00ff88',
              fontSize: '14px',
              fontWeight: 'bold',
              marginBottom: '12px',
            }}
          >
            📊 СОРТИРОВКА
          </label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {[
              { value: 'smart', label: '🧠 УМНАЯ', desc: 'По всем метрикам' },
              { value: 'profit', label: '💰 ПРОФИТ', desc: 'Самый большой %' },
              { value: 'hotness', label: '🔥 ГОРЯЧИЕ', desc: 'Популярные' },
              { value: 'liquidity', label: '💧 ЛИКВИДНОСТЬ', desc: 'Легко продать' },
              { value: 'time', label: '⏰ СВЕЖИЕ', desc: 'Новые листинги' },
            ].map((option) => (
              <button
                key={option.value}
                onClick={() => {
                  hapticFeedback('light');
                  setFilters({ ...filters, sortBy: option.value as Filters['sortBy'] });
                }}
                style={{
                  padding: '12px',
                  background:
                    filters.sortBy === option.value
                      ? 'rgba(0, 255, 136, 0.15)'
                      : 'rgba(20, 20, 30, 0.8)',
                  border:
                    filters.sortBy === option.value
                      ? '2px solid #00ff88'
                      : '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '8px',
                  color: '#fff',
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s ease',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div>
                  <div style={{ fontSize: '14px', fontWeight: 'bold' }}>{option.label}</div>
                  <div style={{ fontSize: '11px', color: '#666' }}>{option.desc}</div>
                </div>
                {filters.sortBy === option.value && (
                  <span style={{ color: '#00ff88', fontSize: '18px' }}>✓</span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: '12px' }}>
          <button
            onClick={handleReset}
            style={{
              flex: 1,
              padding: '14px',
              background: 'rgba(255, 68, 68, 0.1)',
              border: '1px solid rgba(255, 68, 68, 0.3)',
              borderRadius: '10px',
              color: '#ff4444',
              fontSize: '15px',
              fontWeight: 'bold',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255, 68, 68, 0.2)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255, 68, 68, 0.1)';
            }}
          >
            СБРОС
          </button>
          <button
            onClick={handleApply}
            style={{
              flex: 2,
              padding: '14px',
              background: 'linear-gradient(135deg, #00ff88 0%, #00aa55 100%)',
              border: 'none',
              borderRadius: '10px',
              color: '#000',
              fontSize: '15px',
              fontWeight: 'bold',
              cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(0, 255, 136, 0.3)',
              transition: 'all 0.2s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow = '0 6px 16px rgba(0, 255, 136, 0.4)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 4px 12px rgba(0, 255, 136, 0.3)';
            }}
          >
            ПРИМЕНИТЬ 🚀
          </button>
        </div>
      </div>

      <style>
        {`
          @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
          }

          @keyframes slideInRight {
            from {
              transform: translateX(100%);
            }
            to {
              transform: translateX(0);
            }
          }
        `}
      </style>
    </>
  );
};

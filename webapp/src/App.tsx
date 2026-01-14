/**
 * TON GIFTS TERMINAL
 * Главное приложение
 */

import { useEffect, useState } from 'react';
import { apiClient } from './api/client';
import { DealCard } from './components/DealCard';
import { FatDealNotification } from './components/FatDealNotification';
import { RaccoonLoader } from './components/RaccoonLoader';
import { FiltersSidebar, type Filters } from './components/FiltersSidebar';
import { wsClient } from './websocket';
import { hapticFeedback } from './telegram';
import type { Deal, MarketOverview } from './types';
import './App.css';

function App() {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [fatDeal, setFatDeal] = useState<Deal | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'all' | 'profitable' | 'black'>('all');
  const [filters, setFilters] = useState<Filters>({
    minProfit: 0,
    maxPrice: null,
    blackPackOnly: false,
    sortBy: 'smart',
  });

  // Load data
  useEffect(() => {
    let previousDeals: Deal[] = [];
    const minLoadingTime = 2000; // Показывать енота минимум 2 секунды
    const startTime = Date.now();

    const loadData = async () => {
      try {
        console.log('🔄 Загружаем дилы с фильтрами:', filters);
        const [dealsData, overviewData] = await Promise.all([
          apiClient.getDeals({
            page: 0,
            page_size: 50,
            min_profit: filters.minProfit,
            max_price: filters.maxPrice || undefined,
            black_pack_only: filters.blackPackOnly,
            sort_by: filters.sortBy,
          }),
          apiClient.getMarketOverview(),
        ]);

        console.log('✅ Получено дилов:', dealsData.deals.length, '/ Всего:', dealsData.total);
        const newDeals = dealsData.deals;

        // Проверить на ЖИРНЫЙ дил (новый дил с profit >= 30% и GEM/SNIPER badge)
        if (previousDeals.length > 0) {
          const newFatDeals = newDeals.filter((deal) => {
            const isNew = !previousDeals.some((prev) => prev.gift_id === deal.gift_id);
            const isFat = deal.profit_pct >= 30 && (deal.quality_badge === 'GEM' || deal.quality_badge === 'SNIPER');
            return isNew && isFat;
          });

          if (newFatDeals.length > 0 && !fatDeal) {
            // ЖИРНЫЙ ДИЛ DETECTED! 🔥💰
            setFatDeal(newFatDeals[0]);
          }
        }

        previousDeals = newDeals;
        setDeals(newDeals);
        setOverview(overviewData);

        // Гарантируем минимум 2 сек показа енота
        const elapsed = Date.now() - startTime;
        if (elapsed < minLoadingTime) {
          await new Promise((resolve) => setTimeout(resolve, minLoadingTime - elapsed));
        }
      } catch (error) {
        console.error('❌ Ошибка загрузки:', error);
      } finally {
        setLoading(false);
      }
    };

    loadData();

    // Refresh every 30 seconds (WebSocket будет обновлять чаще)
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [fatDeal, filters]);

  // WebSocket для real-time обновлений
  useEffect(() => {
    console.log('🔌 Подключаем WebSocket...');
    wsClient.connect();

    const unsubscribe = wsClient.subscribe((message) => {
      if (message.type === 'connected') {
        console.log('✅', message.message);
        hapticFeedback('light');
      } else if (message.type === 'new_deal') {
        console.log('🔥 Новый дил!', message.data);
        hapticFeedback('medium');

        // Проверить на ЖИРНЫЙ дил
        const deal = message.data;
        if (deal.profit_pct >= 30 && (deal.quality_badge === 'GEM' || deal.quality_badge === 'SNIPER')) {
          setFatDeal(deal);
        }

        // Добавить в начало списка
        setDeals((prev) => [deal, ...prev].slice(0, 50));
      } else if (message.type === 'market_update') {
        console.log('📊 Обновление рынка');
        setOverview(message.data);
      }
    });

    return () => {
      console.log('🔌 Отключаем WebSocket');
      unsubscribe();
      wsClient.disconnect();
    };
  }, []);

  if (loading) {
    return <RaccoonLoader />;
  }

  return (
    <>
      {/* ЖИРНЫЙ ДИЛ NOTIFICATION */}
      {fatDeal && <FatDealNotification deal={fatDeal} onClose={() => setFatDeal(null)} />}

      {/* ФИЛЬТРЫ SIDEBAR */}
      <FiltersSidebar
        isOpen={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        onApply={(newFilters) => setFilters(newFilters)}
        currentFilters={filters}
      />

      <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-title">
          <span style={{ fontSize: '24px' }}>🎯</span>
          <div style={{ display: 'flex', flexDirection: 'column', marginLeft: '8px' }}>
            <span style={{ fontWeight: 'bold' }}>TON GIFTS TERMINAL</span>
            <span style={{ fontSize: '9px', color: '#666', marginTop: '-2px' }}>v2.0</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
        <button
          onClick={() => window.location.reload()}
          style={{
            background: 'rgba(0, 136, 255, 0.1)',
            border: '1px solid rgba(0, 136, 255, 0.3)',
            borderRadius: '8px',
            color: '#0088ff',
            padding: '8px 12px',
            fontSize: '14px',
            fontWeight: 'bold',
            cursor: 'pointer',
          }}
        >
          🔄
        </button>
        <button
          onClick={() => setFiltersOpen(true)}
          style={{
            background: 'rgba(0, 255, 136, 0.1)',
            border: '1px solid rgba(0, 255, 136, 0.3)',
            borderRadius: '8px',
            color: '#00ff88',
            padding: '8px 16px',
            fontSize: '14px',
            fontWeight: 'bold',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            transition: 'all 0.2s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(0, 255, 136, 0.2)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'rgba(0, 255, 136, 0.1)';
          }}
        >
          🎯 ФИЛЬТРЫ
          {(filters.minProfit > 0 || filters.maxPrice || filters.blackPackOnly) && (
            <span style={{
              background: '#00ff88',
              color: '#000',
              borderRadius: '50%',
              width: '6px',
              height: '6px',
              display: 'inline-block',
            }} />
          )}
        </button>
        </div>
      </header>
      <div className="header-subtitle" style={{ textAlign: 'center', marginTop: '8px' }}>
        ПРОФИТ ИЛИ НАХУЙ
      </div>

      {/* Market Overview */}
      {overview && (
        <div className="overview">
          <div className="overview-stat">
            <div className="overview-value">{overview.active_deals}</div>
            <div className="overview-label">Активных дилов</div>
          </div>
          <div className="overview-stat">
            <div className="overview-value" style={{ color: '#ff4444' }}>
              🔥 {overview.hot_deals}
            </div>
            <div className="overview-label">Горячих</div>
          </div>
          <div className="overview-stat">
            <div className="overview-value" style={{ color: '#00ff88' }}>
              ⚡ {overview.priority_deals}
            </div>
            <div className="overview-label">Приоритетных</div>
          </div>
          {overview.black_pack_floor && (
            <div className="overview-stat">
              <div className="overview-value">🖤 {overview.black_pack_floor}</div>
              <div className="overview-label">Black Pack Floor</div>
            </div>
          )}
        </div>
      )}

      {/* Feed Tabs */}
      <div className="tabs">
        <div
          className={`tab ${activeTab === 'all' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('all');
            setFilters({ ...filters, minProfit: 0, blackPackOnly: false });
            hapticFeedback('light');
          }}
          style={{ cursor: 'pointer' }}
        >
          🔥 ВСЕ ДИЛЫ
        </div>
        <div
          className={`tab ${activeTab === 'profitable' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('profitable');
            setFilters({ ...filters, minProfit: 10, blackPackOnly: false });
            hapticFeedback('light');
          }}
          style={{ cursor: 'pointer' }}
        >
          💎 ТОЛЬКО ПРОФИТНЫЕ
        </div>
        <div
          className={`tab ${activeTab === 'black' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('black');
            setFilters({ ...filters, minProfit: 0, blackPackOnly: true });
            hapticFeedback('light');
          }}
          style={{ cursor: 'pointer' }}
        >
          🖤 BLACK PACK
        </div>
      </div>

      {/* Deals Feed */}
      <div className="feed">
        {deals.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px', color: '#666' }}>
            <div style={{ fontSize: '48px', marginBottom: '16px' }}>😴</div>
            <div>Нет дилов. Ждем...</div>
          </div>
        ) : (
          deals.map((deal) => (
            <DealCard
              key={deal.gift_id}
              deal={deal}
              onClick={() => {
                // TODO: Open detail view
                console.log('Clicked deal:', deal);
              }}
            />
          ))
        )}
      </div>
    </div>
    </>
  );
}

export default App;

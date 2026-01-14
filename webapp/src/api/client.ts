/**
 * API client для связи с backend
 */

import type { DealsResponse, MarketOverview } from '../types';

// API URL - используем относительный путь для Vite proxy, или переопределяем через environment variable
const API_BASE = import.meta.env.VITE_API_URL || '/api';

export class ApiClient {
  async getDeals(params?: {
    page?: number;
    page_size?: number;
    sort_by?: string;
    min_profit?: number;
    max_price?: number;
    black_pack_only?: boolean;
  }): Promise<DealsResponse> {
    // Фильтруем undefined значения и min_profit=0 (чтобы не передавать его в API)
    const filteredParams = Object.fromEntries(
      Object.entries(params || {}).filter(([key, v]) => {
        if (v === undefined) return false;
        if (key === 'min_profit' && v === 0) return false; // Не передаём min_profit=0
        return true;
      })
    );
    const query = new URLSearchParams(filteredParams as any).toString();
    const response = await fetch(`${API_BASE}/deals/feed?${query}`);
    if (!response.ok) throw new Error('Не удалось загрузить дилы');
    return response.json();
  }

  async getMarketOverview(): Promise<MarketOverview> {
    const response = await fetch(`${API_BASE}/deals/overview`);
    if (!response.ok) throw new Error('Не удалось загрузить обзор рынка');
    return response.json();
  }
}

export const apiClient = new ApiClient();

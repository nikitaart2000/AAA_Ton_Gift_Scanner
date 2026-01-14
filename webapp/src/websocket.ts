/**
 * WebSocket client для real-time обновлений
 */

export type WebSocketMessage =
  | { type: 'connected'; message: string; timestamp: string }
  | { type: 'ping'; timestamp: string }
  | { type: 'pong'; timestamp: string }
  | { type: 'new_deal'; data: any; timestamp: string }
  | { type: 'market_update'; data: any; timestamp: string };

export type MessageHandler = (message: WebSocketMessage) => void;

export class WSClient {
  private ws: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private pingTimer: number | null = null;
  private handlers: Set<MessageHandler> = new Set();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private url: string;

  constructor(url?: string) {
    // WebSocket URL - используем относительный путь (Vercel proxy)
    if (url) {
      this.url = url;
    } else {
      // Используем относительный путь
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      this.url = `${protocol}//${window.location.host}/api/ws`;
    }
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      console.log('WebSocket уже подключен');
      return;
    }

    console.log('🔌 Подключаемся к WebSocket...');

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log('✅ WebSocket подключен!');
        this.reconnectAttempts = 0;
        this.startPing();
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          console.log('📨 WebSocket message:', message.type);

          // Обработать pong
          if (message.type === 'pong') {
            // Сервер жив
            return;
          }

          // Уведомить всех подписчиков
          this.handlers.forEach((handler) => {
            try {
              handler(message);
            } catch (e) {
              console.error('Ошибка в handler:', e);
            }
          });
        } catch (e) {
          console.error('Ошибка парсинга WebSocket message:', e);
        }
      };

      this.ws.onerror = (error) => {
        console.error('❌ WebSocket ошибка:', error);
      };

      this.ws.onclose = () => {
        console.log('🔌 WebSocket отключен');
        this.stopPing();
        this.scheduleReconnect();
      };
    } catch (e) {
      console.error('Ошибка создания WebSocket:', e);
      this.scheduleReconnect();
    }
  }

  private startPing() {
    this.stopPing();
    this.pingTimer = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send('ping');
      }
    }, 15000); // Ping каждые 15 секунд
  }

  private stopPing() {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) {
      return;
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('🔴 Превышено число попыток переподключения');
      return;
    }

    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectAttempts++;

    console.log(`🔄 Переподключение через ${delay / 1000}s (попытка ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  subscribe(handler: MessageHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  disconnect() {
    this.stopPing();

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

// Singleton instance
export const wsClient = new WSClient();

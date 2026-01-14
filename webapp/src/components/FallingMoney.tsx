/**
 * Falling Money Animation - падающие доллары на фоне
 */
import { useEffect, useState } from 'react';
import './FallingMoney.css';

interface MoneyBill {
  id: number;
  left: number;
  animationDuration: number;
  animationDelay: number;
  rotation: number;
}

export function FallingMoney() {
  const [bills, setBills] = useState<MoneyBill[]>([]);

  useEffect(() => {
    console.log('💵 FallingMoney component mounted');
    // Создаём 15 долларов с рандомными параметрами
    const moneyBills: MoneyBill[] = Array.from({ length: 15 }, (_, i) => ({
      id: i,
      left: Math.random() * 100, // позиция по горизонтали (0-100%)
      animationDuration: 8 + Math.random() * 7, // длительность падения (8-15 секунд)
      animationDelay: Math.random() * 5, // задержка старта (0-5 секунд)
      rotation: Math.random() * 360, // начальный поворот
    }));

    console.log('💵 Created', moneyBills.length, 'money bills');
    setBills(moneyBills);
  }, []);

  return (
    <div className="falling-money-container">
      {bills.map((bill) => (
        <div
          key={bill.id}
          className="money-bill"
          style={{
            left: `${bill.left}%`,
            animationDuration: `${bill.animationDuration}s`,
            animationDelay: `${bill.animationDelay}s`,
            transform: `rotate(${bill.rotation}deg)`,
          }}
        >
          💵
        </div>
      ))}
    </div>
  );
}

"""Check database data."""
import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect('postgresql://scanner_user:scanner_password_2024@localhost:5432/ton_gifts_scanner')

    # Check active_listings
    listings_count = await conn.fetchval('SELECT COUNT(*) FROM active_listings')
    print(f'active_listings rows: {listings_count}')

    # Check asset_analytics
    count = await conn.fetchval('SELECT COUNT(*) FROM asset_analytics')
    print(f'asset_analytics rows: {count}')

    if count > 0:
        sample = await conn.fetch('SELECT asset_key, floor_2nd, liquidity_score, sales_7d FROM asset_analytics LIMIT 5')
        for r in sample:
            print(f"  {r['asset_key']}: floor={r['floor_2nd']}, liq={r['liquidity_score']}, sales={r['sales_7d']}")

        # Count how many have floor
        with_floor = await conn.fetchval('SELECT COUNT(*) FROM asset_analytics WHERE floor_2nd IS NOT NULL')
        print(f'  with floor_2nd: {with_floor}')

    # Check recent market_events (last 2 hours)
    from datetime import datetime, timedelta, timezone
    time_threshold = datetime.now(timezone.utc) - timedelta(hours=2)

    recent_count = await conn.fetchval('''
        SELECT COUNT(*)
        FROM market_events
        WHERE event_time >= $1
    ''', time_threshold)
    print(f'\nmarket_events in last 2 hours: {recent_count}')

    recent_listing_count = await conn.fetchval('''
        SELECT COUNT(*)
        FROM market_events
        WHERE event_time >= $1
          AND event_type IN ('listing', 'change_price')
    ''', time_threshold)
    print(f'listing/change_price events: {recent_listing_count}')

    # Check market_events with analytics join
    join_count = await conn.fetchval('''
        SELECT COUNT(DISTINCT me.gift_id)
        FROM market_events me
        LEFT JOIN asset_analytics aa ON (COALESCE(me.model, 'no_model') || ':' || COALESCE(me.backdrop, 'no_bg')) = aa.asset_key
        WHERE aa.floor_2nd IS NOT NULL
    ''')
    print(f'\nmarket_events with analytics: {join_count}')

    # Check asset_key mismatch
    me_samples = await conn.fetch('''
        SELECT DISTINCT
            COALESCE(model, 'no_model') || ':' || COALESCE(backdrop, 'no_bg') as computed_key,
            model,
            backdrop
        FROM market_events
        WHERE event_time >= $1
        LIMIT 5
    ''', time_threshold)
    print('\nmarket_events asset_key samples:')
    for s in me_samples:
        print(f"  {s['computed_key']} (model={s['model']}, backdrop={s['backdrop']})")

    aa_samples = await conn.fetch('''
        SELECT asset_key FROM asset_analytics LIMIT 5
    ''')
    print('\nasset_analytics asset_key samples:')
    for s in aa_samples:
        print(f"  {s['asset_key']}")

    # Check example deal with profit
    example = await conn.fetchrow('''
        SELECT me.gift_id, me.price, aa.floor_2nd,
               ((aa.floor_2nd - me.price) / me.price) * 100 as profit_pct
        FROM market_events me
        LEFT JOIN asset_analytics aa ON (COALESCE(me.model, 'no_model') || ':' || COALESCE(me.backdrop, 'no_bg')) = aa.asset_key
        WHERE aa.floor_2nd IS NOT NULL
        LIMIT 1
    ''')
    if example:
        print(f"\nExample: gift={example['gift_id']}, price={example['price']}, floor={example['floor_2nd']}, profit={example['profit_pct']:.2f}%")
    else:
        print("\nNo deals found with floor price!")

    await conn.close()

asyncio.run(main())

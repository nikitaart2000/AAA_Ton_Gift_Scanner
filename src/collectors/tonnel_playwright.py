"""Tonnel market collector via Playwright (bypass Cloudflare)."""

import asyncio
import logging
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional, Callable, Awaitable, List
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from src.config import settings
from src.core.models import ActiveListing, EventSource

logger = logging.getLogger(__name__)


class TonnelPlaywrightCollector:
    """Collector for Tonnel market listings using Playwright to bypass Cloudflare."""

    def __init__(self):
        self.base_url = settings.TONNEL_BASE_URL
        self.auth_data = settings.TONNEL_AUTH_DATA
        self.running = False
        self.listing_handler: Optional[Callable[[List[ActiveListing]], Awaitable[None]]] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def start(self, listing_handler: Callable[[List[ActiveListing]], Awaitable[None]]):
        """Start collecting listings."""
        self.listing_handler = listing_handler
        self.running = True

        logger.info("Tonnel Playwright collector started")

        # Initialize browser
        await self._init_browser()

        # Start periodic sync
        await self._sync_listings_loop()

    async def stop(self):
        """Stop collector."""
        self.running = False

        # Close browser
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()

        logger.info("Tonnel Playwright collector stopped")

    async def _init_browser(self):
        """Initialize Playwright browser."""
        playwright = await async_playwright().start()

        # Launch browser in headless mode
        self.browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )

        # Create context with realistic settings
        self.context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/Edmonton',
        )

        # Create page
        self.page = await self.context.new_page()

        # Add stealth scripts
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        logger.info("Browser initialized successfully")

    async def _sync_listings_loop(self):
        """Periodically sync all active listings."""
        while self.running:
            try:
                await self._fetch_and_process_listings()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error syncing listings: {e}", exc_info=True)

            # Wait before next sync
            await asyncio.sleep(settings.TONNEL_SYNC_INTERVAL)

    async def _fetch_and_process_listings(self):
        """Fetch all listings using Playwright."""
        logger.info("Fetching listings from Tonnel via Playwright...")

        try:
            # Navigate to the actual market page (not just base URL)
            market_url = "https://market.tonnel.network/"
            await self.page.goto(market_url, wait_until='networkidle', timeout=60000)

            # Wait for Cloudflare challenge and check if page loaded
            logger.info("Waiting for Cloudflare challenge...")
            await asyncio.sleep(15)

            # Check if we successfully loaded the page (not blocked by CF)
            page_title = await self.page.title()
            logger.info(f"Page title: {page_title}")

            if "Just a moment" in page_title or "Cloudflare" in page_title:
                logger.error("Still blocked by Cloudflare challenge")
                return

            # Get all cookies from the browser after CF challenge passed
            cookies = await self.context.cookies()
            logger.info(f"Got {len(cookies)} cookies from browser")

            # Now make API request using JavaScript fetch() with cookies
            all_listings = []
            page_num = 1
            max_pages = 10  # Safety limit

            while page_num <= max_pages:
                # Prepare request body
                payload = {
                    "authData": self.auth_data,
                    "page": page_num,
                    "limit": 100,
                    "sort": "price_asc",
                }

                try:
                    # Use page.route to intercept and modify requests
                    # Create a new page for API request to avoid CORS issues
                    api_response = await self.page.evaluate("""
                        async (payload) => {
                            // Create a form and submit it to avoid CORS
                            const form = document.createElement('form');
                            form.method = 'POST';
                            form.action = '/api/pageGifts';
                            form.style.display = 'none';

                            const input = document.createElement('input');
                            input.type = 'hidden';
                            input.name = 'data';
                            input.value = JSON.stringify(payload);
                            form.appendChild(input);

                            document.body.appendChild(form);

                            // Actually, let's try XMLHttpRequest instead
                            return new Promise((resolve, reject) => {
                                const xhr = new XMLHttpRequest();
                                xhr.open('POST', '/api/pageGifts', true);
                                xhr.setRequestHeader('Content-Type', 'application/json');
                                xhr.onload = function() {
                                    if (xhr.status === 200) {
                                        try {
                                            resolve({success: true, data: JSON.parse(xhr.responseText)});
                                        } catch (e) {
                                            resolve({success: false, error: 'Failed to parse JSON'});
                                        }
                                    } else {
                                        resolve({success: false, status: xhr.status, error: xhr.responseText});
                                    }
                                };
                                xhr.onerror = function() {
                                    resolve({success: false, error: 'Network error'});
                                };
                                xhr.send(JSON.stringify(payload));
                            });
                        }
                    """, payload)

                    if not api_response.get('success'):
                        logger.error(f"API request failed: {api_response.get('error', 'Unknown error')}")
                        break

                    response_text = json.dumps(api_response['data'])

                    # Parse JSON response
                    data = json.loads(response_text)

                    # Extract listings
                    listings_data = data if isinstance(data, list) else data.get("gifts", [])

                    if not listings_data:
                        break  # No more listings

                    # Parse listings
                    for listing_data in listings_data:
                        listing = self._parse_listing(listing_data)
                        if listing:
                            all_listings.append(listing)

                    logger.info(f"Fetched {len(listings_data)} listings from page {page_num}")

                    # Check if there are more pages
                    if len(listings_data) < payload["limit"]:
                        break  # Last page

                    page_num += 1

                except Exception as e:
                    logger.error(f"Error fetching page {page_num}: {e}", exc_info=True)
                    break

            logger.info(f"Total listings fetched: {len(all_listings)}")

            # Send to handler
            if all_listings and self.listing_handler:
                await self.listing_handler(all_listings)

        except Exception as e:
            logger.error(f"Failed to fetch listings: {e}", exc_info=True)

    def _parse_listing(self, listing_data: dict) -> Optional[ActiveListing]:
        """Parse listing data into ActiveListing."""
        try:
            gift_id = listing_data.get("gift_id") or listing_data.get("asset")
            if not gift_id:
                return None

            price_value = listing_data.get("price")
            if price_value is None:
                return None

            price = Decimal(str(price_value))

            # Parse timestamps
            listed_at = None
            export_at = None

            if listing_data.get("listed_at"):
                listed_at = self._parse_timestamp(listing_data["listed_at"])

            if listing_data.get("export_at"):
                export_at = self._parse_timestamp(listing_data["export_at"])

            # Extract attributes
            gift_name = listing_data.get("name") or listing_data.get("gift_name")
            model = listing_data.get("model")
            backdrop = listing_data.get("backdrop")
            pattern = listing_data.get("pattern") or listing_data.get("symbol")
            number = listing_data.get("number")

            return ActiveListing(
                gift_id=gift_id,
                gift_name=gift_name,
                model=model,
                backdrop=backdrop,
                pattern=pattern,
                number=number,
                price=price,
                listed_at=listed_at,
                export_at=export_at,
                source=EventSource.TONNEL,
                raw_data=listing_data,
            )

        except Exception as e:
            logger.error(f"Error parsing listing: {e}", exc_info=True)
            return None

    def _parse_timestamp(self, ts_value) -> Optional[datetime]:
        """Parse timestamp from various formats."""
        try:
            if isinstance(ts_value, (int, float)):
                # Unix timestamp
                return datetime.fromtimestamp(ts_value)
            elif isinstance(ts_value, str):
                # ISO format
                return datetime.fromisoformat(ts_value.replace("Z", "+00:00"))
            return None
        except Exception as e:
            logger.error(f"Error parsing timestamp {ts_value}: {e}")
            return None

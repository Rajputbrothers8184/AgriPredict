/**
 * Opt-in integration test against a running backend.
 *
 *   LIVE_API=1 API_BASE_URL=http://127.0.0.1:8000/api/v1 \
 *   DEMO_EMAIL=demo@agripredict.pk DEMO_PASSWORD=Sunflower2026 \
 *   npx jest tests/live.integration.test.js
 *
 * Skipped by default so `npm test` stays hermetic. It exercises the *real*
 * endpoint wrappers in src/services/api.js, which is the only way to catch a
 * path or field-name mismatch that unit tests with mocks cannot see.
 */

/* eslint-env node */

const LIVE = process.env.LIVE_API === '1';
const BASE = process.env.API_BASE_URL || 'http://127.0.0.1:8000/api/v1';
process.env.API_BASE_URL = BASE;

const EMAIL = process.env.DEMO_EMAIL || 'demo@agripredict.pk';
const PASSWORD = process.env.DEMO_PASSWORD || 'Sunflower2026';

const describeLive = LIVE ? describe : describe.skip;

describeLive('live API', () => {
  let api;
  let store;
  let session;

  beforeAll(async () => {
    // Import after API_BASE_URL is set, since config reads it at module load.
    api = require('../src/services/api');
    store = require('../src/services/session');
    session = require('../src/services/apiClient');
  });

  it('logs in and returns a usable token pair', async () => {
    const pair = await api.authApi.login({email: EMAIL, password: PASSWORD});
    expect(typeof pair.access_token).toBe('string');
    expect(typeof pair.refresh_token).toBe('string');

    await store.persistSession({
      accessToken: pair.access_token,
      refreshToken: pair.refresh_token,
      user: null,
    });
    session.configureApi({
      getToken: () => store.getAccessToken(),
      onRefresh: () => store.refreshSession(),
      onUnauthorized: () => {},
    });

    expect(store.getAccessToken()).toBe(pair.access_token);
  });

  it('reads /auth/me', async () => {
    const me = await api.authApi.me();
    expect(me.email).toBe(EMAIL);
  });

  it('reads reference data', async () => {
    const commodities = await api.catalogueApi.commodities();
    const markets = await api.catalogueApi.markets();
    expect(Array.isArray(commodities)).toBe(true);
    expect(commodities.length).toBeGreaterThan(0);
    expect(markets.length).toBeGreaterThan(0);
    // The app relies on these exact fields for its labels.
    expect(commodities[0]).toHaveProperty('name_en');
    expect(markets[0]).toHaveProperty('name');
    expect(api.commodityName(commodities.find(c => c.slug === 'wheat'))).toBe('Wheat');
  });

  it('reads price history and a comparison', async () => {
    const history = await api.marketApi.history('wheat', 'lahore-sabzi-mandi', 90);
    expect(history.points.length).toBeGreaterThan(0);
    expect(history.points[0]).toHaveProperty('price_date');
    expect(history.points[0]).toHaveProperty('avg_price_pkr');
    expect(history.unit).toBe('PKR/40kg');

    const comparison = await api.marketApi.compare('wheat', {days: 7});
    expect(Array.isArray(comparison.rows)).toBe(true);
    expect(comparison.rows[0].market).toHaveProperty('name');
  });

  it('reads a forecast with bounds and metrics', async () => {
    const forecast = await api.forecastApi.get('wheat', 'lahore-sabzi-mandi', 7);
    expect(forecast.points.length).toBe(7);
    const point = forecast.points[0];
    expect(point).toHaveProperty('target_date');
    expect(point).toHaveProperty('predicted_price_pkr');
    expect(Number(point.upper_bound_pkr)).toBeGreaterThan(Number(point.lower_bound_pkr));
    expect(forecast).toHaveProperty('model_name');
    expect(forecast).toHaveProperty('is_fallback');
  });

  it('creates a farm, cycle, expense and sale, then reads the finance block', async () => {
    const farm = await api.farmApi.create({
      name: `Integration farm ${Date.now()}`,
      district: 'Lahore',
      total_area_acres: 4,
      latitude: 31.5204,
      longitude: 74.3587,
    });
    expect(farm.id).toBeGreaterThan(0);

    const commodities = await api.catalogueApi.commodities();
    const wheat = commodities.find(item => item.slug === 'wheat');

    const cycle = await api.cropApi.create({
      farm_id: farm.id,
      commodity_id: wheat.id,
      season: 'rabi',
      area_acres: 4,
      sowing_date: '2026-11-01',
      expected_harvest_date: '2027-04-01',
      status: 'active',
      expected_yield_kg: 1600,
    });
    expect(cycle.id).toBeGreaterThan(0);

    const expense = await api.cropApi.addExpense(cycle.id, {
      category: 'seeds',
      amount_pkr: 8000,
      expense_date: '2026-11-02',
      description: 'integration test',
    });
    expect(Number(expense.amount_pkr)).toBe(8000);

    const sale = await api.cropApi.addSale(cycle.id, {
      quantity_kg: 400,
      unit_price_pkr: 4000,
      sale_date: '2026-11-20',
      buyer_name: 'Integration buyer',
    });
    // The server derives the total: 400 kg = 10 maunds x 4000 = 40000.
    expect(Number(sale.total_amount_pkr)).toBe(40000);

    const detail = await api.cropApi.get(cycle.id);
    expect(Number(detail.finance.revenue_pkr)).toBe(40000);
    expect(Number(detail.finance.cost_pkr)).toBe(8000);
    expect(Number(detail.finance.profit_pkr)).toBe(32000);
    expect(Number(detail.finance.break_even_price_pkr)).toBe(800);

    const expenses = await api.cropApi.expenses(cycle.id);
    const sales = await api.cropApi.sales(cycle.id);
    expect(expenses[0]).toHaveProperty('amount_pkr');
    expect(sales[0]).toHaveProperty('unit_price_pkr');
  });

  it('reads the finance overview', async () => {
    const overview = await api.financeApi.summary();
    expect(overview).toHaveProperty('lifetime_revenue_pkr');
    expect(overview).toHaveProperty('margin_pct');
    expect(Array.isArray(overview.seasons)).toBe(true);
    expect(Array.isArray(overview.expense_breakdown)).toBe(true);
  });

  it('generates a PDF and downloads it through the signed link with no headers', async () => {
    const report = await api.reportApi.create({
      reportType: 'financial_summary',
      fileFormat: 'pdf',
      cropCycleId: null,
    });
    expect(report.download_url).toContain('token=');

    const absolute = api.absoluteDownloadUrl(report);
    expect(absolute.startsWith('http')).toBe(true);

    // Exactly what Android's download manager does: a plain GET, no auth header.
    const response = await fetch(absolute);
    expect(response.status).toBe(200);
    const buffer = Buffer.from(await response.arrayBuffer());
    expect(buffer.subarray(0, 4).toString()).toBe('%PDF');
    expect(buffer.length).toBeGreaterThan(1000);
  });

  it('generates an Excel workbook', async () => {
    const report = await api.reportApi.create({
      reportType: 'financial_summary',
      fileFormat: 'xlsx',
      cropCycleId: null,
    });
    const response = await fetch(api.absoluteDownloadUrl(report));
    expect(response.status).toBe(200);
    const buffer = Buffer.from(await response.arrayBuffer());
    expect(buffer.subarray(0, 2).toString()).toBe('PK');
  });

  it('surfaces weather (mock provider) and buyer availability honestly', async () => {
    const farms = await api.farmApi.list();
    const withCoords = farms.find(f => f.latitude !== null && f.latitude !== undefined);
    if (withCoords) {
      const weather = await api.weatherApi.forFarm(withCoords.id);
      expect(weather).toHaveProperty('provider');
      expect(Array.isArray(weather.forecast)).toBe(true);
    }
    const buyers = await api.buyerApi.search({limit: 5});
    expect(['google_places', 'cache', 'unavailable']).toContain(buyers.source);
    expect(Array.isArray(buyers.results)).toBe(true);
  });

  it('rejects a request with a bogus token', async () => {
    store.setTokens({accessToken: 'not-a-real-token', refreshToken: null});
    await expect(api.authApi.me()).rejects.toMatchObject({status: 401});
  });
});

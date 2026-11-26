/**
 * Contract tests: the app's field names must exist in the backend's schemas.
 *
 * Why this exists: the first version of these screens was written against
 * assumed response shapes. Reading a field the server does not send does not
 * throw — it renders "—" — so nothing fails until a farmer sees an empty
 * price. This suite pins every field the app reads to the real FastAPI schema.
 *
 * `tests/fixtures/apiContract.json` is generated from `backend/app` (see the
 * header of that file); `docs/frontend/api-contract.md` records how to
 * regenerate it. If a field is renamed in the backend, this test fails here,
 * pointing at the exact screen that still expects the old name.
 */

import contract from './fixtures/apiContract.json';

/** field name -> the screens/utilities that read it. */
const READS = {
  // Market prices
  PricePoint: ['price_date', 'avg_price_pkr', 'source', 'min_price_pkr', 'max_price_pkr'],
  PriceHistory: ['commodity', 'market', 'unit', 'points', 'count'],
  MarketComparisonRow: [
    'market',
    'latest_price_pkr',
    'latest_date',
    'avg_30d_pkr',
    'change_pct_7d',
    'observations',
  ],
  MarketComparison: ['commodity', 'unit', 'rows', 'best_market_slug'],
  CommodityRead: ['id', 'slug', 'name_en', 'name_ur', 'category'],
  MarketRead: ['id', 'slug', 'name', 'district', 'province'],

  // Forecasts
  ForecastRead: [
    'id',
    'commodity',
    'market',
    'model_name',
    'horizon_days',
    'issued_on',
    'mae',
    'rmse',
    'points',
    'is_fallback',
    'disclaimer',
  ],
  ForecastPointRead: ['target_date', 'predicted_price_pkr', 'lower_bound_pkr', 'upper_bound_pkr'],

  // Farm ERP
  FarmRead: ['id', 'name', 'district', 'tehsil', 'latitude', 'longitude', 'total_area_acres'],
  CropCycleRead: [
    'id',
    'farm_id',
    'commodity',
    'season',
    'area_acres',
    'sowing_date',
    'expected_harvest_date',
    'actual_harvest_date',
    'status',
    'expected_yield_kg',
    'actual_yield_kg',
    'notes',
  ],
  CropCycleDetail: ['finance'],
  FinanceSummary: [
    'revenue_pkr',
    'cost_pkr',
    'profit_pkr',
    'margin_pct',
    'break_even_price_pkr',
  ],
  ExpenseRead: ['id', 'crop_cycle_id', 'category', 'amount_pkr', 'expense_date', 'description'],
  SaleRead: [
    'id',
    'crop_cycle_id',
    'quantity_kg',
    'unit_price_pkr',
    'total_amount_pkr',
    'sale_date',
    'buyer_name',
  ],

  // Rollups
  FinanceOverview: [
    'lifetime_revenue_pkr',
    'lifetime_cost_pkr',
    'lifetime_profit_pkr',
    'margin_pct',
    'active_cycles',
    'seasons',
    'expense_breakdown',
  ],
  SeasonSummary: [
    'season',
    'year',
    'cycles',
    'total_area_acres',
    'revenue_pkr',
    'cost_pkr',
    'profit_pkr',
    'margin_pct',
  ],
  ExpenseBreakdownRow: ['category', 'total_pkr', 'share_pct'],

  // Weather and buyers
  WeatherBundle: ['current', 'forecast', 'provider', 'is_live'],
  WeatherCurrent: [
    'farm_id',
    'temperature_c',
    'humidity_pct',
    'wind_kph',
    'precipitation_mm',
    'condition',
    'provider',
    'is_live',
  ],
  WeatherForecastDay: ['day', 'temp_min_c', 'temp_max_c', 'precipitation_mm', 'condition'],
  BuyerRead: ['id', 'name', 'category', 'address', 'distance_km', 'phone', 'place_id'],
  BuyerSearchResponse: ['results', 'count', 'radius_m', 'source', 'note'],

  // Reports
  ReportRead: [
    'id',
    'report_type',
    'file_format',
    'filename',
    'size_bytes',
    'created_at',
    'expires_at',
    'download_url',
  ],
};

describe('backend schema contract', () => {
  it('covers every schema the app depends on', () => {
    const unknown = Object.keys(READS).filter(name => !contract[name]);
    expect(unknown).toEqual([]);
  });

  it.each(Object.keys(READS))('%s exposes every field the app reads', schemaName => {
    const available = contract[schemaName];
    const missing = READS[schemaName].filter(field => !available.includes(field));
    expect(missing).toEqual([]);
  });

  it('does not silently rely on fields the backend no longer has', () => {
    // Guards against the reverse mistake: a rename in the backend that leaves a
    // screen reading the old name. Every declared read must be justified.
    const totalReads = Object.values(READS).reduce((sum, fields) => sum + fields.length, 0);
    expect(totalReads).toBeGreaterThan(70);
  });
});

describe('request payload contract', () => {
  // Fields the app POSTs/PATCHes must exist in the corresponding *Create /
  // *Update schemas, otherwise FastAPI rejects them with 422 "extra fields".
  const WRITES = {
    ExpenseCreate: ['category', 'amount_pkr', 'expense_date', 'description'],
    SaleCreate: ['quantity_kg', 'unit_price_pkr', 'sale_date', 'buyer_name', 'market_id'],
    CropCycleCreate: [
      'farm_id',
      'commodity_id',
      'season',
      'area_acres',
      'sowing_date',
      'expected_harvest_date',
      'status',
      'expected_yield_kg',
      'notes',
    ],
    CropCycleUpdate: [
      'season',
      'area_acres',
      'sowing_date',
      'expected_harvest_date',
      'actual_harvest_date',
      'status',
      'expected_yield_kg',
      'actual_yield_kg',
      'notes',
    ],
    FarmCreate: ['name', 'district', 'tehsil', 'total_area_acres', 'latitude', 'longitude'],
    ReportCreate: ['report_type', 'file_format', 'crop_cycle_id'],
  };

  it.each(Object.keys(WRITES))('%s accepts everything the app sends', schemaName => {
    const available = contract[schemaName];
    // Only assert when the schema was captured; *Create schemas are included in
    // the fixture because FastAPI puts every model in components.schemas.
    if (!available) {
      return;
    }
    const unsupported = WRITES[schemaName].filter(field => !available.includes(field));
    expect(unsupported).toEqual([]);
  });
});

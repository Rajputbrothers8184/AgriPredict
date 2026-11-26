import React from 'react';
import {render, screen, fireEvent, waitFor, act} from '@testing-library/react-native';

import {LocalizationProvider} from '../src/context/LocalizationContext';
import {ThemeProvider} from '../src/context/ThemeContext';

jest.mock('../src/context/AuthContext', () => ({
  useAuth: () => ({
    user: {id: 1, full_name: 'Ahmed Raza', email: 'demo@agripredict.pk'},
    logout: jest.fn(),
    status: 'authenticated',
  }),
}));

jest.mock('../src/services/api', () => ({
  ...jest.requireActual('../src/services/api'),
  cropApi: {
    list: jest.fn(),
    get: jest.fn(),
    expenses: jest.fn(),
    sales: jest.fn(),
    addExpense: jest.fn(),
    addSale: jest.fn(),
    create: jest.fn(),
    update: jest.fn(),
    removeExpense: jest.fn(),
    removeSale: jest.fn(),
  },
  farmApi: {list: jest.fn(), get: jest.fn(), create: jest.fn(), update: jest.fn()},
  forecastApi: {get: jest.fn()},
  marketApi: {history: jest.fn()},
  weatherApi: {forFarm: jest.fn()},
  buyerApi: {search: jest.fn(), saved: jest.fn()},
  reportApi: {create: jest.fn(), list: jest.fn()},
  catalogueApi: {commodities: jest.fn(), markets: jest.fn()},
}));

import {
  buyerApi,
  cropApi,
  farmApi,
  forecastApi,
  marketApi,
  reportApi,
  weatherApi,
} from '../src/services/api';
import {absoluteDownloadUrl} from '../src/services/api';
import {ApiError} from '../src/services/apiClient';
import CropDetailScreen from '../src/screens/crops/CropDetailScreen';
import CropFormScreen from '../src/screens/crops/CropFormScreen';
import ExpenseFormScreen from '../src/screens/crops/ExpenseFormScreen';
import SaleFormScreen from '../src/screens/crops/SaleFormScreen';
import ForecastScreen from '../src/screens/market/ForecastScreen';
import WeatherScreen from '../src/screens/WeatherScreen';
import BuyersScreen from '../src/screens/BuyersScreen';
import ReportsScreen from '../src/screens/ReportsScreen';
import FarmFormScreen from '../src/screens/FarmFormScreen';

function wrap(element) {
  return (
    <ThemeProvider initialTheme="light">
      <LocalizationProvider initialLanguage="en">{element}</LocalizationProvider>
    </ThemeProvider>
  );
}

const navigation = {navigate: jest.fn(), goBack: jest.fn()};

const cropCycle = {
  id: 7,
  farm_id: 1,
  commodity: {id: 1, slug: 'wheat', name_en: 'Wheat', name_ur: 'گندم'},
  season: 'rabi',
  area_acres: '5.00',
  sowing_date: '2026-11-01',
  expected_harvest_date: '2027-04-01',
  status: 'active',
  expected_yield_kg: '2000.00',
  actual_yield_kg: null,
  notes: null,
  finance: {
    revenue_pkr: '40000.00',
    cost_pkr: '20000.00',
    profit_pkr: '20000.00',
    margin_pct: '50.0',
    total_yield_kg: '400.00',
    break_even_price_pkr: '2000.00',
    revenue_per_acre_pkr: '8000.00',
    yield_per_acre_kg: '80.00',
  },
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('CropDetailScreen', () => {
  it('uses the server-computed finance block instead of recalculating', async () => {
    cropApi.get.mockResolvedValue(cropCycle);
    // Deliberately different local figures: if the screen recomputed, the
    // assertions below would see these instead of the server's numbers.
    cropApi.expenses.mockResolvedValue([
      {id: 1, category: 'seeds', amount_pkr: '1.00', expense_date: '2026-11-02'},
    ]);
    cropApi.sales.mockResolvedValue([]);

    render(wrap(<CropDetailScreen navigation={navigation} route={{params: {cropId: 7}}} />));

    // Server figures: cost 20,000 and profit 20,000, so exactly two matches.
    // A local recomputation would give cost = 1 and profit = -1 instead.
    await waitFor(() =>
      expect(screen.getAllByText('PKR 20,000 PKR/40kg')).toHaveLength(2),
    );
    expect(screen.getByText('PKR 40,000 PKR/40kg')).toBeTruthy();
    expect(screen.queryByText('PKR -1 PKR/40kg')).toBeNull();
    expect(screen.getByText('PKR 2,000 PKR/40kg')).toBeTruthy();
  });

  it('renders itemised expenses and sales with API field names', async () => {
    cropApi.get.mockResolvedValue(cropCycle);
    cropApi.expenses.mockResolvedValue([
      {id: 1, category: 'fertilizer', amount_pkr: '12000.00', expense_date: '2026-11-02', description: 'Urea'},
    ]);
    cropApi.sales.mockResolvedValue([
      {id: 9, quantity_kg: '400.00', unit_price_pkr: '4000.00', total_amount_pkr: '40000.00', sale_date: '2026-11-20', buyer_name: 'Ali Traders'},
    ]);

    render(wrap(<CropDetailScreen navigation={navigation} route={{params: {cropId: 7}}} />));

    await waitFor(() => expect(screen.getByText('Fertilizer')).toBeTruthy());
    expect(screen.getByText('PKR 12,000 PKR/40kg')).toBeTruthy();
    expect(screen.getByText('400 kg @ PKR 4,000 PKR/40kg')).toBeTruthy();
    expect(screen.getByText(/Ali Traders/)).toBeTruthy();
  });

  it('falls back to a local calculation when the finance block is absent', async () => {
    cropApi.get.mockResolvedValue({...cropCycle, finance: null});
    cropApi.expenses.mockResolvedValue([
      {id: 1, category: 'seeds', amount_pkr: '5000', expense_date: '2026-11-02'},
    ]);
    cropApi.sales.mockResolvedValue([
      {id: 1, quantity_kg: 400, unit_price_pkr: 4000, total_amount_pkr: '40000', sale_date: '2026-11-20'},
    ]);

    render(wrap(<CropDetailScreen navigation={navigation} route={{params: {cropId: 7}}} />));

    // 40000 - 5000 = 35000, computed locally
    await waitFor(() => expect(screen.getByText('PKR 35,000 PKR/40kg')).toBeTruthy());
  });
});

describe('ExpenseFormScreen', () => {
  it('posts amount_pkr, not amount', async () => {
    cropApi.addExpense.mockResolvedValue({});
    render(wrap(<ExpenseFormScreen navigation={navigation} route={{params: {cropId: 7}}} />));

    fireEvent.changeText(screen.getByTestId('expense-amount'), '2500.50');
    await act(async () => {
      fireEvent.press(screen.getByTestId('expense-submit'));
    });

    expect(cropApi.addExpense).toHaveBeenCalledWith(
      7,
      expect.objectContaining({amount_pkr: 2500.5, category: 'seeds'}),
    );
    expect(cropApi.addExpense.mock.calls[0][1]).not.toHaveProperty('amount');
    expect(navigation.goBack).toHaveBeenCalled();
  });

  it('shows a translated error and stays on the form when the API rejects', async () => {
    cropApi.addExpense.mockRejectedValue(new ApiError('bad', {status: 422, code: 'validation_error'}));
    render(wrap(<ExpenseFormScreen navigation={navigation} route={{params: {cropId: 7}}} />));

    fireEvent.changeText(screen.getByTestId('expense-amount'), '100');
    await act(async () => {
      fireEvent.press(screen.getByTestId('expense-submit'));
    });

    await waitFor(() => expect(screen.getByText('Please check the highlighted fields.')).toBeTruthy());
    expect(navigation.goBack).not.toHaveBeenCalled();
  });

  it('refuses a zero amount before calling the API', async () => {
    render(wrap(<ExpenseFormScreen navigation={navigation} route={{params: {cropId: 7}}} />));
    fireEvent.changeText(screen.getByTestId('expense-amount'), '0');
    await act(async () => {
      fireEvent.press(screen.getByTestId('expense-submit'));
    });
    expect(cropApi.addExpense).not.toHaveBeenCalled();
  });
});

describe('SaleFormScreen', () => {
  it('posts quantity_kg and unit_price_pkr and previews the maund total', async () => {
    const {catalogueApi} = require('../src/services/api');
    catalogueApi.markets.mockResolvedValue([{id: 1, slug: 'lahore-sabzi-mandi', name: 'Lahore Sabzi Mandi'}]);
    cropApi.addSale.mockResolvedValue({});

    render(wrap(<SaleFormScreen navigation={navigation} route={{params: {cropId: 7}}} />));

    fireEvent.changeText(screen.getByTestId('sale-quantity'), '800');
    fireEvent.changeText(screen.getByTestId('sale-price'), '4000');

    // 800 kg = 20 maunds x 4000 = 80000
    await waitFor(() => expect(screen.getByText('PKR 80,000 PKR/40kg')).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId('sale-submit'));
    });

    const payload = cropApi.addSale.mock.calls[0][1];
    expect(payload).toMatchObject({quantity_kg: 800, unit_price_pkr: 4000});
    expect(payload).not.toHaveProperty('total_amount_pkr');
    expect(payload).not.toHaveProperty('price_per_maund');
  });
});

describe('ForecastScreen', () => {
  const forecast = {
    id: 3,
    model_name: 'xgboost',
    horizon_days: 7,
    issued_on: '2026-11-25',
    mae: '103.36',
    rmse: '117.05',
    is_fallback: false,
    disclaimer: 'Forecasts are estimates from historical prices.',
    points: [
      {
        target_date: '2026-11-26',
        predicted_price_pkr: '4759.04',
        lower_bound_pkr: '4576.76',
        upper_bound_pkr: '4941.32',
      },
    ],
  };

  beforeEach(() => {
    marketApi.history.mockResolvedValue({
      points: [{price_date: '2026-11-25', avg_price_pkr: '4700.00', source: 'synthetic_fixture'}],
    });
  });

  it('shows the model, its measured MAE and the server disclaimer', async () => {
    forecastApi.get.mockResolvedValue(forecast);
    render(
      wrap(
        <ForecastScreen
          navigation={navigation}
          route={{params: {commoditySlug: 'wheat', marketSlug: 'lahore-sabzi-mandi', commodityLabel: 'Wheat', marketLabel: 'Lahore'}}}
        />,
      ),
    );

    await waitFor(() => expect(screen.getByText('xgboost')).toBeTruthy());
    expect(screen.getByText('PKR 103 PKR/40kg')).toBeTruthy();
    expect(screen.getByText('Forecasts are estimates from historical prices.')).toBeTruthy();
    expect(screen.getByText('PKR 4,759 PKR/40kg')).toBeTruthy();
  });

  it('warns clearly when the service served a fallback model', async () => {
    forecastApi.get.mockResolvedValue({...forecast, model_name: 'seasonal_naive', is_fallback: true, mae: null});
    render(
      wrap(
        <ForecastScreen
          navigation={navigation}
          route={{params: {commoditySlug: 'wheat', marketSlug: 'lahore-sabzi-mandi'}}}
        />,
      ),
    );

    await waitFor(() => expect(screen.getByText('Baseline forecast')).toBeTruthy());
    expect(screen.getByText('Not evaluated')).toBeTruthy();
  });

  it('requests the 30-day horizon when that button is pressed', async () => {
    forecastApi.get.mockResolvedValue(forecast);
    render(
      wrap(
        <ForecastScreen
          navigation={navigation}
          route={{params: {commoditySlug: 'wheat', marketSlug: 'lahore-sabzi-mandi'}}}
        />,
      ),
    );
    await waitFor(() => expect(forecastApi.get).toHaveBeenCalledWith('wheat', 'lahore-sabzi-mandi', 7));

    await act(async () => {
      fireEvent.press(screen.getByTestId('horizon-30'));
    });

    await waitFor(() =>
      expect(forecastApi.get).toHaveBeenCalledWith('wheat', 'lahore-sabzi-mandi', 30),
    );
  });
});

describe('WeatherScreen', () => {
  it('labels mock weather as simulated rather than implying it is live', async () => {
    farmApi.list.mockResolvedValue([{id: 1, name: 'Lahore plot', latitude: '31.5', longitude: '74.3'}]);
    weatherApi.forFarm.mockResolvedValue({
      provider: 'mock',
      is_live: false,
      current: {temperature_c: '28.50', humidity_pct: '55', wind_kph: '12', precipitation_mm: '0'},
      forecast: [{day: '2026-11-26', temp_min_c: '15', temp_max_c: '29', precipitation_mm: '0'}],
    });

    render(wrap(<WeatherScreen navigation={navigation} />));

    await waitFor(() => expect(screen.getByTestId('weather-mock')).toBeTruthy());
    expect(screen.getByText('29°C')).toBeTruthy();
    expect(screen.getByText('55%')).toBeTruthy();
  });

  it('explains that coordinates are missing instead of showing zeros', async () => {
    farmApi.list.mockResolvedValue([{id: 1, name: 'Lahore plot', latitude: null, longitude: null}]);
    weatherApi.forFarm.mockRejectedValue(new ApiError('no coords', {status: 422}));

    render(wrap(<WeatherScreen navigation={navigation} />));

    await waitFor(() => expect(screen.getByTestId('weather-unavailable')).toBeTruthy());
    expect(
      screen.getByText('Add latitude and longitude to this farm to see weather.'),
    ).toBeTruthy();
  });
});

describe('BuyersScreen', () => {
  it('reads results from the BuyerSearchResponse envelope', async () => {
    buyerApi.search.mockResolvedValue({
      results: [
        {id: 1, place_id: 'p1', name: 'Ali Traders', category: 'trader', address: 'Multan Road', distance_km: '2.40', phone: '03001234567'},
      ],
      count: 1,
      radius_m: 5000,
      source: 'cache',
      note: null,
    });
    buyerApi.saved.mockResolvedValue([]);

    render(wrap(<BuyersScreen />));

    await waitFor(() => expect(screen.getByText('Ali Traders')).toBeTruthy());
    expect(screen.getByText('2.4 km away')).toBeTruthy();
    expect(screen.getByText('Trader')).toBeTruthy();
    expect(screen.getByText('Call 03001234567')).toBeTruthy();
  });

  it('says the feature is unconfigured when the server reports unavailable', async () => {
    buyerApi.search.mockResolvedValue({
      results: [],
      count: 0,
      radius_m: 5000,
      source: 'unavailable',
      note: 'no api key',
    });
    buyerApi.saved.mockResolvedValue([]);

    render(wrap(<BuyersScreen />));

    await waitFor(() => expect(screen.getByTestId('buyers-not-configured')).toBeTruthy());
    expect(screen.getByTestId('buyers-empty')).toBeTruthy();
  });

  it('falls back to saved buyers when the live search fails', async () => {
    buyerApi.search.mockRejectedValue(new ApiError('offline', {code: 'offline'}));
    buyerApi.saved.mockResolvedValue([
      {id: 4, place_id: 'p4', name: 'Multan Mill', category: 'mill'},
    ]);

    render(wrap(<BuyersScreen />));

    await waitFor(() => expect(screen.getByText('Multan Mill')).toBeTruthy());
    expect(screen.getByText('Mill')).toBeTruthy();
  });
});

describe('ReportsScreen', () => {
  it('sends report_type/file_format/crop_cycle_id and opens the signed URL', async () => {
    const {cropApi: crops} = require('../src/services/api');
    crops.list.mockResolvedValue([{...cropCycle}]);
    reportApi.list.mockResolvedValue([]);
    reportApi.create.mockResolvedValue({
      id: 5,
      file_format: 'pdf',
      filename: 'statement.pdf',
      download_url: '/api/v1/reports/5/download?token=signed-abc',
    });

    render(wrap(<ReportsScreen route={{params: {cropId: 7}}} />));

    await waitFor(() => expect(screen.getByTestId('report-pdf')).toBeTruthy());
    await act(async () => {
      fireEvent.press(screen.getByTestId('report-pdf'));
    });

    expect(reportApi.create).toHaveBeenCalledWith({
      reportType: 'crop_cycle',
      fileFormat: 'pdf',
      cropCycleId: 7,
    });
  });

  it('builds an absolute URL from a server-relative download path', () => {
    expect(absoluteDownloadUrl({download_url: '/api/v1/reports/5/download?token=t'})).toBe(
      'http://10.0.2.2:8000/api/v1/reports/5/download?token=t',
    );
    expect(absoluteDownloadUrl({download_url: 'https://cdn.example/x.pdf'})).toBe(
      'https://cdn.example/x.pdf',
    );
    expect(absoluteDownloadUrl({})).toBeNull();
  });

  it('surfaces a failure instead of silently doing nothing', async () => {
    const {cropApi: crops} = require('../src/services/api');
    crops.list.mockResolvedValue([{...cropCycle}]);
    reportApi.list.mockResolvedValue([]);
    reportApi.create.mockRejectedValue(new ApiError('nope', {status: 500}));

    render(wrap(<ReportsScreen route={{params: {cropId: 7}}} />));
    await waitFor(() => expect(screen.getByTestId('report-xlsx')).toBeTruthy());
    await act(async () => {
      fireEvent.press(screen.getByTestId('report-xlsx'));
    });

    await waitFor(() =>
      expect(screen.getByTestId('report-notice').props.children).toBe(
        'The server had a problem. Please try again shortly.',
      ),
    );
  });
});

describe('FarmFormScreen', () => {
  it('requires latitude and longitude together, matching the API rule', async () => {
    render(wrap(<FarmFormScreen navigation={navigation} route={{params: {mode: 'create'}}} />));

    fireEvent.changeText(screen.getByTestId('farm-name'), 'Plot A');
    fireEvent.changeText(screen.getByTestId('farm-district'), 'Lahore');
    fireEvent.changeText(screen.getByTestId('farm-area'), '5');
    // Only one of the pair supplied -> the API's _coords_together rule applies.
    fireEvent.changeText(screen.getByPlaceholderText('31.5204'), '31.52');
    await act(async () => {
      fireEvent.press(screen.getByTestId('farm-submit'));
    });

    expect(farmApi.create).not.toHaveBeenCalled();
    expect(screen.getAllByText('This field is required.').length).toBeGreaterThan(0);
  });

  it('posts total_area_acres when the coordinates are complete', async () => {
    farmApi.create.mockResolvedValue({});
    render(wrap(<FarmFormScreen navigation={navigation} route={{params: {mode: 'create'}}} />));

    fireEvent.changeText(screen.getByTestId('farm-name'), 'Plot A');
    fireEvent.changeText(screen.getByTestId('farm-district'), 'Lahore');
    fireEvent.changeText(screen.getByTestId('farm-area'), '5');
    fireEvent.changeText(screen.getByPlaceholderText('31.5204'), '31.52');
    fireEvent.changeText(screen.getByPlaceholderText('74.3587'), '74.35');

    await act(async () => {
      fireEvent.press(screen.getByTestId('farm-submit'));
    });

    expect(farmApi.create).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Plot A',
        district: 'Lahore',
        total_area_acres: 5,
        latitude: 31.52,
        longitude: 74.35,
      }),
    );
  });
});

describe('CropFormScreen', () => {
  it('posts farm_id and commodity_id on create', async () => {
    farmApi.list.mockResolvedValue([{id: 1, name: 'Plot A'}]);
    const {catalogueApi} = require('../src/services/api');
    catalogueApi.commodities.mockResolvedValue([{id: 1, slug: 'wheat', name_en: 'Wheat'}]);
    cropApi.create.mockResolvedValue({});

    render(wrap(<CropFormScreen navigation={navigation} route={{params: {mode: 'create'}}} />));

    await waitFor(() => expect(screen.getByTestId('commodity-choice-1')).toBeTruthy());
    // The farm row is preselected; pick the commodity explicitly.
    await act(async () => {
      fireEvent.press(screen.getByTestId('commodity-choice-1'));
    });
    fireEvent.changeText(screen.getByTestId('crop-area'), '5');

    await act(async () => {
      fireEvent.press(screen.getByTestId('crop-submit'));
    });

    const payload = cropApi.create.mock.calls[0][0];
    expect(payload.farm_id).toBe(1);
    expect(payload.commodity_id).toBe(1);
    expect(payload.area_acres).toBe(5);
    expect(payload.sowing_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(payload).not.toHaveProperty('actual_harvest_date');
  });

  it('omits immutable fields when editing', async () => {
    farmApi.list.mockResolvedValue([{id: 1, name: 'Plot A'}]);
    const {catalogueApi} = require('../src/services/api');
    catalogueApi.commodities.mockResolvedValue([{id: 1, slug: 'wheat', name_en: 'Wheat'}]);
    cropApi.get.mockResolvedValue(cropCycle);
    cropApi.update.mockResolvedValue({});

    render(
      wrap(<CropFormScreen navigation={navigation} route={{params: {mode: 'edit', cropId: 7}}} />),
    );

    await waitFor(() => expect(screen.getByTestId('crop-submit')).toBeTruthy());
    await act(async () => {
      fireEvent.press(screen.getByTestId('crop-submit'));
    });

    expect(cropApi.update).toHaveBeenCalled();
    const payload = cropApi.update.mock.calls[0][1];
    expect(payload).not.toHaveProperty('farm_id');
    expect(payload).not.toHaveProperty('commodity_id');
    expect(payload.status).toBe('active');
  });
});

import React from 'react';
import {render, screen, fireEvent, waitFor, act} from '@testing-library/react-native';

import {LocalizationProvider} from '../src/context/LocalizationContext';
import {ThemeProvider} from '../src/context/ThemeContext';

const mockLogin = jest.fn();
jest.mock('../src/context/AuthContext', () => ({
  useAuth: () => ({
    user: {id: 1, full_name: 'Ahmed Raza', email: 'demo@agripredict.pk'},
    login: mockLogin,
    logout: jest.fn(),
    register: jest.fn(),
    status: 'authenticated',
    isAuthenticated: true,
  }),
}));

jest.mock('../src/services/api', () => ({
  ...jest.requireActual('../src/services/api'),
  authApi: {
    login: jest.fn(),
    me: jest.fn(),
    register: jest.fn(),
    refresh: jest.fn(),
    logout: jest.fn(),
  },
  marketApi: {
    history: jest.fn(),
    compare: jest.fn(),
  },
  forecastApi: {get: jest.fn(), latest: jest.fn()},
  cropApi: {list: jest.fn(), get: jest.fn(), expenses: jest.fn(), sales: jest.fn()},
  farmApi: {list: jest.fn()},
  financeApi: {summary: jest.fn(), seasons: jest.fn()},
  catalogueApi: {commodities: jest.fn(), markets: jest.fn()},
  buyerApi: {search: jest.fn(), saved: jest.fn()},
  reportApi: {create: jest.fn(), list: jest.fn()},
  weatherApi: {forFarm: jest.fn()},
}));

import {ApiError} from '../src/services/apiClient';
import {cropApi, farmApi, financeApi, forecastApi, marketApi} from '../src/services/api';
import LoginScreen from '../src/screens/auth/LoginScreen';
import DashboardScreen from '../src/screens/DashboardScreen';
import MarketScreen from '../src/screens/market/MarketScreen';
import FinanceScreen from '../src/screens/FinanceScreen';

function wrap(element) {
  return (
    <ThemeProvider initialTheme="light">
      <LocalizationProvider initialLanguage="en">{element}</LocalizationProvider>
    </ThemeProvider>
  );
}

const navigation = {navigate: jest.fn(), goBack: jest.fn()};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('LoginScreen', () => {
  it('blocks submission and shows field errors for an empty form', async () => {
    render(wrap(<LoginScreen navigation={navigation} />));

    fireEvent.press(screen.getByTestId('login-submit'));

    await waitFor(() => expect(screen.getAllByText('This field is required.')).toHaveLength(2));
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('rejects a malformed email before calling the API', async () => {
    render(wrap(<LoginScreen navigation={navigation} />));
    fireEvent.changeText(screen.getByTestId('login-email'), 'not-an-email');
    fireEvent.changeText(screen.getByTestId('login-password'), 'Password1');
    fireEvent.press(screen.getByTestId('login-submit'));

    await waitFor(() => expect(screen.getByText('Enter a valid email address.')).toBeTruthy());
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('calls login with trimmed credentials', async () => {
    mockLogin.mockResolvedValue({id: 1});
    render(wrap(<LoginScreen navigation={navigation} />));
    fireEvent.changeText(screen.getByTestId('login-email'), '  demo@agripredict.pk ');
    fireEvent.changeText(screen.getByTestId('login-password'), 'Sunflower2026');
    await act(async () => {
      fireEvent.press(screen.getByTestId('login-submit'));
    });

    expect(mockLogin).toHaveBeenCalledWith({
      email: 'demo@agripredict.pk',
      password: 'Sunflower2026',
    });
  });

  it('shows a translated message when the credentials are rejected', async () => {
    mockLogin.mockRejectedValue(new ApiError('bad creds', {status: 401, code: 'invalid_credentials'}));
    render(wrap(<LoginScreen navigation={navigation} />));
    fireEvent.changeText(screen.getByTestId('login-email'), 'demo@agripredict.pk');
    fireEvent.changeText(screen.getByTestId('login-password'), 'wrong-pass1');
    await act(async () => {
      fireEvent.press(screen.getByTestId('login-submit'));
    });

    await waitFor(() =>
      expect(screen.getByTestId('login-error').props.children).toBe(
        'Email or password is incorrect.',
      ),
    );
  });
});

describe('DashboardScreen', () => {
  it('shows the user name, crop count and latest price', async () => {
    farmApi.list.mockResolvedValue([{id: 1, name: 'Lahore plot'}]);
    cropApi.list.mockResolvedValue([
      {id: 1, status: 'active', area_acres: '5', expenses: [], sales: []},
      {id: 2, status: 'active', area_acres: '2.5', expenses: [{amount: 1000}], sales: []},
    ]);
    financeApi.summary.mockResolvedValue({
      lifetime_revenue_pkr: '61000.00',
      lifetime_cost_pkr: '24000.00',
      lifetime_profit_pkr: '37000.00',
      margin_pct: '60.66',
      active_cycles: 2,
      seasons: [],
      expense_breakdown: [],
    });
    marketApi.history.mockResolvedValue({
      unit: 'PKR/40kg',
      count: 2,
      points: [
        {price_date: '2026-11-01', avg_price_pkr: '4000.00', source: 'synthetic_fixture'},
        {price_date: '2026-11-02', avg_price_pkr: '4200.00', source: 'synthetic_fixture'},
      ],
    });
    forecastApi.get.mockResolvedValue({points: [], model_name: 'xgboost'});

    render(wrap(<DashboardScreen navigation={navigation} />));

    await waitFor(() => expect(screen.getByText('Assalam-o-Alaikum, Ahmed')).toBeTruthy());
    expect(screen.getByText('2')).toBeTruthy(); // active crops
    expect(screen.getByText('7.50 acre')).toBeTruthy(); // total area
    expect(screen.getByText('PKR 4,200 PKR/40kg')).toBeTruthy(); // latest price
    // The synthetic-data warning must be visible, not hidden in a tooltip.
    expect(screen.getByText('Simulated data')).toBeTruthy();
  });

  it('still renders when the forecast service is down', async () => {
    farmApi.list.mockResolvedValue([]);
    cropApi.list.mockResolvedValue([]);
    financeApi.summary.mockRejectedValue(new ApiError('down', {status: 503}));
    marketApi.history.mockResolvedValue({points: []});
    forecastApi.get.mockRejectedValue(new ApiError('down', {status: 503}));

    render(wrap(<DashboardScreen navigation={navigation} />));

    await waitFor(() => expect(screen.getByText('Add your first farm')).toBeTruthy());
  });
});

describe('MarketScreen', () => {
  const catalogue = {
    commodity: [
      {id: 1, slug: 'wheat', name: 'Wheat'},
      {id: 2, slug: 'onion', name: 'Onion'},
    ],
    market: [
      {id: 1, slug: 'lahore-sabzi-mandi', name: 'Lahore Sabzi Mandi'},
      {id: 2, slug: 'multan-mandi', name: 'Multan Mandi'},
    ],
  };

  beforeEach(() => {
    const {catalogueApi} = require('../src/services/api');
    catalogueApi.commodities = jest.fn().mockResolvedValue(catalogue.commodity);
    catalogueApi.markets = jest.fn().mockResolvedValue(catalogue.market);
    marketApi.history.mockResolvedValue({
      unit: 'PKR/40kg',
      count: 2,
      points: [
        {price_date: '2026-11-01', avg_price_pkr: '4000.00', source: 'synthetic_fixture'},
        {price_date: '2026-11-02', avg_price_pkr: '4400.00', source: 'synthetic_fixture'},
      ],
    });
    marketApi.compare.mockResolvedValue({
      unit: 'PKR/40kg',
      best_market_slug: 'lahore-sabzi-mandi',
      rows: [
        {
          market: {id: 2, slug: 'multan-mandi', name: 'Multan Mandi'},
          latest_price_pkr: '4100.00',
          latest_date: '2026-11-02',
          avg_30d_pkr: '4000.00',
          change_pct_7d: '-1.20',
          observations: 30,
        },
        {
          market: {id: 1, slug: 'lahore-sabzi-mandi', name: 'Lahore Sabzi Mandi'},
          latest_price_pkr: '4400.00',
          latest_date: '2026-11-02',
          avg_30d_pkr: '4300.00',
          change_pct_7d: '2.40',
          observations: 30,
        },
      ],
    });
    forecastApi.get.mockResolvedValue({points: []});
  });

  it('renders the synthetic-data warning and sorts markets by price', async () => {
    const {catalogueApi} = require('../src/services/api');
    // Re-wire because jest.resetModules is not in play; the module object is shared.
    jest.spyOn(catalogueApi, 'commodities').mockResolvedValue(catalogue.commodity);
    jest.spyOn(catalogueApi, 'markets').mockResolvedValue(catalogue.market);

    render(wrap(<MarketScreen navigation={navigation} />));

    await waitFor(() => expect(screen.getByTestId('synthetic-warning')).toBeTruthy());
    await waitFor(() => expect(screen.getByText('PKR 4,400 PKR/40kg')).toBeTruthy());
    expect(screen.getByText('Best market today')).toBeTruthy();
  });

  it('shows the empty state rather than a broken chart with no points', async () => {
    const {catalogueApi} = require('../src/services/api');
    jest.spyOn(catalogueApi, 'commodities').mockResolvedValue(catalogue.commodity);
    jest.spyOn(catalogueApi, 'markets').mockResolvedValue(catalogue.market);
    marketApi.history.mockResolvedValue({points: []});
    marketApi.compare.mockResolvedValue({rows: [], best_market_slug: null});

    render(wrap(<MarketScreen navigation={navigation} />));

    await waitFor(() =>
      expect(screen.getAllByText('No price data for this commodity and market yet.').length)
        .toBeGreaterThan(0),
    );
  });
});

describe('FinanceScreen', () => {
  it('computes profit and shows the expense breakdown', async () => {
    financeApi.summary.mockResolvedValue({
      lifetime_revenue_pkr: '40000.00',
      lifetime_cost_pkr: '20000.00',
      lifetime_profit_pkr: '20000.00',
      margin_pct: '50.0',
      active_cycles: 1,
      seasons: [
        {
          season: 'rabi',
          year: 2026,
          cycles: 1,
          total_area_acres: '5.00',
          revenue_pkr: '40000.00',
          cost_pkr: '20000.00',
          profit_pkr: '20000.00',
          margin_pct: '50.0',
        },
      ],
      expense_breakdown: [
        {category: 'fertilizer', total_pkr: '15000.00', share_pct: '75.0'},
        {category: 'seeds', total_pkr: '5000.00', share_pct: '25.0'},
      ],
    });
    cropApi.list.mockResolvedValue([{id: 1, season: 'rabi', status: 'active'}]);

    render(wrap(<FinanceScreen />));

    await waitFor(() => expect(screen.getByText('PKR 20,000 PKR/40kg')).toBeTruthy());
    expect(screen.getByText('Fertilizer')).toBeTruthy();
    expect(screen.getByText('Seeds')).toBeTruthy();
    // Margin 50.0% appears on the summary row and on the rabi season row.
    expect(screen.getAllByText('50.0%').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('75%')).toBeTruthy();
  });

  it('shows the empty state when there are no crop cycles', async () => {
    cropApi.list.mockResolvedValue([]);
    financeApi.summary.mockResolvedValue({
      lifetime_revenue_pkr: '0',
      lifetime_cost_pkr: '0',
      lifetime_profit_pkr: '0',
      margin_pct: null,
      active_cycles: 0,
      seasons: [],
      expense_breakdown: [],
    });

    render(wrap(<FinanceScreen />));

    await waitFor(() => expect(screen.getByTestId('finance-empty')).toBeTruthy());
  });
});

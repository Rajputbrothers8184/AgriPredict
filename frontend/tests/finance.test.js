import {
  breakEvenPricePerMaund,
  expensesByCategory,
  normaliseBreakdown,
  priceChange,
  profitSummary,
  totalAreaAcres,
  totalExpenses,
  totalRevenue,
} from '../src/utils/finance';

const expenses = [
  {id: 1, category: 'seeds', amount_pkr: '8000'},
  {id: 2, category: 'fertilizer', amount_pkr: '12000'},
  {id: 3, category: 'fertilizer', amount_pkr: 4000},
];

const sales = [
  {id: 1, quantity_kg: 400, unit_price_pkr: 4000, total_amount_pkr: '40000'},
  {id: 2, quantity_kg: 200, unit_price_pkr: 4200},
];

describe('totalExpenses', () => {
  it('sums decimal strings and numbers', () => {
    expect(totalExpenses(expenses)).toBe(24000);
  });

  it('returns 0 for an empty list rather than NaN', () => {
    expect(totalExpenses([])).toBe(0);
    expect(totalExpenses(undefined)).toBe(0);
  });
});

describe('totalRevenue', () => {
  it('uses total_amount_pkr when stored and computes it when absent', () => {
    // 40000 stored + (200/40)*4200 = 21000 computed
    expect(totalRevenue(sales)).toBe(61000);
  });

  it('treats a maund as 40 kg in the fallback calculation', () => {
    expect(totalRevenue([{quantity_kg: 40, unit_price_pkr: 3900}])).toBe(3900);
    expect(totalRevenue([{quantity_kg: 80, unit_price_pkr: 3900}])).toBe(7800);
  });
});

describe('profitSummary', () => {
  it('computes cost, revenue, profit and margin', () => {
    const summary = profitSummary({expenses, sales});
    expect(summary.cost).toBe(24000);
    expect(summary.revenue).toBe(61000);
    expect(summary.profit).toBe(37000);
    expect(summary.margin).toBeCloseTo((37000 / 61000) * 100, 6);
    expect(summary.isProfit).toBe(true);
  });

  it('reports a null margin when there is no revenue, instead of dividing by zero', () => {
    const summary = profitSummary({expenses, sales: []});
    expect(summary.profit).toBe(-24000);
    expect(summary.margin).toBeNull();
    expect(summary.isProfit).toBe(false);
  });
});

describe('breakEvenPricePerMaund', () => {
  it('divides total cost by the harvested maunds', () => {
    // 24000 cost over 800 kg = 20 maunds => 1200 per maund
    expect(breakEvenPricePerMaund({expenses, expectedYieldKg: 800})).toBe(1200);
  });

  it('prefers actually sold quantity over expected yield', () => {
    // 24000 / (600 kg / 40) = 1600
    expect(
      breakEvenPricePerMaund({expenses, sales, expectedYieldKg: 5000}),
    ).toBeCloseTo(1600, 6);
  });

  it('returns null when there is nothing to divide by', () => {
    expect(breakEvenPricePerMaund({expenses: [], expectedYieldKg: 800})).toBeNull();
    expect(breakEvenPricePerMaund({expenses, expectedYieldKg: 0})).toBeNull();
  });
});

describe('expensesByCategory', () => {
  it('groups, sorts by amount and computes each share', () => {
    const rows = expensesByCategory(expenses);
    expect(rows.map(row => row.category)).toEqual(['fertilizer', 'seeds']);
    expect(rows[0].amount).toBe(16000);
    expect(rows[0].count).toBe(2);
    expect(rows[0].share).toBeCloseTo((16000 / 24000) * 100, 6);
  });

  it('buckets a missing category under "other"', () => {
    const rows = expensesByCategory([{amount_pkr: 100}]);
    expect(rows).toHaveLength(1);
    expect(rows[0].category).toBe('other');
  });
});

describe('totalAreaAcres', () => {
  it('sums decimal strings', () => {
    expect(totalAreaAcres([{area_acres: '5.00'}, {area_acres: 2.5}])).toBe(7.5);
  });

  it('is 0 for no cycles', () => {
    expect(totalAreaAcres([])).toBe(0);
  });
});

describe('normaliseBreakdown', () => {
  it('accepts the server shape (total_pkr / share_pct)', () => {
    const rows = normaliseBreakdown([
      {category: 'fertilizer', total_pkr: '15000.00', share_pct: '75.0'},
    ]);
    expect(rows[0]).toEqual({category: 'fertilizer', amount: 15000, share: 75});
  });

  it('accepts the locally computed shape (amount / share)', () => {
    const rows = normaliseBreakdown([{category: 'seeds', amount: 5000, share: 25}]);
    expect(rows[0]).toEqual({category: 'seeds', amount: 5000, share: 25});
  });

  it('never yields NaN for a malformed row', () => {
    const rows = normaliseBreakdown([{category: 'other'}]);
    expect(rows[0].amount).toBe(0);
    expect(rows[0].share).toBe(0);
  });
});

describe('priceChange', () => {
  it('compares the first and last price of a series', () => {
    const change = priceChange([4000, 4100, 4400]);
    expect(change.absolute).toBe(400);
    expect(change.percent).toBeCloseTo(10, 6);
  });

  it('returns null for a series that is too short or starts at zero', () => {
    expect(priceChange([4000])).toBeNull();
    expect(priceChange([])).toBeNull();
    expect(priceChange([0, 100])).toBeNull();
  });

  it('ignores non-numeric entries', () => {
    expect(priceChange(['4000', 'x', '4400'])).toEqual(
      expect.objectContaining({absolute: 400}),
    );
  });
});

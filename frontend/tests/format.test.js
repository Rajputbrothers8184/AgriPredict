import {
  daysUntil,
  formatArea,
  formatCompact,
  formatPercent,
  formatPrice,
  formatPriceWithUnit,
  formatQuantityKg,
  isPositiveNumber,
  toNumber,
  todayIso,
} from '../src/utils/format';

describe('toNumber', () => {
  it('coerces decimal strings from the API', () => {
    expect(toNumber('3900.50')).toBe(3900.5);
    expect(toNumber(42)).toBe(42);
  });

  it('returns null for empty and non-numeric values instead of NaN', () => {
    expect(toNumber('')).toBeNull();
    expect(toNumber(null)).toBeNull();
    expect(toNumber(undefined)).toBeNull();
    expect(toNumber('abc')).toBeNull();
    expect(toNumber(Infinity)).toBeNull();
  });
});

describe('price formatting', () => {
  it('formats whole rupees with thousands separators', () => {
    expect(formatPrice(3900)).toBe('PKR 3,900');
    expect(formatPrice(150000)).toBe('PKR 150,000');
    expect(formatPrice('12400.40')).toBe('PKR 12,400');
  });

  it('never renders a negative zero', () => {
    expect(formatPrice(-0.4)).toBe('PKR 0');
    expect(formatPrice(-1500)).toBe('PKR -1,500');
  });

  it('renders an em dash rather than "PKR 0" for missing data', () => {
    expect(formatPrice(null)).toBe('—');
    expect(formatPriceWithUnit(undefined)).toBe('—');
  });

  it('states the unit explicitly when asked', () => {
    expect(formatPriceWithUnit(3900)).toBe('PKR 3,900 PKR/40kg');
  });
});

describe('quantity and area formatting', () => {
  it('switches to tonnes at 1000 kg', () => {
    expect(formatQuantityKg(999)).toBe('999 kg');
    expect(formatQuantityKg(2000)).toBe('2.00 tonne');
  });

  it('drops decimals for whole acres', () => {
    expect(formatArea(5)).toBe('5 acre');
    expect(formatArea(2.5)).toBe('2.50 acre');
  });
});

describe('compact numbers', () => {
  it('uses Pakistani scale words', () => {
    expect(formatCompact(150000)).toBe('1.5 lakh');
    expect(formatCompact(25000000)).toBe('2.5 crore');
    expect(formatCompact(950)).toBe('950');
  });
});

describe('percent and dates', () => {
  it('formats percentages with a fixed precision', () => {
    expect(formatPercent(12.345)).toBe('12.3%');
    expect(formatPercent(null)).toBe('—');
  });

  it('produces an ISO date for form defaults', () => {
    expect(todayIso()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it('counts whole days until a date', () => {
    const future = new Date();
    future.setDate(future.getDate() + 10);
    expect(daysUntil(future)).toBe(10);
    expect(daysUntil('not-a-date')).toBeNull();
  });
});

describe('isPositiveNumber', () => {
  it('rejects zero, negatives and text', () => {
    expect(isPositiveNumber('0')).toBe(false);
    expect(isPositiveNumber('-3')).toBe(false);
    expect(isPositiveNumber('abc')).toBe(false);
    expect(isPositiveNumber('1.5')).toBe(true);
  });
});

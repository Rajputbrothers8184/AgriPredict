/**
 * Derived farm-finance calculations.
 *
 * The backend is authoritative and its `finance` block on a crop cycle is used
 * wherever it is available. These helpers exist for two cases the server cannot
 * cover: figures that must update while the farmer types, and offline use.
 * Field names follow the API schemas (`amount_pkr`, `unit_price_pkr`,
 * `total_amount_pkr`).
 */

import {toNumber} from './format';

export const KG_PER_MAUND = 40;

export function totalExpenses(expenses = []) {
  return expenses.reduce((sum, expense) => sum + (toNumber(expense.amount_pkr) || 0), 0);
}

/**
 * Sum of sale totals.
 *
 * `total_amount_pkr` is derived server-side; the local product is only a
 * fallback for an optimistic UI before the response arrives. The maund
 * conversion (1 maund = 40 kg) must match `finance_service.compute_sale_total`.
 */
export function totalRevenue(sales = []) {
  return sales.reduce((sum, sale) => {
    const stored = toNumber(sale.total_amount_pkr);
    if (stored !== null) {
      return sum + stored;
    }
    const kg = toNumber(sale.quantity_kg) || 0;
    const price = toNumber(sale.unit_price_pkr) || 0;
    return sum + (kg / KG_PER_MAUND) * price;
  }, 0);
}

export function profitSummary({expenses = [], sales = []} = {}) {
  const cost = totalExpenses(expenses);
  const revenue = totalRevenue(sales);
  const profit = revenue - cost;
  return {
    cost,
    revenue,
    profit,
    // A zero-revenue cycle has no meaningful margin; null beats Infinity on a
    // screen the farmer may act on.
    margin: revenue > 0 ? (profit / revenue) * 100 : null,
    isProfit: profit >= 0,
  };
}

/** Total area across cycles, in acres. */
export function totalAreaAcres(cycles = []) {
  return cycles.reduce((sum, cycle) => sum + (toNumber(cycle.area_acres) || 0), 0);
}

/**
 * Break-even price per 40 kg = total cost / (harvested maunds).
 * Falls back to the expected yield when nothing has been sold yet, which is the
 * number the farmer actually needs before harvest.
 */
export function breakEvenPricePerMaund({expenses = [], sales = [], expectedYieldKg = null} = {}) {
  const cost = totalExpenses(expenses);
  const soldKg = sales.reduce((sum, sale) => sum + (toNumber(sale.quantity_kg) || 0), 0);
  const kg = soldKg || toNumber(expectedYieldKg) || 0;
  if (cost <= 0 || kg <= 0) {
    return null;
  }
  return cost / (kg / KG_PER_MAUND);
}

/** Group expenses by category, largest first. */
export function expensesByCategory(expenses = []) {
  const groups = new Map();
  expenses.forEach(expense => {
    const category = expense.category || 'other';
    const amount = toNumber(expense.amount_pkr) || 0;
    const current = groups.get(category) || {category, amount: 0, count: 0};
    groups.set(category, {category, amount: current.amount + amount, count: current.count + 1});
  });
  const rows = [...groups.values()].sort((a, b) => b.amount - a.amount);
  const total = rows.reduce((sum, row) => sum + row.amount, 0);
  return rows.map(row => ({...row, share: total > 0 ? (row.amount / total) * 100 : 0}));
}

/**
 * Normalise the two shapes the app receives for expense breakdowns:
 * the server's ExpenseBreakdownRow ({category, total_pkr, share_pct}) and the
 * locally computed row ({category, amount, share}).
 */
export function normaliseBreakdown(rows = []) {
  return rows.map(row => ({
    category: row.category,
    amount: toNumber(row.total_pkr) ?? toNumber(row.amount) ?? 0,
    share: toNumber(row.share_pct) ?? toNumber(row.share) ?? 0,
  }));
}

/** Percentage change between the first and last value of a series. */
export function priceChange(prices = []) {
  const values = prices.map(toNumber).filter(value => value !== null);
  if (values.length < 2) {
    return null;
  }
  const first = values[0];
  const last = values[values.length - 1];
  if (first === 0) {
    return null;
  }
  return {absolute: last - first, percent: ((last - first) / first) * 100};
}

export default {
  totalExpenses,
  totalRevenue,
  profitSummary,
  totalAreaAcres,
  breakEvenPricePerMaund,
  expensesByCategory,
  normaliseBreakdown,
  priceChange,
  KG_PER_MAUND,
};

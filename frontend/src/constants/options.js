/**
 * Fixed option lists shared by forms, badges and filters.
 *
 * Values match the backend enums exactly (`expense_category`, `season`,
 * `crop_cycle.status`). Labels are translation keys, so nothing here needs a
 * translation import and tests can assert the option set.
 */

export const EXPENSE_CATEGORIES = [
  {value: 'seeds', labelKey: 'expenses.catSeeds'},
  {value: 'fertilizer', labelKey: 'expenses.catFertilizer'},
  {value: 'pesticide', labelKey: 'expenses.catPesticide'},
  {value: 'labour', labelKey: 'expenses.catLabour'},
  {value: 'irrigation', labelKey: 'expenses.catIrrigation'},
  {value: 'transport', labelKey: 'expenses.catTransport'},
  {value: 'machinery', labelKey: 'expenses.catMachinery'},
  {value: 'other', labelKey: 'expenses.catOther'},
];

export const SEASONS = [
  {value: 'rabi', labelKey: 'crops.seasonRabi'},
  {value: 'kharif', labelKey: 'crops.seasonKharif'},
  {value: 'yearly', labelKey: 'crops.seasonYearly'},
];

export const CROP_STATUSES = [
  {value: 'planned', labelKey: 'crops.statusPlanned', tone: 'neutral'},
  {value: 'active', labelKey: 'crops.statusActive', tone: 'info'},
  {value: 'harvested', labelKey: 'crops.statusHarvested', tone: 'success'},
  {value: 'failed', labelKey: 'crops.statusFailed', tone: 'danger'},
];

export const BUYER_CATEGORIES = [
  {value: 'trader', labelKey: 'buyers.categoryTrader'},
  {value: 'commission_agent', labelKey: 'buyers.categoryAgent'},
  {value: 'cold_storage', labelKey: 'buyers.categoryColdStorage'},
  {value: 'mill', labelKey: 'buyers.categoryMill'},
  {value: 'cooperative', labelKey: 'buyers.categoryCooperative'},
  {value: 'other', labelKey: 'buyers.categoryOther'},
];

export const FORECAST_HORIZONS = [
  {value: 7, labelKey: 'forecast.horizon7'},
  {value: 30, labelKey: 'forecast.horizon30'},
];

function findLabel(list, value, fallbackKey = null) {
  const match = list.find(option => option.value === value);
  return match ? match.labelKey : fallbackKey;
}

export function labelKeyFor(list, value, fallbackKey = null) {
  return findLabel(list, value, fallbackKey);
}

export function toneForStatus(status) {
  const match = CROP_STATUSES.find(option => option.value === status);
  return match ? match.tone : 'neutral';
}

export const MAUND_KG = 40;

/** kg -> maunds, the unit prices are quoted in. */
export function kgToMaunds(kg) {
  const number = Number(kg);
  return Number.isFinite(number) ? number / MAUND_KG : null;
}

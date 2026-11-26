/**
 * Form validation shared by every screen.
 *
 * Each validator returns a translation key (or null), never a literal sentence,
 * so messages are translated in both languages. This mirrors the backend's rules
 * so the user sees the problem before a round trip, but the backend remains the
 * authority — validation here is convenience, not security.
 */

import {toNumber} from './format';

export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
export const MIN_PASSWORD_LENGTH = 8;

export function required(value) {
  if (value === null || value === undefined) {
    return 'validation.required';
  }
  const text = String(value).trim();
  return text.length === 0 ? 'validation.required' : null;
}

export function validEmail(value) {
  const missing = required(value);
  if (missing) {
    return missing;
  }
  return EMAIL_PATTERN.test(String(value).trim()) ? null : 'auth.invalidEmail';
}

export function validPassword(value) {
  const missing = required(value);
  if (missing) {
    return missing;
  }
  const text = String(value);
  if (text.length < MIN_PASSWORD_LENGTH) {
    return 'auth.passwordRule';
  }
  const hasLetter = /[A-Za-z]/.test(text);
  const hasDigit = /[0-9]/.test(text);
  return hasLetter && hasDigit ? null : 'auth.passwordRule';
}

export function passwordsMatch(password, confirmation) {
  return password === confirmation ? null : 'auth.passwordsDoNotMatch';
}

export function positiveNumber(value) {
  const number = toNumber(value);
  return number !== null && number > 0 ? null : 'validation.positiveNumber';
}

export function nonNegativeNumber(value) {
  const number = toNumber(value);
  return number !== null && number >= 0 ? null : 'validation.nonNegativeNumber';
}

export function isoDate(value, {allowFuture = false} = {}) {
  const missing = required(value);
  if (missing) {
    return missing;
  }
  if (!ISO_DATE_PATTERN.test(value)) {
    return 'validation.invalidDate';
  }
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return 'validation.invalidDate';
  }
  if (!allowFuture) {
    const today = new Date();
    today.setHours(23, 59, 59, 999);
    if (parsed > today) {
      return 'validation.futureDate';
    }
  }
  return null;
}

export function harvestAfterSowing(sowingDate, harvestDate) {
  if (!sowingDate || !harvestDate) {
    return null;
  }
  return new Date(harvestDate) >= new Date(sowingDate) ? null : 'validation.harvestBeforeSowing';
}

/**
 * Run a field->validator map and return `{errors, valid}`.
 * Validators receive (value, allValues) so cross-field rules can be expressed.
 */
export function validateForm(values, rules) {
  const errors = {};
  Object.entries(rules).forEach(([field, validator]) => {
    const result = validator(values[field], values);
    if (result) {
      errors[field] = result;
    }
  });
  return {errors, valid: Object.keys(errors).length === 0};
}

/** "Yes/no"-style helpers used by the crop form. */
export function optionalPositiveNumber(value) {
  if (value === undefined || value === null || String(value).trim() === '') {
    return null;
  }
  return positiveNumber(value);
}

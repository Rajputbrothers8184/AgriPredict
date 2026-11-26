import {
  harvestAfterSowing,
  isoDate,
  nonNegativeNumber,
  passwordsMatch,
  positiveNumber,
  required,
  validEmail,
  validPassword,
  validateForm,
} from '../src/utils/validation';

describe('required', () => {
  it('rejects empty and whitespace-only values', () => {
    expect(required('')).toBe('validation.required');
    expect(required('   ')).toBe('validation.required');
    expect(required(null)).toBe('validation.required');
    expect(required(undefined)).toBe('validation.required');
  });

  it('accepts real content, including the number zero', () => {
    expect(required('Lahore')).toBeNull();
    expect(required(0)).toBeNull();
  });
});

describe('validEmail', () => {
  it('accepts ordinary addresses', () => {
    expect(validEmail('demo@agripredict.pk')).toBeNull();
    expect(validEmail('first.last+tag@mail.example.org')).toBeNull();
  });

  it('rejects malformed addresses', () => {
    ['demo', 'demo@', '@example.com', 'demo @example.com', 'demo@example'].forEach(
      value => {
        expect(validEmail(value)).toBe('auth.invalidEmail');
      },
    );
  });

  it('reports the missing case before the format case', () => {
    expect(validEmail('')).toBe('validation.required');
  });
});

describe('validPassword', () => {
  it('requires at least 8 characters with a letter and a digit', () => {
    expect(validPassword('Sunflower2026')).toBeNull();
    expect(validPassword('short1')).toBe('auth.passwordRule');
    expect(validPassword('allletters')).toBe('auth.passwordRule');
    expect(validPassword('12345678')).toBe('auth.passwordRule');
  });
});

describe('passwordsMatch', () => {
  it('flags a mismatch', () => {
    expect(passwordsMatch('abc12345', 'abc12345')).toBeNull();
    expect(passwordsMatch('abc12345', 'abc12346')).toBe('auth.passwordsDoNotMatch');
  });
});

describe('numeric fields', () => {
  it('accepts positive numbers only', () => {
    expect(positiveNumber('2.5')).toBeNull();
    expect(positiveNumber('0')).toBe('validation.positiveNumber');
    expect(positiveNumber('')).toBe('validation.positiveNumber');
  });

  it('allows zero where zero is meaningful', () => {
    expect(nonNegativeNumber('0')).toBeNull();
    expect(nonNegativeNumber('-1')).toBe('validation.nonNegativeNumber');
  });
});

describe('isoDate', () => {
  it('accepts a YYYY-MM-DD date', () => {
    expect(isoDate('2026-11-25', {allowFuture: true})).toBeNull();
  });

  it('rejects other formats', () => {
    expect(isoDate('25/11/2026')).toBe('validation.invalidDate');
    expect(isoDate('2026-13-01')).toBe('validation.invalidDate');
  });

  it('rejects a future date by default', () => {
    const nextYear = new Date();
    nextYear.setFullYear(nextYear.getFullYear() + 1);
    const iso = nextYear.toISOString().slice(0, 10);
    expect(isoDate(iso)).toBe('validation.futureDate');
    expect(isoDate(iso, {allowFuture: true})).toBeNull();
  });
});

describe('harvestAfterSowing', () => {
  it('requires the harvest date not to precede sowing', () => {
    expect(harvestAfterSowing('2026-11-01', '2027-04-01')).toBeNull();
    expect(harvestAfterSowing('2026-11-01', '2026-10-01')).toBe(
      'validation.harvestBeforeSowing',
    );
  });

  it('is skipped when either date is missing', () => {
    expect(harvestAfterSowing('', '2027-04-01')).toBeNull();
  });
});

describe('validateForm', () => {
  it('returns per-field keys and a validity flag', () => {
    const {errors, valid} = validateForm(
      {name: '', area: '0'},
      {name: required, area: positiveNumber},
    );
    expect(valid).toBe(false);
    expect(errors).toEqual({
      name: 'validation.required',
      area: 'validation.positiveNumber',
    });
  });

  it('passes a fully valid form', () => {
    const {errors, valid} = validateForm(
      {name: 'Wheat plot', area: '5'},
      {name: required, area: positiveNumber},
    );
    expect(valid).toBe(true);
    expect(errors).toEqual({});
  });
});

import en from '../src/localization/en';
import ur from '../src/localization/ur';
import {
  flattenKeys,
  interpolate,
  isRtl,
  missingKeys,
  placeholdersIn,
  translate,
} from '../src/localization';

describe('catalogue parity', () => {
  it('has no English key missing from Urdu', () => {
    expect(missingKeys(en, ur)).toEqual([]);
  });

  it('has no Urdu key that English lacks (a stale translation)', () => {
    expect(missingKeys(ur, en)).toEqual([]);
  });

  it('does not translate any key to an empty string', () => {
    const empties = flattenKeys(ur).filter(key => {
      const value = key.split('.').reduce((node, part) => node[part], ur);
      return typeof value === 'string' && value.trim() === '';
    });
    expect(empties).toEqual([]);
  });

  it('keeps the same placeholders in both languages', () => {
    const mismatches = [];
    flattenKeys(en).forEach(key => {
      const english = key.split('.').reduce((node, part) => node[part], en);
      const urdu = key.split('.').reduce((node, part) => node[part], ur);
      if (typeof english !== 'string') {
        return;
      }
      const a = placeholdersIn(english).join(',');
      const b = placeholdersIn(urdu).join(',');
      if (a !== b) {
        mismatches.push(`${key}: en{${a}} vs ur{${b}}`);
      }
    });
    expect(mismatches).toEqual([]);
  });
});

describe('translate', () => {
  it('resolves nested keys in the requested language', () => {
    expect(translate('en', 'nav.dashboard')).toBe('Dashboard');
    expect(translate('ur', 'nav.dashboard')).toBe('ڈیش بورڈ');
  });

  it('interpolates named parameters', () => {
    expect(translate('en', 'market.observations', {count: 31})).toBe('31 observations');
    expect(interpolate('Hello {name}, {count} items', {name: 'Ali', count: 2})).toBe(
      'Hello Ali, 2 items',
    );
  });

  it('leaves an unknown placeholder visible instead of printing undefined', () => {
    expect(interpolate('Hello {name}', {})).toBe('Hello {name}');
  });

  it('falls back to English for a key missing in the chosen locale', () => {
    // Simulated by asking for a real key with an unknown language code.
    expect(translate('xx', 'common.save')).toBe('Save');
  });

  it('returns the key itself when it exists nowhere', () => {
    expect(translate('en', 'nope.not.here')).toBe('nope.not.here');
  });
});

describe('direction', () => {
  it('marks Urdu as right-to-left and English as not', () => {
    expect(isRtl('ur')).toBe(true);
    expect(isRtl('en')).toBe(false);
    expect(isRtl('de')).toBe(false);
  });
});

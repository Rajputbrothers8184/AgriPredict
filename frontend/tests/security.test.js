/**
 * Security tests for the app's own attack surface.
 *
 * The backend suites prove the server refuses bad requests. They cannot prove
 * anything about the device, where the tokens live and what the app does with
 * untrusted values. These tests cover that side.
 */

/* eslint-disable no-script-url -- these tests deliberately feed hostile URLs *
 * to the scheme guard; asserting on the literal is the whole point.          */

import AsyncStorage from '@react-native-async-storage/async-storage';

import {STORAGE_KEYS} from '../src/config';
import {safeExternalUrl, telUri} from '../src/utils/format';
import {validEmail, validPassword} from '../src/utils/validation';
import {
  clearSession,
  getAccessToken,
  persistSession,
  restoreSession,
  setTokens,
} from '../src/services/session';

jest.mock('../src/services/api', () => ({
  authApi: {refresh: jest.fn()},
}));

beforeEach(async () => {
  await AsyncStorage.clear();
  setTokens({accessToken: null, refreshToken: null});
});

describe('what is written to device storage', () => {
  it('persists the tokens under explicit keys', async () => {
    await persistSession({
      accessToken: 'access-abc',
      refreshToken: 'refresh-xyz',
      user: {id: 1, email: 'farmer@agripredict.pk', role: 'farmer'},
    });

    const keys = await AsyncStorage.getAllKeys();
    expect(keys).toEqual(
      expect.arrayContaining([
        STORAGE_KEYS.accessToken,
        STORAGE_KEYS.refreshToken,
        STORAGE_KEYS.user,
      ]),
    );
  });

  it('never writes a password or a password hash to storage', async () => {
    await persistSession({
      accessToken: 'access-abc',
      refreshToken: 'refresh-xyz',
      user: {id: 1, email: 'farmer@agripredict.pk'},
    });

    const keys = await AsyncStorage.getAllKeys();
    const everything = JSON.stringify(await AsyncStorage.multiGet(keys));
    expect(everything).not.toMatch(/password/i);
    expect(everything).not.toMatch(/\$2[aby]\$/);
  });

  it('keeps tokens out of the stored user object', async () => {
    await persistSession({
      accessToken: 'access-abc',
      refreshToken: 'refresh-xyz',
      user: {id: 1, email: 'farmer@agripredict.pk'},
    });
    const storedUser = await AsyncStorage.getItem(STORAGE_KEYS.user);
    expect(storedUser).not.toContain('access-abc');
    expect(storedUser).not.toContain('refresh-xyz');
  });

  it('clears every token on sign-out, leaving nothing usable behind', async () => {
    await persistSession({
      accessToken: 'access-abc',
      refreshToken: 'refresh-xyz',
      user: {id: 1, email: 'farmer@agripredict.pk'},
    });

    await clearSession();

    expect(getAccessToken()).toBeNull();
    const keys = await AsyncStorage.getAllKeys();
    const everything = JSON.stringify(await AsyncStorage.multiGet(keys));
    expect(everything).not.toContain('access-abc');
    expect(everything).not.toContain('refresh-xyz');
  });

  it('survives a corrupted stored session instead of crashing at launch', async () => {
    await AsyncStorage.setItem(STORAGE_KEYS.user, '{not json');
    const restored = await restoreSession();
    expect(restored.user).toBeNull();
  });
});

describe('URLs handed to other apps', () => {
  it('refuses dangerous schemes', () => {
    expect(safeExternalUrl('javascript:alert(1)')).toBeNull();
    expect(safeExternalUrl('JavaScript:alert(1)')).toBeNull();
    expect(safeExternalUrl('data:text/html,<script>alert(1)</script>')).toBeNull();
    expect(safeExternalUrl('file:///etc/passwd')).toBeNull();
    expect(safeExternalUrl('intent://scan/#Intent;scheme=zxing;end')).toBeNull();
    expect(safeExternalUrl('content://com.android.contacts/data/1')).toBeNull();
  });

  it('refuses values that are not URLs at all', () => {
    expect(safeExternalUrl('')).toBeNull();
    expect(safeExternalUrl(null)).toBeNull();
    expect(safeExternalUrl(undefined)).toBeNull();
    expect(safeExternalUrl('//evil.example.com/x')).toBeNull();
    expect(safeExternalUrl(42)).toBeNull();
  });

  it('allows the schemes the app actually uses', () => {
    expect(safeExternalUrl('https://api.agripredict.pk/r/7.pdf')).toBe(
      'https://api.agripredict.pk/r/7.pdf',
    );
    expect(safeExternalUrl('  https://example.com/a.pdf  ')).toBe('https://example.com/a.pdf');
    expect(safeExternalUrl('tel:+923001234567')).toBe('tel:+923001234567');
    expect(safeExternalUrl('mailto:farmer@agripredict.pk')).toBe('mailto:farmer@agripredict.pk');
  });

  it('builds a tel: URI from a hostile phone value without injecting a scheme', () => {
    // A buyer record comes from an external search provider; the number is not
    // trusted. Anything that is not dialler syntax is dropped.
    expect(telUri('0300-1234567')).toBe('tel:0300-1234567');
    expect(telUri('+92 300 1234567')).toBe('tel:+92 300 1234567');
    expect(telUri('0300; DIAL *123#')).toBe('tel:0300  123');
    expect(telUri('0300; DIAL *123#')).not.toContain('#');
    expect(telUri('0300; DIAL *123#')).not.toContain(';');
    expect(telUri('javascript:alert(1)')).toBeNull();
    expect(telUri('12')).toBeNull();
    expect(telUri(null)).toBeNull();
  });
});

describe('values that reach the screen', () => {
  it('renders a non-numeric price as a placeholder, never as markup', () => {
    const hostile = '<img src=x onerror="steal()">';
    const {formatPrice} = require('../src/utils/format');
    // A string from the server is not coerced into markup or echoed back; a
    // price that is not a number becomes the "no value" placeholder.
    expect(formatPrice(hostile)).toBe('—');
    expect(formatPrice(hostile)).not.toContain('<');
  });

  it('does not crash on control characters or emoji', () => {
    const {formatPrice} = require('../src/utils/format');
    expect(formatPrice('\u0000\u001b[31m')).toBe('—');
    expect(formatPrice('🌾')).toBe('—');
  });
});

describe('client-side validation', () => {
  it('rejects a weak password without a round trip', () => {
    expect(validPassword('short')).toBeTruthy();
    expect(validPassword('12345678')).toBeTruthy(); // digits only
    expect(validPassword('abcdefgh')).toBeTruthy(); // letters only
    expect(validPassword('Sunflower2026')).toBeNull();
  });

  it('rejects a malformed email without a round trip', () => {
    expect(validEmail('not-an-email')).toBeTruthy();
    expect(validEmail('a@b')).toBeTruthy();
    expect(validEmail('two@@at.pk')).toBeTruthy();
    expect(validEmail('farmer@agripredict.pk')).toBeNull();
  });
});

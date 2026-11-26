import AsyncStorage from '@react-native-async-storage/async-storage';

jest.mock('../src/services/api', () => ({
  authApi: {
    refresh: jest.fn(),
  },
}));

import {authApi} from '../src/services/api';
import {
  __resetSession,
  clearSession,
  getAccessToken,
  getRefreshToken,
  persistSession,
  refreshSession,
  restoreSession,
  setSessionLostHandler,
} from '../src/services/session';
import {STORAGE_KEYS} from '../src/config';

describe('session storage', () => {
  beforeEach(async () => {
    __resetSession();
    await AsyncStorage.clear();
    jest.clearAllMocks();
  });

  it('persists tokens and the user, then restores them', async () => {
    await persistSession({
      accessToken: 'access-1',
      refreshToken: 'refresh-1',
      user: {id: 1, email: 'demo@agripredict.pk'},
    });

    expect(await AsyncStorage.getItem(STORAGE_KEYS.accessToken)).toBe('access-1');

    __resetSession();
    const restored = await restoreSession();
    expect(restored.accessToken).toBe('access-1');
    expect(restored.refreshToken).toBe('refresh-1');
    expect(restored.user.email).toBe('demo@agripredict.pk');
  });

  it('clears everything on sign out', async () => {
    await persistSession({accessToken: 'a', refreshToken: 'r', user: {id: 1}});
    await clearSession();

    expect(getAccessToken()).toBeNull();
    expect(getRefreshToken()).toBeNull();
    expect(await AsyncStorage.getItem(STORAGE_KEYS.accessToken)).toBeNull();
    expect(await AsyncStorage.getItem(STORAGE_KEYS.refreshToken)).toBeNull();
    expect(await AsyncStorage.getItem(STORAGE_KEYS.user)).toBeNull();
  });

  it('survives corrupt stored JSON instead of crashing on launch', async () => {
    await AsyncStorage.setItem(STORAGE_KEYS.user, '{not json');
    const restored = await restoreSession();
    expect(restored.accessToken).toBeNull();
    expect(restored.user).toBeNull();
  });

  it('returns null without a refresh token', async () => {
    expect(await refreshSession()).toBeNull();
  });

  it('rotates the pair on a successful refresh', async () => {
    await persistSession({accessToken: 'old', refreshToken: 'r1', user: {id: 1}});
    authApi.refresh.mockResolvedValue({access_token: 'new', refresh_token: 'r2'});

    const token = await refreshSession();

    expect(token).toBe('new');
    expect(getRefreshToken()).toBe('r2');
    expect(await AsyncStorage.getItem(STORAGE_KEYS.refreshToken)).toBe('r2');
  });

  it('collapses concurrent refreshes into one request', async () => {
    await persistSession({accessToken: 'old', refreshToken: 'r1', user: {id: 1}});
    authApi.refresh.mockResolvedValue({access_token: 'new', refresh_token: 'r2'});

    const results = await Promise.all([refreshSession(), refreshSession(), refreshSession()]);

    expect(authApi.refresh).toHaveBeenCalledTimes(1);
    expect(results).toEqual(['new', 'new', 'new']);
  });

  it('clears the session and notifies when the refresh is rejected', async () => {
    const onLost = jest.fn();
    setSessionLostHandler(onLost);
    await persistSession({accessToken: 'old', refreshToken: 'r1', user: {id: 1}});
    authApi.refresh.mockRejectedValue(new Error('401'));

    const token = await refreshSession();

    expect(token).toBeNull();
    expect(onLost).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBeNull();
  });
});

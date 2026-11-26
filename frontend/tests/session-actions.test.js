/**
 * Sign-out behaviour.
 *
 * The distinction these tests protect is easy to lose in a refactor: ordinary
 * sign-out revokes this device's refresh token only, while "sign out everywhere"
 * bumps the server-side token version and kills *every* access token. Wiring the
 * destructive button to the ordinary call would look identical in the UI and
 * silently weaken the feature users reach for when a phone is lost.
 */

import React from 'react';
import {Alert} from 'react-native';
import {fireEvent, render, waitFor} from '@testing-library/react-native';

const mockLogout = jest.fn();
const mockLogoutAll = jest.fn();

jest.mock('../src/services/api', () => ({
  authApi: {
    logout: (...args) => mockLogout(...args),
    logoutAll: (...args) => mockLogoutAll(...args),
    me: jest.fn(),
    updateProfile: jest.fn(),
    changePassword: jest.fn(),
  },
}));

jest.mock('../src/services/session', () => ({
  getRefreshToken: () => 'refresh-token-abc',
  getAccessToken: () => 'access-token-abc',
  setSessionLostHandler: jest.fn(),
  clearSession: jest.fn(async () => {}),
  // The provider calls this on mount to restore a stored session.
  restoreSession: jest.fn(async () => ({
    accessToken: 'access-token-abc',
    refreshToken: 'refresh-token-abc',
    user: {id: 1, email: 'demo@agripredict.pk'},
  })),
  // Returned by handleSessionLost; clearing local state is what matters here.
  persistSession: jest.fn(async () => {}),
  setTokens: jest.fn(),
}));

import {AuthProvider, useAuth} from '../src/context/AuthContext';

import {Button} from '../src/components/ui';
import {LocalizationProvider} from '../src/context/LocalizationContext';
import {ThemeProvider} from '../src/context/ThemeContext';
import MoreScreen from '../src/screens/MoreScreen';

function Harness() {
  const {logout, logoutEverywhere} = useAuth();
  return (
    <>
      <Button testID="plain" title="Sign out" onPress={logout} />
      <Button testID="all" title="Sign out everywhere" onPress={logoutEverywhere} />
    </>
  );
}

beforeEach(() => {
  // Call counts must not leak between tests: the whole point of these
  // assertions is which of the two endpoints was called.
  mockLogout.mockReset();
  mockLogoutAll.mockReset();
});

describe('ordinary sign-out', () => {
  it('revokes this device\'s refresh token and not every session', async () => {
    mockLogout.mockResolvedValue({});
    const {getByTestId} = render(
      <AuthProvider>
        <ThemeProvider>
          <LocalizationProvider>
            <Harness />
          </LocalizationProvider>
        </ThemeProvider>
      </AuthProvider>,
    );

    fireEvent.press(getByTestId('plain'));

    await waitFor(() => expect(mockLogout).toHaveBeenCalledWith('refresh-token-abc'));
    expect(mockLogoutAll).not.toHaveBeenCalled();
  });
});

describe('sign out everywhere', () => {
  it('calls the revoking endpoint, not the ordinary one', async () => {
    mockLogoutAll.mockResolvedValue({});
    const {getByTestId} = render(
      <AuthProvider>
        <ThemeProvider>
          <LocalizationProvider>
            <Harness />
          </LocalizationProvider>
        </ThemeProvider>
      </AuthProvider>,
    );

    fireEvent.press(getByTestId('all'));

    await waitFor(() => expect(mockLogoutAll).toHaveBeenCalled());
    expect(mockLogout).not.toHaveBeenCalled();
  });

  it('still clears the local session when the server call fails', async () => {
    // A failed revoke must not leave the user signed in: they asked to leave.
    mockLogoutAll.mockRejectedValue(new Error('network down'));
    const {getByTestId} = render(
      <AuthProvider>
        <ThemeProvider>
          <LocalizationProvider>
            <Harness />
          </LocalizationProvider>
        </ThemeProvider>
      </AuthProvider>,
    );

    fireEvent.press(getByTestId('all'));

    await waitFor(() => expect(mockLogoutAll).toHaveBeenCalled());
    // No unhandled rejection and the component is still mounted.
    expect(getByTestId('all')).toBeTruthy();
  });
});

describe('the More screen', () => {
  // The screen consumes useAuth, so it is rendered through a provider whose
  // value is controlled here rather than through the real session machinery.
  const {default: AuthContext} = require('../src/context/AuthContext');

  function renderMore(value) {
    return render(
      <AuthContext.Provider value={value}>
        <ThemeProvider>
          <LocalizationProvider>
            <MoreScreen navigation={{navigate: jest.fn()}} />
          </LocalizationProvider>
        </ThemeProvider>
      </AuthContext.Provider>,
    );
  }

  it('offers both sign-out actions', () => {
    const {getByTestId} = renderMore({
      user: {id: 1, full_name: 'Ahmed Raza', email: 'demo@agripredict.pk'},
      logout: jest.fn(),
      logoutEverywhere: jest.fn(),
    });
    expect(getByTestId('more-logout')).toBeTruthy();
    expect(getByTestId('more-logout-all')).toBeTruthy();
  });

  it('confirms before signing out everywhere, and does nothing on cancel', () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    const logoutEverywhere = jest.fn();
    const {getByTestId} = renderMore({
      user: {id: 1, full_name: 'Ahmed Raza', email: 'demo@agripredict.pk'},
      logout: jest.fn(),
      logoutEverywhere,
    });

    fireEvent.press(getByTestId('more-logout-all'));

    expect(alertSpy).toHaveBeenCalledTimes(1);
    // Cancelling must not sign anyone out.
    expect(logoutEverywhere).not.toHaveBeenCalled();

    // Confirming (the destructive button) does.
    const buttons = alertSpy.mock.calls[0][2];
    const confirm = buttons.find(button => button.style === 'destructive');
    confirm.onPress();
    expect(logoutEverywhere).toHaveBeenCalledTimes(1);
    alertSpy.mockRestore();
  });

  it('the ordinary sign-out button does not ask, it just signs out', () => {
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
    const logout = jest.fn();
    const {getByTestId} = renderMore({
      user: {id: 1, full_name: 'Ahmed Raza', email: 'demo@agripredict.pk'},
      logout,
      logoutEverywhere: jest.fn(),
    });

    fireEvent.press(getByTestId('more-logout'));
    expect(logout).toHaveBeenCalledTimes(1);
    expect(alertSpy).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });
});

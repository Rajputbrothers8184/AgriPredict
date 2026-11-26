/**
 * Map API/network errors to translation keys.
 *
 * Screens render `t(error.messageKey)`, so every failure the user can hit has a
 * translated sentence in both languages instead of an English server string.
 */

import {ApiError} from '../services/apiClient';

export function mapApiError(error) {
  if (!(error instanceof ApiError)) {
    return {
      messageKey: 'common.somethingWentWrong',
      code: 'unknown',
      status: 0,
      details: null,
    };
  }

  const byCode = {
    offline: 'errors.network',
    timeout: 'errors.timeout',
    session_expired: 'errors.unauthorized',
    invalid_credentials: 'auth.loginFailed',
    email_taken: 'auth.registerFailed',
    not_configured: 'errors.notConfigured',
    not_found: 'errors.notFound',
    validation_error: 'errors.validation',
  };

  let messageKey = byCode[error.code];
  if (!messageKey) {
    if (error.status === 401) {
      messageKey = 'errors.unauthorized';
    } else if (error.status === 404) {
      messageKey = 'errors.notFound';
    } else if (error.status === 422) {
      messageKey = 'errors.validation';
    } else if (error.status === 503) {
      messageKey = 'errors.notConfigured';
    } else if (error.status >= 500) {
      messageKey = 'errors.server';
    } else {
      messageKey = 'common.somethingWentWrong';
    }
  }

  return {
    messageKey,
    code: error.code,
    status: error.status,
    details: error.details,
    // The server's own message is kept for logs and for wording that carries
    // information the catalogue cannot (e.g. which field is invalid).
    serverMessage: error.message,
    retryable: error.isRetryable,
  };
}

export default mapApiError;

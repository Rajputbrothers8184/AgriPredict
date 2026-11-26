import {ApiError} from '../src/services/apiClient';
import {mapApiError} from '../src/utils/errors';

describe('mapApiError', () => {
  it('prefers the error code over the HTTP status', () => {
    const error = new ApiError('no places key', {status: 503, code: 'not_configured'});
    expect(mapApiError(error).messageKey).toBe('errors.notConfigured');
  });

  it('maps offline and timeout to their own messages', () => {
    expect(mapApiError(new ApiError('x', {code: 'offline'})).messageKey).toBe(
      'errors.network',
    );
    expect(mapApiError(new ApiError('x', {code: 'timeout'})).messageKey).toBe(
      'errors.timeout',
    );
  });

  it('maps bare statuses when there is no code', () => {
    const cases = [
      [401, 'errors.unauthorized'],
      [404, 'errors.notFound'],
      [422, 'errors.validation'],
      [503, 'errors.notConfigured'],
      [500, 'errors.server'],
      [418, 'common.somethingWentWrong'],
    ];
    cases.forEach(([status, expected]) => {
      expect(mapApiError(new ApiError('x', {status})).messageKey).toBe(expected);
    });
  });

  it('carries the server message through for diagnostics', () => {
    const mapped = mapApiError(
      new ApiError('area_acres must be greater than 0', {status: 422, code: 'validation_error'}),
    );
    expect(mapped.serverMessage).toBe('area_acres must be greater than 0');
  });

  it('handles a non-ApiError without crashing', () => {
    const mapped = mapApiError(new Error('boom'));
    expect(mapped.messageKey).toBe('common.somethingWentWrong');
    expect(mapped.code).toBe('unknown');
  });

  it('marks 5xx and offline as retryable but not a 404', () => {
    expect(mapApiError(new ApiError('x', {status: 500})).retryable).toBe(true);
    expect(mapApiError(new ApiError('x', {status: 404})).retryable).toBe(false);
  });
});

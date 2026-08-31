const TIME_ZONE_SUFFIX = /(?:z|[+-]\d{2}:?\d{2})$/i;

export function parseApiTimestamp(value: string): Date {
  // The API stores UTC values, but SQLite serializes them without a trailing
  // timezone. Browsers otherwise interpret those values as local time.
  return new Date(TIME_ZONE_SUFFIX.test(value) ? value : `${value}Z`);
}

export function formatLocalTimestamp(value: string): string {
  return parseApiTimestamp(value).toLocaleString();
}

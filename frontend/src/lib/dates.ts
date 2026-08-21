export const parseApiDate = (isoString?: string | null) => {
  if (!isoString) return null;
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(isoString);
  return new Date(hasTimezone ? isoString : `${isoString}Z`);
};

export const formatApiDateTime = (isoString?: string | null) => {
  const date = parseApiDate(isoString);
  if (!date || Number.isNaN(date.getTime())) return isoString || '-';

  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

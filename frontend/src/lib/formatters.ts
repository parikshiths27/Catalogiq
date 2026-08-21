export interface FormattedValueUnit {
  value: string;
  unit: string;
}

/**
 * Formats value and unit strings ensuring units are cleanly separated
 * and not duplicated (e.g. preventing "230 V V" or "24 in in").
 */
export const formatAttrValueAndUnit = (
  rawValue?: any,
  unit?: string | null,
  normalizedValue?: any
): FormattedValueUnit => {
  let valStr =
    normalizedValue !== undefined && normalizedValue !== null && normalizedValue !== ''
      ? String(normalizedValue)
      : String(rawValue || '');

  valStr = valStr.trim();
  const unitStr = (unit || '').trim();

  if (!unitStr) {
    return { value: valStr, unit: '' };
  }

  // Remove unit if already embedded at the end of value string (case-insensitive)
  const escapedUnit = unitStr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const trailingUnitRegex = new RegExp(`\\s*${escapedUnit}$`, 'i');

  if (trailingUnitRegex.test(valStr)) {
    valStr = valStr.replace(trailingUnitRegex, '').trim();
  }

  return { value: valStr, unit: unitStr };
};

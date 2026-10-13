/** Common exchange:ticker identity; bare Korean codes remain valid legacy inputs. */
export function tickerOf(id: string): string {
  return id.split(":").at(-1) || id;
}

export function isUSInstrument(id: string): boolean {
  return /^(NASDAQ|NYSE|AMEX):/i.test(id);
}

export function isInstrumentId(id: string): boolean {
  return /^(?:[0-9][A-Z0-9]{5}|(?:KRX|KOSPI|KOSDAQ):[A-Z0-9]{6})$/.test(id) ||
    (/^(NASDAQ|NYSE|AMEX):[A-Z0-9][A-Z0-9./\-]{0,19}$/.test(id) && !id.includes(".."));
}

export function sameInstrument(left: string, right: string): boolean {
  if (isUSInstrument(left) || isUSInstrument(right)) return left === right;
  if (left.includes(":") && right.includes(":") && !left.startsWith("KRX:") && !right.startsWith("KRX:")) return left === right;
  return tickerOf(left) === tickerOf(right);
}

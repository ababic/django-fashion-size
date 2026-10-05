/**Centimetre / inch conversion matching ``fashion_size`` (1 in = 2.54 cm).

Stored tokens keep the exact value (28 significant digits, half up).
Displayed tokens round to the nearest centimetre or half inch.
*/

const SIGNIFICANT = 28;
const CM_NUMERATOR = 254n;
const CM_DENOMINATOR = 100n;

function parseDecimal(text) {
  const raw = String(text ?? "").trim();
  if (!/^\d+(\.\d+)?$/.test(raw)) {
    return null;
  }
  const [whole, frac = ""] = raw.split(".");
  return {
    num: BigInt(whole + frac),
    den: 10n ** BigInt(frac.length),
  };
}

function gcd(left, right) {
  let a = left < 0n ? -left : left;
  let b = right < 0n ? -right : right;
  while (b) {
    const next = a % b;
    a = b;
    b = next;
  }
  return a || 1n;
}

function simplify(num, den) {
  const divisor = gcd(num, den);
  return [num / divisor, den / divisor];
}

function formatSignificant(num, den) {
  if (num === 0n) {
    return "0";
  }
  const integer = num / den;
  const integerText = integer.toString();
  let remainder = num % den;
  if (remainder === 0n) {
    return integerText;
  }

  if (integer > 0n) {
    const fractionDigits = Math.max(SIGNIFICANT - integerText.length, 0);
    let digits = "";
    let guard = 0;
    for (let index = 0; index < fractionDigits + 1; index += 1) {
      remainder *= 10n;
      const digit = remainder / den;
      remainder %= den;
      if (index < fractionDigits) {
        digits += digit.toString();
      } else {
        guard = Number(digit);
      }
    }
    let combined = integerText + digits;
    if (guard >= 5) {
      combined = (BigInt(combined) + 1n).toString();
    }
    if (fractionDigits === 0) {
      return combined;
    }
    const whole = combined.slice(0, combined.length - fractionDigits);
    const fraction = combined.slice(combined.length - fractionDigits).replace(/0+$/, "");
    return fraction ? `${whole}.${fraction}` : whole;
  }

  let leading = "";
  let significant = "";
  let guard = 0;
  for (let index = 0; index < 80 && significant.length < SIGNIFICANT + 1; index += 1) {
    remainder *= 10n;
    const digit = remainder / den;
    remainder %= den;
    if (!significant && digit === 0n) {
      leading += "0";
      continue;
    }
    if (significant.length < SIGNIFICANT) {
      significant += digit.toString();
    } else {
      guard = Number(digit);
      break;
    }
  }
  if (guard >= 5) {
    const rounded = BigInt(significant) + 1n;
    significant = rounded.toString();
    if (significant.length > SIGNIFICANT) {
      significant = significant.slice(1);
      leading = leading.slice(1);
      if (!leading && !significant) {
        return "1";
      }
      if (!leading) {
        return significant.replace(/0+$/, "") || "1";
      }
    }
  }
  significant = significant.replace(/0+$/, "");
  return `0.${leading}${significant}`;
}

function inchesOf(text, unit) {
  const parsed = parseDecimal(text);
  if (!parsed) {
    return null;
  }
  if (unit === "in") {
    return simplify(parsed.num, parsed.den);
  }
  if (unit === "cm") {
    return simplify(parsed.num * CM_DENOMINATOR, parsed.den * CM_NUMERATOR);
  }
  return null;
}

function inRange(inchesNum, inchesDen) {
  const min = inchesNum * 1n >= 5n * inchesDen;
  const max = inchesNum * 1n <= 150n * inchesDen;
  return min && max;
}

function roundHalfUpRational(num, den) {
  const base = num / den;
  const remainder = num % den;
  return base + (remainder * 2n >= den ? 1n : 0n);
}

function roundHalfInchRational(num, den) {
  const doubled = roundHalfUpRational(num * 2n, den);
  if (doubled % 2n === 0n) {
    return (doubled / 2n).toString();
  }
  return `${doubled / 2n}.5`;
}

export function convertLength(text, fromUnit, toUnit, { display = false } = {}) {
  const from = fromUnit === "inches" ? "in" : fromUnit;
  const to = toUnit === "centimetres" ? "cm" : toUnit;
  if ((from !== "in" && from !== "cm") || (to !== "in" && to !== "cm")) {
    return null;
  }
  const parsed = parseDecimal(text);
  const inches = inchesOf(text, from);
  if (!parsed || !inches || !inRange(inches[0], inches[1])) {
    return null;
  }
  let storedNum;
  let storedDen;
  if (from === to) {
    [storedNum, storedDen] = simplify(parsed.num, parsed.den);
  } else if (to === "cm") {
    [storedNum, storedDen] = simplify(inches[0] * CM_NUMERATOR, inches[1] * CM_DENOMINATOR);
  } else {
    [storedNum, storedDen] = inches;
  }
  if (display && from !== to) {
    if (to === "cm") {
      return roundHalfUpRational(storedNum, storedDen).toString();
    }
    return roundHalfInchRational(storedNum, storedDen);
  }
  return formatSignificant(storedNum, storedDen);
}

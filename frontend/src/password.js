// Password and recovery-code rules. Same rules as backend/app/security.py.
export const PASSWORD_RULES = [
  { key: 'len', label: 'At least 8 characters', test: (p) => p.length >= 8 },
  { key: 'upper', label: 'A capital letter (A–Z)', test: (p) => /[A-Z]/.test(p) },
  { key: 'lower', label: 'A small letter (a–z)', test: (p) => /[a-z]/.test(p) },
  { key: 'digit', label: 'A number (0–9)', test: (p) => /[0-9]/.test(p) },
  { key: 'symbol', label: 'A symbol, like ! @ # $', test: (p) => /[^A-Za-z0-9]/.test(p) }
];

export const passwordProblem = (p = '') => {
  const miss = PASSWORD_RULES.find((r) => !r.test(p));
  return miss ? `Password needs ${miss.label.charAt(0).toLowerCase()}${miss.label.slice(1)}.` : '';
};

const WEAK_CODES = new Set(['0000', '1111', '2222', '3333', '4444', '5555', '6666', '7777', '8888', '9999',
  '1234', '2345', '3456', '4567', '5678', '6789', '4321', '9876', '0123', '1212', '1122']);

export const codeProblem = (c = '') => {
  if (!/^\d{4}$/.test(c)) return 'Enter 4 digits.';
  if (WEAK_CODES.has(c)) return 'Too easy to guess. Pick a less obvious code.';
  return '';
};

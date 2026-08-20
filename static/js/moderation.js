/**
 * Nearby Chat — Client-Side Real-Time Content Moderation Guard
 * Instant detection of abusive language, profanities, and slurs before submission.
 */

const BLOCKED_WORDS = [
  // English
  'fuck', 'fucking', 'fucker', 'motherfuck', 'motherfucker', 'bitch', 'bitches',
  'bastard', 'asshole', 'cunt', 'pussy', 'whore', 'slut', 'nigger', 'faggot',
  'twat', 'wanker', 'prick', 'stfu', 'gtfo', 'fck', 'fuk', 'mfer',

  // Hinglish & Hindi Romanized
  'madarchod', 'maderchod', 'madarjaat', 'behenchod', 'bhenchod', 'bhosdike',
  'bhosad', 'bhosada', 'chutiya', 'chutya', 'choot', 'gandu', 'gaand',
  'lauda', 'loda', 'lavda', 'lund', 'randi', 'raand', 'chinal', 'jhant',
  'harami', 'muthal', 'chodu', 'behenkelode', 'tatte',

  // Acronyms
  'bsdk', 'bkl', 'mkc', 'mc', 'bc'
];

const SEPARATED_PATTERNS = [
  /\bb[\s._*-]+c\b/i,
  /\bm[\s._*-]+c\b/i,
  /\bb[\s._*-]+k[\s._*-]+l\b/i,
  /\bm[\s._*-]+k[\s._*-]+c\b/i,
  /\bb[\s._*-]+s[\s._*-]+d[\s._*-]+k\b/i,
  /\bf[\s._*-]+u[\s._*-]+c[\s._*-]+k\b/i,
  /\bs[\s._*-]+t[\s._*-]+f[\s._*-]+u\b/i,
  /\bass\b/i,
  /\bdick\b/i,
  /\bcock\b/i,
  /\btits\b/i
];

window.ContentModerator = {
  normalizeText: function(text) {
    if (!text) return '';
    let norm = text.toLowerCase();
    const map = {
      '@': 'a', '4': 'a',
      '$': 's', '5': 's',
      '1': 'i', '!': 'i', '|': 'i',
      '0': 'o', '3': 'e', '+': 't', '7': 't', '*': 'u'
    };
    for (const [k, v] of Object.entries(map)) {
      norm = norm.replaceAll(k, v);
    }
    // collapse 3+ repeats
    norm = norm.replace(/(.)\1{2,}/g, '$1');
    return norm;
  },

  isAbusive: function(text) {
    if (!text || !text.trim()) return false;
    const raw = text.trim();
    const norm = this.normalizeText(raw);

    // Check exact word boundaries
    for (const word of BLOCKED_WORDS) {
      const regex = new RegExp(`\\b${word}\\b`, 'i');
      if (regex.test(raw) || regex.test(norm)) {
        return true;
      }
    }

    // Check separated abbreviations
    for (const pattern of SEPARATED_PATTERNS) {
      if (pattern.test(raw) || pattern.test(norm)) {
        return true;
      }
    }

    return false;
  }
};

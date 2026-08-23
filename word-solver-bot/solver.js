const DIRECTIONS = [
  { dr: 0, dc: 1, name: 'Right' },
  { dr: 0, dc: -1, name: 'Left' },
  { dr: 1, dc: 0, name: 'Down' },
  { dr: -1, dc: 0, name: 'Up' },
  { dr: 1, dc: 1, name: 'Down-Right' },
  { dr: -1, dc: -1, name: 'Up-Left' },
  { dr: 1, dc: -1, name: 'Down-Left' },
  { dr: -1, dc: 1, name: 'Up-Right' }
];

/**
 * Parse clues from text message or OCR output.
 * Matches multiple format types:
 * 1. Pattern clues with length: B--- (4), 1. B----- (6), 2) C..... (6), S________ (9)
 * 2. Pattern clues without length: B---, C------, S......
 * 3. Full word clues: SILVER, CUSTOMER, 1. SILVER (6)
 */
export function parseClues(text) {
  if (!text) return [];

  let cleanText = text;
  // If CLUES: section is present in OCR output, extract text under CLUES:
  const cluesSectionMatch = text.match(/CLUES:\s*\n([\s\S]*?)(?=\n\s*GRID:|$)/i);
  if (cluesSectionMatch) {
    cleanText = cluesSectionMatch[1].trim();
  }

  const lines = cleanText.split(/\r?\n/);
  const clues = [];
  let index = 1;

  for (const line of lines) {
    const rawLine = line.trim();
    if (!rawLine) continue;

    // Ignore section headers or common title lines
    if (/^(GRID|CLUES|FIND THESE WORDS|HARD MODE|REPLAY|REFRESH|SOLVER)/i.test(rawLine)) continue;

    // Strip leading number or bullet prefixes (e.g., "1. ", "1) ", "- ", "* ", "• ")
    const stripped = rawLine.replace(/^(?:\d+[\.\)]|[-*•])\s*/, '').trim();
    if (!stripped) continue;

    // Format 1: Pattern clue with explicit length in parentheses/brackets e.g. B--- (4) or B... [4]
    const patternWithLenMatch = stripped.match(/^([A-Z])[-_\u2013\u2014.*~]+\s*[\(\[:]\s*(\d+)\s*[\)\]]?/i);
    if (patternWithLenMatch) {
      clues.push({
        id: index++,
        letter: patternWithLenMatch[1].toUpperCase(),
        length: parseInt(patternWithLenMatch[2], 10),
        raw: rawLine
      });
      continue;
    }

    // Format 2: Pattern clue WITHOUT explicit length e.g. B--- or C------ or S......
    const patternNoLenMatch = stripped.match(/^([A-Z])([-_\u2013\u2014.*~]+)$/i);
    if (patternNoLenMatch) {
      const letter = patternNoLenMatch[1].toUpperCase();
      const patternChars = patternNoLenMatch[2];
      const length = 1 + patternChars.length;
      clues.push({
        id: index++,
        letter,
        length,
        raw: rawLine
      });
      continue;
    }

    // Format 3: Pattern with underscores/dots in middle e.g. S_LV_R (6) or S..V.R (6)
    const partialPatternMatch = stripped.match(/^([A-Z][A-Z-_\u2013\u2014.*~]+)\s*[\(\[:]\s*(\d+)\s*[\)\]]?/i);
    if (partialPatternMatch && /[ -_\u2013\u2014.*~]/.test(partialPatternMatch[1])) {
      clues.push({
        id: index++,
        letter: partialPatternMatch[1][0].toUpperCase(),
        length: parseInt(partialPatternMatch[2], 10),
        raw: rawLine
      });
      continue;
    }

    // Format 4: Full word clue with or without explicit length e.g. "SILVER", "SILVER (6)", "CUSTOMER"
    const fullWordMatch = stripped.match(/^([A-Z]{3,})\s*(?:\([\d]+\))?$/i);
    if (fullWordMatch) {
      const word = fullWordMatch[1].toUpperCase();
      clues.push({
        id: index++,
        letter: word[0],
        length: word.length,
        exactWord: word,
        raw: rawLine
      });
      continue;
    }
  }

  return clues;
}

/**
 * Parse a raw text grid extracted from image OCR or user text.
 */
export function parseGrid(text) {
  if (!text) return null;

  // Strip code blocks if present
  let cleanText = text.replace(/```[a-zA-Z]*\n?/g, '').replace(/```/g, '').trim();

  // If GRID: section exists, extract text under GRID:
  const gridSectionMatch = cleanText.match(/GRID:\s*\n([\s\S]*?)(?=\n\s*CLUES:|$)/i);
  if (gridSectionMatch) {
    cleanText = gridSectionMatch[1].trim();
  }

  const lines = cleanText
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(line => line.length > 0);

  if (lines.length === 0) return null;

  const grid = [];
  for (const line of lines) {
    const upperLine = line.toUpperCase();

    // Ignore section headers and common title lines
    if (/^(GRID|CLUES|FIND|CHALLENGE|WORDS|MODE)/i.test(upperLine)) continue;
    // Ignore markdown table headers like |---|---|
    if (/^[|\s\-+]+$/.test(upperLine)) continue;
    // Ignore lines that look like clues (e.g. B--- (4), SILVER, 1. B---)
    if (/([A-Z])[-_\u2013\u2014.*~]{2,}/i.test(upperLine)) continue;
    if (/\(\d+\)/.test(upperLine)) continue;

    if (upperLine.includes('|')) {
      const letters = upperLine.split('|').map(c => c.trim()).filter(c => c.length === 1 && /[A-Z]/.test(c));
      if (letters.length > 0) grid.push(letters);
    } else if (upperLine.includes(' ')) {
      const letters = upperLine.split(/\s+/).filter(c => c.length === 1 && /[A-Z]/.test(c));
      if (letters.length > 0) grid.push(letters);
    } else {
      const lettersOnly = upperLine.replace(/[^A-Z]/g, '');
      if (lettersOnly.length >= 3) grid.push(lettersOnly.split(''));
    }
  }

  if (grid.length < 2) return null;
  const rowLen = grid[0].length;
  if (rowLen < 2) return null;

  const validGrid = grid.filter(row => row.length === rowLen);
  return validGrid.length >= 2 ? validGrid : null;
}

/**
 * Solve puzzle by searching all 8 directions for valid words in dictionary.
 */
export function solvePuzzle(grid, clues, dictionary) {
  const R = grid.length;
  if (R === 0) return [];
  const C = grid[0].length;

  const results = [];

  for (const clue of clues) {
    const rawCandidates = [];
    const targetLetter = clue.letter;
    const len = clue.length;

    for (let r = 0; r < R; r++) {
      for (let c = 0; c < C; c++) {
        if (grid[r][c] === targetLetter) {
          for (const dir of DIRECTIONS) {
            const endR = r + (len - 1) * dir.dr;
            const endC = c + (len - 1) * dir.dc;

            if (endR >= 0 && endR < R && endC >= 0 && endC < C) {
              let word = '';
              for (let i = 0; i < len; i++) {
                word += grid[r + i * dir.dr][c + i * dir.dc];
              }

              if (clue.exactWord) {
                if (word === clue.exactWord) {
                  rawCandidates.push({
                    word,
                    start: { row: r + 1, col: c + 1 }, // 1-indexed for display
                    end: { row: endR + 1, col: endC + 1 },
                    direction: dir.name
                  });
                }
              } else if (dictionary.has(word)) {
                rawCandidates.push({
                  word,
                  start: { row: r + 1, col: c + 1 }, // 1-indexed for display
                  end: { row: endR + 1, col: endC + 1 },
                  direction: dir.name
                });
              }
            }
          }
        }
      }
    }

    // Deduplicate candidates
    const seen = new Set();
    const candidates = [];
    for (const cand of rawCandidates) {
      const key = `${cand.word}-${cand.start.row}-${cand.start.col}-${cand.end.row}-${cand.end.col}`;
      if (!seen.has(key)) {
        seen.add(key);
        candidates.push(cand);
      }
    }

    results.push({
      clue,
      candidates
    });
  }

  return results;
}

/**
 * Select initial candidate indices so duplicate words are not assigned to different clues.
 */
export function assignUniqueCandidates(results) {
  const selectedIndices = new Array(results.length).fill(0);
  const usedWords = new Set();

  for (let i = 0; i < results.length; i++) {
    const candidates = results[i].candidates;
    if (!candidates || candidates.length === 0) continue;

    let chosenIdx = 0;
    for (let k = 0; k < candidates.length; k++) {
      const word = candidates[k].word;
      if (!usedWords.has(word)) {
        chosenIdx = k;
        break;
      }
    }

    selectedIndices[i] = chosenIdx;
    if (candidates[chosenIdx]) {
      usedWords.add(candidates[chosenIdx].word);
    }
  }

  return selectedIndices;
}

/**
 * Advance candidate index for a clue to the next unused word.
 */
export function advanceCandidateIndex(session, clueIdx) {
  const { results, selectedIndices } = session;
  const candidates = results[clueIdx].candidates;
  if (!candidates || candidates.length <= 1) return false;

  const usedWords = new Set();
  selectedIndices.forEach((idx, i) => {
    if (i !== clueIdx && results[i].candidates[idx]) {
      usedWords.add(results[i].candidates[idx].word);
    }
  });

  const current = selectedIndices[clueIdx];
  for (let step = 1; step < candidates.length; step++) {
    const nextIdx = (current + step) % candidates.length;
    const cand = candidates[nextIdx];
    if (!usedWords.has(cand.word)) {
      selectedIndices[clueIdx] = nextIdx;
      return true;
    }
  }

  selectedIndices[clueIdx] = (current + 1) % candidates.length;
  return true;
}

/**
 * Format the solution list for Telegram.
 */
export function formatSolution(session, updatedClueId = null) {
  const { clues, results, selectedIndices } = session;
  let text = '🔥 **HARD MODE CHALLENGE SOLVED** 🔥\n\n';

  results.forEach((res, i) => {
    const clueNum = i + 1;
    const selectedIdx = selectedIndices[i] || 0;
    const cand = res.candidates[selectedIdx];
    const isUpdated = clueNum === updatedClueId;

    const prefix = isUpdated ? '🔄 ' : `${clueNum}. `;

    if (cand) {
      const altCount = res.candidates.length;
      const altInfo = altCount > 1 ? ` _(${selectedIdx + 1}/${altCount} options)_` : '';
      text += `${prefix}**${cand.word}** (${res.clue.raw}) -> Row ${cand.start.row}, Col ${cand.start.col} to Row ${cand.end.row}, Col ${cand.end.col} (${cand.direction})${altInfo}\n`;
    } else {
      text += `${prefix}❌ No match found for \`${res.clue.raw}\`\n`;
    }
  });

  text += '\n💡 *If any word is wrong, reply with the word number (e.g. `5` or `5 wrong`) to switch to another word option!*';
  return text;
}

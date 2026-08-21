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
 * Parse clues from text message.
 * Matches lines like: B--- (4), C----- (6), S-------- (9), etc.
 */
export function parseClues(text) {
  const lines = text.split(/\r?\n/);
  const clues = [];
  let index = 1;

  // Regex matches: Letter, followed by hyphens/dashes/underscores, followed by (Length)
  const clueRegex = /^\s*([A-Z])[-_\u2013\u2014.]+\s*\(([0-9]+)\)/i;

  for (const line of lines) {
    const match = line.trim().match(clueRegex);
    if (match) {
      clues.push({
        id: index++,
        letter: match[1].toUpperCase(),
        length: parseInt(match[2], 10),
        raw: line.trim()
      });
    }
  }

  return clues;
}

/**
 * Parse a raw text grid extracted from image OCR.
 */
export function parseGrid(text) {
  if (!text) return null;

  // Strip code blocks if present
  let cleanText = text.replace(/```[a-zA-Z]*\n?/g, '').replace(/```/g, '').trim();

  const lines = cleanText
    .split(/\r?\n/)
    .map(line => line.trim().toUpperCase())
    .filter(line => line.length > 0);

  if (lines.length === 0) return null;

  const grid = [];
  for (const line of lines) {
    // Ignore markdown table headers like |---|---|
    if (/^[|\s\-+]+$/.test(line)) continue;

    if (line.includes('|')) {
      const letters = line.split('|').map(c => c.trim()).filter(c => c.length === 1 && /[A-Z]/.test(c));
      if (letters.length > 0) grid.push(letters);
    } else if (line.includes(' ')) {
      const letters = line.split(/\s+/).filter(c => c.length === 1 && /[A-Z]/.test(c));
      if (letters.length > 0) grid.push(letters);
    } else {
      const lettersOnly = line.replace(/[^A-Z]/g, '');
      if (lettersOnly.length >= 3) grid.push(lettersOnly.split(''));
    }
  }

  return grid.length > 0 ? grid : null;
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

              if (dictionary.has(word)) {
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

import { loadDictionary } from './dictionary.js';
import { parseGrid, parseClues, solvePuzzle, assignUniqueCandidates, formatSolution } from './solver.js';

const combinedOcrOutput = `
GRID:
U S I L V E R U T N
H X A D R I B G C U
A U X T N Q O E N K
H X A D R I B G C U
A U X T N Q O E N K
M T O E E U V V F S
J G R R E S N A P H
I S C U S T O M E R
S E M I T E M O S X
S A N S W E R I N G

CLUES:
1. B--- (4)
2) C..... (6)
* S________ (9)
- CUSTOMER
SILVER
`;

async function runMultiFormatTest() {
  console.log('🧪 Testing Multi-Format Grid & Clues Parser...');

  const dictionary = await loadDictionary();
  const grid = parseGrid(combinedOcrOutput);
  const clues = parseClues(combinedOcrOutput);

  console.log(`Grid parsed: ${grid ? grid.length + 'x' + grid[0].length : 'FAILED'}`);
  console.log(`Clues parsed: ${clues.length} clues found:`, clues.map(c => c.raw));

  if (!grid || clues.length === 0) {
    throw new Error('Multi-format parsing failed!');
  }

  const results = solvePuzzle(grid, clues, dictionary);
  const selectedIndices = assignUniqueCandidates(results);
  const session = { clues, results, selectedIndices };

  console.log('\n--- Solved Output ---');
  console.log(formatSolution(session));

  console.log('\n✅ MULTI-FORMAT TEST PASSED!');
}

runMultiFormatTest().catch(err => {
  console.error('❌ Multi-format test failed:', err);
  process.exit(1);
});

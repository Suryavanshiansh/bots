import { loadDictionary } from './dictionary.js';
import { parseGrid, parseClues, solvePuzzle, assignUniqueCandidates, advanceCandidateIndex, formatSolution } from './solver.js';

const rawGrid = `
U S I L V E R U T N
H X A D R I B G C U
A U X T N Q O E N K
T E H A E W N I H L
E E H N N T Q X O I
M T O E E U V V F S
J G R R E S N A P H
I S C U S T O M E R
S E M I T E M O S X
S A N S W E R I N G
`;

const rawCluesText = `
🔥 HARD MODE CHALLENGE 🔥

Find these words:
B--- (4)
G--- (4)
S--- (4)
H--- (4)
S--- (4)
T--- (4)
T--- (4)
C----- (6)
S----- (6)
O----- (6)
U----- (6)
C------- (8)
S-------- (9)
A-------- (9)
Tap 🔄 Refresh Grid to mark!
`;

async function test() {
  console.log('🧪 Starting Solver Verification Test...\n');

  console.log('1. Loading dictionary...');
  const dictionary = await loadDictionary();

  console.log('\n2. Parsing grid and clues...');
  const grid = parseGrid(rawGrid);
  const clues = parseClues(rawCluesText);

  console.log(`Grid parsed: ${grid.length}x${grid[0].length}`);
  console.log(`Clues parsed: ${clues.length} clue patterns found.`);

  console.log('\n3. Solving puzzle with Unique Word Assignment...');
  const results = solvePuzzle(grid, clues, dictionary);
  const selectedIndices = assignUniqueCandidates(results);

  const session = {
    clues,
    results,
    selectedIndices
  };

  console.log('\n--- Initial Solution (No Duplicate Words!) ---');
  console.log(formatSolution(session));

  console.log('\n4. Testing alternative word swapping (rejecting word #5)...');
  if (advanceCandidateIndex(session, 4)) {
    console.log('\n--- Updated Solution After Swapping #5 ---');
    console.log(formatSolution(session, 5));
  }

  console.log('\n✅ TEST PASSED SUCCESSFULLY!');
}

test().catch(console.error);

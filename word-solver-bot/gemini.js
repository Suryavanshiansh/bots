import { GoogleGenerativeAI } from '@google/generative-ai';

const CANDIDATE_MODELS = [
  'gemini-2.5-flash',
  'gemini-3.6-flash',
  'gemini-3.5-flash',
  'gemini-2.5-flash-lite',
  'gemini-flash-latest'
];

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

export async function extractGridFromImage(imageBuffer, mimeType = 'image/jpeg', apiKey) {
  if (!apiKey) {
    throw new Error('GEMINI_API_KEY is not configured in .env file.');
  }

  const genAI = new GoogleGenerativeAI(apiKey);

  const prompt = `You are an expert helper for word search puzzles.
Analyze the provided image of a word search puzzle.

The image may contain:
1. A 2D letter grid of the word search puzzle.
2. A list of clues / words to find (e.g., "B--- (4)", "C----- (6)", "S........ (9)", or full words like "SILVER", "CUSTOMER").
3. BOTH the letter grid and the list of clues/words in the same image.

Your task:
- If a letter grid is present, extract all the uppercase letters row by row. Format each row with single space separated uppercase letters.
- If a list of clues/words is present, extract all the clues/words line by line exactly as shown.

Return the result strictly in this format:

GRID:
<Row 1 letters separated by single space>
<Row 2 letters separated by single space>
...

CLUES:
<Clue line 1>
<Clue line 2>
...

Important rules:
- If no grid is present, omit the GRID: section.
- If no clues are present, omit the CLUES: section.
- Do NOT add markdown code blocks (like \`\`\` or \`), headers, page numbers, or extra text outside GRID: and CLUES:.`;

  const imagePart = {
    inlineData: {
      data: imageBuffer.toString('base64'),
      mimeType: mimeType
    }
  };

  let lastError = null;

  for (const modelName of CANDIDATE_MODELS) {
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        console.log(`Trying Gemini model ${modelName} (attempt ${attempt})...`);
        const model = genAI.getGenerativeModel({ model: modelName });
        const result = await model.generateContent([prompt, imagePart]);
        const responseText = result.response.text();

        if (responseText && responseText.trim()) {
          console.log(`Grid extracted successfully using model: ${modelName}`);
          return responseText;
        }
      } catch (err) {
        console.warn(`Model ${modelName} attempt ${attempt} error: ${err.message}`);
        lastError = err;

        // Handle temporary 503 high demand or 429 rate limit errors with exponential retry
        const isTemporaryError = err.message && (
          err.message.includes('503') ||
          err.message.includes('429') ||
          err.message.includes('high demand') ||
          err.message.includes('Unavailable')
        );

        if (isTemporaryError && attempt < 3) {
          console.log(`⏳ Server busy (503/429). Retrying in 1.5 seconds...`);
          await sleep(1500);
          continue;
        }

        // If not a retryable error or max attempts reached, switch to next candidate model
        break;
      }
    }
  }

  throw lastError || new Error('Failed to extract grid using available Gemini models.');
}

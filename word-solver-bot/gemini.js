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
Analyze the provided image of a word search puzzle grid.
Extract all the letters in the grid and format them as a 2D text grid.
Return ONLY the grid of uppercase letters, where:
- Letters in the same row are separated by a single space.
- Each row is on a new line.
- Do NOT add any markdown formatting (like \`\`\` or \`), headers, page numbers, or introductory text. Just the grid itself.

Example output format:
U S I L V E R U T N
H X A D R I B G C U
A U X T N Q O E N K`;

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

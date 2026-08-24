import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
dotenv.config();

// ─── API Key Pool (rotates on rate limit) ────────────────────────────────────
function loadApiKeys() {
  const keys = [];
  // Load GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3, ... up to 20
  if (process.env.GEMINI_API_KEY) keys.push(process.env.GEMINI_API_KEY);
  for (let i = 2; i <= 20; i++) {
    const key = process.env[`GEMINI_API_KEY_${i}`];
    if (key) keys.push(key);
  }
  return keys;
}

const API_KEYS = loadApiKeys();
let currentKeyIndex = 0;

function getNextApiKey() {
  if (API_KEYS.length === 0) return null;
  currentKeyIndex = (currentKeyIndex + 1) % API_KEYS.length;
  return API_KEYS[currentKeyIndex];
}

function getCurrentApiKey(providedKey) {
  // If a key is explicitly passed (e.g. from .env in index.js), use the pool
  return API_KEYS.length > 0 ? API_KEYS[currentKeyIndex] : providedKey;
}

console.log(`🔑 Loaded ${API_KEYS.length} Gemini API key(s).`);

// ─── Model list ──────────────────────────────────────────────────────────────
const CANDIDATE_MODELS = [
  'gemini-3.6-flash',
  'gemini-2.5-flash-lite',
  'gemini-3.5-flash',
  'gemini-flash-latest',
  'gemini-2.0-flash',
  'gemini-1.5-flash'
];

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// ─── Main extraction function ─────────────────────────────────────────────────
export async function extractGridFromImage(imageBuffer, mimeType = 'image/jpeg', apiKey) {
  const effectiveKey = getCurrentApiKey(apiKey);
  if (!effectiveKey) {
    throw new Error('No GEMINI_API_KEY configured in .env file.');
  }

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
  // Track which key we started with so we know when we've tried them all
  const startingKeyIndex = currentKeyIndex;
  let keysTriedCount = 0;

  for (const modelName of CANDIDATE_MODELS) {
    let keyForThisModel = getCurrentApiKey(apiKey);

    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        console.log(`🔑 Key #${currentKeyIndex + 1}/${API_KEYS.length} | Model: ${modelName} | Attempt ${attempt}`);
        const genAI = new GoogleGenerativeAI(keyForThisModel);
        const model = genAI.getGenerativeModel({ model: modelName });
        const result = await model.generateContent([prompt, imagePart]);
        const responseText = result.response.text();

        if (responseText && responseText.trim()) {
          console.log(`✅ Success with key #${currentKeyIndex + 1}, model: ${modelName}`);
          return responseText;
        }
      } catch (err) {
        console.warn(`⚠️ Key #${currentKeyIndex + 1} | ${modelName} attempt ${attempt}: ${err.message}`);
        lastError = err;

        // 404: model deprecated/unavailable — skip to next model immediately
        if (err.message && (
          err.message.includes('404') ||
          err.message.includes('not found') ||
          err.message.includes('no longer available')
        )) {
          console.warn(`❌ Model ${modelName} unavailable. Skipping to next model...`);
          break;
        }

        // 429: rate limit hit — rotate to next API key immediately
        if (err.message && (
          err.message.includes('429') ||
          err.message.includes('quota') ||
          err.message.includes('rate limit') ||
          err.message.includes('RESOURCE_EXHAUSTED')
        )) {
          if (API_KEYS.length > 1 && keysTriedCount < API_KEYS.length - 1) {
            keyForThisModel = getNextApiKey();
            keysTriedCount++;
            console.log(`🔄 Rate limit hit! Rotating to API key #${currentKeyIndex + 1}/${API_KEYS.length}...`);
            await sleep(500); // brief pause before retrying with new key
            continue; // retry same model with new key
          } else {
            // All keys exhausted for this rate limit — wait before moving on
            console.warn(`⏳ All ${API_KEYS.length} key(s) rate limited. Waiting 5 seconds...`);
            await sleep(5000);
            keysTriedCount = 0; // reset key tracking
            break;
          }
        }

        // 503: server busy — wait and retry same key
        if (err.message && (
          err.message.includes('503') ||
          err.message.includes('high demand') ||
          err.message.includes('Unavailable')
        )) {
          if (attempt < 3) {
            console.log(`⏳ Server busy. Retrying in 1 second...`);
            await sleep(1000);
            continue;
          }
          break;
        }

        // Any other error — skip to next model
        break;
      }
    }
  }

  throw lastError || new Error('Failed to extract grid using all available Gemini models and API keys.');
}

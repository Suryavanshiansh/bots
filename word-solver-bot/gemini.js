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
  'gemini-2.0-flash',
  'gemini-2.0-pro-exp-02-05',
  'gemini-1.5-pro',
  'gemini-2.0-flash-lite',
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
  let keysTriedCount = 0;

  // Helper for per-request timeout (18 seconds max per request so 4 attempts fit within Telegram's 90s window)
  const generateContentWithTimeout = (model, contents, timeoutMs = 18000) => {
    return Promise.race([
      model.generateContent(contents),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error(`Request timed out after ${timeoutMs / 1000}s`)), timeoutMs)
      )
    ]);
  };

  for (const modelName of CANDIDATE_MODELS) {
    let keyForThisModel = getCurrentApiKey(apiKey);
    const maxAttempts = modelName === 'gemini-3.6-flash' ? 4 : 2; // Give gemini-3.6-flash extra retry attempts

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        console.log(`🔑 Key #${currentKeyIndex + 1}/${API_KEYS.length} | Model: ${modelName} | Attempt ${attempt}/${maxAttempts}`);
        const genAI = new GoogleGenerativeAI(keyForThisModel);
        const model = genAI.getGenerativeModel({ model: modelName });

        const result = await generateContentWithTimeout(model, [prompt, imagePart], 18000);
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
            await sleep(500);
            continue;
          } else {
            console.warn(`⏳ All ${API_KEYS.length} key(s) rate limited. Waiting 3 seconds...`);
            await sleep(3000);
            keysTriedCount = 0;
            break;
          }
        }

        // 503 / High Demand / Timeout: server busy — try key rotation & exponential delay
        if (err.message && (
          err.message.includes('503') ||
          err.message.includes('high demand') ||
          err.message.includes('Unavailable') ||
          err.message.includes('timed out')
        )) {
          if (API_KEYS.length > 1 && keysTriedCount < API_KEYS.length - 1) {
            keyForThisModel = getNextApiKey();
            keysTriedCount++;
            console.log(`🔄 503 High Demand! Rotating to API key #${currentKeyIndex + 1}/${API_KEYS.length} for ${modelName}...`);
            await sleep(1000);
            continue;
          }

          if (attempt < maxAttempts) {
            const backoffMs = attempt * 1500;
            console.log(`⏳ Server busy/timed out. Retrying ${modelName} in ${backoffMs / 1000}s...`);
            await sleep(backoffMs);
            continue;
          }
          break;
        }

        // 403: Forbidden / API key disabled or denied access
        if (err.message && (
          err.message.includes('403') ||
          err.message.includes('denied access') ||
          err.message.includes('Forbidden') ||
          err.message.includes('API_KEY_INVALID')
        )) {
          console.warn(`❌ Key #${currentKeyIndex + 1} access denied (403 Forbidden). API Key is revoked, disabled, or blocked.`);
          if (API_KEYS.length > 1 && keysTriedCount < API_KEYS.length - 1) {
            keyForThisModel = getNextApiKey();
            keysTriedCount++;
            console.log(`🔄 Rotating to API key #${currentKeyIndex + 1}/${API_KEYS.length}...`);
            await sleep(500);
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

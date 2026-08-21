import { Telegraf } from 'telegraf';
import dotenv from 'dotenv';
import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { loadDictionary } from './dictionary.js';
import { extractGridFromImage } from './gemini.js';
import { parseGrid, parseClues, solvePuzzle, assignUniqueCandidates, advanceCandidateIndex, formatSolution } from './solver.js';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const PORT = process.env.PORT || 3000;
const SESSIONS_FILE = path.join(__dirname, 'sessions_data.json');
const RENDER_EXTERNAL_URL = process.env.RENDER_EXTERNAL_URL;

// Start dummy HTTP health check server for Render Web Service port scanner
http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('Word Solver Bot is running!\n');
}).listen(PORT, () => {
  console.log(`🌐 Health check HTTP server listening on port ${PORT}`);
});

// Self-ping heartbeat to prevent Render free instance from sleeping
if (RENDER_EXTERNAL_URL) {
  console.log(`💓 Keep-alive heartbeat enabled for URL: ${RENDER_EXTERNAL_URL}`);
  setInterval(() => {
    fetch(RENDER_EXTERNAL_URL)
      .then(() => console.log('💓 Keep-alive ping sent successfully.'))
      .catch((err) => console.log('⚠️ Keep-alive ping warning:', err.message));
  }, 10 * 60 * 1000); // 10 minutes
}

if (!BOT_TOKEN) {
  console.warn('⚠️ TELEGRAM_BOT_TOKEN is missing in .env file!');
}

let dictionary = new Set();
const sessions = new Map();

// Load sessions from disk on startup
function loadSessionsFromDisk() {
  try {
    if (fs.existsSync(SESSIONS_FILE)) {
      const data = JSON.parse(fs.readFileSync(SESSIONS_FILE, 'utf-8'));
      for (const [key, val] of Object.entries(data)) {
        sessions.set(Number(key), val);
      }
      console.log(`💾 Loaded ${sessions.size} saved sessions from disk.`);
    }
  } catch (e) {
    console.error('Error loading sessions from disk:', e);
  }
}

// Save sessions to disk
function saveSessionsToDisk() {
  try {
    const obj = {};
    for (const [key, val] of sessions.entries()) {
      obj[key] = val;
    }
    fs.writeFileSync(SESSIONS_FILE, JSON.stringify(obj, null, 2), 'utf-8');
  } catch (e) {
    console.error('Error saving sessions to disk:', e);
  }
}

loadSessionsFromDisk();

function getSession(chatId) {
  if (!sessions.has(chatId)) {
    sessions.set(chatId, {
      grid: null,
      clues: null,
      results: null,
      selectedIndices: []
    });
  }
  return sessions.get(chatId);
}

const bot = new Telegraf(BOT_TOKEN || 'DUMMY_TOKEN');

bot.command(['start', 'help'], (ctx) => {
  ctx.replyWithMarkdown(
    `🔥 **HARD MODE WORD SEARCH SOLVER BOT** 🔥\n\n` +
    `How to use me:\n` +
    `1️⃣ **Send an Image** of the word search grid.\n` +
    `2️⃣ **Send the Clues List** (e.g. \`B--- (4)\`, \`C----- (6)\`, etc.).\n` +
    `*(Or send/forward an image with the clues in the caption!)*\n\n` +
    `3️⃣ I will extract the grid and solve all words!\n` +
    `4️⃣ If a word is wrong, reply with the number (e.g. \`5\` or \`5 wrong\`) to switch to another word option!`
  );
});

bot.command('reset', (ctx) => {
  const chatId = ctx.chat.id;
  sessions.delete(chatId);
  saveSessionsToDisk();
  ctx.reply('🔄 Session reset! Send a new grid image or clue list to start a fresh puzzle.');
});

// Photo Handler
bot.on('photo', async (ctx) => {
  const chatId = ctx.chat.id;
  const session = getSession(chatId);

  try {
    const photos = ctx.message.photo;
    const highestResPhoto = photos[photos.length - 1];

    await ctx.reply('🔍 Extracting grid from image using Gemini Vision...');

    const fileUrl = await ctx.telegram.getFileLink(highestResPhoto.file_id);
    const response = await fetch(fileUrl.href);
    const arrayBuffer = await response.arrayBuffer();
    const imageBuffer = Buffer.from(arrayBuffer);

    const extractedText = await extractGridFromImage(imageBuffer, 'image/jpeg', GEMINI_API_KEY);
    const grid = parseGrid(extractedText);

    if (grid && grid.length > 0) {
      session.grid = grid;
      saveSessionsToDisk();
      await ctx.reply(`✅ Grid extracted successfully (${grid.length}x${grid[0].length})!\n\nNow send or reply with the clues list (e.g. \`B--- (4)\`, \`C----- (6)\`).`);
    } else {
      await ctx.reply('❌ Failed to parse grid from image. Please ensure the image is clear and try again.');
    }

    if (ctx.message.caption) {
      const clues = parseClues(ctx.message.caption);
      if (clues && clues.length > 0) {
        session.clues = clues;
        saveSessionsToDisk();
        runSolverAndReply(ctx, session);
      }
    }
  } catch (err) {
    console.error('Error handling photo:', err);
    ctx.reply(`❌ Error processing image: ${err.message}`);
  }
});

// Text Handler
bot.on('text', async (ctx) => {
  const text = ctx.message.text.trim();
  const chatId = ctx.chat.id;
  const session = getSession(chatId);

  // Check if user is requesting to swap/change a word number (e.g. "1", "1 wrong", "5", etc.)
  const swapMatch = text.match(/^(\d+)(?:\s+(?:wrong|reject|next|swap))?$/i);
  if (swapMatch) {
    const wordNum = parseInt(swapMatch[1], 10);

    if (!session.results || !session.selectedIndices || session.results.length === 0) {
      return ctx.reply('⚠️ No active puzzle solution found for your chat. Please send your clues or image grid to start a puzzle!');
    }

    const itemIndex = wordNum - 1;
    if (itemIndex >= 0 && itemIndex < session.results.length) {
      const advanced = advanceCandidateIndex(session, itemIndex);
      saveSessionsToDisk();

      if (advanced) {
        const solutionText = formatSolution(session, wordNum);
        return ctx.replyWithMarkdown(`🔄 **Updated Word #${wordNum}:**\n\n${solutionText}`);
      } else {
        return ctx.reply(`⚠️ No alternative word options found for Word #${wordNum}.`);
      }
    } else {
      return ctx.reply(`⚠️ Invalid word number #${wordNum}. Please enter a number between 1 and ${session.results.length}.`);
    }
  }

  const clues = parseClues(text);
  if (clues && clues.length > 0) {
    session.clues = clues;
    saveSessionsToDisk();

    if (session.grid) {
      runSolverAndReply(ctx, session);
    } else {
      ctx.reply(`✅ Parsed ${clues.length} clue patterns!\n\nNow send an image of the word search grid to solve!`);
    }
    return;
  }

  const grid = parseGrid(text);
  if (grid && grid.length >= 3 && grid[0].length >= 3) {
    session.grid = grid;
    saveSessionsToDisk();
    await ctx.reply(`✅ Grid parsed manually (${grid.length}x${grid[0].length})!`);

    if (session.clues) {
      runSolverAndReply(ctx, session);
    } else {
      ctx.reply('Now send the clues list (e.g. `B--- (4)`).');
    }
    return;
  }

  ctx.reply('Forward me a word challenge message (with clues like `B--- (4)`) or send an image of the grid!');
});

function runSolverAndReply(ctx, session) {
  if (!dictionary || dictionary.size === 0) {
    return ctx.reply('⏳ Dictionary is still loading, please try again in a few seconds...');
  }

  session.results = solvePuzzle(session.grid, session.clues, dictionary);
  session.selectedIndices = assignUniqueCandidates(session.results);
  saveSessionsToDisk();

  const solutionText = formatSolution(session);
  ctx.replyWithMarkdown(solutionText);
}

async function main() {
  console.log('🚀 Loading dictionary...');
  dictionary = await loadDictionary();

  if (BOT_TOKEN && BOT_TOKEN !== 'DUMMY_TOKEN') {
    bot.launch();
    console.log('🤖 Telegram bot is running!');
  } else {
    console.log('⚠️ BOT_TOKEN missing. Configure TELEGRAM_BOT_TOKEN in .env to start receiving Telegram messages.');
  }
}

main().catch(console.error);

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));

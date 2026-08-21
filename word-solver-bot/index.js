import { Telegraf } from 'telegraf';
import dotenv from 'dotenv';
import http from 'http';
import { loadDictionary } from './dictionary.js';
import { extractGridFromImage } from './gemini.js';
import { parseGrid, parseClues, solvePuzzle, assignUniqueCandidates, advanceCandidateIndex, formatSolution } from './solver.js';

dotenv.config();

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const PORT = process.env.PORT || 3000;

// Start dummy HTTP health check server for Render / Web Service port scanner
http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('Word Solver Bot is running!\n');
}).listen(PORT, () => {
  console.log(`🌐 Health check HTTP server listening on port ${PORT}`);
});

if (!BOT_TOKEN) {
  console.warn('⚠️ TELEGRAM_BOT_TOKEN is missing in .env file!');
}

let dictionary = new Set();
const sessions = new Map();

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
    `4️⃣ If a word is wrong, reply with the number (e.g. \`5\` or \`5 wrong\`) to swap it with another option!`
  );
});

bot.command('reset', (ctx) => {
  const chatId = ctx.chat.id;
  sessions.delete(chatId);
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
      await ctx.reply(`✅ Grid extracted successfully (${grid.length}x${grid[0].length})!\n\nNow send or reply with the clues list (e.g. \`B--- (4)\`, \`C----- (6)\`).`);
    } else {
      await ctx.reply('❌ Failed to parse grid from image. Please ensure the image is clear and try again.');
    }

    if (ctx.message.caption) {
      const clues = parseClues(ctx.message.caption);
      if (clues && clues.length > 0) {
        session.clues = clues;
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

  const swapMatch = text.match(/^(\d+)(?:\s+(?:wrong|reject|next|swap))?$/i);
  if (swapMatch && session.results && session.selectedIndices) {
    const wordNum = parseInt(swapMatch[1], 10);
    const itemIndex = wordNum - 1;

    if (itemIndex >= 0 && itemIndex < session.results.length) {
      const advanced = advanceCandidateIndex(session.results[itemIndex], session.selectedIndices, itemIndex);
      if (advanced) {
        const solutionText = formatSolution(session);
        return ctx.replyWithMarkdown(`🔄 **Updated Word #${wordNum}:**\n\n${solutionText}`);
      } else {
        return ctx.reply(`⚠️ No alternative positions found for Word #${wordNum}.`);
      }
    }
  }

  const clues = parseClues(text);
  if (clues && clues.length > 0) {
    session.clues = clues;

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

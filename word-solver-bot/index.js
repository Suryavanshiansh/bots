import { Telegraf } from 'telegraf';
import dotenv from 'dotenv';
import { loadDictionary } from './dictionary.js';
import { extractGridFromImage } from './gemini.js';
import { parseGrid, parseClues, solvePuzzle, assignUniqueCandidates, advanceCandidateIndex, formatSolution } from './solver.js';

dotenv.config();

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;

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

    const fileLink = await ctx.telegram.getFileLink(highestResPhoto.file_id);
    const response = await fetch(fileLink.href);
    const arrayBuffer = await response.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    const rawGridText = await extractGridFromImage(buffer, 'image/jpeg', GEMINI_API_KEY);
    const grid = parseGrid(rawGridText);

    if (!grid || grid.length === 0) {
      return ctx.reply('❌ Could not parse grid letters from the image. Please make sure the image is clear.');
    }

    // Reset old session state for new photo
    session.grid = grid;
    session.clues = null;
    session.results = null;

    // Check if caption has clues
    const caption = ctx.message.caption || '';
    const clues = parseClues(caption);

    if (clues.length > 0) {
      session.clues = clues;
      return runSolverAndReply(ctx, session);
    }

    ctx.reply(`✅ Grid parsed successfully (${grid.length}x${grid[0].length})!\n\n📋 Now send or forward the list of target words (e.g. \`B--- (4)\`).`);
  } catch (err) {
    console.error('Error processing photo:', err);
    ctx.reply(`❌ Error processing image: ${err.message}`);
  }
});

// Text Handler
bot.on('text', async (ctx) => {
  const chatId = ctx.chat.id;
  const text = ctx.message.text.trim();
  const session = getSession(chatId);

  // Wrong word replacement (e.g. "5", "5 wrong", "5 is wrong")
  const wrongWordMatch = text.match(/^(?:number\s+)?([0-9]+)(?:\s+is)?(?:\s+wrong)?$/i);
  if (wrongWordMatch && session.results && session.results.length > 0) {
    const clueNum = parseInt(wrongWordMatch[1], 10);
    const clueIdx = clueNum - 1;

    if (clueIdx >= 0 && clueIdx < session.results.length) {
      const candidates = session.results[clueIdx].candidates;
      if (candidates.length <= 1) {
        return ctx.reply(`⚠️ No alternative words found in the grid for clue #${clueNum} (${session.clues[clueIdx].raw}).`);
      }

      advanceCandidateIndex(session, clueIdx);
      const solutionMsg = formatSolution(session, clueNum);
      return ctx.replyWithMarkdown(solutionMsg);
    }
  }

  // Parse clues from text
  const clues = parseClues(text);

  if (clues.length > 0) {
    session.clues = clues;

    if (session.grid) {
      return runSolverAndReply(ctx, session);
    } else {
      return ctx.reply(`✅ Received ${clues.length} clue patterns!\n\n🖼️ Now please send or forward the image of the word search grid.`);
    }
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

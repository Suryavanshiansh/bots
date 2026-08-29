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
const TARGETS_FILE = path.join(__dirname, 'targets_data.json');
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

// targetChats: maps userId -> { chatId, chatTitle }
const targetChats = new Map();

// ─── Session persistence ────────────────────────────────────────────────────

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

// ─── Target chat persistence ─────────────────────────────────────────────────

function loadTargetsFromDisk() {
  try {
    if (fs.existsSync(TARGETS_FILE)) {
      const data = JSON.parse(fs.readFileSync(TARGETS_FILE, 'utf-8'));
      for (const [key, val] of Object.entries(data)) {
        targetChats.set(Number(key), val);
      }
      console.log(`🎯 Loaded ${targetChats.size} saved target chats from disk.`);
    }
  } catch (e) {
    console.error('Error loading targets from disk:', e);
  }
}

function saveTargetsToDisk() {
  try {
    const obj = {};
    for (const [key, val] of targetChats.entries()) {
      obj[key] = val;
    }
    fs.writeFileSync(TARGETS_FILE, JSON.stringify(obj, null, 2), 'utf-8');
  } catch (e) {
    console.error('Error saving targets to disk:', e);
  }
}

loadSessionsFromDisk();
loadTargetsFromDisk();

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

// ─── Commands ────────────────────────────────────────────────────────────────

bot.command(['start', 'help'], (ctx) => {
  ctx.replyWithMarkdown(
    `🔥 **HARD MODE WORD SEARCH SOLVER BOT** 🔥\n\n` +
    `How to use me:\n` +
    `1️⃣ **Send an Image** of the word search grid.\n` +
    `2️⃣ **Send the Clues List** (e.g. \`B--- (4)\`, \`C----- (6)\`, etc.).\n` +
    `*(Or send/forward an image with the clues in the caption!)*\n\n` +
    `3️⃣ I will extract the grid and solve all words!\n` +
    `4️⃣ If a word is wrong, reply with the number (e.g. \`5\` or \`5 wrong\`) to switch!\n\n` +
    `**📢 Group Chat Auto-Send:**\n` +
    `Add me to your GC and type \`/settarget\` there.\n` +
    `I'll send words directly to the GC — no "Forwarded from" label!\n\n` +
    `Commands:\n` +
    `• \`/settarget\` — Set current chat as target GC (run in GC)\n` +
    `• \`/cleartarget\` — Remove target GC\n` +
    `• \`/status\` — Show your current target GC\n` +
    `• \`/reset\` — Reset your puzzle session`
  );
});

bot.command('reset', (ctx) => {
  const chatId = ctx.chat.id;
  sessions.delete(chatId);
  saveSessionsToDisk();
  ctx.reply('🔄 Session reset! Send a new grid image or clue list to start a fresh puzzle.');
});

// /settarget — run this in the GROUP CHAT to set it as the target
bot.command('settarget', (ctx) => {
  const chatId = ctx.chat.id;
  const chatType = ctx.chat.type;
  const chatTitle = ctx.chat.title || ctx.chat.username || String(chatId);
  const fromId = ctx.from.id;

  if (chatType === 'private') {
    return ctx.reply(
      '⚠️ Run /settarget inside the **group chat** you want words sent to!\n\n' +
      'Steps:\n1. Add this bot to your GC\n2. Open the GC\n3. Type /settarget there',
      { parse_mode: 'Markdown' }
    );
  }

  // Save: this user's target GC is this chat
  targetChats.set(fromId, { chatId, chatTitle });
  saveTargetsToDisk();

  ctx.reply(`✅ Target GC set!\n\nWords will be sent directly to: **${chatTitle}**\n\nNow go to your DM with me and solve puzzles — I'll send the answers here automatically!`, { parse_mode: 'Markdown' });
});

// /cleartarget — remove target GC
bot.command('cleartarget', (ctx) => {
  const fromId = ctx.from.id;
  if (targetChats.has(fromId)) {
    const target = targetChats.get(fromId);
    targetChats.delete(fromId);
    saveTargetsToDisk();
    ctx.reply(`✅ Target GC removed.\n\nWas: ${target.chatTitle}\n\nWords will no longer be auto-sent to any GC.`);
  } else {
    ctx.reply('ℹ️ You have no target GC set. Use /settarget in a group chat to set one.');
  }
});

// /status — check target
bot.command('status', (ctx) => {
  const fromId = ctx.from.id;
  if (targetChats.has(fromId)) {
    const target = targetChats.get(fromId);
    ctx.reply(`🎯 Your target GC: **${target.chatTitle}** (ID: \`${target.chatId}\`)\n\nWords will be auto-sent there when you solve a puzzle.`, { parse_mode: 'Markdown' });
  } else {
    ctx.reply('ℹ️ No target GC set.\n\nAdd me to your GC and run /settarget there to enable auto-send.');
  }
});

// ─── Media Handlers ──────────────────────────────────────────────────────────

async function processMediaMessage(ctx, fileId, mimeType = 'image/jpeg') {
  const chatId = ctx.chat.id;
  const session = getSession(chatId);

  try {
    await ctx.reply('🔍 Extracting grid & clues from image using Gemini Vision...');

    const fileUrl = await ctx.telegram.getFileLink(fileId);
    const response = await fetch(fileUrl.href);
    const arrayBuffer = await response.arrayBuffer();
    const imageBuffer = Buffer.from(arrayBuffer);

    let extractedText = '';
    try {
      extractedText = await extractGridFromImage(imageBuffer, mimeType, GEMINI_API_KEY);
    } catch (e) {
      console.warn('Gemini OCR extraction warning:', e.message);
    }

    const extractedGrid = parseGrid(extractedText);
    const extractedClues = parseClues(extractedText);

    let updatedGrid = false;
    let updatedClues = false;

    if (extractedGrid && extractedGrid.length >= 2 && extractedGrid[0].length >= 2) {
      session.grid = extractedGrid;
      updatedGrid = true;
    }

    if (extractedClues && extractedClues.length > 0) {
      session.clues = extractedClues;
      updatedClues = true;
    }

    if (ctx.message.caption) {
      const captionClues = parseClues(ctx.message.caption);
      if (captionClues && captionClues.length > 0) {
        session.clues = captionClues;
        updatedClues = true;
      }
      const captionGrid = parseGrid(ctx.message.caption);
      if (captionGrid && captionGrid.length >= 2 && captionGrid[0].length >= 2) {
        session.grid = captionGrid;
        updatedGrid = true;
      }
    }

    saveSessionsToDisk();

    if (updatedGrid && updatedClues) {
      await ctx.reply(`✅ Extracted Grid (${session.grid.length}x${session.grid[0].length}) and ${session.clues.length} clues!`);
      await runSolverAndReply(ctx, session);
    } else if (updatedGrid) {
      await ctx.reply(`✅ Grid extracted successfully (${session.grid.length}x${session.grid[0].length})!`);
      if (session.clues && session.clues.length > 0) {
        await runSolverAndReply(ctx, session);
      } else {
        await ctx.reply('Now send or reply with the clues list (e.g. `B--- (4)`, `C----- (6)`, or full words).');
      }
    } else if (updatedClues) {
      await ctx.reply(`✅ Parsed ${session.clues.length} clues!`);
      if (session.grid && session.grid.length > 0) {
        await runSolverAndReply(ctx, session);
      } else {
        await ctx.reply('Now send an image of the word search grid to solve!');
      }
    } else {
      await ctx.reply('❌ Failed to parse grid or clues from the file. Please ensure the image is clear and try again.');
    }
  } catch (err) {
    console.error('Error handling media:', err);
    ctx.reply(`❌ Error processing image: ${err.message}`);
  }
}

// Photo Handler
bot.on('photo', async (ctx) => {
  const photos = ctx.message.photo;
  const highestResPhoto = photos[photos.length - 1];
  await processMediaMessage(ctx, highestResPhoto.file_id, 'image/jpeg');
});

// Document / File Attachment Handler (Handles forwarded image documents)
bot.on('document', async (ctx) => {
  const doc = ctx.message.document;
  const mime = doc.mime_type || 'image/jpeg';
  await processMediaMessage(ctx, doc.file_id, mime);
});

// ─── Text Handler ─────────────────────────────────────────────────────────────

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
        await ctx.replyWithMarkdown(`🔄 **Updated Word #${wordNum}:**\n\n${solutionText}`);

        const updatedCand = session.results[itemIndex]?.candidates[session.selectedIndices[itemIndex]];
        if (updatedCand) {
          // Send to target GC if set, otherwise DM
          const fromId = ctx.from.id;
          const target = targetChats.get(fromId);
          if (target) {
            try {
              await bot.telegram.sendMessage(target.chatId, updatedCand.word);
              await ctx.reply(`✅ Sent updated word **${updatedCand.word}** directly to **${target.chatTitle}**!`, { parse_mode: 'Markdown' });
            } catch (e) {
              console.error('Failed to send to target GC:', e.message);
              await ctx.reply(`🔄 New word #${wordNum}: ${updatedCand.word}\n\n⚠️ Failed to send to GC: ${e.message}`);
            }
          } else {
            await ctx.reply(`🔄 New word #${wordNum}: ${updatedCand.word}`);
          }
        }
        return;
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
      await runSolverAndReply(ctx, session);
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
      await runSolverAndReply(ctx, session);
    } else {
      ctx.reply('Now send the clues list (e.g. `B--- (4)`).');
    }
    return;
  }

  ctx.reply('Forward me a word challenge message (with clues like `B--- (4)`) or send an image of the grid!');
});

// ─── Solver ───────────────────────────────────────────────────────────────────

async function runSolverAndReply(ctx, session) {
  if (!dictionary || dictionary.size === 0) {
    return ctx.reply('⏳ Dictionary is still loading, please try again in a few seconds...');
  }

  session.results = solvePuzzle(session.grid, session.clues, dictionary);
  session.selectedIndices = assignUniqueCandidates(session.results);
  saveSessionsToDisk();

  // 1. Send full solution summary in DM
  const solutionText = formatSolution(session);
  await ctx.replyWithMarkdown(solutionText);

  // 2. Collect solved words
  const wordMessages = [];
  session.results.forEach((res, i) => {
    const selectedIdx = session.selectedIndices[i] || 0;
    const cand = res.candidates[selectedIdx];
    if (cand) {
      wordMessages.push(cand.word);
    }
  });

  if (wordMessages.length === 0) return;

  // 3. Check if user has a target GC set
  const fromId = ctx.from.id;
  const target = targetChats.get(fromId);

  if (target) {
    // Send words directly to GC (no "Forwarded from" label!)
    try {
      for (const word of wordMessages) {
        await bot.telegram.sendMessage(target.chatId, word);
        await new Promise(r => setTimeout(r, 150));
      }
      await ctx.reply(`✅ All ${wordMessages.length} words sent directly to **${target.chatTitle}**! 🎯`, { parse_mode: 'Markdown' });
    } catch (e) {
      console.error('Failed to send words to target GC:', e.message);
      await ctx.reply(`⚠️ Failed to send to GC (${e.message}).\n\nMake sure I'm still a member of the group!\n\nSending words here instead:`);
      // Fallback: send in DM
      await ctx.reply('📤 *Words (send manually):*', { parse_mode: 'Markdown' });
      for (const word of wordMessages) {
        await ctx.reply(word);
        await new Promise(r => setTimeout(r, 100));
      }
    }
  } else {
    // No GC set — send words one-by-one in DM so user can forward
    await ctx.reply('📤 *Words to forward one by one:*\n_(Tip: Set a target GC with /settarget to skip forwarding!)_', { parse_mode: 'Markdown' });
    for (const word of wordMessages) {
      await ctx.reply(word);
      await new Promise(r => setTimeout(r, 100));
    }
  }
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  console.log('🚀 Loading dictionary...');
  dictionary = await loadDictionary();

  if (BOT_TOKEN && BOT_TOKEN !== 'DUMMY_TOKEN') {
    bot.launch().then(() => {
      console.log('🤖 Telegram bot is running!');
    }).catch(err => {
      if (err.code === 401 || err.response?.error_code === 401) {
        console.error('❌ Telegram 401 Unauthorized: The TELEGRAM_BOT_TOKEN in your .env or Render settings is invalid or revoked. Please get a new token from @BotFather on Telegram!');
      } else {
        console.error('⚠️ Bot launch error:', err.message);
      }
    });
  } else {
    console.log('⚠️ BOT_TOKEN missing. Configure TELEGRAM_BOT_TOKEN in .env to start receiving Telegram messages.');
  }
}

main().catch(console.error);

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));

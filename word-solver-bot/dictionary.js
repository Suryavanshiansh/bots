import fs from 'fs';
import path from 'path';
import https from 'https';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DICTIONARY_URL = 'https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt';
const COMMON_WORDS_URL = 'https://raw.githubusercontent.com/first20hours/google-10000-english/master/20k.txt';

const DICTIONARY_PATH = path.join(__dirname, 'dictionary.txt');
const COMMON_WORDS_PATH = path.join(__dirname, 'common_words.txt');

function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    https.get(url, (response) => {
      if (response.statusCode === 301 || response.statusCode === 302) {
        return downloadFile(response.headers.location, dest).then(resolve).catch(reject);
      }
      response.pipe(file);
      file.on('finish', () => {
        file.close(resolve);
      });
    }).on('error', (err) => {
      fs.unlink(dest, () => {});
      reject(err);
    });
  });
}

// Map of word -> frequency rank (lower rank = more common/meaningful word)
export const wordRankMap = new Map();

export async function loadDictionary() {
  if (!fs.existsSync(DICTIONARY_PATH)) {
    console.log('Downloading English dictionary (approx 4MB)...');
    await downloadFile(DICTIONARY_URL, DICTIONARY_PATH);
    console.log('Dictionary downloaded successfully.');
  }

  if (!fs.existsSync(COMMON_WORDS_PATH)) {
    console.log('Downloading common English frequency word list (approx 20k words)...');
    try {
      await downloadFile(COMMON_WORDS_URL, COMMON_WORDS_PATH);
      console.log('Common words list downloaded successfully.');
    } catch (e) {
      console.warn('Could not download common words list, proceeding with standard dictionary:', e.message);
    }
  }

  // Load common words rank map
  if (fs.existsSync(COMMON_WORDS_PATH)) {
    const commonContent = fs.readFileSync(COMMON_WORDS_PATH, 'utf8');
    const commonList = commonContent
      .split(/\r?\n/)
      .map(w => w.trim().toUpperCase())
      .filter(w => w.length >= 3);

    commonList.forEach((w, index) => {
      if (!wordRankMap.has(w)) {
        wordRankMap.set(w, index + 1); // 1 = most common word
      }
    });
    console.log(`Loaded frequency rank for ${wordRankMap.size} common English words.`);
  }

  const content = fs.readFileSync(DICTIONARY_PATH, 'utf8');
  const wordList = content
    .split(/\r?\n/)
    .map(w => w.trim().toUpperCase())
    .filter(w => w.length >= 3);

  const dictionarySet = new Set(wordList);
  console.log(`Loaded ${dictionarySet.size} total words into dictionary.`);
  return dictionarySet;
}

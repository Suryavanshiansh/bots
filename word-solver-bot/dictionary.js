import fs from 'fs';
import path from 'path';
import https from 'https';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DICTIONARY_URL = 'https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt';
const DICTIONARY_PATH = path.join(__dirname, 'dictionary.txt');

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

export async function loadDictionary() {
  if (!fs.existsSync(DICTIONARY_PATH)) {
    console.log('Downloading English dictionary (approx 4MB)...');
    await downloadFile(DICTIONARY_URL, DICTIONARY_PATH);
    console.log('Dictionary downloaded successfully.');
  }

  const content = fs.readFileSync(DICTIONARY_PATH, 'utf8');
  const wordList = content
    .split(/\r?\n/)
    .map(w => w.trim().toUpperCase())
    .filter(w => w.length >= 3);

  const dictionarySet = new Set(wordList);
  console.log(`Loaded ${dictionarySet.size} words into dictionary.`);
  return dictionarySet;
}

import dotenv from 'dotenv';
import { extractGridFromImage } from './gemini.js';

dotenv.config();

// Create a small 1x1 transparent PNG buffer for API verification
const samplePngBase64 = 'iVBORw0KGgoAAAANSU5EUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';
const imageBuffer = Buffer.from(samplePngBase64, 'base64');

async function testOCR() {
  console.log('Testing image grid extraction with GEMINI_API_KEY...');
  try {
    const result = await extractGridFromImage(imageBuffer, 'image/png', process.env.GEMINI_API_KEY);
    console.log('✅ OCR Success! Output length:', result.length);
  } catch (err) {
    console.error('❌ Error testing OCR:', err);
  }
}

testOCR();

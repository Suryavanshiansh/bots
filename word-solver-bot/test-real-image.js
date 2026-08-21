import dotenv from 'dotenv';
import { extractGridFromImage } from './gemini.js';

dotenv.config();

// A tiny valid 10x10 red/blue sample JPEG image in base64
const sampleJpegBase64 = '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=';
const imageBuffer = Buffer.from(sampleJpegBase64, 'base64');

async function testOCR() {
  console.log('Testing image grid extraction with GEMINI_API_KEY...');
  try {
    const result = await extractGridFromImage(imageBuffer, 'image/jpeg', process.env.GEMINI_API_KEY);
    console.log('✅ OCR Response received:');
    console.log(result);
  } catch (err) {
    console.error('❌ Error testing OCR:', err);
  }
}

testOCR();

import dotenv from 'dotenv';
import { GoogleGenerativeAI } from '@google/generative-ai';

dotenv.config();

const apiKey = process.env.GEMINI_API_KEY;

console.log('Testing GEMINI_API_KEY:', apiKey ? `${apiKey.substring(0, 10)}...` : 'MISSING');

async function testModels() {
  try {
    const url = `https://generativelanguage.googleapis.com/v1beta/models?key=${apiKey}`;
    const res = await fetch(url);
    const data = await res.json();

    if (data.error) {
      console.error('❌ API Key Error:', JSON.stringify(data.error, null, 2));
      return;
    }

    if (data.models) {
      console.log('✅ Available Models for this API Key:');
      const supported = data.models
        .filter(m => m.supportedGenerationMethods && m.supportedGenerationMethods.includes('generateContent'))
        .map(m => m.name.replace('models/', ''));
      console.log(supported);
    } else {
      console.log('Response:', data);
    }
  } catch (err) {
    console.error('Network Error:', err);
  }
}

testModels();

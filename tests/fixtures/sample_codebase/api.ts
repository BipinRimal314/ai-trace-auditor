import Anthropic from '@anthropic-ai/sdk';
import { PineconeClient } from '@pinecone-database/pinecone';
import express from 'express';

const client = new Anthropic();
const app = express();

const MODEL = 'claude-3-haiku-20240307';

app.post('/api/generate', async (req, res) => {
  const response = await client.messages.create({
    model: MODEL,
    max_tokens: 512,
    messages: [{ role: 'user', content: req.body.prompt }],
  });
  res.json({ text: response.content[0].text });
});

app.get('/api/search', async (req, res) => {
  // vector search endpoint
  res.json({ results: [] });
});

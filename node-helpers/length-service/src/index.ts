/**
 * Twitter text length validation service
 * Placeholder implementation - will be expanded in Prompt 04
 */

import express, { Express, Request, Response } from 'express';

const app: Express = express();
const PORT = process.env.PORT || 8080;

app.use(express.json());

app.get('/health', (_req: Request, res: Response) => {
  res.json({ ok: true });
});

// Placeholder - will implement in Prompt 04
app.post('/length/check', (_req: Request, res: Response) => {
  res.json({ 
    isValid: true, 
    weightedLength: 0, 
    permillage: 0, 
    validRange: { start: 0, end: 0 } 
  });
});

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`Length service running on port ${PORT}`);
  });
}

export default app;

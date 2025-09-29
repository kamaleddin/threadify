/**
 * Twitter text length validation service
 * Uses official twitter-text library for accurate length calculations
 */

import express, { Express, Request, Response } from 'express';
import twitter from 'twitter-text';

const app: Express = express();
const PORT = process.env.PORT || 8080;

app.use(express.json());

interface LengthCheckRequest {
  text: string;
}

interface LengthCheckResponse {
  isValid: boolean;
  weightedLength: number;
  permillage: number;
  validRange: {
    start: number;
    end: number;
  };
}

interface BatchLengthCheckRequest {
  texts: string[];
}

interface BatchLengthCheckResponse {
  results: LengthCheckResponse[];
}

app.get('/healthz', (_req: Request, res: Response) => {
  res.json({ ok: true });
});

/**
 * Check the length of a single tweet text
 * POST /length/check
 * Body: { "text": "..." }
 */
app.post('/length/check', (req: Request, res: Response) => {
  try {
    const { text } = req.body as LengthCheckRequest;

    if (typeof text !== 'string') {
      res.status(400).json({ error: 'text must be a string' });
      return;
    }

    const parsed = twitter.parseTweet(text);

    const response: LengthCheckResponse = {
      isValid: parsed.valid,
      weightedLength: parsed.weightedLength,
      permillage: parsed.permillage,
      validRange: {
        start: parsed.validRangeStart,
        end: parsed.validRangeEnd,
      },
    };

    res.json(response);
  } catch (error) {
    console.error('Error checking length:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * Check the length of multiple tweet texts in batch
 * POST /length/batch
 * Body: { "texts": ["...", "..."] }
 */
app.post('/length/batch', (req: Request, res: Response) => {
  try {
    const { texts } = req.body as BatchLengthCheckRequest;

    if (!Array.isArray(texts)) {
      res.status(400).json({ error: 'texts must be an array' });
      return;
    }

    if (texts.some((text) => typeof text !== 'string')) {
      res.status(400).json({ error: 'all texts must be strings' });
      return;
    }

    const results: LengthCheckResponse[] = texts.map((text) => {
      const parsed = twitter.parseTweet(text);
      return {
        isValid: parsed.valid,
        weightedLength: parsed.weightedLength,
        permillage: parsed.permillage,
        validRange: {
          start: parsed.validRangeStart,
          end: parsed.validRangeEnd,
        },
      };
    });

    const response: BatchLengthCheckResponse = {
      results,
    };

    res.json(response);
  } catch (error) {
    console.error('Error checking batch lengths:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`Length service running on port ${PORT}`);
  });
}

export default app;

/**
 * Tests for the Twitter text length validation service
 */

import request from 'supertest';
import app from '../src/index';

describe('Length Service', () => {
  describe('GET /healthz', () => {
    it('should return health check ok', async () => {
      const res = await request(app).get('/healthz');
      expect(res.statusCode).toEqual(200);
      expect(res.body).toEqual({ ok: true });
    });
  });

  describe('POST /length/check', () => {
    it('should validate a simple short tweet', async () => {
      const res = await request(app)
        .post('/length/check')
        .send({ text: 'Hello world' });

      expect(res.statusCode).toEqual(200);
      expect(res.body).toHaveProperty('isValid', true);
      expect(res.body).toHaveProperty('weightedLength');
      expect(res.body).toHaveProperty('permillage');
      expect(res.body).toHaveProperty('validRange');
      expect(res.body.validRange).toHaveProperty('start');
      expect(res.body.validRange).toHaveProperty('end');
    });

    it('should handle empty text', async () => {
      const res = await request(app)
        .post('/length/check')
        .send({ text: '' });

      expect(res.statusCode).toEqual(200);
      expect(res.body.isValid).toBe(false); // Empty tweet is invalid
    });

    it('should validate tweet with exactly 280 characters', async () => {
      const text = 'a'.repeat(280);
      const res = await request(app)
        .post('/length/check')
        .send({ text });

      expect(res.statusCode).toEqual(200);
      expect(res.body.isValid).toBe(true);
      expect(res.body.weightedLength).toBe(280);
    });

    it('should invalidate tweet over 280 characters', async () => {
      const text = 'a'.repeat(281);
      const res = await request(app)
        .post('/length/check')
        .send({ text });

      expect(res.statusCode).toEqual(200);
      expect(res.body.isValid).toBe(false);
      expect(res.body.weightedLength).toBe(281);
    });

    it('should handle URLs with weighted length', async () => {
      const text = 'Check this out: https://example.com/very/long/url/path/that/would/be/much/longer/than/23/chars';
      const res = await request(app)
        .post('/length/check')
        .send({ text });

      expect(res.statusCode).toEqual(200);
      expect(res.body.isValid).toBe(true);
      // URL should be counted as 23 characters
      expect(res.body.weightedLength).toBeLessThan(text.length);
    });

    it('should handle emojis correctly', async () => {
      const text = '🔥🔥🔥';
      const res = await request(app)
        .post('/length/check')
        .send({ text });

      expect(res.statusCode).toEqual(200);
      expect(res.body.isValid).toBe(true);
      // Each emoji should count as 2 characters
      expect(res.body.weightedLength).toBe(6);
    });

    it('should return 400 for missing text', async () => {
      const res = await request(app)
        .post('/length/check')
        .send({});

      expect(res.statusCode).toEqual(400);
      expect(res.body).toHaveProperty('error');
    });

    it('should return 400 for non-string text', async () => {
      const res = await request(app)
        .post('/length/check')
        .send({ text: 123 });

      expect(res.statusCode).toEqual(400);
      expect(res.body).toHaveProperty('error');
    });
  });

  describe('POST /length/batch', () => {
    it('should validate multiple tweets', async () => {
      const res = await request(app)
        .post('/length/batch')
        .send({
          texts: ['First tweet', 'Second tweet', 'Third tweet'],
        });

      expect(res.statusCode).toEqual(200);
      expect(res.body).toHaveProperty('results');
      expect(res.body.results).toHaveLength(3);
      expect(res.body.results[0]).toHaveProperty('isValid', true);
      expect(res.body.results[1]).toHaveProperty('isValid', true);
      expect(res.body.results[2]).toHaveProperty('isValid', true);
    });

    it('should handle mix of valid and invalid tweets', async () => {
      const shortText = 'Valid tweet';
      const longText = 'a'.repeat(300);

      const res = await request(app)
        .post('/length/batch')
        .send({
          texts: [shortText, longText],
        });

      expect(res.statusCode).toEqual(200);
      expect(res.body.results).toHaveLength(2);
      expect(res.body.results[0].isValid).toBe(true);
      expect(res.body.results[1].isValid).toBe(false);
    });

    it('should return 400 for non-array texts', async () => {
      const res = await request(app)
        .post('/length/batch')
        .send({ texts: 'not an array' });

      expect(res.statusCode).toEqual(400);
      expect(res.body).toHaveProperty('error');
    });

    it('should return 400 for array with non-string elements', async () => {
      const res = await request(app)
        .post('/length/batch')
        .send({ texts: ['valid', 123, 'also valid'] });

      expect(res.statusCode).toEqual(400);
      expect(res.body).toHaveProperty('error');
    });

    it('should handle empty array', async () => {
      const res = await request(app)
        .post('/length/batch')
        .send({ texts: [] });

      expect(res.statusCode).toEqual(200);
      expect(res.body.results).toHaveLength(0);
    });
  });
});
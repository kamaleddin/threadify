/**
 * Placeholder tests for length service
 */

import request from 'supertest';
import app from '../src/index';

describe('Length Service', () => {
  it('should return health check ok', async () => {
    const response = await request(app).get('/health');
    expect(response.status).toBe(200);
    expect(response.body).toEqual({ ok: true });
  });

  it('should have length check endpoint', async () => {
    const response = await request(app)
      .post('/length/check')
      .send({ text: 'Hello world' });
    expect(response.status).toBe(200);
    expect(response.body).toHaveProperty('isValid');
    expect(response.body).toHaveProperty('weightedLength');
  });
});

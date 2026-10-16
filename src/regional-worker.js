import { handleRequest } from './app/handle-request.js';

export default {
  /**
   * Run the existing download pipeline in a separately placed Worker.
   * @param {Request} request
   * @param {Record<string, unknown>} env
   * @param {ExecutionContext} ctx
   */
  async fetch(request, env, ctx) {
    const response = await handleRequest(request, env, ctx);
    const headers = new Headers(response.headers);
    headers.set('X-Xget-Region', String(env.WORKER_REGION));
    headers.set(
      'X-Xget-Worker-Placement',
      request.headers.get('cf-placement') || headers.get('cf-placement') || 'unknown'
    );
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers
    });
  }
};

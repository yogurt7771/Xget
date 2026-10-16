import { handleRequest } from './app/handle-request.js';

export default {
  /**
   * Run the existing download pipeline in a separately placed Worker.
   * @param {Request} request
   * @param {Record<string, unknown>} env
   * @param {ExecutionContext} ctx
   */
  async fetch(request, env, ctx) {
    let placement = request.headers.get('cf-placement');
    if (request.headers.get('X-Xget-Measure-Placement') === '1') {
      request = new Request(request);
      request.headers.delete('X-Xget-Measure-Placement');
      // Service bindings do not consistently expose cf-placement. A trace
      // subrequest observes this Worker's outbound Cloudflare data center.
      const trace = await fetch('https://www.cloudflare.com/cdn-cgi/trace', {
        signal: AbortSignal.timeout(5000)
      });
      const colo = (await trace.text()).match(/^colo=([A-Z]{3})$/m)?.[1];
      placement = trace.ok && colo ? `trace-${colo}` : 'unknown';
    }
    const response = await handleRequest(request, env, ctx);
    const headers = new Headers(response.headers);
    headers.set('X-Xget-Region', String(env.WORKER_REGION));
    headers.set('X-Xget-Worker-Placement', placement || headers.get('cf-placement') || 'unknown');
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers
    });
  }
};

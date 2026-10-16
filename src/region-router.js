/** @typedef {{fetch: (request: Request) => Promise<Response>}} WorkerService */

export const REGIONS = ['hk', 'sg', 'jp', 'tw'];

export default {
  /**
   * Route downloads to one of the independently placed regional Workers.
   * @param {Request} request
   * @param {Record<string, unknown>} env
   */
  async fetch(request, env) {
    const url = new URL(request.url);
    const active = String(env.ACTIVE_REGION || 'hk');
    if (url.pathname === '/__xget/status') {
      return Response.json(
        { active_region: active, regions: REGIONS },
        { headers: { 'Cache-Control': 'no-store' } }
      );
    }
    let region = active;
    if (url.pathname.startsWith('/__xget/regions/')) {
      const match = url.pathname.match(/^\/__xget\/regions\/([^/]+)(\/.*)?$/);
      if (!match || !REGIONS.includes(match[1])) {
        return new Response('Unknown Worker region', { status: 404 });
      }
      [, region] = match;
      url.pathname = match[2] || '/';
    }
    if (!REGIONS.includes(region)) {
      return new Response('Invalid active Worker region', { status: 503 });
    }
    const service = /** @type {WorkerService | undefined} */ (env[`XGET_${region.toUpperCase()}`]);
    if (!service) return new Response('Regional Worker unavailable', { status: 503 });
    const forwarded = new Request(url, request);
    forwarded.headers.delete('cf-placement');
    const response = await service.fetch(forwarded);
    const headers = new Headers(response.headers);
    headers.set('X-Xget-Region', region);
    headers.set('X-Xget-Default-Region', active);
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers
    });
  }
};

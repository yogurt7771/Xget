import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { execFileSync } from 'node:child_process';

const regions = JSON.parse(await readFile('scripts/worker-regions.json', 'utf8'));
const token = process.env.CLOUDFLARE_API_TOKEN;
const account = process.env.CLOUDFLARE_ACCOUNT_ID;
if (!token || !account) throw new Error('Cloudflare deployment credentials are required');

// Preserve the selected region on ordinary code deployments.
let active = process.env.ACTIVE_REGION;
if (!active) {
  const response = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${account}/workers/scripts/xget/settings`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  if (!response.ok) throw new Error(`Cannot read existing Worker settings: ${response.status}`);
  const data = await response.json();
  if (!data.success) throw new Error('Cannot read existing Worker settings');
  active = data.result.bindings?.find(binding => binding.name === 'ACTIVE_REGION')?.text || 'hk';
}
if (!(active in regions)) throw new Error('Unknown active region');

const directory = resolve('.wrangler/regional-deploy');
await mkdir(directory, { recursive: true });
const base = {
  compatibility_date: '2024-10-22',
  compatibility_flags: ['nodejs_compat', 'cache_option_enabled'],
  workers_dev: false,
  observability: { enabled: false }
};
async function deploy(name, config) {
  const path = resolve(directory, `${name}.json`);
  await writeFile(path, JSON.stringify({ ...base, name, ...config }, null, 2));
  execFileSync('wrangler', ['deploy', '--config', path], { stdio: 'inherit' });
}

if (process.env.DEPLOY_ALL !== 'false') {
  for (const [region, settings] of Object.entries(regions)) {
    await deploy(`xget-${region}`, {
      main: resolve('src/regional-worker.js'),
      placement: { region: settings.placement },
      vars: { WORKER_REGION: region }
    });
  }
}
await deploy('xget', {
  main: resolve('src/region-router.js'),
  vars: { ACTIVE_REGION: active },
  services: Object.keys(regions).map(region => ({
    binding: `XGET_${region.toUpperCase()}`,
    service: `xget-${region}`
  }))
});
console.log(`Active Worker region: ${active}; regional Workers retained: ${Object.keys(regions)}`);

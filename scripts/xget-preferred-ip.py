"""Dual-stack entry IP and regional Worker selection for xget.qyqq.wang."""

import argparse
import ctypes
import datetime
import hashlib
import ipaddress
import json
import os
import re
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

HOST = 'xget.qyqq.wang'
HOSTS = Path(r'C:\Windows\System32\drivers\etc\hosts')
MODEL = '/hf/SmilingWolf/wd-eva02-large-tagger-v3/resolve/main/model.msgpack?download=true'
OFFSET = 1048576
SIZE = 4194304
POOL = Path(__file__).with_name('xget-ip-candidates.json')
REPORT = None
WORKER_REGIONS = json.loads(Path(__file__).with_name('worker-regions.json').read_text(encoding='utf-8'))
GITHUB_REPO = 'yogurt7771/Xget'


def normalize_ip(value):
    return str(ipaddress.ip_address(value.strip().removeprefix('[').removesuffix(']')))


def family(ip):
    return ipaddress.ip_address(normalize_ip(ip)).version


def exit_baselines(value):
    if isinstance(value, dict):
        return dict(value)
    return {family(value): normalize_ip(value)} if value else {}


def check_exit(trace, expected):
    if isinstance(expected, dict):
        expected = expected.get(family(trace['connected_ip']))
    if expected and normalize_ip(trace['exit_ip']) != normalize_ip(expected):
        raise RuntimeError('Exit IP changed within the same address family')


def render_hosts(before, ip):
    if ip:
        ip = normalize_ip(ip)
    if before.startswith((b'\xff\xfe', b'\xfe\xff')):
        raise ValueError('UTF-16 hosts is not supported; file was not changed')
    bom = b'\xef\xbb\xbf' if before.startswith(b'\xef\xbb\xbf') else b''
    text = before[len(bom):].decode('latin1')
    newline = '\r\n' if '\r\n' in text else '\n'
    kept = []
    for line in text.splitlines(keepends=True):
        content = line.rstrip('\r\n')
        ending = line[len(content):]
        address, sep, comment = content.partition('#')
        fields = address.split()
        if len(fields) > 1 and HOST in [x.lower() for x in fields[1:]]:
            aliases = [x for x in fields[1:] if x.lower() != HOST]
            if aliases:
                kept.append(fields[0] + ' ' + ' '.join(aliases) +
                            ((' ' + sep + comment) if sep else '') + ending)
            elif sep:
                kept.append(sep + comment + ending)
        else:
            kept.append(line)
    result = ''.join(kept)
    if ip:
        if result and not result.endswith(('\r', '\n')):
            result += newline
        result += f'{ip} {HOST}{newline}'
    return bom + result.encode('latin1')


def save_hosts(path, before, after):
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = path.with_name(path.name + '.xget-backup-' + stamp)
    with path.open('r+b') as f:
        if f.read() != before:
            raise RuntimeError('Hosts changed concurrently; nothing written')
        with backup.open('xb') as b:
            b.write(before)
        try:
            f.seek(0)
            f.write(after)
            f.truncate()
            f.flush()
        except Exception:
            f.seek(0)
            f.write(before)
            f.truncate()
            raise
    return backup


def flush_dns():
    subprocess.run(['ipconfig', '/flushdns'], check=True, capture_output=True)


def request(ip=None, download=False, size=SIZE, seconds=30, region=None):
    with tempfile.TemporaryDirectory(prefix='xget-ip-') as directory:
        root = Path(directory)
        body, headers = root / 'body', root / 'headers'
        args = ['curl.exe', '--noproxy', '*', '--http1.1', '--silent', '--show-error',
                '--connect-timeout', '5', '--max-time', str(seconds),
                '--header', 'Accept-Encoding: identity', '--dump-header', str(headers),
                '--output', str(body), '--write-out', '%{json}']
        if ip:
            ip = normalize_ip(ip)
            target = f'[{ip}]' if family(ip) == 6 else ip
            args += [f'--ipv{family(ip)}', '--resolve', f'{HOST}:443:{target}']
        if download:
            args += ['--range', f'{OFFSET}-{OFFSET + size - 1}', '--max-filesize', str(size),
                     '--header', 'X-Xget-Measure-Placement: 1']
        path = MODEL if download else '/cdn-cgi/trace'
        if download and region:
            path = f'/__xget/regions/{region}' + path
        args.append(f'https://{HOST}' + path)
        p = subprocess.run(args, capture_output=True, timeout=seconds + 10)
        if p.returncode:
            raise RuntimeError(p.stderr.decode(errors='replace').strip())
        info = json.loads(p.stdout)
        data = body.read_bytes()
        h = {}
        for line in headers.read_text(errors='replace').splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                h[key.lower()] = value.strip()
        result = {'connected_ip': normalize_ip(info['remote_ip']),
                  'ip_version': family(info['remote_ip']), 'seconds': round(info['time_total'], 3)}
        if download:
            expected = f'bytes {OFFSET}-{OFFSET + size - 1}/'
            if (info['http_code'] != 206 or len(data) != size or
                    not h.get('content-range', '').startswith(expected)):
                raise RuntimeError(f'Download failed: expected complete {size}-byte Range response')
            worker_region = h.get('x-xget-region', 'hk')
            placement = h.get('x-xget-worker-placement', h.get('cf-placement', 'unknown'))
            if region and worker_region != region:
                raise RuntimeError(f'Requested Worker {region}, got {worker_region}')
            if (worker_region not in WORKER_REGIONS or
                    placement.rsplit('-', 1)[-1] not in WORKER_REGIONS[worker_region]['colos']):
                raise RuntimeError(f'Worker placement not confirmed: {worker_region} / {placement}')
            result.update(MiB_s=round(size / 1048576 / info['time_total'], 3),
                          worker_region=worker_region, placement=placement,
                          sha256=hashlib.sha256(data).hexdigest())
        else:
            trace = dict(line.split('=', 1) for line in data.decode().splitlines() if '=' in line)
            if info['http_code'] != 200 or trace.get('loc') != 'CN':
                raise RuntimeError(f"CN exit not confirmed: {trace.get('loc')}")
            result.update(exit_ip=normalize_ip(trace['ip']), country=trace['loc'], colo=trace['colo'])
        if ip and result['connected_ip'] != ip:
            raise RuntimeError('Connection did not use selected IP')
        return result


def probe(ip=None, exit_ip=None, region=None):
    trace = request(ip)
    check_exit(trace, exit_ip)
    download = request(ip, download=True, **({'region': region} if region else {}))
    if normalize_ip(download['connected_ip']) != normalize_ip(trace['connected_ip']):
        raise RuntimeError('Trace and download connected to different addresses')
    return {**trace, **download}


def emit(value):
    line = json.dumps(value, ensure_ascii=False)
    print(line, flush=True)
    if REPORT:
        with REPORT.open('a', encoding='utf-8') as report:
            report.write(line + '\n')


def current_exit():
    try:
        baseline = request()
        emit({'baseline': baseline})
        return baseline['exit_ip']
    except Exception as e:
        emit({'warning': 'Current address unavailable or CN exit unconfirmed; '
                         'candidate must independently confirm CN. Old exit cannot be compared.',
              'detail': str(e)})
        return None


def rank_runs(results, rounds):
    ranking = []
    for ip, runs in results.items():
        consistent = bool(runs) and len({r['sha256'] for r in runs}) == 1
        ranking.append({'ip': ip, 'successes': len(runs), 'rounds': rounds,
                        'consistent': consistent, 'eligible': len(runs) == rounds and consistent,
                        'median_MiB_s': statistics.median(r['MiB_s'] for r in runs) if runs else 0,
                        'minimum_MiB_s': min((r['MiB_s'] for r in runs), default=0),
                        'sha256': runs[0]['sha256'] if consistent else None,
                        'exit_ip': runs[0]['exit_ip'] if runs else None})
    # Stable sort retains the current IP on exact ties (it is inserted first).
    return sorted(ranking, key=lambda r: (r['eligible'], r['minimum_MiB_s'],
                                         r['median_MiB_s']), reverse=True)


def benchmark(ips, rounds=3, exit_ip=None):
    exits = exit_baselines(exit_ip)
    results = {normalize_ip(ip): [] for ip in ips}
    for round_number in range(rounds):
        for ip, runs in results.items():
            try:
                result = probe(ip, exits)
                exits[family(ip)] = result['exit_ip']
                runs.append(result)
                emit({'ip': ip, 'round': round_number + 1, **result})
            except Exception as e:
                emit({'ip': ip, 'round': round_number + 1, 'error': str(e)})
    ranking = rank_runs(results, rounds)
    emit({'ranking': ranking})
    if not any(r['eligible'] for r in ranking):
        raise RuntimeError('No candidate passed every round consistently; hosts unchanged')
    return ranking


def switch_ip(ip, expected_exit=None, expected_hash=None):
    if ip:
        ip = normalize_ip(ip)
    before = HOSTS.read_bytes()
    after = render_hosts(before, ip)
    if before != after and not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError('Run this command in an Administrator terminal to change Windows hosts')
    candidate = probe(ip, expected_exit or exit_baselines(current_exit())) if ip else None
    if candidate:
        if expected_hash and candidate['sha256'] != expected_hash:
            raise RuntimeError('Download checksum changed since benchmark; hosts unchanged')
        emit({'preflight': candidate})
    backup = None
    if before != after:
        backup = save_hosts(HOSTS, before, after)
        emit({'backup': str(backup)})
    try:
        if backup:
            flush_dns()
        if ip:
            verified = probe(exit_ip=candidate['exit_ip'])
            if verified['connected_ip'] != ip:
                raise RuntimeError('System resolver did not select the requested IP')
            if verified['sha256'] != candidate['sha256']:
                raise RuntimeError('Download checksum changed after switching IP')
            emit({'verified': verified})
        else:
            emit({'cleared': HOST})
    except BaseException:
        if backup:
            save_hosts(HOSTS, after, before)
            flush_dns()
            emit({'rolled_back': True})
        raise


def elevated_action(action_arguments):
    # Elevate only a hosts operation, not the menu or benchmark.
    with tempfile.TemporaryDirectory(prefix='xget-switch-') as directory:
        report = Path(directory) / 'result.jsonl'
        report.write_text('', encoding='utf-8')
        arguments = subprocess.list2cmdline([str(Path(__file__).resolve()), *action_arguments,
                                             '--report', str(report)])
        quote = lambda s: "'" + s.replace("'", "''") + "'"
        command = (f"$p = Start-Process -FilePath {quote(sys.executable)} "
                   f"-ArgumentList {quote(arguments)} -Verb RunAs -WindowStyle Hidden -Wait -PassThru; "
                   "if ($null -eq $p) { exit 1 }; exit $p.ExitCode")
        emit({'elevation': 'Allow Windows UAC to update hosts'})
        p = subprocess.Popen(['powershell.exe', '-NoProfile', '-Command', command],
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        offset = 0
        while p.poll() is None:
            lines = report.read_text(encoding='utf-8').splitlines()
            for line in lines[offset:]:
                print(line, flush=True)
            offset = len(lines)
            time.sleep(0.5)
        lines = report.read_text(encoding='utf-8').splitlines()
        for line in lines[offset:]:
            print(line, flush=True)
        completed = 'verified' if action_arguments[0] == 'set' else 'cleared'
        if p.returncode or not any(completed in json.loads(line) for line in lines):
            raise RuntimeError('Elevated switch did not succeed; inspect the reported error or UAC cancellation')


def elevated_switch(winner):
    elevated_action(['set', winner['ip'], '--expected-exit', winner['exit_ip'],
                     '--expected-hash', winner['sha256']])


def fetch_source(url):
    result = subprocess.run(
        ['curl.exe', '--fail', '--location', '--silent', '--show-error',
         '--connect-timeout', '5', '--max-time', '15', url],
        capture_output=True, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace').strip())
    return result.stdout.decode('utf-8-sig')


def parse_candidates(text, region=None, version=None):
    if re.search(r'<!doctype\s+html|<html\b', text, re.IGNORECASE):
        raise ValueError('Source returned HTML instead of an IP list')
    ips = []
    for line in text.splitlines():
        endpoint, _, label = line.strip().partition('#')
        if region and not re.search(r'(?<![A-Za-z])' + re.escape(region) + r'(?![A-Za-z])',
                                     label, re.IGNORECASE):
            continue
        try:
            endpoint = endpoint.strip()
            if endpoint.startswith('['):
                match = re.fullmatch(r'\[([^\]]+)\](?::(\d+))?', endpoint)
                if not match or match[2] not in (None, '443'):
                    continue
                ip = normalize_ip(match[1])
            elif '.' in endpoint and endpoint.count(':') == 1:
                address, port = endpoint.rsplit(':', 1)
                if port != '443':
                    continue
                ip = normalize_ip(address)
            else:
                ip = normalize_ip(endpoint)
        except ValueError:
            continue
        if version and family(ip) != version:
            continue
        if ip not in ips:
            ips.append(ip)
    if not ips:
        raise ValueError(f'No usable IP:443 entries for {region or "unlabelled pool"}')
    return ips


def save_pool(pool, before):
    after = (json.dumps(pool, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with POOL.open('r+b') as f:
        if f.read() != before:
            raise RuntimeError('Candidate file changed concurrently; local file not overwritten')
        with tempfile.NamedTemporaryFile(prefix='xget-candidates-backup-', suffix='.json',
                                         delete=False) as backup:
            backup.write(before)
        try:
            f.seek(0)
            f.write(after)
            f.truncate()
            f.flush()
        except BaseException:
            f.seek(0)
            f.write(before)
            f.truncate()
            f.flush()
            raise
    return Path(backup.name)


def refresh_pool():
    before = POOL.read_bytes()
    pool = json.loads(before.decode('utf-8-sig'))
    fetched = {}
    changed = False
    checked_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    for region, group in pool['regions'].items():
        url = group.get('refresh_url')
        if not url:
            emit({'stage': 'refresh', 'region': region, 'status': 'local',
                  'reason': 'No refresh source configured', 'count': len(group['ips'])})
            continue
        try:
            if url not in fetched:
                try:
                    fetched[url] = fetch_source(url)
                except Exception as e:
                    fetched[url] = e
            if isinstance(fetched[url], Exception):
                raise fetched[url]
            ips = parse_candidates(fetched[url], group.get('region_filter', region),
                                   group.get('version'))
        except Exception as e:
            emit({'stage': 'refresh', 'region': region, 'status': 'fallback',
                  'reason': str(e), 'count': len(group['ips'])})
            continue
        group.update(ips=ips, source=url, last_refresh_utc=checked_at)
        changed = True
        emit({'stage': 'refresh', 'region': region, 'status': 'updated',
              'count': len(ips), 'url': url})
    if changed:
        pool['updated'] = checked_at
        try:
            backup = save_pool(pool, before)
            emit({'stage': 'refresh', 'saved': str(POOL), 'backup': str(backup)})
        except Exception as e:
            emit({'stage': 'refresh', 'warning': 'Could not save refreshed candidates; '
                  'using them for this run only. Previous local list retained.', 'reason': str(e)})
    return pool


def worker_status():
    data = json.loads(fetch_source(f'https://{HOST}/__xget/status'))
    if data.get('active_region') not in WORKER_REGIONS:
        raise RuntimeError('Four-region Worker deployment is not available')
    return data


def gh(*arguments):
    child_env = os.environ.copy()
    # Python isolates XDG_CONFIG_HOME; gh uses the existing Windows login.
    # The launcher preserves any explicitly configured gh/XDG directory.
    if not child_env.get('GH_CONFIG_DIR'):
        child_env.pop('XDG_CONFIG_HOME', None)
    result = subprocess.run(['gh', *arguments], capture_output=True, timeout=45, env=child_env)
    if result.returncode:
        raise RuntimeError('GitHub deployment failed: ' + result.stderr.decode(errors='replace').strip())
    return result.stdout.decode('utf-8')


def deploy_region(region):
    request_id = uuid.uuid4().hex
    gh('workflow', 'run', 'workers.yml', '--repo', GITHUB_REPO, '--ref', 'main',
       '-f', f'active_region={region}', '-f', 'deploy_all=false', '-f', f'request_id={request_id}')
    emit({'worker_deploy': region, 'status': 'queued'})
    deadline = time.monotonic() + 600
    run_id = None
    previous_status = None
    while time.monotonic() < deadline:
        if run_id is None:
            runs = json.loads(gh('run', 'list', '--repo', GITHUB_REPO, '--workflow', 'workers.yml',
                                 '--limit', '30', '--json', 'databaseId,displayTitle'))
            run_id = next((r['databaseId'] for r in runs if request_id in r['displayTitle']), None)
        if run_id:
            run = json.loads(gh('run', 'view', str(run_id), '--repo', GITHUB_REPO,
                                '--json', 'status,conclusion,url'))
            if run['status'] != previous_status:
                emit({'worker_deploy': region, **run})
                previous_status = run['status']
            if run['status'] == 'completed':
                if run['conclusion'] != 'success':
                    raise RuntimeError('Worker selection deployment failed: ' + run['url'])
                return
        time.sleep(3)
    if run_id:
        gh('run', 'cancel', str(run_id), '--repo', GITHUB_REPO)
    raise RuntimeError('Worker selection deployment timed out; check GitHub Actions before retrying')


def verify_worker(region, ip, expected_exit, expected_hash):
    for attempt in range(6):
        verified = probe(exit_ip=expected_exit)
        if (verified['sha256'] != expected_hash or
                normalize_ip(verified['connected_ip']) != normalize_ip(ip)):
            raise RuntimeError('Default Worker content or connection verification failed')
        if verified['worker_region'] == region:
            return verified
        if attempt < 5:
            emit({'worker_wait': region, 'observed_region': verified['worker_region']})
            time.sleep(5)
    raise RuntimeError('Default Worker region did not converge after deployment')


def select_worker(ip, expected_exit, expected_hash, dry_run=False):
    previous = worker_status()['active_region']
    regions = [previous] + [region for region in WORKER_REGIONS if region != previous]
    results = {region: [] for region in regions}
    for round_number in range(3):
        for region in regions:
            try:
                result = probe(ip, expected_exit, region=region)
                if result['sha256'] != expected_hash:
                    raise RuntimeError('Model content differs between regional Workers')
                results[region].append(result)
                emit({'worker_round': round_number + 1, 'region': region, **result})
            except Exception as e:
                emit({'worker_round': round_number + 1, 'region': region, 'error': str(e)})
    ranking = rank_runs(results, 3)
    emit({'worker_ranking': ranking})
    winner = next((r for r in ranking if r['eligible']), None)
    if not winner:
        raise RuntimeError('No regional Worker passed all rounds; default Worker unchanged')
    chosen = winner['ip']
    emit({'worker_selected': chosen, 'dry_run': dry_run})
    if dry_run:
        return chosen
    if worker_status()['active_region'] != previous:
        raise RuntimeError('Default Worker changed concurrently; selection not applied')
    try:
        if chosen != previous:
            deploy_region(chosen)
        verified = verify_worker(chosen, ip, expected_exit, expected_hash)
        emit({'verified': verified})
    except Exception:
        if chosen != previous:
            deploy_region(previous)
            verify_worker(previous, ip, expected_exit, expected_hash)
            emit({'worker_restored': previous})
        raise
    return chosen


def auto_select(dry_run=False):
    pool = refresh_pool()
    resolved = list(dict.fromkeys(normalize_ip(r[4][0])
                                 for r in socket.getaddrinfo(HOST, 443, socket.AF_UNSPEC)))
    candidates = {ip: 'current' for ip in resolved}
    for region, group in pool['regions'].items():
        for ip in group['ips']:
            candidates.setdefault(normalize_ip(ip), region)
    for ip in pool.get('fallback_ips', []):
        candidates.setdefault(normalize_ip(ip), 'previously-tested')
    exits = exit_baselines(current_exit())
    emit({'candidate_count': len(candidates), 'regions': pool['regions'],
          'note': 'Region labels describe candidate sources; actual colo is measured'})
    screened = {}
    for ip, region in candidates.items():
        try:
            trace = request(ip, seconds=12)
            check_exit(trace, exits)
            result = request(ip, download=True, size=1048576, seconds=12)
            exits[family(ip)] = trace['exit_ip']
            screened[ip] = result
            emit({'stage': 'screen', 'ip': ip, 'source_region': region, **trace, **result})
        except Exception as e:
            emit({'stage': 'screen', 'ip': ip, 'source_region': region, 'error': str(e)})
    if not screened:
        raise RuntimeError('No candidate passed screening; hosts unchanged')
    fastest = sorted(screened, key=lambda ip: screened[ip]['MiB_s'], reverse=True)[:4]
    shortlist = list(dict.fromkeys([ip for ip in resolved if ip in screened] + fastest))
    emit({'shortlist': shortlist, 'rounds': 3, 'bytes_per_round': SIZE})
    ranking = benchmark(shortlist, rounds=3, exit_ip=exits)
    winner = next(r for r in ranking if r['eligible'])
    emit({'selected': winner, 'dry_run': dry_run})
    if not dry_run:
        if (render_hosts(HOSTS.read_bytes(), winner['ip']) == HOSTS.read_bytes() or
                ctypes.windll.shell32.IsUserAnAdmin()):
            switch_ip(winner['ip'], winner['exit_ip'], winner['sha256'])
        else:
            elevated_switch(winner)
    select_worker(winner['ip'], winner['exit_ip'], winner['sha256'], dry_run=dry_run)
    return winner


def main():
    global REPORT
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    auto = sub.add_parser('auto', help='Benchmark the four-region pool and switch to the best stable IP')
    auto.add_argument('--dry-run', action='store_true', help='Benchmark only; do not modify hosts')
    test = sub.add_parser('test', help='Compare IPs without modifying hosts; 4 MiB per round')
    test.add_argument('ips', nargs='+', type=normalize_ip)
    test.add_argument('--rounds', type=int, choices=range(1, 6), default=3)
    change = sub.add_parser('set', help='Preflight, back up, switch, verify; administrator required')
    change.add_argument('ip', type=normalize_ip)
    change.add_argument('--expected-exit', help=argparse.SUPPRESS)
    change.add_argument('--expected-hash', help=argparse.SUPPRESS)
    change.add_argument('--report', type=Path, help=argparse.SUPPRESS)
    change.add_argument('--elevate', action='store_true', help=argparse.SUPPRESS)
    clear = sub.add_parser('clear', help='Remove only this hostname from hosts; administrator required')
    clear.add_argument('--elevate', action='store_true', help=argparse.SUPPRESS)
    clear.add_argument('--report', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    REPORT = getattr(args, 'report', None)
    if args.command == 'auto':
        auto_select(args.dry_run)
        return
    if args.command == 'status':
        emit({'resolved': sorted({r[4][0] for r in socket.getaddrinfo(HOST, 443)}),
              'network': probe()})
        return
    if args.command == 'test':
        benchmark(args.ips, args.rounds, current_exit())
        return
    if getattr(args, 'elevate', False):
        before = HOSTS.read_bytes()
        after = render_hosts(before, args.ip if args.command == 'set' else None)
        if before != after and not ctypes.windll.shell32.IsUserAnAdmin():
            arguments = ['set', args.ip] if args.command == 'set' else ['clear']
            for option, value in [('--expected-exit', getattr(args, 'expected_exit', None)),
                                  ('--expected-hash', getattr(args, 'expected_hash', None))]:
                if value:
                    arguments.extend([option, value])
            elevated_action(arguments)
            return
    switch_ip(args.ip if args.command == 'set' else None,
              getattr(args, 'expected_exit', None), getattr(args, 'expected_hash', None))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        emit({'error': str(error)})
        raise SystemExit(1)

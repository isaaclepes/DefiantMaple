#!/usr/bin/env python3
"""Read-only candidate inventory; never a closure attestation or pin manifest."""
import hashlib
import json
import os
import pathlib
import re
import resource
import shutil
import stat
import subprocess
import sys
import tempfile

MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_OUTPUT = 256 * 1024
MAX_COMMAND_OUTPUT = 8192
COMMAND_TIMEOUT = 5
DPKG_QUERY = '/usr/bin/dpkg-query'
LOADER = '/lib64/ld-linux-x86-64.so.2'
PACKAGE = re.compile(r'[a-z0-9][a-z0-9+.-]*(?::[a-z0-9][a-z0-9-]*)?')
TOOLS = ('python3', 'docker', 'dockerd', 'containerd', 'containerd-shim-runc-v2',
         'runc', 'qemu-system-x86_64', 'qemu-img', 'readelf', 'systemctl', 'gpgv')
PATH_PROBES = {
    'ubuntu_archive_keyring': '/usr/share/keyrings/ubuntu-archive-keyring.gpg',
    'dynamic_loader': LOADER,
}
TEXT = ('/etc/os-release', '/proc/sys/kernel/osrelease', '/proc/version',
        '/proc/self/cgroup', '/sys/fs/cgroup/cgroup.controllers',
        '/sys/fs/cgroup/cgroup.subtree_control', '/proc/meminfo')


def read_small(path, cap=8192):
    try:
        with open(path, 'rb') as handle:
            data = handle.read(cap + 1)
        return {'text': data[:cap].decode('utf-8', 'replace'), 'truncated': len(data) > cap}
    except OSError as exc:
        return {'error': type(exc).__name__}


def kind(mode):
    if stat.S_ISREG(mode):
        return 'regular'
    if stat.S_ISDIR(mode):
        return 'directory'
    if stat.S_ISLNK(mode):
        return 'symlink'
    if stat.S_ISSOCK(mode):
        return 'socket'
    if stat.S_ISFIFO(mode):
        return 'fifo'
    if stat.S_ISCHR(mode):
        return 'character'
    if stat.S_ISBLK(mode):
        return 'block'
    return 'unknown'


def stat_record(info):
    return {'type': kind(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid,
            'mode': oct(stat.S_IMODE(info.st_mode)), 'size': info.st_size,
            'nlink': info.st_nlink, 'device': info.st_dev, 'inode': info.st_ino}


def path_stat(path, follow):
    try:
        info = os.stat(path, follow_symlinks=follow)
        return stat_record(info)
    except OSError as exc:
        return {'error': type(exc).__name__}


def parent_records(path):
    records = []
    parent = pathlib.Path(path).parent
    for _ in range(8):
        records.append({'path': str(parent), **path_stat(parent, False)})
        if parent == parent.parent:
            break
        parent = parent.parent
    return records


def identify(path, budget):
    """Hash a held regular descriptor, bound reads, reject observed mutation."""
    try:
        resolved = str(pathlib.Path(path).resolve(strict=True))
        descriptor = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as handle:
            before = os.fstat(handle.fileno())
            result = {'resolved': resolved, **stat_record(before)}
            if not stat.S_ISREG(before.st_mode):
                return dict(result, error='not regular')
            if before.st_size > MAX_FILE or before.st_size > budget[0]:
                return dict(result, error='hash budget exceeded')
            digest = hashlib.sha256()
            count = 0
            while count <= before.st_size:
                data = handle.read(min(65536, before.st_size + 1 - count))
                if not data:
                    break
                count += len(data)
                digest.update(data)
            budget[0] -= count
            after = os.fstat(handle.fileno())
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                                      after.st_mtime_ns, after.st_ctime_ns) or count != before.st_size:
                return dict(result, error='changed during read')
            return dict(result, sha256=digest.hexdigest())
    except (OSError, RuntimeError) as exc:
        return {'error': type(exc).__name__}


def probe_path(path, budget):
    requested = pathlib.Path(path)
    result = {'requested': str(requested), 'lstat': path_stat(requested, False),
              'stat': path_stat(requested, True), 'parents': parent_records(requested)}
    if result['lstat'].get('type') == 'symlink':
        try:
            target = os.readlink(requested)
            result['symlink_target'] = target[:4096]
            result['symlink_target_truncated'] = len(target) > 4096
        except OSError as exc:
            result['symlink_target_error'] = type(exc).__name__
    if result['stat'].get('type') == 'regular':
        result['canonical_bytes'] = identify(requested, budget)
        resolved = result['canonical_bytes'].get('resolved')
        if isinstance(resolved, str):
            result['canonical'] = {
                'path': resolved,
                'lstat': path_stat(resolved, False),
                'stat': path_stat(resolved, True),
                'bytes': result['canonical_bytes'],
            }
        else:
            result['canonical'] = {'error': 'strict canonical path unavailable'}
    else:
        result['canonical_bytes'] = {'error': 'not regular or unavailable'}
        result['canonical'] = {'error': 'not regular or unavailable'}
    return result


def bounded_command(argv):
    """Run one fixed read-only dpkg query with bounded files, time and retained bytes."""
    environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                   'LANGUAGE': 'C.UTF-8', 'HOME': '/nonexistent'}

    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_COMMAND_OUTPUT, MAX_COMMAND_OUTPUT))

    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL, stdout=stdout_file, stderr=stderr_file,
                cwd='/', env=environment, close_fds=True, preexec_fn=limits,
            )
        except OSError as exc:
            return {'argv': argv, 'returncode': None, 'timed_out': False,
                    'exec_error': type(exc).__name__, 'stdout_bytes': 0,
                    'stdout_sha256': hashlib.sha256(b'').hexdigest(), 'stdout_text': '',
                    'stdout_truncated': False, 'stderr_bytes': 0,
                    'stderr_sha256': hashlib.sha256(b'').hexdigest(), 'stderr_text': '',
                    'stderr_truncated': False}
        timed_out = False
        try:
            process.wait(timeout=COMMAND_TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read(MAX_COMMAND_OUTPUT + 1)
        stderr = stderr_file.read(MAX_COMMAND_OUTPUT + 1)
    return {
        'argv': argv, 'returncode': process.returncode, 'timed_out': timed_out,
        'exec_error': None,
        'stdout_bytes': len(stdout), 'stdout_sha256': hashlib.sha256(stdout).hexdigest(),
        'stdout_text': stdout[:MAX_COMMAND_OUTPUT].decode('utf-8', 'replace'),
        'stdout_truncated': len(stdout) >= MAX_COMMAND_OUTPUT,
        'stderr_bytes': len(stderr), 'stderr_sha256': hashlib.sha256(stderr).hexdigest(),
        'stderr_text': stderr[:MAX_COMMAND_OUTPUT].decode('utf-8', 'replace'),
        'stderr_truncated': len(stderr) >= MAX_COMMAND_OUTPUT,
    }


def exact_owner(raw, queried_path):
    """Return one normal exact-path owner only when the entire output is unambiguous."""
    lines = [line for line in raw.splitlines() if line]
    if len(lines) != 1:
        return None
    prefix, separator, observed_path = lines[0].rpartition(': ')
    if not separator or observed_path != queried_path:
        return None
    owners = [value.strip() for value in prefix.split(',')]
    if len(owners) != 1 or not PACKAGE.fullmatch(owners[0]):
        return None
    return owners[0]


def loader_package_observation(loader_probe):
    resolved = loader_probe.get('canonical_bytes', {}).get('resolved')
    paths = [('requested', LOADER), ('resolved', resolved)]
    observations = []
    for role, path in paths:
        if not isinstance(path, str) or not path.startswith('/') or '\n' in path or '\r' in path:
            observations.append({'role': role, 'path': path, 'query_error': 'canonical path unavailable'})
            continue
        query = bounded_command([DPKG_QUERY, '-S', path])
        owner = None
        if (query['returncode'] == 0 and not query['timed_out'] and query['exec_error'] is None
                and not query['stdout_truncated'] and not query['stderr_truncated']
                and query['stderr_bytes'] == 0):
            owner = exact_owner(query['stdout_text'], path)
        record = {'role': role, 'path': path, 'ownership_query': query,
                  'unambiguous_direct_owner': owner}
        if owner is not None:
            record['version_query'] = bounded_command(
                [DPKG_QUERY, '-W', '-f=${binary:Package}\t${Version}\t${Architecture}\n', owner]
            )
        observations.append(record)
    return observations


def collect():
    budget = [MAX_TOTAL]
    probes = {name: probe_path(path, budget) for name, path in PATH_PROBES.items()}
    dpkg_query = identify(DPKG_QUERY, budget)
    loader_ownership = loader_package_observation(probes['dynamic_loader'])
    tools = {}
    for name in TOOLS:
        path = shutil.which(name)
        tools[name] = identify(path, budget) if path else {'error': 'not found in PATH'}
    socket_path = '/var/run/docker.sock'
    try:
        info = os.stat(socket_path)
        docker_socket = {'is_socket': stat.S_ISSOCK(info.st_mode), 'uid': info.st_uid,
                         'gid': info.st_gid, 'mode': oct(stat.S_IMODE(info.st_mode)),
                         'device': info.st_dev, 'inode': info.st_ino}
    except OSError as exc:
        docker_socket = {'error': type(exc).__name__}
    # No daemon connection, process scan, environment dump or candidate import.
    return {'schema': 'enospc-host-candidate-inventory-3', 'runnable': False,
            'closure_complete': False, 'uid': os.getuid(), 'gid': os.getgid(),
            'host': {p: read_small(p) for p in TEXT}, 'tools': tools,
            'filesystem_probes': probes,
            'dpkg_query_tool': dpkg_query, 'dynamic_loader_package_queries': loader_ownership,
            'collector': identify(__file__, budget),
            'interpreter': identify(sys.executable, budget),
            'docker_socket': docker_socket, 'hash_budget_remaining': budget[0],
            'missing': ['runner provenance', 'immutable platform identity',
                        'native and Python runtime closure', 'firmware/data closure',
                        'daemon/runtime configuration and effective allocation bounds',
                        'preinstalled OCI image identity and closure',
                        'independent completeness review', 'execution authorization']}


def main():
    if len(sys.argv) != 1:
        raise SystemExit('No arguments supported; select the host out of band.')
    encoded = json.dumps(collect(), sort_keys=True, indent=2).encode() + b'\n'
    if len(encoded) > MAX_OUTPUT:
        raise SystemExit('Inventory output cap exceeded; no partial result emitted.')
    sys.stdout.buffer.write(encoded)


if __name__ == '__main__':
    main()

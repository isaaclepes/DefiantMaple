#!/usr/bin/env python3
"""Read-only candidate inventory; never a closure attestation or pin manifest."""
import hashlib
import json
import os
import pathlib
import shutil
import stat
import sys

MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_OUTPUT = 256 * 1024
TOOLS = ('python3', 'docker', 'dockerd', 'containerd', 'containerd-shim-runc-v2',
         'runc', 'qemu-system-x86_64', 'qemu-img', 'readelf', 'systemctl', 'gpgv')
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


def identify(path, budget):
    """Hash a held regular descriptor, bound reads, reject observed mutation."""
    try:
        resolved = str(pathlib.Path(path).resolve(strict=True))
        with open(resolved, 'rb') as handle:
            before = os.fstat(handle.fileno())
            result = {'resolved': resolved, 'size': before.st_size,
                      'device': before.st_dev, 'inode': before.st_ino}
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


def collect():
    budget = [MAX_TOTAL]
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
    return {'schema': 'enospc-host-candidate-inventory-1', 'runnable': False,
            'closure_complete': False, 'uid': os.getuid(), 'gid': os.getgid(),
            'host': {p: read_small(p) for p in TEXT}, 'tools': tools,
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

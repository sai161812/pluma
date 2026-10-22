"""Bounded exact application/window resolution; ambiguous names never select first."""
from pluma.adapters.app_windows import enumerate_windows


def by_name(name, *, window=False):
    wanted = name.casefold().removesuffix('.exe')
    observed = enumerate_windows({'visible_only': True, 'max_entries': 200,
        'max_scan_entries': 4096, 'filter': None})
    if observed['limited'] or any(not row['available'] for row in observed['windows']):
        raise ValueError('Application targets are incomplete or unavailable.')
    matches = [row for row in observed['windows'] if row['name'].casefold().removesuffix('.exe') == wanted]
    identities = {(row['hwnd'], row['pid'], row['creation_time']) if window else (row['pid'], row['creation_time'])
                  for row in matches}
    if len(identities) != 1:
        raise ValueError('Exactly one matching application target is required.')
    value = identities.pop()
    return dict(zip(('hwnd', 'pid', 'creation_time') if window else ('pid', 'creation_time'), value))


def process(args):
    return by_name(args['app_name']) if args.get('app_name') else {key: args[key] for key in ('pid', 'creation_time')}

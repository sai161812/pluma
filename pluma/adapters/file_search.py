"""Bounded native candidate enumeration; no content reads or implicit selection."""
from contextlib import ExitStack
import fnmatch
import os
from pathlib import Path

from pluma.adapters import file_identity as identity


def search(arguments, token=None):
    if token is not None:
        token.raise_if_cancelled()
    root = identity._checked_path(arguments['directory'])
    pending, matches, directories = [(root, 0)], [], []
    scanned, limited = 0, False
    with ExitStack() as held:
        for parent in reversed(root.parents):
            if token is not None:
                token.raise_if_cancelled()
            held.enter_context(identity._open(parent, parent=True))
        while pending and not limited:
            if token is not None:
                token.raise_if_cancelled()
            directory, depth = pending.pop()
            handle = held.enter_context(identity._open(directory, parent=True))
            before = identity._metadata(handle)
            directories.append((str(directory), handle, before))
            with os.scandir(directory) as entries:
                for entry in entries:
                    if token is not None:
                        token.raise_if_cancelled()
                    if scanned == arguments['max_scan_entries']:
                        limited = True
                        break
                    scanned += 1
                    path = Path(entry.path)
                    info = path.lstat()
                    if getattr(info, 'st_file_attributes', 0) & 0x400:
                        raise ValueError('Search cannot follow or silently omit a reparse target.')
                    is_directory = entry.is_dir(follow_symlinks=False)
                    if is_directory and depth < arguments['max_depth']:
                        pending.append((path, depth + 1))
                    if not fnmatch.fnmatchcase(entry.name.casefold(), arguments['pattern'].casefold()):
                        continue
                    kind = 'directory' if is_directory else 'file'
                    if arguments['kind'] not in ('any', kind):
                        continue
                    with identity._open(path, parent=is_directory) as child:
                        native = identity._metadata(child)
                        if native['kind'] != kind:
                            raise ValueError('Search candidate changed type.')
                        observed = path.lstat()
                        created, modified = observed.st_birthtime_ns, observed.st_mtime_ns
                        if any((arguments[field + '_after_ns'] is not None and value < arguments[field + '_after_ns'])
                               or (arguments[field + '_before_ns'] is not None and value >= arguments[field + '_before_ns'])
                               for field, value in (('created', created), ('modified', modified))):
                            continue
                        if identity._metadata(child) != native:
                            raise ValueError('Search candidate changed during inspection.')
                    matches.append({'name': entry.name, 'path': str(path), 'is_dir': is_directory,
                                    'kind': kind, 'identity': native, 'created_ns': created, 'modified_ns': modified})
                    if len(matches) == arguments['max_results']:
                        limited = True
                        break
        for path, handle, before in directories:
            if token is not None:
                token.raise_if_cancelled()
            if identity._metadata(handle) != before:
                raise ValueError('Search directory changed during enumeration.')
        proof = {path: before for path, handle, before in directories}
    matches.sort(key=lambda item: item['path'].casefold())
    return dict(arguments, matches=matches, count=len(matches), scanned_entries=scanned,
                limited=limited, unambiguous=len(matches) == 1 and not limited), proof


def verify(data, proof, arguments):
    current, current_proof = search(arguments)
    return current == data and current_proof == proof

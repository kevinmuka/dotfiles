"""Validate a ZIP archive before extracting one rooted settings tree.

This module is also copied into Alfred's installed workflow, so it uses only
Python syntax supported by the macOS system interpreter.
"""

import argparse
from pathlib import PurePosixPath
import stat
from zipfile import ZipFile, is_zipfile


def validate_zip(path, root):
    """Reject damaged ZIPs, unexpected paths, and writes through links."""
    if not is_zipfile(path):
        raise ValueError("Not a ZIP archive")
    members = []
    links = set()
    files = 0
    seen = set()
    with ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity check failed")
        for item in archive.infolist():
            name = item.filename
            path_parts = PurePosixPath(name)
            if (
                path_parts.is_absolute()
                or ".." in path_parts.parts
                or "\\" in name
                or "\x00" in name
            ):
                raise ValueError("Unsafe archive path: " + name)
            if path_parts.parts == ("._" + root,):
                continue  # macOS metadata for the archive root
            if not path_parts.parts or path_parts.parts[0] != root:
                raise ValueError("Unexpected archive root: " + name)
            parts = path_parts.parts
            if len(parts) == 1:
                if not item.is_dir():
                    raise ValueError("Archive root is not a folder")
                continue
            if parts in seen:
                raise ValueError("Duplicate archive entry: " + name)
            seen.add(parts)
            kind = stat.S_IFMT(item.external_attr >> 16)
            if item.is_dir():
                pass
            elif kind == stat.S_IFLNK:
                links.add(parts)
            elif kind in (0, stat.S_IFREG):
                files += 1
            else:
                raise ValueError("Unsupported ZIP entry: " + name)
            members.append(parts)
    if not files:
        raise ValueError("ZIP contains no files")
    for parts in members:
        if any(parts[:length] in links for length in range(1, len(parts))):
            raise ValueError("Archive writes through a symbolic link")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("root")
    args = parser.parse_args()
    try:
        validate_zip(args.archive, args.root)
    except Exception as error:
        parser.exit(1, "Invalid ZIP archive: {}\n".format(error))


if __name__ == "__main__":
    main()

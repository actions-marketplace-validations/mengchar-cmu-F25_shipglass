"""Command line interface for release inspection."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from itertools import combinations
from pathlib import Path

from . import __version__, npm
from .core import compare, scan
from .demo import create_demo
from .markdown import render_markdown
from .report import render_report


def _nonnegative(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('expected a non-negative integer') from exc
    if number < 0:
        raise argparse.ArgumentTypeError('expected a non-negative integer')
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='See what changed inside your release. No uploads, no package scripts.')
    parser.add_argument('--version', action='version', version=f'shipglass {__version__}')
    commands = parser.add_subparsers(dest='command', required=True)
    for name, help_text in [('compare', 'Compare two local release archives'), ('npm', 'Compare two exact public npm package versions'), ('inspect', 'Inspect one local archive'), ('demo', 'Explore a synthetic release with a 6 MiB surprise')]:
        command = commands.add_parser(name, help=help_text)
        if name == 'compare':
            command.add_argument('before', type=Path)
            command.add_argument('after', type=Path)
        elif name == 'npm':
            command.add_argument('package')
            command.add_argument('before_version')
            command.add_argument('after_version')
        elif name == 'inspect':
            command.add_argument('artifact', type=Path)
        if name in ('compare', 'npm'):
            command.add_argument('--fail-on-growth', type=_nonnegative, metavar='BYTES', help='Exit 1 if unpacked growth exceeds BYTES; still write reports')
        command.add_argument('-o', '--output', type=Path, default=Path('shipglass-report.html'), help='HTML output path (default: shipglass-report.html)')
        command.add_argument('--json', type=Path, dest='json_output', metavar='PATH', help='Also write the structured comparison')
        command.add_argument('--markdown', type=Path, dest='markdown_output', metavar='PATH', help='Also write a compact Markdown summary for CI or review')
        command.add_argument('--fail-on-warnings', action='store_true', help='Exit 1 if the current archive has packaging cautions')
        if name != 'demo':
            command.add_argument('--strip-components', type=_nonnegative, default=0, metavar='N', help='Explicitly remove N leading path components from both archives')
    return parser


def _size(value: int) -> str:
    sign = '-' if value < 0 else ''
    size = abs(value)
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if size < 1024 or unit == 'GiB':
            return f'{sign}{size:.1f} {unit}' if unit != 'B' else f'{sign}{size} B'
        size /= 1024
    raise AssertionError('unreachable')


def _display(value: object) -> str:
    """Keep paths readable without allowing terminal control sequences."""
    return ''.join(char if char.isprintable() else ascii(char)[1:-1] for char in str(value))


def _validate_outputs(args: argparse.Namespace) -> None:
    inputs = {getattr(args, name).resolve() for name in ('before', 'after', 'artifact') if hasattr(args, name)}
    outputs = [path for path in (args.output, args.json_output, args.markdown_output) if path is not None]
    resolved = [p.resolve() for p in outputs]
    if len(set(resolved)) != len(resolved):
        raise ValueError('output files must use different paths')
    if inputs.intersection(resolved):
        raise ValueError('an output path must not overwrite an input archive')
    # Same-file checks also protect hard-linked aliases, which resolve() cannot see.
    for output in outputs:
        if output.exists() and any(output.samefile(p) for p in inputs if p.exists()):
            raise ValueError('an output path must not overwrite an input archive')
    for first, second in combinations(outputs, 2):
        if first.exists() and second.exists() and first.samefile(second):
            raise ValueError('outputs must use different files')


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _validate_outputs(args)
        if args.command == 'demo':
            with tempfile.TemporaryDirectory(prefix='shipglass-demo-') as directory:
                first, second = create_demo(Path(directory))
                result = compare(scan(first), scan(second))
        elif args.command == 'compare':
            result = compare(scan(args.before, strip_components=args.strip_components), scan(args.after, strip_components=args.strip_components))
        elif args.command == 'npm':
            with tempfile.TemporaryDirectory(prefix='shipglass-npm-') as directory:
                print(f'Downloading {_display(args.package)}@{_display(args.before_version)}', file=sys.stderr)
                first = npm.download(args.package, args.before_version, Path(directory))
                if args.after_version == args.before_version:
                    second = first
                else:
                    print(f'Downloading {_display(args.package)}@{_display(args.after_version)}', file=sys.stderr)
                    second = npm.download(args.package, args.after_version, Path(directory))
                before = scan(first, strip_components=args.strip_components)
                after = scan(second, strip_components=args.strip_components)
                before['name'] = f'{args.package}@{args.before_version}'
                after['name'] = f'{args.package}@{args.after_version}'
                result = compare(before, after)
        else:
            current = scan(args.artifact, strip_components=args.strip_components)
            empty = {'name': 'Empty baseline', 'archive_bytes': 0, 'total_bytes': 0, 'files': [], 'warnings': [], 'format': 'empty'}
            result = compare(empty, current)
        html = render_report(result)
        markdown = render_markdown(result) if args.markdown_output else None
        args.output.write_text(html, encoding='utf-8')
        if args.json_output:
            args.json_output.write_text(json.dumps(result, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
        if args.markdown_output:
            args.markdown_output.write_text(markdown, encoding='utf-8')
        summary = result['summary']
        print(f"Shipglass  {_display(result['before']['name'])} -> {_display(result['after']['name'])}")
        print(f"Unpacked: {_size(summary['before_bytes'])} -> {_size(summary['after_bytes'])} ({'+' if summary['delta_bytes'] >= 0 else ''}{_size(summary['delta_bytes'])})")
        print(f"Files: {summary['added']} added, {summary['removed']} removed, {summary['changed']} changed, {summary['unchanged']} unchanged")
        current_warnings = len(result['after']['warnings']) + sum(len(f['warnings']) for f in result['after']['files'])
        print(f'Packaging cautions in current archive: {current_warnings} (filename checks, not a security audit)')
        print(f'Report: {_display(args.output.resolve())}')
        if args.json_output:
            print(f'JSON: {_display(args.json_output.resolve())}')
        if args.markdown_output:
            print(f'Markdown: {_display(args.markdown_output.resolve())}')
        exceeded = hasattr(args, 'fail_on_growth') and args.fail_on_growth is not None and summary['delta_bytes'] > args.fail_on_growth
        if exceeded:
            print(f'Growth exceeds {args.fail_on_growth} bytes.', file=sys.stderr)
        return 1 if exceeded or (args.fail_on_warnings and current_warnings) else 0
    except (OSError, ValueError) as exc:
        print(f'shipglass: {_display(exc)}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

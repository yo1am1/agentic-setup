import { afterEach, expect, test } from 'bun:test';
import { mkdtempSync, mkdirSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { readInside } from './files';

const temporary: string[] = [];
afterEach(() => { for (const path of temporary.splice(0)) rmSync(path, { recursive: true, force: true }); });

function repo(): string {
  const base = mkdtempSync(join(tmpdir(), 'sssf-files-test-'));
  temporary.push(base);
  const root = join(base, 'product');
  mkdirSync(join(root, 'src'), { recursive: true });
  writeFileSync(join(base, 'secret.txt'), 'outside the factory\n');
  writeFileSync(join(root, 'src/app.py'), 'print("hello")\n');
  writeFileSync(join(root, 'logo.bin'), new Uint8Array([0x89, 0x50, 0x00, 0x01]));
  symlinkSync(join(base, 'secret.txt'), join(root, 'escape.txt'));
  return root;
}

test('reads a text file and lists a directory inside the factory', async () => {
  const root = repo();
  const file = await readInside(root, 'src/app.py');
  expect(file).toMatchObject({ kind: 'file', path: 'src/app.py', truncated: false });
  expect(file.kind === 'file' && file.text).toBe('print("hello")\n');

  const dir = await readInside(root, '');
  expect(dir.kind).toBe('dir');
  // Directories sort ahead of files so navigation reads top-down.
  expect(dir.kind === 'dir' && dir.entries[0]).toMatchObject({ name: 'src', kind: 'dir' });
});

test('refuses to leave the factory, by traversal or by symlink', async () => {
  const root = repo();
  await Promise.all(
    ['../secret.txt', 'src/../../secret.txt', 'escape.txt'].map(path =>
      expect(readInside(root, path)).rejects.toThrow('outside the factory'),
    ),
  );
  // A leading slash is stripped, not honoured as an absolute path.
  await expect(readInside(root, '/etc/passwd')).rejects.toThrow('no such path');
});

test('refuses binary content instead of streaming it into the page', async () => {
  await expect(readInside(repo(), 'logo.bin')).rejects.toThrow('binary file');
});

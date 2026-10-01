/**
 * Read a file or directory out of a factory repo, for the trace UI.
 *
 * A trace names paths constantly — every read, write, grep and diff — but a
 * name is not evidence. This turns those names into the thing itself, without
 * leaving the browser and without letting the browser leave the repo: every
 * request is resolved through realpath and must still land inside the factory
 * root, so a symlink pointing at /etc is refused rather than followed.
 */
import { readdirSync, realpathSync, statSync } from "node:fs";
import { join, resolve, sep } from "node:path";
import { OperatorError } from "./operator.ts";
import type { DirEntry, FileView } from "../shared/types.ts";

/** Enough to read any source file; past this the browser is the wrong tool. */
const MAX_BYTES = 512 * 1024;
/** A directory listing is for navigating, not for auditing node_modules. */
const MAX_ENTRIES = 1000;

/**
 * Resolve a repo-relative path to a real one inside `root`.
 *
 * Both sides go through realpath so that neither `..` nor a symlink can widen
 * the boundary; the repo root itself is allowed, everything above it is not.
 */
function inside(root: string, requested: string): string {
  const relative = requested.replace(/^[/\\]+/, "");
  const target = resolve(root, relative);
  const realRoot = realpathSync(root);
  // realpath needs the path to exist; a miss is a 404, not a boundary failure.
  let realTarget: string;
  try {
    realTarget = realpathSync(target);
  } catch {
    throw new OperatorError(`no such path: ${relative || "."}`, 404);
  }
  if (realTarget !== realRoot && !realTarget.startsWith(realRoot + sep)) {
    throw new OperatorError("path resolves outside the factory", 403);
  }
  return realTarget;
}

function listing(target: string, path: string): FileView {
  const names = readdirSync(target, { withFileTypes: true });
  const entries: DirEntry[] = [];
  for (const item of names.slice(0, MAX_ENTRIES)) {
    let size = 0;
    // A broken symlink still deserves a row; it just has no size.
    try {
      size = statSync(join(target, item.name)).size;
    } catch {
      /* keep 0 */
    }
    entries.push({ name: item.name, kind: item.isDirectory() ? "dir" : "file", size });
  }
  entries.sort((a, b) =>
    a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === "dir" ? -1 : 1,
  );
  return { kind: "dir", path, entries, truncated: names.length > MAX_ENTRIES };
}

export async function readInside(root: string, requested: string): Promise<FileView> {
  const target = inside(root, requested);
  const path = requested.replace(/^[/\\]+/, "");
  if (statSync(target).isDirectory()) return listing(target, path);

  const file = Bun.file(target);
  const bytes = file.size;
  const slice = bytes > MAX_BYTES ? file.slice(0, MAX_BYTES) : file;
  const buffer = new Uint8Array(await slice.arrayBuffer());
  // A NUL byte in the first block is the cheap, reliable binary tell.
  if (buffer.subarray(0, 4096).includes(0)) {
    throw new OperatorError("binary file — open it in an editor", 415);
  }
  return {
    kind: "file",
    path,
    text: new TextDecoder().decode(buffer),
    bytes,
    truncated: bytes > MAX_BYTES,
  };
}

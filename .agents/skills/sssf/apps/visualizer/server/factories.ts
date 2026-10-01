/**
 * Factory discovery — every stamped repo under one root, watched as a set.
 *
 * A factory has a trace DB or local SSSF config. New projects can therefore
 * be selected for their first web launch before a trace DB exists.
 *
 * The scan is depth-1 and cached. It never walks a tree, so its cost is the
 * number of top-level directories under the root and a symlink cannot send it
 * in a circle.
 */
import { existsSync, readdirSync, statSync } from "node:fs";
import { isAbsolute, join, resolve } from "node:path";
import { SssfDb } from "./db.ts";

const DEFAULT_ROOT = "/home/user/VS";
const DB_RELATIVE = "adws/adw_data/sssf.db";
const CONFIG_RELATIVE = "adws/adw_sssf_config/sssf.config.yaml";
/** How often the directory listing is refreshed, independent of UI polling. */
const RESCAN_MS = 3_000;

/**
 * Where to look for factories: --factories-root, then SSSF_FACTORIES_ROOT,
 * then the default. Same precedence shape as resolveDbPath.
 *
 * Several roots are given the way PATH gives several directories — colon
 * separated — so `~/VS:~/work` watches both. Order is meaningful: it decides
 * which repo keeps its name when two roots hold one of the same name (see
 * rescan). Duplicates and empty segments are dropped so a trailing colon or a
 * root listed twice cannot make one factory appear twice.
 */
export function resolveFactoriesRoots(argv: string[] = Bun.argv): string[] {
  const flagIndex = argv.indexOf("--factories-root");
  const inline = argv.find((a) => a.startsWith("--factories-root="));
  const raw =
    (flagIndex !== -1 ? argv[flagIndex + 1] : undefined) ??
    inline?.slice("--factories-root=".length) ??
    process.env.SSSF_FACTORIES_ROOT ??
    DEFAULT_ROOT;

  const roots: string[] = [];
  const seen = new Set<string>();
  for (const part of raw.split(":")) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    const abs = isAbsolute(trimmed) ? trimmed : resolve(process.cwd(), trimmed);
    if (seen.has(abs)) continue;
    seen.add(abs);
    roots.push(abs);
  }
  return roots.length ? roots : [DEFAULT_ROOT];
}

export interface FactoryEntry {
  name: string;
  /** Absolute path to the repo root. */
  path: string;
  /** Absolute path to its sssf.db. */
  dbPath: string;
  /** Test seam; production entries always use the shared user-scoped engine. */
  enginePath?: string;
  /**
   * The scanned roots this factory was found under. `just init` links a
   * project's rosters back to the factory that owns the shared engine, so a
   * roster symlink landing inside a scanned root is the architecture working
   * rather than an escape — and anywhere else is still refused.
   */
  trustedRoots?: string[];
}

export class FactoryRegistry {
  readonly roots: string[];
  private entries = new Map<string, FactoryEntry>();
  private readonly open = new Map<string, SssfDb>();
  private timer: ReturnType<typeof setInterval> | undefined;
  /** Collisions already reported, so a 3s rescan does not repeat itself. */
  private readonly warned = new Set<string>();

  constructor(roots: string[]) {
    this.roots = roots;
    this.rescan();
  }

  /** Refresh on a timer so a repo stamped after startup still shows up. */
  watch(): void {
    this.timer ??= setInterval(() => this.rescan(), RESCAN_MS);
  }

  stop(): void {
    clearInterval(this.timer);
    this.timer = undefined;
    for (const db of this.open.values()) db.close();
    this.open.clear();
  }

  /**
   * One listing per root, keeping directories that contain a trace db.
   *
   * statSync rather than Dirent.isDirectory() on purpose: a repo checked out
   * elsewhere and symlinked into the root is still a repo, and Dirent would
   * report it as a link and skip it.
   *
   * A root that cannot be read is skipped rather than fatal — one bad entry in
   * a colon-separated list must not blank out the factories found by the rest.
   */
  rescan(): void {
    const found = new Map<string, FactoryEntry>();

    for (const root of this.roots) {
      let names: string[];
      try {
        names = readdirSync(root);
      } catch (error) {
        if (!this.warned.has(root)) {
          this.warned.add(root);
          console.error(`[sssf] cannot read factories root ${root}:`, error);
        }
        continue;
      }

      for (const name of names) {
        const path = join(root, name);
        try {
          if (!statSync(path).isDirectory()) continue;
        } catch {
          continue;                 // vanished or unreadable between listing and stat
        }
        const dbPath = join(path, DB_RELATIVE);
        if (!existsSync(dbPath) && !existsSync(join(path, CONFIG_RELATIVE))) continue;

        // The name is the URL segment and the map key, so two roots holding a
        // repo of the same name cannot both be addressed. Earlier roots win —
        // the list is the operator's stated precedence — and the shadowed one
        // is named once rather than disappearing without a word.
        const clash = found.get(name);
        if (clash) {
          if (clash.dbPath !== dbPath && !this.warned.has(dbPath)) {
            this.warned.add(dbPath);
            console.error(
              `[sssf] two factories are named ${name}: serving ${clash.path}, ` +
                `hiding ${path}. Rename one, or drop a root.`,
            );
          }
          continue;
        }
        found.set(name, { name, path, dbPath, trustedRoots: this.roots });
      }
    }

    // Drop cached connections for factories that are gone, so a deleted repo
    // does not keep a handle (and a file descriptor) alive forever.
    for (const [name, db] of this.open) {
      if (!found.has(name)) {
        db.close();
        this.open.delete(name);
      }
    }
    this.entries = found;
  }

  list(): FactoryEntry[] {
    return [...this.entries.values()].toSorted((a, b) => a.name.localeCompare(b.name));
  }

  /**
   * The reader for one factory, or null if it is not a factory we know.
   *
   * The name is resolved through the scanned map and never joined into a path,
   * so a hostile segment cannot reach outside the root even if it survived the
   * caller's validation. Returns null rather than throwing: one unreadable db
   * must not take down an index that lists a dozen healthy ones.
   */
  getDb(name: string): SssfDb | null {
    const entry = this.entries.get(name);
    if (!entry) return null;

    // Cheap stat every call: catches a db deleted since the last rescan without
    // making the UI wait out the rescan interval to stop showing it.
    if (!existsSync(entry.dbPath)) {
      this.evict(name);
      return null;
    }

    const cached = this.open.get(name);
    if (cached) return cached;

    try {
      const db = new SssfDb(entry.dbPath);
      this.open.set(name, db);
      return db;
    } catch (error) {
      console.error(`[sssf] factory ${name}: ${(error as Error).message}`);
      return null;
    }
  }

  private evict(name: string): void {
    const db = this.open.get(name);
    if (!db) return;
    try {
      db.close();
    } catch {
      /* already closed or the file went away — nothing to salvage */
    }
    this.open.delete(name);
  }
}

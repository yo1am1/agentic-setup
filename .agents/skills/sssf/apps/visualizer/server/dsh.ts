/**
 * The dsh web UI's own login link, read from its systemd unit's journal.
 *
 * dsh mints a fresh launch token every boot and accepts it only as a `?token=`
 * query param on `GET /` — by design, confirmed against dsh's own source
 * before this was written: its connection package states outright "there is
 * no method-specific loopback tier," because the surface behind it is full
 * shell and filesystem access. There is no way around needing the token once;
 * this endpoint only saves finding it by hand in `journalctl`.
 *
 * Exposed as a POST route in index.ts specifically so `safely()`'s existing
 * write-gate applies to it — revealing a login credential is not a mutation,
 * but it carries the same sensitivity as one, and the route table has no
 * other way to ask for the operator token on a GET.
 */
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { OperatorError } from './operator.ts';

const execute = promisify(execFile);
const DSH_UNIT = 'dsh-web';
const TOKEN_LINE = /dsh web: http:\/\/[^\s]+\?token=([\w-]+)/g;

function dshPort(): number {
  const configured = Number(process.env.DSH_WEB_PORT);
  return Number.isInteger(configured) && configured > 0 ? configured : 3080;
}

/**
 * The current dsh web URL, on the SAME host the request already arrived on.
 *
 * `requestHost` is the incoming request's own Host header (e.g.
 * `user-loq-15irx9.tail0204df.ts.net:4600`) — stripping its port and
 * substituting dsh's own means the link always matches whichever authority
 * the browser is already using to reach this app, tailnet FQDN or localhost
 * alike, rather than this server guessing a name of its own that might not be
 * one dsh's --trusted-host fence was configured to accept.
 */
export async function dshUrl(requestHost: string | null): Promise<string> {
  const host = (requestHost ?? 'localhost').split(':')[0];
  let stdout: string;
  try {
    ({ stdout } = await execute(
      'journalctl', ['--user', '-u', DSH_UNIT, '-n', '200', '--no-pager', '--output=cat'],
      { timeout: 5000, maxBuffer: 1_000_000 },
    ));
  } catch (error) {
    throw new OperatorError(`could not read the dsh-web log: ${(error as Error).message}`, 502);
  }
  // journalctl prints oldest-first and dsh logs one startup line per boot, so
  // a unit with restart history carries several — the LAST match is the
  // current process's. services.py's own dsh-url command hands back a dead
  // token for an old process if it reads the first match instead; found live
  // there before this endpoint was written the same way.
  const last = [...stdout.matchAll(TOKEN_LINE)].at(-1);
  if (!last) {
    throw new OperatorError('no dsh-web startup line in its recent log — is the service running?', 404);
  }
  return `http://${host}:${dshPort()}/?token=${last[1]}`;
}

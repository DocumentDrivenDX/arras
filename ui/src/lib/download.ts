// SPDX-License-Identifier: MIT OR Apache-2.0
/** How long a saved file's object URL is kept before it is revoked (the download has begun by then). */
export const REVOKE_AFTER_MS = 10_000;

/**
 * Save `text` as a file named `filename`: a Blob behind an object URL, saved by clicking an `<a download>`,
 * then the URL is revoked. Nothing goes to a server, a URL carries no content, and browser storage is not
 * used, so the page's strict Content-Security-Policy (`default-src 'none'`) allows it.
 */
export function downloadText(filename: string, text: string, type = "application/json"): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  a.hidden = true;
  document.body.append(a);
  try {
    a.click();
  } finally {
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS);
  }
}

/** The signature a host or a test can replace to observe what would be saved. */
export type SaveFile = (filename: string, text: string) => void;

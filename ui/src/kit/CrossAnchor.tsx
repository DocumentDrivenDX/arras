// SPDX-License-Identifier: MIT OR Apache-2.0
import type { ReactNode } from "react";
import type { CrossLink } from "./links";

const plain = (e: React.MouseEvent) =>
  e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey;

/**
 * A cross-mode link: an anchor where the shell gave an `href`, a button where only `go` exists. A plain
 * click runs `go`; a modified click keeps the anchor's own behaviour (a new tab).
 */
export function CrossAnchor({
  link,
  children,
  className,
  ...rest
}: {
  link: CrossLink;
  children: ReactNode;
  className?: string;
  "aria-label"?: string;
  title?: string;
}) {
  if (link.href === undefined)
    return (
      <button type="button" className={className} onClick={() => link.go()} {...rest}>
        {children}
      </button>
    );
  return (
    <a
      href={link.href}
      className={className}
      onClick={(e) => {
        if (!plain(e) || e.defaultPrevented) return;
        e.preventDefault();
        link.go();
      }}
      {...rest}
    >
      {children}
    </a>
  );
}

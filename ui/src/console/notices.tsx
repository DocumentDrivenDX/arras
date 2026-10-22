// SPDX-License-Identifier: MIT OR Apache-2.0
import { NotFound } from "../areas/ConsoleNotices";
import { ErrorPanel } from "../components/ui";

export function NoModules({ module }: { module: string | undefined }) {
  return (
    <>
      <div className="p-6 text-muted" data-testid="no-modules">
        No modules are readable by you.
      </div>
      {module && (
        // A deep link to a module answers as for any module the viewer cannot read (US-060 AC4).
        <NotFound />
      )}
    </>
  );
}

export function QueryError({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <div className="p-4">
      <ErrorPanel error={error} onRetry={retry} />
    </div>
  );
}

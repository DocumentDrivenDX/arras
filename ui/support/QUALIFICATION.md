# Downstream theme qualification

`arras-ui-qualify <URL>` checks an HTTP(S) host using the public Arras UI in a real Chromium browser. Add `--host-build` when the page is a compiled host using `ArrasApp`, and `--console` when the route is the operator console. The command checks the public root, WCAG 2.1 A/AA axe rules, the 18 documented role tokens, color contrast, keyboard focus, and screenshots. For host builds it also verifies app-owned theme Button/Mark use and opens, searches, and dismisses the command palette while checking focus restoration.

Install `@playwright/test@1.63.0` and `@axe-core/playwright@4.13.0` in the invoking host and install a compatible Chromium browser before running the command. These are optional peer dependencies. The command never installs packages, downloads browsers, or accesses the network to obtain dependencies. Missing tools produce an actionable error.

Use `--output <dir>` to retain screenshots and a JSON receipt; by default they go to `arras-ui-qualification/` under the current directory. Use `--baselines <dir>` to compare against platform-specific PNG baselines. With no baseline directory, screenshots are captured and the receipt marks visual comparison unqualified. macOS compares baselines when supplied; other platforms report visual comparison skipped while still running every nonvisual gate. Updating is explicit and macOS-only: `--baselines <dir> --update-baselines`. Review updated images before accepting them. Unknown or malformed arguments exit with status 2; `--help` prints the supported arguments.

For installed-artifact validation, build and install the wheel-carried npm package into an external consumer and invoke its `arras-ui-qualify` bin. A completed receipt should be retained with the exact wheel, npm package, theme package, and runner hashes and the runtime versions used. The qualification fixture installs the Arras and theme tarballs from the selected cohort and obtains public tooling and React peers from the npm registry in an isolated temporary project.

The result qualifies only the tested host, theme, package cohort, browser, and platform. It is not a certification of other host applications or themes.

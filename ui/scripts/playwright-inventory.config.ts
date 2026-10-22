// SPDX-License-Identifier: MIT OR Apache-2.0
// Discovery-only config: include the visual project on every build host so its canonical count is hashed.

import type { PlaywrightTestConfig } from "@playwright/test";
import config from "../playwright.config";

export function includeVisualInventoryProject(
  current: PlaywrightTestConfig["projects"],
): NonNullable<PlaywrightTestConfig["projects"]> {
  const projects = [...(current ?? [])];
  if (!projects.some((project) => project.name === "visual"))
    projects.push({
      name: "visual",
      testMatch: /visual\.spec\.ts$/,
      use: {
        browserName: "chromium",
        baseURL: "http://127.0.0.1:8123",
        timezoneId: "UTC",
        locale: "en-GB",
      },
    });
  return projects;
}

export default { ...config, projects: includeVisualInventoryProject(config.projects) };

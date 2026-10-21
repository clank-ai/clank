// Runs the host suite inside a real VS Code (decision 0029): VS Code 1.138.0, the oldest the extension accepts,
// downloaded once into `.vscode-test/`; a throwaway profile with no other extension and AI features off; CLANK_HOME an
// empty temporary folder that the suite fills as it needs.

import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import { runTests } from "@vscode/test-electron";

const VERSION = "1.138.0";

async function main(): Promise<void> {
  const folder = resolve(__dirname, "..", "..");
  const scratch = mkdtempSync(join(tmpdir(), "clank-host-"));
  const profile = join(scratch, "profile");
  mkdirSync(join(profile, "User"), { recursive: true });
  writeFileSync(
    join(profile, "User", "settings.json"),
    JSON.stringify({ "chat.disableAIFeatures": true, "workbench.startupEditor": "none", "update.mode": "none" }),
  );
  const code = await runTests({
    version: VERSION,
    extensionDevelopmentPath: folder,
    extensionTestsPath: join(__dirname, "suite.js"),
    launchArgs: [
      "--disable-extensions",
      "--disable-workspace-trust",
      "--skip-welcome",
      "--skip-release-notes",
      "--user-data-dir",
      profile,
      "--extensions-dir",
      join(scratch, "extensions"),
      scratch,
    ],
    extensionTestsEnv: { CLANK_HOME: join(scratch, "clank-home") },
  });
  process.exitCode = code;
}

main().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});

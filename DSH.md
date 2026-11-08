# DeepSeek Harness plugin

The `1.5.0-rc.29` source candidate adds a Cordis wrapper around the existing
`babeldoc-pdf-translate` skill. It does not alter the Python translation pipeline,
BabelDOC patches, model selection, quality gates, or existing Codex installation.
The last downloadable translation release remains `v1.5.0-rc.28`, with its
[documented validation limits](VALIDATION.md).

## Install

Requirements: DeepSeek Harness `0.2.2-rc.1`, Node.js `>=24.9.0`, and the host's
existing `skills` service. The declared compatibility range is
`>=0.2.2-rc.1 <0.3.0-0`; later versions in that range still need verification as
DSH is a developer preview. The `web` profile supplies the normal skill tools.

```sh
dsh plugin --profile web add github:reliable-ly0411/babeldoc-pdf-translate
```

Restart that profile after installation. The `babeldoc-pdf-translate` skill is
then available to the agent. Ask it to use that skill with a PDF path, language,
page range and output preferences. Inspect or prepare a job before authorizing
translation. This is an instruction package, not a self-contained PDF engine.
Install Python 3.12 and the separate runtime by following
[deployment](references/deployment.md).

For a reproducible source installation, append `#<commit SHA>` to the GitHub
specifier. For a local checkout or inspected package archive:

```sh
npm pack --ignore-scripts
dsh plugin --profile web add /absolute/path/to/dsh-babeldoc-pdf-translate-1.5.0-rc.29.tgz
```

The package has no runtime npm dependencies, install hooks, or build step.
The `dsh.bundle` field selects `cordis.patch.yml`, which inserts one plugin row;
`apply(ctx)` registers one provider with `ctx.skills`. The host owns cleanup when
the plugin is disabled or unloaded. The provider uses DSH's bundled priority, so
an existing project or user skill of the same name takes precedence.

## Remove

```sh
dsh plugin --profile web remove dsh-babeldoc-pdf-translate
```

Restart that profile. This removes the plugin contribution. Separately installed
Python runtimes, document outputs, caches and filesystem skill copies remain
under the user's control.

## Permissions and external services

- Registration and loading read only the packaged `SKILL.md` and expose its
  local resource directory. The adapter does not access credentials, private
  documents, environment secrets, the network, or other profiles.
- The adapter does not start processes or install/repair the runtime. Its npm
  package excludes tests, benchmark PDFs, model files, caches and environments.
- Running the workflow is a separate, user-directed operation using the host's
  file and command tools. It reads selected documents and writes selected output
  folders. Translation can send document text to the configured provider; visual
  review can send rendered page images. Review that provider and the document's
  confidentiality before execution. An already-running local backend can also
  be configured.
- No telemetry, bundled cloud account or automatic provider/model upgrade is
  added. Native-account and API routes keep their existing explicit setup and
  usage-budget requirements.

## Distribution and license

This source-installable plugin is submitted for the community website catalog,
not claimed to be an official DeepSeek plugin. No npm package has been published;
the Hub's in-app npm-only marketplace is therefore not yet an installation path.

Original skill/adapter code is MIT. The shipped derived BabelDOC patches are
AGPL-3.0-only and retain their license in `patches/babeldoc-0.6.4/LICENSE`.
The package declares `MIT AND AGPL-3.0-only`. Runtime dependencies retain their
own licenses and are not bundled.

## Verification

From the source checkout:

```sh
npm run check
python scripts/sync_plugin_skill.py --check
```

The Node checks cover service registration, immutable catalog metadata,
resource resolution, unchanged instruction content, cancellation, rejected
foreign locators, version agreement and the absence of install hooks.
Real host installation/loading checks are recorded in the corresponding pull
request. They verify discovery, resource access and plugin removal, not PDF
translation quality. No paid model calls are needed for these checks.

Complex formulas, scanned pages, the unvalidated automatic quality protocol and
other [existing translation limits](VALIDATION.md) remain unchanged. No new
full-document or cross-platform translation acceptance is claimed.

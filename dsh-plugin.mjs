/** Expose the existing PDF workflow through DeepSeek Harness's skill registry. */
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

export const name = 'babeldoc-pdf-translate';
export const inject = ['skills'];

const description = 'Translate PDF documents with BabelDOC while retaining layout, figures and formulas; supports bilingual output, custom glossaries, domain terminology and local processing with configurable translation providers. Use for translated PDFs, not merely summaries or plain text extraction.';
const skillURL = new URL('./SKILL.md', import.meta.url);
const resourceBase = Object.freeze({
  kind: 'directory',
  path: fileURLToPath(new URL('./', import.meta.url)),
});
const invocation = Object.freeze({ modelInvocable: true, userInvocable: true });
const candidate = Object.freeze({
  name,
  description,
  invocation,
  provider: 'babeldoc-pdf-translate',
  source: 'bundled',
  path: fileURLToPath(skillURL),
  resourceBase,
  // DSH's documented bundled-skill rank; project and user skills take priority.
  rank: 600,
  locator: 'SKILL.md',
});

/** Build a read-only provider. Registration never installs runtimes or invokes a model. */
export function createSkillProvider() {
  return {
    name: candidate.provider,
    async list(options = {}) {
      options.signal?.throwIfAborted();
      return [candidate];
    },
    async get(selected, options = {}) {
      options.signal?.throwIfAborted();
      if (selected?.name !== name || selected?.locator !== candidate.locator) return undefined;
      let raw;
      try {
        raw = await readFile(skillURL, { encoding: 'utf8', signal: options.signal });
      } catch (error) {
        if (error.code === 'ENOENT') return undefined;
        throw error;
      }
      const frontmatter = /^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/u.exec(raw);
      if (!frontmatter) throw new Error('BabelDOC skill is missing its frontmatter.');
      const { rank: _rank, locator: _locator, ...summary } = candidate;
      return { ...summary, content: raw.slice(frontmatter[0].length).trim() };
    },
  };
}

/** Register packaged instructions with the host-owned registry and lifecycle. */
export function apply(ctx) {
  if (typeof ctx.skills?.registerProvider !== 'function') {
    throw new Error('BabelDOC requires a DSH host with the skills.registerProvider API.');
  }
  ctx.skills.registerProvider(() => createSkillProvider());
}

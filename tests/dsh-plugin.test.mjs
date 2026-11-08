import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { isAbsolute, join } from 'node:path';
import test from 'node:test';
import { apply, createSkillProvider, inject, name } from '../dsh-plugin.mjs';

const root = new URL('../', import.meta.url);
const readJSON = async (path) => JSON.parse(await readFile(new URL(path, root), 'utf8'));

test('exports a Cordis plugin requiring the existing skill registry', () => {
  assert.equal(name, 'babeldoc-pdf-translate');
  assert.deepEqual(inject, ['skills']);
  assert.throws(() => apply({}), /skills.registerProvider/);
  assert.throws(() => apply({ skills: {} }), /skills.registerProvider/);
});

test('registers one provider without requesting other host capabilities', () => {
  const registrations = [];
  const ctx = new Proxy({ skills: { registerProvider: (factory) => registrations.push(factory()) } }, {
    get(target, key) {
      assert.equal(key, 'skills');
      return target[key];
    },
  });
  apply(ctx);
  assert.equal(registrations.length, 1);
  assert.equal(registrations[0].name, name);
});

test('lists immutable packaged metadata with lower priority than local skills', async () => {
  const [skill] = await createSkillProvider().list();
  const raw = await readFile(new URL('SKILL.md', root), 'utf8');
  assert.equal(skill.name, /^name: (.+)$/mu.exec(raw)[1]);
  assert.equal(skill.description, /^description: (.+)$/mu.exec(raw)[1]);
  assert.deepEqual(skill.invocation, { modelInvocable: true, userInvocable: true });
  assert.equal(skill.source, 'bundled');
  assert.equal(skill.rank, 600);
  assert.equal(skill.resourceBase.kind, 'directory');
  assert.ok(isAbsolute(skill.resourceBase.path));
  assert.equal(skill.path, join(skill.resourceBase.path, 'SKILL.md'));
  assert.ok(Object.isFrozen(skill));
  assert.ok(Object.isFrozen(skill.resourceBase));
  assert.ok(Object.isFrozen(skill.invocation));
});

test('loads the unchanged skill body and resolves packaged resources', async () => {
  const provider = createSkillProvider();
  const [candidate] = await provider.list();
  const skill = await provider.get(candidate);
  const raw = await readFile(new URL('SKILL.md', root), 'utf8');
  const expected = raw.replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/u, '').trim();
  assert.equal(skill.content, expected);
  assert.equal(skill.name, name);
  assert.equal(skill.provider, provider.name);
  assert.ok(!('locator' in skill));
  assert.ok(!('rank' in skill));
  for (const resource of ['scripts/pdf_translate.py', 'references/deployment.md', 'assets/job.example.json', 'patches/babeldoc-0.6.4/LICENSE']) {
    assert.ok((await readFile(join(skill.resourceBase.path, resource))).length > 0);
  }
});

test('does not follow a forged locator or return an unrelated skill', async () => {
  const provider = createSkillProvider();
  const [candidate] = await provider.list();
  assert.equal(await provider.get({ ...candidate, locator: '/etc/passwd' }), undefined);
  assert.equal(await provider.get({ ...candidate, name: 'unrelated' }), undefined);
  assert.equal(await provider.get(undefined), undefined);
});

test('honors cancellation before discovery and loading', async () => {
  const provider = createSkillProvider();
  const [candidate] = await provider.list();
  const controller = new AbortController();
  controller.abort(new Error('cancelled test'));
  await assert.rejects(provider.list({ signal: controller.signal }), /cancelled test/);
  await assert.rejects(provider.get(candidate, { signal: controller.signal }), /cancelled test/);
});

test('all package manifests use the same candidate version', async () => {
  const manifests = await Promise.all(['package.json', 'plugin.json', '.codex-plugin/plugin.json'].map(readJSON));
  assert.equal(new Set(manifests.map((manifest) => manifest.version)).size, 1);
  assert.equal(manifests[0].repository.url, 'git+https://github.com/reliable-ly0411/babeldoc-pdf-translate.git');
  assert.equal(manifests[0].license, 'MIT AND AGPL-3.0-only');
  assert.equal(manifests[0].main, 'dsh-plugin.mjs');
  assert.equal(manifests[0].engines.dsh, '>=0.2.2-rc.1 <0.3.0-0');
  assert.equal(manifests[0].dsh.engines, undefined);
  assert.equal(manifests[0].dsh.bundle.patch, './cordis.patch.yml');
  const patch = await readFile(new URL('cordis.patch.yml', root), 'utf8');
  assert.match(patch, new RegExp(`name: ${manifests[0].name}\\n`));
  for (const forbidden of ['preinstall', 'install', 'postinstall', 'prepare', 'prepack', 'postpack']) {
    assert.equal(manifests[0].scripts[forbidden], undefined);
  }
  assert.deepEqual(manifests[0].dependencies ?? {}, {});
});

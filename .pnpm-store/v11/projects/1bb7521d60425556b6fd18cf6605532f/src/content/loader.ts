import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { eventSchema, travelSchema, enemySchema, guidedSchema, itemsSchema } from './schema.js';
import type { EventDefinition, TravelDefinition, EnemyDefinition, GuidedManifest } from '../game/types.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const contentRoot = path.resolve(here, '../../content');

function readJson(filePath: string): unknown {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function loadDir<T>(dir: string, parse: (value: unknown) => T): Map<string, T> {
  const out = new Map<string, T>();
  for (const file of fs.readdirSync(dir).filter((f) => f.endsWith('.json'))) {
    const parsed = parse(readJson(path.join(dir, file)));
    const id = (parsed as { id: string }).id;
    if (out.has(id)) throw new Error(`Duplicate content id: ${id}`);
    out.set(id, parsed);
  }
  return out;
}

export class ContentStore {
  events = loadDir<EventDefinition>(path.join(contentRoot, 'events'), (v) => eventSchema.parse(v) as EventDefinition);
  travels = loadDir<TravelDefinition>(path.join(contentRoot, 'travel'), (v) => travelSchema.parse(v) as TravelDefinition);
  enemies = loadDir<EnemyDefinition>(path.join(contentRoot, 'enemies'), (v) => enemySchema.parse(v) as EnemyDefinition);
  items = new Map(itemsSchema.parse(readJson(path.join(contentRoot, 'items/items.json'))).map((x) => [x.id, x]));

  guided(version: string): GuidedManifest {
    const file = path.join(contentRoot, 'guided', `${version}.json`);
    if (!fs.existsSync(file)) throw new Error(`Missing guided manifest for ${version}`);
    return guidedSchema.parse(readJson(file)) as GuidedManifest;
  }

  event(id: string): EventDefinition {
    const value = this.events.get(id);
    if (!value) throw new Error(`Unknown event definition: ${id}`);
    return value;
  }

  travel(id: string): TravelDefinition {
    const value = this.travels.get(id);
    if (!value) throw new Error(`Unknown travel definition: ${id}`);
    return value;
  }

  enemy(id: string): EnemyDefinition {
    const value = this.enemies.get(id);
    if (!value) throw new Error(`Unknown enemy definition: ${id}`);
    return value;
  }
}

export const content = new ContentStore();

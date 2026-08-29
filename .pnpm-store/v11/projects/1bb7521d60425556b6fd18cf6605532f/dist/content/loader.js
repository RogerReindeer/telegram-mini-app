import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { eventSchema, travelSchema, enemySchema, guidedSchema, itemsSchema } from './schema.js';
const here = path.dirname(fileURLToPath(import.meta.url));
const contentRoot = path.resolve(here, '../../content');
function readJson(filePath) {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}
function loadDir(dir, parse) {
    const out = new Map();
    for (const file of fs.readdirSync(dir).filter((f) => f.endsWith('.json'))) {
        const parsed = parse(readJson(path.join(dir, file)));
        const id = parsed.id;
        if (out.has(id))
            throw new Error(`Duplicate content id: ${id}`);
        out.set(id, parsed);
    }
    return out;
}
export class ContentStore {
    events = loadDir(path.join(contentRoot, 'events'), (v) => eventSchema.parse(v));
    travels = loadDir(path.join(contentRoot, 'travel'), (v) => travelSchema.parse(v));
    enemies = loadDir(path.join(contentRoot, 'enemies'), (v) => enemySchema.parse(v));
    items = new Map(itemsSchema.parse(readJson(path.join(contentRoot, 'items/items.json'))).map((x) => [x.id, x]));
    guided(version) {
        const file = path.join(contentRoot, 'guided', `${version}.json`);
        if (!fs.existsSync(file))
            throw new Error(`Missing guided manifest for ${version}`);
        return guidedSchema.parse(readJson(file));
    }
    event(id) {
        const value = this.events.get(id);
        if (!value)
            throw new Error(`Unknown event definition: ${id}`);
        return value;
    }
    travel(id) {
        const value = this.travels.get(id);
        if (!value)
            throw new Error(`Unknown travel definition: ${id}`);
        return value;
    }
    enemy(id) {
        const value = this.enemies.get(id);
        if (!value)
            throw new Error(`Unknown enemy definition: ${id}`);
        return value;
    }
}
export const content = new ContentStore();

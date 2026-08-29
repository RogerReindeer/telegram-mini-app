import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { z } from 'zod';
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../../content/openlife');
const read = (name) => JSON.parse(fs.readFileSync(path.join(root, name), 'utf8'));
const exitSchema = z.object({ to: z.string(), label: z.string(), seconds: z.number().int().positive() });
const actionSchema = z.object({
    id: z.string(), label: z.string(), kind: z.string(), activityId: z.string().optional(),
    requiresSkillMin: z.object({ skill: z.string(), level: z.number().int().min(0).max(3) }).optional(),
    requiresSkillMax: z.object({ skill: z.string(), level: z.number().int().min(0).max(3) }).optional(),
    requiresNpcId: z.string().optional()
});
const observationSchema = z.object({
    id: z.string(), skill: z.string(), minLevel: z.number().int().min(0).max(3), text: z.string(),
    action: z.object({ id: z.string(), label: z.string() }).optional()
});
const perceptionGroupSchema = z.object({
    id: z.string(), skill: z.string(), levels: z.array(z.object({ minLevel: z.number().int().min(0).max(3), text: z.string() })).min(1)
});
const resourceSchema = z.object({
    id: z.string(), itemId: z.string(), label: z.string(), quantity: z.number().int().positive().default(1),
    skill: z.string().optional(), minLevel: z.number().int().min(0).max(3).optional(), cooldownWorldDays: z.number().int().positive(), depletedText: z.string()
});
const microSchema = z.object({ id: z.string(), text: z.string(), action: z.object({ id: z.string(), label: z.string() }).optional() });
const locationSchema = z.object({
    id: z.string(), name: z.string(), kind: z.enum(['town', 'wild']), base: z.array(z.string()).min(1),
    ambient: z.object({ morning: z.string(), day: z.string(), evening: z.string(), night: z.string(), rain: z.string().optional() }),
    observations: z.array(observationSchema).optional(), perceptionGroups: z.array(perceptionGroupSchema).optional(), resources: z.array(resourceSchema).optional(),
    exits: z.array(exitSchema), actions: z.array(actionSchema), microScenes: z.array(microSchema).optional()
});
const topicSchema = z.object({
    id: z.string(), label: z.string(), lines: z.array(z.string()).min(1), repeatLines: z.array(z.string()).optional(), cooldownMinutes: z.number().int().positive().optional(),
    requiresKnowledge: z.object({ topic: z.string(), stage: z.string() }).optional(),
    requiresWorldEvent: z.string().optional(),
    requiresSkillMin: z.object({ skill: z.string(), level: z.number().int().min(0).max(3) }).optional(),
    requiresSkillMax: z.object({ skill: z.string(), level: z.number().int().min(0).max(3) }).optional(),
    requiresHealthBelowMax: z.boolean().optional(), requiresAnomalyCount: z.number().int().nonnegative().optional(), requiresItem: z.string().optional()
});
const npcSchema = z.object({ id: z.string(), name: z.string(), locations: z.array(z.string()), primaryLocation: z.string(), description: z.string(), topics: z.array(topicSchema) });
const worldEventSchema = z.object({
    id: z.string(), category: z.enum(['LIFE', 'ANOMALY']), name: z.string(), durationWorldDays: z.number().int().positive(), locations: z.record(z.string(), z.string()), aftermath: z.record(z.string(), z.string()).optional()
});
const activityStageSchema = z.object({
    id: z.string(), name: z.string(), share: z.number().positive(),
    interruptPolicy: z.enum(['SAFE', 'PARTIAL', 'PAUSABLE', 'RISKY']).optional(),
    interruptPreview: z.string().optional()
});
const activitySchema = z.object({
    id: z.string(), kind: z.enum(['WORK', 'PRACTICE', 'TREATMENT', 'REST']), name: z.string(), locationId: z.string(), durationSeconds: z.number().int().positive(), money: z.number().int(),
    skill: z.string().optional(), practice: z.number().int().nonnegative().optional(), heal: z.number().int().nonnegative().optional(), situationId: z.string().optional(),
    interruptPolicy: z.enum(['SAFE', 'PARTIAL', 'PAUSABLE', 'RISKY']).default('PARTIAL'),
    interruptPreview: z.string(), completedText: z.string().optional(), partialText: z.string().optional(),
    pausedItemId: z.string().optional(), pauseExpiresSeconds: z.number().int().positive().optional(),
    stages: z.array(activityStageSchema).min(2).optional()
});
const situationSchema = z.object({
    id: z.string(), activityId: z.string(), title: z.string(), text: z.string(), choices: z.array(z.object({ id: z.string(), label: z.string(), result: z.string().optional() })).min(2)
});
const travelFlavorSkillSchema = z.object({ skill: z.string(), minLevel: z.number().int().min(0).max(3) });
const travelFlavorKnowledgeSchema = z.object({ topic: z.string(), stages: z.array(z.string()).min(1).optional() });
const travelFlavorSchema = z.object({
    id: z.string(),
    type: z.enum(['TIP', 'LOCAL_FACT', 'QUOTE', 'JOKE', 'FOLKLORE', 'MEMORY', 'OBSERVATION']),
    text: z.string().min(1),
    allowedRoutes: z.array(z.string()).optional(),
    locationTags: z.array(z.string()).optional(),
    minDuration: z.number().int().positive().optional(),
    maxDuration: z.number().int().positive().optional(),
    periods: z.array(z.enum(['morning', 'day', 'evening', 'night'])).optional(),
    seasons: z.array(z.string()).optional(),
    weather: z.array(z.string()).optional(),
    requiredSkills: z.array(travelFlavorSkillSchema).optional(),
    requiredKnowledge: z.array(travelFlavorKnowledgeSchema).optional(),
    forbiddenKnowledge: z.array(travelFlavorKnowledgeSchema).optional(),
    requiredFlagsAll: z.array(z.string()).optional(),
    requiredFlagsAny: z.array(z.string()).optional(),
    forbiddenFlags: z.array(z.string()).optional(),
    requiredWorldEvents: z.array(z.string()).optional(),
    weight: z.number().positive().default(1),
    cooldownSeconds: z.number().int().positive().default(1800)
});
const groveSchema = z.object({
    boar: z.object({
        locations: z.array(z.string()), dangerousExits: z.record(z.string(), z.array(z.string())),
        texts: z.object({ tracks: z.string(), sound: z.string(), distant: z.string(), trackingWarning: z.string(), avoidLabel: z.string(), avoidResult: z.string() })
    }),
    silence: z.object({
        locations: z.array(z.string()), texts: z.object({ base: z.string(), tracking1: z.string(), tracking2: z.string(), remembered: z.string() })
    }),
    animalRoutes: z.object({ eventId: z.string(), locations: z.array(z.string()), skill: z.string(), minLevel: z.number().int().min(0).max(3), text: z.string() }),
    whiteback: z.object({
        locations: z.array(z.string()), level1: z.array(z.string()).min(1), level2: z.string(), level3: z.string(), remembered: z.string()
    }),
    recentPlayerTrace: z.string()
});
const locationsArray = z.array(locationSchema).parse(read('locations.json'));
const npcsArray = z.array(npcSchema).parse(read('npcs.json'));
const eventsArray = z.array(worldEventSchema).parse(read('world_events.json'));
const activitiesArray = z.array(activitySchema).parse(read('activities.json'));
const situationsArray = z.array(situationSchema).parse(read('professional_situations.json'));
const travelFlavorArray = z.array(travelFlavorSchema).parse(read('travel_flavor.json'));
const grove = groveSchema.parse(read('grove.json'));
function toMap(rows, label) {
    const m = new Map();
    for (const row of rows) {
        if (m.has(row.id))
            throw new Error(`Duplicate ${label} id ${row.id}`);
        m.set(row.id, row);
    }
    return m;
}
export const openLifeContent = {
    locations: toMap(locationsArray, 'location'),
    npcs: toMap(npcsArray, 'npc'),
    worldEvents: toMap(eventsArray, 'world event'),
    activities: toMap(activitiesArray, 'activity'),
    situations: toMap(situationsArray, 'situation'),
    travelFlavor: toMap(travelFlavorArray, 'travel flavor'),
    grove,
    location(id) { const v = this.locations.get(id); if (!v)
        throw new Error(`Unknown open-life location ${id}`); return v; },
    npc(id) { const v = this.npcs.get(id); if (!v)
        throw new Error(`Unknown npc ${id}`); return v; },
    activity(id) { const v = this.activities.get(id); if (!v)
        throw new Error(`Unknown activity ${id}`); return v; },
    situation(id) { const v = this.situations.get(id); if (!v)
        throw new Error(`Unknown situation ${id}`); return v; }
};
export function validateOpenLifeContent() {
    for (const loc of locationsArray) {
        for (const exit of loc.exits)
            if (!openLifeContent.locations.has(exit.to))
                throw new Error(`Location ${loc.id} points to missing ${exit.to}`);
        for (const action of loc.actions)
            if (action.activityId && !openLifeContent.activities.has(action.activityId))
                throw new Error(`Location ${loc.id} action ${action.id} points to missing activity ${action.activityId}`);
        for (const action of loc.actions)
            if (action.requiresNpcId && !openLifeContent.npcs.has(action.requiresNpcId))
                throw new Error(`Location ${loc.id} action ${action.id} points to missing NPC ${action.requiresNpcId}`);
    }
    for (const npc of npcsArray) {
        for (const locationId of npc.locations)
            if (!openLifeContent.locations.has(locationId))
                throw new Error(`NPC ${npc.id} points to missing location ${locationId}`);
    }
    for (const activity of activitiesArray) {
        if (!openLifeContent.locations.has(activity.locationId))
            throw new Error(`Activity ${activity.id} points to missing location ${activity.locationId}`);
        if (activity.situationId && !openLifeContent.situations.has(activity.situationId))
            throw new Error(`Activity ${activity.id} points to missing situation ${activity.situationId}`);
        if (activity.stages?.length) {
            const share = activity.stages.reduce((sum, stage) => sum + stage.share, 0);
            if (Math.abs(share - 1) > 0.001)
                throw new Error(`Activity ${activity.id} stage shares must sum to 1; got ${share}`);
            const stageIds = new Set();
            for (const stage of activity.stages) {
                if (stageIds.has(stage.id))
                    throw new Error(`Activity ${activity.id} has duplicate stage ${stage.id}`);
                stageIds.add(stage.id);
            }
        }
    }
    for (const situation of situationsArray)
        if (!openLifeContent.activities.has(situation.activityId))
            throw new Error(`Situation ${situation.id} points to missing activity ${situation.activityId}`);
    for (const event of eventsArray) {
        for (const locationId of Object.keys(event.locations))
            if (!openLifeContent.locations.has(locationId))
                throw new Error(`World event ${event.id} points to missing location ${locationId}`);
        for (const locationId of Object.keys(event.aftermath ?? {}))
            if (!openLifeContent.locations.has(locationId))
                throw new Error(`World event ${event.id} aftermath points to missing location ${locationId}`);
    }
    for (const locationId of grove.boar.locations)
        if (!openLifeContent.locations.has(locationId))
            throw new Error(`Grove boar points to missing location ${locationId}`);
    for (const [from, tos] of Object.entries(grove.boar.dangerousExits)) {
        const loc = openLifeContent.locations.get(from);
        if (!loc)
            throw new Error(`Grove dangerous exit points from missing ${from}`);
        for (const to of tos)
            if (!loc.exits.some(e => e.to === to))
                throw new Error(`Grove dangerous exit ${from} -> ${to} is not a location exit`);
    }
    for (const locationId of [...grove.silence.locations, ...grove.animalRoutes.locations, ...grove.whiteback.locations])
        if (!openLifeContent.locations.has(locationId))
            throw new Error(`Grove context points to missing location ${locationId}`);
    for (const flavor of travelFlavorArray) {
        for (const route of flavor.allowedRoutes ?? []) {
            const parts = route.includes('<>') ? route.split('<>') : route.split('>');
            if (parts.length !== 2)
                throw new Error(`Travel flavor ${flavor.id} has invalid route ${route}`);
            for (const locationId of parts)
                if (!openLifeContent.locations.has(locationId))
                    throw new Error(`Travel flavor ${flavor.id} points to missing location ${locationId}`);
        }
        for (const eventId of flavor.requiredWorldEvents ?? [])
            if (!openLifeContent.worldEvents.has(eventId))
                throw new Error(`Travel flavor ${flavor.id} points to missing world event ${eventId}`);
    }
    return { locations: locationsArray.length, npcs: npcsArray.length, events: eventsArray.length, activities: activitiesArray.length, situations: situationsArray.length, travelFlavor: travelFlavorArray.length };
}

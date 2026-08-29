import { openLifeContent, validateOpenLifeContent } from './openLife.js';
import { content } from './loader.js';
const contentVersion = process.env.CONTENT_VERSION ?? 'qinghe-v3.1';
const guided = content.guided(contentVersion);
for (const [slot, def] of Object.entries(guided.slots)) {
    content.event(def.eventId);
    if (def.nextSlot && !guided.slots[def.nextSlot])
        throw new Error(`Slot ${slot} points to missing nextSlot ${def.nextSlot}`);
}
for (const travel of content.travels.values()) {
    const nodeIds = new Set(travel.nodes.map((n) => n.id));
    if (!nodeIds.has(travel.entryNodeId))
        throw new Error(`${travel.id}: missing entry node`);
    for (const node of travel.nodes) {
        for (const choice of node.choices) {
            for (const effect of choice.effects) {
                if (effect.type === 'GO_TO_NODE' && !nodeIds.has(effect.nodeId))
                    throw new Error(`${travel.id}/${node.id}: missing node ${effect.nodeId}`);
                if (effect.type === 'START_COMBAT')
                    content.enemy(effect.enemyId);
            }
        }
    }
}
const open = validateOpenLifeContent();
const itemIds = new Set(content.items.keys());
for (const event of content.events.values()) {
    for (const choice of event.choices) {
        const effectGroups = [choice.effects ?? [], ...Object.values(choice.effectsByOrigin ?? {})];
        for (const effects of effectGroups)
            for (const effect of effects) {
                if ((effect.type === 'ADD_ITEM' || effect.type === 'REMOVE_ITEM' || effect.type === 'EQUIP_ITEM') && !itemIds.has(effect.itemId))
                    throw new Error(`${event.id}/${choice.id}: missing item ${effect.itemId}`);
                if (effect.type === 'EQUIP_ITEM') {
                    const item = content.items.get(effect.itemId);
                    if (!item.instance)
                        throw new Error(`${event.id}/${choice.id}: EQUIP_ITEM ${effect.itemId} is not an item instance`);
                    if (!(item.equipSlots ?? []).includes(effect.slot))
                        throw new Error(`${event.id}/${choice.id}: ${effect.itemId} cannot equip to ${effect.slot}`);
                }
            }
    }
}
for (const travel of content.travels.values())
    for (const node of travel.nodes)
        for (const choice of node.choices)
            for (const effect of choice.effects) {
                if (effect.type === 'ADD_TRAVEL_LOOT' && !itemIds.has(effect.itemId))
                    throw new Error(`${travel.id}/${node.id}: missing loot item ${effect.itemId}`);
            }
for (const enemy of content.enemies.values())
    for (const loot of enemy.loot)
        if (!itemIds.has(loot.itemId))
            throw new Error(`${enemy.id}: missing loot item ${loot.itemId}`);
for (const location of openLifeContent.locations.values())
    for (const resource of location.resources ?? [])
        if (!itemIds.has(resource.itemId))
            throw new Error(`${location.id}/${resource.id}: missing resource item ${resource.itemId}`);
for (const npc of openLifeContent.npcs.values())
    for (const topic of npc.topics)
        if (topic.requiresItem && !itemIds.has(topic.requiresItem))
            throw new Error(`${npc.id}/${topic.id}: missing required item ${topic.requiresItem}`);
for (const activity of openLifeContent.activities.values())
    if (activity.pausedItemId && !itemIds.has(activity.pausedItemId))
        throw new Error(`${activity.id}: missing paused workpiece ${activity.pausedItemId}`);
console.log(`Content OK: ${content.events.size} guided events, ${content.travels.size} travel definitions, ${content.enemies.size} enemies; OPEN_LIFE: ${open.locations} locations, ${open.npcs} NPCs, ${open.events} world events, ${open.activities} activities, ${open.situations} situations, ${open.travelFlavor} travel flavor lines`);

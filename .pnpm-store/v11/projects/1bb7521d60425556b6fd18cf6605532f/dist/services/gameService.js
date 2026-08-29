import crypto from 'node:crypto';
import { inTransaction } from '../db.js';
import { content } from '../content/loader.js';
import { config } from '../config.js';
import { HttpError } from '../utils/http.js';
import { buildOpenLifeScreen, prepareOpenLife } from './openLifeService.js';
import { addItem, removeItem, equipFirstByItemId, ensureBaseEquipment, inventoryViews, equippedItemIds } from './itemService.js';
const ORIGINS = ['blacksmith_family', 'herbalist_family', 'hunter_family', 'merchant_family'];
function pickOrigin() {
    return ORIGINS[crypto.randomInt(0, ORIGINS.length)];
}
function originText(base, byOrigin, origin) {
    return origin && byOrigin?.[origin] !== undefined ? byOrigin[origin] : base;
}
async function getLife(client, playerId, lock = false) {
    const q = `select * from lives where player_id=$1 and alive=true order by life_number desc limit 1${lock ? ' for update' : ''}`;
    const result = await client.query(q, [playerId]);
    if (!result.rows[0])
        throw new HttpError(404, 'life_not_found', 'Active life not found');
    return result.rows[0];
}
async function createActiveEvent(client, life, definitionId, guidedSlot, logGuidedStart = true) {
    content.event(definitionId);
    const result = await client.query(`insert into active_events(life_id,definition_id,content_version,guided_slot) values($1,$2,$3,$4) returning id`, [life.id, definitionId, life.content_version, guidedSlot]);
    const id = result.rows[0].id;
    await client.query(`update lives set active_event_id=$1, mode='EVENT', updated_at=now() where id=$2`, [id, life.id]);
    life.active_event_id = id;
    life.mode = 'EVENT';
    if (guidedSlot && logGuidedStart)
        await analytics(client, life, 'guided_slot_started', { slot: guidedSlot, eventId: definitionId, origin: life.origin_id });
    return id;
}
async function activateGuidedSlot(client, life) {
    const manifest = content.guided(life.content_version);
    const slot = manifest.slots[life.guided_slot];
    if (!slot)
        throw new Error(`Missing guided slot ${life.guided_slot}`);
    await createActiveEvent(client, life, slot.eventId, life.guided_slot);
}
export async function getOrCreatePlayer(telegramUserId, username) {
    return inTransaction(async (client) => {
        const playerResult = await client.query(`insert into players(telegram_user_id,telegram_username) values($1,$2)
       on conflict(telegram_user_id) do update set telegram_username=excluded.telegram_username,last_seen_at=now()
       returning *`, [telegramUserId, username ?? null]);
        const player = playerResult.rows[0];
        const existing = await client.query(`select id from lives where player_id=$1 and alive=true limit 1`, [player.id]);
        if (!existing.rows[0]) {
            const lifeResult = await client.query(`insert into lives(player_id,content_version,guided_slot,mode) values($1,$2,'BIRTH','EVENT') returning *`, [player.id, config.CONTENT_VERSION]);
            const life = lifeResult.rows[0];
            await client.query(`insert into life_locations(life_id,location_id,state,discovered_world_day,first_visited_world_day) values($1,'qinghe','visited',0,0)`, [life.id]);
            await ensureBaseEquipment(client, life);
            await activateGuidedSlot(client, life);
            await client.query(`insert into analytics_events(player_id,life_id,event_name,payload,world_day) values($1,$2,'life_created',$3,0)`, [player.id, life.id, { contentVersion: config.CONTENT_VERSION }]);
        }
        return player;
    });
}
async function getActiveEvent(client, life) {
    if (!life.active_event_id)
        throw new HttpError(409, 'event_missing', 'No active event');
    const result = await client.query(`select * from active_events where id=$1 and life_id=$2`, [life.active_event_id, life.id]);
    if (!result.rows[0])
        throw new HttpError(409, 'event_missing', 'Active event not found');
    return result.rows[0];
}
async function getTravel(client, life, lock = false) {
    if (!life.active_travel_id)
        throw new HttpError(409, 'travel_missing', 'No active travel');
    const result = await client.query(`select * from travel_runs where id=$1 and life_id=$2${lock ? ' for update' : ''}`, [life.active_travel_id, life.id]);
    if (!result.rows[0])
        throw new HttpError(409, 'travel_missing', 'Travel not found');
    const row = result.rows[0];
    row.run_flags ??= {};
    row.visited_nodes ??= [];
    return row;
}
async function getCombat(client, life, lock = false) {
    if (!life.active_combat_id)
        throw new HttpError(409, 'combat_missing', 'No active combat');
    const result = await client.query(`select * from combat_sessions where id=$1 and life_id=$2${lock ? ' for update' : ''}`, [life.active_combat_id, life.id]);
    if (!result.rows[0])
        throw new HttpError(409, 'combat_missing', 'Combat not found');
    const row = result.rows[0];
    row.combat_flags ??= {};
    return row;
}
async function analytics(client, life, eventName, payload = {}) {
    await client.query(`insert into analytics_events(player_id,life_id,event_name,payload,world_day)
     select player_id,id,$2,$3,current_world_day from lives where id=$1`, [life.id, eventName, payload]);
}
async function addBiography(client, life, contentId, choiceId, biography) {
    if (!biography)
        return;
    const text = originText(biography.entry, biography.entryByOrigin, life.origin_id);
    await client.query(`insert into life_log(life_id,world_day,entry_type,content_id,choice_id,text,data) values($1,$2,$3,$4,$5,$6,$7)`, [life.id, life.current_world_day, biography.importance, contentId, choiceId, text, {}]);
}
async function addFlag(client, life, flagId) {
    await client.query(`insert into life_flags(life_id,flag_id,created_world_day) values($1,$2,$3) on conflict do nothing`, [life.id, flagId, life.current_world_day]);
}
async function hasFlag(client, lifeId, flagId) {
    const r = await client.query(`select 1 from life_flags where life_id=$1 and flag_id=$2`, [lifeId, flagId]);
    return Boolean(r.rows[0]);
}
async function getFlags(client, lifeId) {
    const r = await client.query(`select flag_id from life_flags where life_id=$1`, [lifeId]);
    return new Set(r.rows.map((x) => String(x.flag_id)));
}
function requirementsMet(requirements, life, skills, flags, runFlags = {}) {
    if (!requirements)
        return true;
    if (requirements.flagPresent && !flags.has(requirements.flagPresent))
        return false;
    if (requirements.flagAbsent && flags.has(requirements.flagAbsent))
        return false;
    if (requirements.flagsAll && requirements.flagsAll.some((flag) => !flags.has(flag)))
        return false;
    if (requirements.flagsNone && requirements.flagsNone.some((flag) => flags.has(flag)))
        return false;
    if (requirements.originId && life.origin_id !== requirements.originId)
        return false;
    if (requirements.originNot && life.origin_id === requirements.originNot)
        return false;
    if (requirements.skillMin && (skills[requirements.skillMin.skillId] ?? 0) < requirements.skillMin.level)
        return false;
    if (requirements.skillMax && (skills[requirements.skillMax.skillId] ?? 0) > requirements.skillMax.level)
        return false;
    if (requirements.runFlagAbsent && runFlags[requirements.runFlagAbsent] !== undefined)
        return false;
    return true;
}
function appendConditionalBodies(base, additions, life, skills, flags, runFlags = {}) {
    const out = [...base];
    for (const addition of additions ?? []) {
        if (requirementsMet(addition.requirements, life, skills, flags, runFlags))
            out.push(...addition.body);
    }
    return out;
}
async function upsertInventory(client, life, itemId, delta) {
    if (delta > 0)
        await addItem(client, life, itemId, delta);
    else if (delta < 0)
        await removeItem(client, life, itemId, -delta);
}
async function startTravel(client, life, locationId) {
    const def = content.travel(locationId);
    const result = await client.query(`insert into travel_runs(life_id,location_definition_id,content_version,current_node_id,started_world_day,health_start,health_current,visited_nodes)
     values($1,$2,$3,$4,$5,$6,$6,$7) returning id`, [life.id, def.id, life.content_version, def.entryNodeId, life.current_world_day, life.health, JSON.stringify([def.entryNodeId])]);
    const travelId = result.rows[0].id;
    await client.query(`update lives set mode='TRAVEL',active_travel_id=$1,active_combat_id=null,current_location_id=$2,updated_at=now() where id=$3`, [travelId, locationId, life.id]);
    await client.query(`insert into life_locations(life_id,location_id,state,discovered_world_day,first_visited_world_day) values($1,$2,'visited',$3,$3)
     on conflict(life_id,location_id) do update set state='visited',first_visited_world_day=coalesce(life_locations.first_visited_world_day,excluded.first_visited_world_day)`, [life.id, locationId, life.current_world_day]);
    life.mode = 'TRAVEL';
    life.active_travel_id = travelId;
    life.current_location_id = locationId;
    await analytics(client, life, 'travel_started', { locationId, origin: life.origin_id });
}
async function startCombat(client, life, travel, enemyId) {
    const enemy = content.enemy(enemyId);
    const combatFlags = {
        lastActionText: 'Кабан прижимает уши и переносит вес на передние ноги. Он бросится после вашего следующего действия.'
    };
    const result = await client.query(`insert into combat_sessions(life_id,travel_id,enemy_definition_id,content_version,player_hp,enemy_hp,enemy_state,enemy_intent,combat_flags)
     values($1,$2,$3,$4,$5,$6,$7,$8,$9) returning id`, [life.id, travel.id, enemy.id, life.content_version, travel.health_current, enemy.maxHp, enemy.initialState, enemy.initialIntent, combatFlags]);
    const combatId = result.rows[0].id;
    await client.query(`update lives set mode='COMBAT',active_combat_id=$1,updated_at=now() where id=$2`, [combatId, life.id]);
    life.mode = 'COMBAT';
    life.active_combat_id = combatId;
    await analytics(client, life, 'combat_started', { enemyId, health: travel.health_current, node: travel.current_node_id });
}
async function applyGameEffect(client, life, effect) {
    switch (effect.type) {
        case 'SET_ORIGIN': {
            const origin = effect.originId === 'RANDOM' ? pickOrigin() : effect.originId;
            await client.query(`update lives set origin_id=$1 where id=$2`, [origin, life.id]);
            life.origin_id = origin;
            await addFlag(client, life, `origin_${origin.replace('_family', '')}`);
            return;
        }
        case 'ADD_FLAG':
            await addFlag(client, life, effect.flagId);
            return;
        case 'SET_KNOWLEDGE':
            await client.query(`insert into life_knowledge(life_id,topic_id,stage,updated_world_day) values($1,$2,$3,$4)
         on conflict(life_id,topic_id) do update set stage=excluded.stage,updated_world_day=excluded.updated_world_day`, [life.id, effect.topicId, effect.stage, life.current_world_day]);
            return;
        case 'SET_RUMOR':
            await client.query(`insert into life_rumors(life_id,rumor_id,state,source_npc_id,heard_world_day,updated_world_day) values($1,$2,$3,$4,$5,$5)
         on conflict(life_id,rumor_id) do update set state=excluded.state,source_npc_id=coalesce(life_rumors.source_npc_id,excluded.source_npc_id),updated_world_day=excluded.updated_world_day`, [life.id, effect.rumorId, effect.state, effect.sourceNpcId ?? null, life.current_world_day]);
            return;
        case 'CHANGE_MONEY': {
            const next = life.money + effect.amount;
            if (next < 0)
                throw new HttpError(409, 'not_enough_money', 'Not enough money');
            await client.query(`update lives set money=$1 where id=$2`, [next, life.id]);
            life.money = next;
            return;
        }
        case 'CHANGE_HEALTH': {
            const next = Math.max(0, Math.min(life.max_health, life.health + effect.amount));
            await client.query(`update lives set health=$1 where id=$2`, [next, life.id]);
            life.health = next;
            return;
        }
        case 'CHANGE_SKILL':
            await client.query(`insert into life_skills(life_id,skill_id,level) values($1,$2,$3)
         on conflict(life_id,skill_id) do update set level=greatest(0,least(3,life_skills.level+$3))`, [life.id, effect.skillId, Math.max(0, effect.amount)]);
            return;
        case 'CHANGE_RELATIONSHIP':
            await client.query(`insert into life_relationships(life_id,npc_id,status,familiarity,updated_world_day) values($1,$2,$3,$4,$5)
         on conflict(life_id,npc_id) do update set status=coalesce(excluded.status,life_relationships.status),familiarity=life_relationships.familiarity+excluded.familiarity,updated_world_day=excluded.updated_world_day`, [life.id, effect.npcId, effect.status ?? null, effect.familiarity ?? 0, life.current_world_day]);
            return;
        case 'ADD_ITEM':
            await addItem(client, life, effect.itemId, effect.quantity, effect.originNote ? { note: effect.originNote } : {});
            return;
        case 'REMOVE_ITEM':
            await upsertInventory(client, life, effect.itemId, -effect.quantity);
            return;
        case 'EQUIP_ITEM':
            await equipFirstByItemId(client, life, effect.itemId, effect.slot);
            return;
        case 'ADVANCE_TIME':
            life.current_world_day += effect.days;
            await client.query(`update lives set current_world_day=$1 where id=$2`, [life.current_world_day, life.id]);
            return;
        case 'SET_LOCATION':
            life.current_location_id = effect.locationId;
            await client.query(`update lives set current_location_id=$1 where id=$2`, [effect.locationId, life.id]);
            return;
        case 'DISCOVER_LOCATION':
            await client.query(`insert into life_locations(life_id,location_id,state,discovered_world_day,first_visited_world_day) values($1,$2,$3,$4,$5)
         on conflict(life_id,location_id) do update set state=case when life_locations.state='visited' then 'visited' else excluded.state end`, [life.id, effect.locationId, effect.state ?? 'known', life.current_world_day, effect.state === 'visited' ? life.current_world_day : null]);
            return;
        case 'SET_STATE':
            await client.query(`insert into life_state(life_id,scope,target_id,state_key,value,updated_world_day) values($1,$2,$3,$4,$5,$6)
         on conflict(life_id,scope,target_id,state_key) do update set value=excluded.value,updated_world_day=excluded.updated_world_day`, [life.id, effect.scope, effect.targetId, effect.key, effect.value, life.current_world_day]);
            return;
        case 'START_EVENT':
            await createActiveEvent(client, life, effect.eventId, effect.carryGuidedSlot ? life.guided_slot : null, !effect.carryGuidedSlot);
            return;
        case 'START_TRAVEL':
            await startTravel(client, life, effect.locationId);
            return;
        case 'START_COMBAT': {
            const travel = await getTravel(client, life, true);
            await startCombat(client, life, travel, effect.enemyId);
            return;
        }
    }
}
function choiceEffects(choice, origin) {
    return [...(choice.effects ?? []), ...(origin ? choice.effectsByOrigin?.[origin] ?? [] : [])];
}
async function advanceGuidedAfterEvent(client, life, active, def) {
    if (!active.guided_slot || def.completeGuidedSlot === false)
        return;
    const manifest = content.guided(life.content_version);
    const slot = manifest.slots[active.guided_slot];
    if (slot.opensLife) {
        life.phase = 'OPEN_LIFE';
        life.mode = 'FREE';
        life.active_event_id = null;
        await client.query(`update lives set phase='OPEN_LIFE',mode='FREE',active_event_id=null,updated_at=now() where id=$1`, [life.id]);
        await analytics(client, life, 'guided_open_life_reached', { origin: life.origin_id });
        return;
    }
    if (!slot.nextSlot)
        return;
    life.guided_slot = slot.nextSlot;
    await client.query(`update lives set guided_slot=$1 where id=$2`, [slot.nextSlot, life.id]);
    if (life.mode === 'EVENT')
        await activateGuidedSlot(client, life);
}
async function fetchProcessed(client, actionId, playerId) {
    const r = await client.query(`select result from processed_actions where client_action_id=$1 and player_id=$2`, [actionId, playerId]);
    return r.rows[0]?.result ?? null;
}
async function storeProcessed(client, actionId, life, actionType, result) {
    await client.query(`insert into processed_actions(client_action_id,player_id,life_id,action_type,result)
     select $1,player_id,id,$2,$3 from lives where id=$4`, [actionId, actionType, result, life.id]);
}
async function bumpVersion(client, life) {
    life.state_version += 1;
    await client.query(`update lives set state_version=$1,updated_at=now() where id=$2`, [life.state_version, life.id]);
}
function assertVersion(life, expected) {
    if (life.state_version !== expected)
        throw new HttpError(409, 'stale_game_state', 'Game state changed', { currentStateVersion: life.state_version });
}
export async function chooseEvent(playerId, choiceId, actionId, expectedVersion) {
    return inTransaction(async (client) => {
        const duplicate = await fetchProcessed(client, actionId, playerId);
        if (duplicate)
            return duplicate;
        const life = await getLife(client, playerId, true);
        assertVersion(life, expectedVersion);
        if (life.mode !== 'EVENT')
            throw new HttpError(409, 'wrong_mode', `Expected EVENT, got ${life.mode}`);
        const active = await getActiveEvent(client, life);
        const def = content.event(active.definition_id);
        const skills = await getSkills(client, life.id);
        const flags = await getFlags(client, life.id);
        const choice = def.choices.find((x) => x.id === choiceId && requirementsMet(x.requirements, life, skills, flags));
        if (!choice)
            throw new HttpError(400, 'choice_unavailable', 'Choice is not available');
        await analytics(client, life, 'choice_selected', { eventId: def.id, choiceId, slot: active.guided_slot, origin: life.origin_id });
        for (const effect of choiceEffects(choice, life.origin_id))
            await applyGameEffect(client, life, effect);
        await addBiography(client, life, def.id, choice.id, def.biography);
        await addBiography(client, life, def.id, choice.id, choice.biography);
        await client.query(`update active_events set status='completed',updated_at=now() where id=$1`, [active.id]);
        if (active.guided_slot)
            await analytics(client, life, 'guided_slot_completed', { slot: active.guided_slot, eventId: def.id, choiceId, origin: life.origin_id });
        if (life.active_event_id === active.id) {
            life.active_event_id = null;
            await client.query(`update lives set active_event_id=null where id=$1`, [life.id]);
        }
        await advanceGuidedAfterEvent(client, life, active, def);
        await bumpVersion(client, life);
        const result = await buildView(client, life);
        await storeProcessed(client, actionId, life, 'event_choice', result);
        return result;
    });
}
async function getSkills(client, lifeId) {
    const r = await client.query(`select skill_id,level from life_skills where life_id=$1`, [lifeId]);
    return Object.fromEntries(r.rows.map((x) => [x.skill_id, Number(x.level)]));
}
function travelChoiceAvailable(choice, life, travel, skills, flags) {
    return requirementsMet(choice.requirements, life, skills, flags, travel.run_flags ?? {});
}
async function addTravelLoot(client, travelId, itemId, quantity) {
    await client.query(`insert into travel_loot(travel_id,item_id,quantity) values($1,$2,$3)
     on conflict(travel_id,item_id) do update set quantity=travel_loot.quantity+excluded.quantity`, [travelId, itemId, quantity]);
}
async function applyTravelEffect(client, life, travel, effect) {
    switch (effect.type) {
        case 'GO_TO_NODE': {
            travel.current_node_id = effect.nodeId;
            const visited = Array.isArray(travel.visited_nodes) ? travel.visited_nodes : [];
            if (!visited.includes(effect.nodeId))
                visited.push(effect.nodeId);
            travel.visited_nodes = visited;
            await client.query(`update travel_runs set current_node_id=$1,visited_nodes=$2,updated_at=now() where id=$3`, [effect.nodeId, JSON.stringify(visited), travel.id]);
            return 'CONTINUE';
        }
        case 'ADD_RUN_FLAG':
            travel.run_flags = { ...(travel.run_flags ?? {}), [effect.key]: effect.value };
            await client.query(`update travel_runs set run_flags=$1,updated_at=now() where id=$2`, [travel.run_flags, travel.id]);
            return 'CONTINUE';
        case 'ADD_TRAVEL_LOOT':
            await addTravelLoot(client, travel.id, effect.itemId, effect.quantity);
            return 'CONTINUE';
        case 'CHANGE_TRAVEL_HEALTH':
            travel.health_current = Math.max(0, Math.min(life.max_health, travel.health_current + effect.amount));
            await client.query(`update travel_runs set health_current=$1,updated_at=now() where id=$2`, [travel.health_current, travel.id]);
            return 'CONTINUE';
        case 'START_COMBAT':
            await startCombat(client, life, travel, effect.enemyId);
            return 'CONTINUE';
        case 'RETURN_HOME':
            await finishTravel(client, life, travel, effect.reason ?? 'player_return');
            return 'RETURN';
        case 'ADD_FLAG':
            await addFlag(client, life, effect.flagId);
            if (effect.flagId === 'saw_white_back')
                await analytics(client, life, 'whiteback_seen', { health: travel.health_current, node: travel.current_node_id, origin: life.origin_id });
            if (effect.flagId === 'went_deeper')
                await analytics(client, life, 'continue_deeper_selected', { health: travel.health_current, node: travel.current_node_id, origin: life.origin_id });
            return 'CONTINUE';
        case 'SET_KNOWLEDGE':
            await applyGameEffect(client, life, effect);
            return 'CONTINUE';
        case 'SET_RUMOR':
            await applyGameEffect(client, life, effect);
            return 'CONTINUE';
    }
}
async function transferTravelLoot(client, life, travel) {
    const loot = await client.query(`select item_id,quantity from travel_loot where travel_id=$1`, [travel.id]);
    for (const row of loot.rows)
        await upsertInventory(client, life, row.item_id, Number(row.quantity));
}
async function finishTravel(client, life, travel, reason, wounded = false) {
    await transferTravelLoot(client, life, travel);
    if (travel.location_definition_id === 'bamboo_grove')
        await addFlag(client, life, 'grove_first_visit');
    life.health = Math.max(wounded ? 10 : 1, travel.health_current);
    life.current_location_id = 'qinghe';
    life.active_travel_id = null;
    life.active_combat_id = null;
    life.mode = 'EVENT';
    await client.query(`update travel_runs set status='completed',updated_at=now() where id=$1`, [travel.id]);
    await client.query(`update lives set health=$1,current_location_id='qinghe',active_travel_id=null,active_combat_id=null,mode='EVENT',updated_at=now() where id=$2`, [life.health, life.id]);
    const sawWhiteback = await hasFlag(client, life.id, 'saw_white_back');
    if (sawWhiteback) {
        life.guided_slot = 'FIRST_RETURN';
        await client.query(`update lives set guided_slot='FIRST_RETURN' where id=$1`, [life.id]);
        const manifest = content.guided(life.content_version);
        await createActiveEvent(client, life, manifest.slots.FIRST_RETURN.eventId, 'FIRST_RETURN');
    }
    else {
        await createActiveEvent(client, life, wounded ? 'qinghe_return_wounded_01' : 'qinghe_return_early_01', null);
    }
    await analytics(client, life, 'travel_returned', { reason, wounded, sawWhiteback, health: life.health });
    if (!sawWhiteback)
        await analytics(client, life, 'guided_home_pause_entered', { reason, wounded, health: life.health, origin: life.origin_id });
}
export async function chooseTravel(playerId, choiceId, actionId, expectedVersion) {
    return inTransaction(async (client) => {
        const duplicate = await fetchProcessed(client, actionId, playerId);
        if (duplicate)
            return duplicate;
        const life = await getLife(client, playerId, true);
        assertVersion(life, expectedVersion);
        if (life.mode !== 'TRAVEL')
            throw new HttpError(409, 'wrong_mode', `Expected TRAVEL, got ${life.mode}`);
        const travel = await getTravel(client, life, true);
        const def = content.travel(travel.location_definition_id);
        const node = def.nodes.find((x) => x.id === travel.current_node_id);
        if (!node)
            throw new Error(`Missing node ${travel.current_node_id}`);
        const skills = await getSkills(client, life.id);
        const flags = await getFlags(client, life.id);
        const choice = node.choices.find((x) => x.id === choiceId && travelChoiceAvailable(x, life, travel, skills, flags));
        if (!choice)
            throw new HttpError(400, 'choice_unavailable', 'Travel choice is not available');
        await analytics(client, life, 'travel_choice_selected', { node: node.id, choiceId, health: travel.health_current, origin: life.origin_id });
        for (const effect of choice.effects) {
            const result = await applyTravelEffect(client, life, travel, effect);
            if (result === 'RETURN')
                break;
        }
        await addBiography(client, life, `${def.id}:${node.id}`, choice.id, choice.biography);
        await bumpVersion(client, life);
        const result = await buildView(client, life);
        await storeProcessed(client, actionId, life, 'travel_choice', result);
        return result;
    });
}
async function combatEndToTravel(client, life, travel, combat, status, nodeId) {
    combat.status = status;
    travel.health_current = Math.max(0, combat.player_hp);
    travel.current_node_id = nodeId;
    await client.query(`update combat_sessions set status=$1,player_hp=$2,enemy_hp=$3,enemy_state=$4,enemy_intent=$5,combat_flags=$6,updated_at=now() where id=$7`, [status, combat.player_hp, combat.enemy_hp, combat.enemy_state, combat.enemy_intent, combat.combat_flags ?? {}, combat.id]);
    const visited = Array.isArray(travel.visited_nodes) ? travel.visited_nodes : [];
    if (!visited.includes(nodeId))
        visited.push(nodeId);
    travel.visited_nodes = visited;
    await client.query(`update travel_runs set health_current=$1,current_node_id=$2,visited_nodes=$3,updated_at=now() where id=$4`, [travel.health_current, nodeId, JSON.stringify(visited), travel.id]);
    life.mode = 'TRAVEL';
    life.active_combat_id = null;
    await client.query(`update lives set mode='TRAVEL',active_combat_id=null where id=$1`, [life.id]);
}
async function combatEndToOpenLife(client, life, combat, status) {
    combat.status = status;
    life.health = Math.max(1, combat.player_hp);
    life.mode = 'FREE';
    life.active_combat_id = null;
    await client.query(`update combat_sessions set status=$1,player_hp=$2,enemy_hp=$3,enemy_state=$4,enemy_intent=$5,combat_flags=$6,updated_at=now() where id=$7`, [status, combat.player_hp, combat.enemy_hp, combat.enemy_state, combat.enemy_intent, combat.combat_flags ?? {}, combat.id]);
    await client.query(`update lives set health=$1,mode='FREE',active_combat_id=null,updated_at=now() where id=$2`, [life.health, life.id]);
}
function intentLabel(intent) {
    return { prepare_charge: 'Готовится к броску', charge: 'Готовится к броску', recover: 'Пытается подняться после неудачного броска' }[intent] ?? intent;
}
export async function combatAction(playerId, action, actionId, expectedVersion) {
    return inTransaction(async (client) => {
        const duplicate = await fetchProcessed(client, actionId, playerId);
        if (duplicate)
            return duplicate;
        const life = await getLife(client, playerId, true);
        assertVersion(life, expectedVersion);
        if (life.mode !== 'COMBAT')
            throw new HttpError(409, 'wrong_mode', `Expected COMBAT, got ${life.mode}`);
        const combat = await getCombat(client, life, true);
        const openLifeCombat = life.phase === 'OPEN_LIFE' && !combat.travel_id;
        const travel = openLifeCombat ? null : await getTravel(client, life, true);
        const enemy = content.enemy(combat.enemy_definition_id);
        const skills = await getSkills(client, life.id);
        const inventoryRows = await client.query(`select item_id,quantity from life_inventory where life_id=$1 and quantity>0`, [life.id]);
        const inventory = new Map(inventoryRows.rows.map((row) => [String(row.item_id), Number(row.quantity)]));
        const equipped = await equippedItemIds(client, life.id);
        const allowed = new Set(['ATTACK', 'DEFEND', 'DRIVE_OFF', 'RETREAT', 'USE_SALVE', 'AIM_LEG']);
        if (!allowed.has(action))
            throw new HttpError(400, 'invalid_combat_action', 'Unknown combat action');
        if (action === 'DRIVE_OFF' && combat.enemy_state !== 'off_balance')
            throw new HttpError(400, 'action_unavailable', 'Enemy is not vulnerable to drive off');
        if (action === 'AIM_LEG' && ((skills.tracking ?? 0) < 1 || equipped.get('main_hand') !== 'short_bow' || Boolean(combat.combat_flags?.aimedLegUsed)))
            throw new HttpError(400, 'action_unavailable', 'Action unavailable');
        if (action === 'USE_SALVE' && ((skills.herbalism ?? 0) < 1 || (inventory.get('healing_salve') ?? 0) < 1))
            throw new HttpError(400, 'action_unavailable', 'Healing salve unavailable');
        await analytics(client, life, 'combat_action_selected', { action, turn: combat.turn_no, playerHp: combat.player_hp, enemyHp: combat.enemy_hp, intent: combat.enemy_intent, context: openLifeCombat ? 'open_life' : 'guided_travel' });
        const narration = [];
        const setNarration = (...parts) => { narration.push(...parts.filter(Boolean)); combat.combat_flags = { ...(combat.combat_flags ?? {}), lastActionText: narration.join(' ') }; };
        const finish = async (status, travelNode, outcome) => {
            if (openLifeCombat)
                await combatEndToOpenLife(client, life, combat, status);
            else
                await combatEndToTravel(client, life, travel, combat, status, travelNode);
            await analytics(client, life, openLifeCombat ? 'open_combat_ended' : 'combat_ended', { outcome, health: combat.player_hp, locationId: life.current_location_id });
        };
        if (action === 'RETREAT') {
            setNarration('Вы не ждёте следующего броска и разрываете дистанцию. Кабан не преследует вас далеко.');
            if (!openLifeCombat)
                await addFlag(client, life, 'grove_boar_retreat');
            await finish('player_retreat', 'after_combat_retreat', 'player_retreat');
        }
        else if (action === 'DRIVE_OFF') {
            setNarration('Пока кабан пытается вернуть равновесие, вы резко идёте вперёд. Зверь отступает, разворачивается и исчезает между бамбуком.');
            if (!openLifeCombat) {
                await addFlag(client, life, 'drove_off_boar');
                await addFlag(client, life, 'grove_boar_driven_off');
            }
            await finish('enemy_fled', 'after_boar', 'enemy_fled');
        }
        else {
            const defended = action === 'DEFEND';
            const aimedShot = action === 'AIM_LEG';
            if (action === 'ATTACK') {
                const damage = combat.enemy_state === 'off_balance' ? 10 : 7;
                combat.enemy_hp -= damage;
                narration.push(combat.enemy_state === 'off_balance'
                    ? 'Вы пользуетесь моментом и бьёте, пока кабан не успел подняться.'
                    : 'Вы встречаете зверя ударом. Кабан взвизгивает, но не отступает.');
            }
            if (action === 'DEFEND')
                narration.push('Вы не рискуете и принимаете устойчивую стойку, готовясь к рывку.');
            if (aimedShot) {
                combat.enemy_hp -= 6;
                combat.enemy_state = 'off_balance';
                combat.enemy_intent = 'recover';
                combat.combat_flags = { ...(combat.combat_flags ?? {}), aimedLegUsed: true };
                narration.push('Вы целитесь не в корпус, а в переднюю ногу. Стрела заставляет кабана сорвать шаг и уйти вбок.');
            }
            if (action === 'USE_SALVE') {
                await upsertInventory(client, life, 'healing_salve', -1);
                combat.player_hp = Math.min(life.max_health, combat.player_hp + 22);
                narration.push('Вы быстро стягиваете ткань и наносите мазь туда, где боль сильнее всего. Руки работают привычнее, чем мысли.');
            }
            if (combat.enemy_hp <= 0) {
                combat.enemy_hp = 0;
                for (const item of enemy.loot) {
                    if (openLifeCombat)
                        await upsertInventory(client, life, item.itemId, item.quantity);
                    else
                        await addTravelLoot(client, travel.id, item.itemId, item.quantity);
                }
                if (!openLifeCombat) {
                    await addFlag(client, life, 'fought_boar');
                    await addFlag(client, life, 'grove_boar_defeated');
                }
                narration.push('Кабан ещё пытается удержаться на ногах, но вскоре тяжело валится на землю.');
                setNarration();
                await finish('enemy_defeated', 'after_boar', 'enemy_defeated');
            }
            else if (aimedShot) {
                narration.push('Зверю требуется мгновение, чтобы снова поставить ногу правильно.');
                setNarration();
                combat.turn_no += 1;
                if (travel)
                    travel.health_current = Math.max(0, combat.player_hp);
                await client.query(`update combat_sessions set turn_no=$1,player_hp=$2,enemy_hp=$3,enemy_state=$4,enemy_intent=$5,combat_flags=$6,updated_at=now() where id=$7`, [combat.turn_no, combat.player_hp, combat.enemy_hp, combat.enemy_state, combat.enemy_intent, combat.combat_flags, combat.id]);
                if (travel)
                    await client.query(`update travel_runs set health_current=$1,updated_at=now() where id=$2`, [travel.health_current, travel.id]);
                else {
                    life.health = Math.max(1, combat.player_hp);
                    await client.query(`update lives set health=$1,updated_at=now() where id=$2`, [life.health, life.id]);
                }
            }
            else {
                if (combat.enemy_intent === 'charge' || combat.enemy_intent === 'prepare_charge') {
                    const damage = defended ? enemy.defendedChargeDamage : enemy.chargeDamage;
                    combat.player_hp -= damage;
                    combat.enemy_state = 'off_balance';
                    combat.enemy_intent = 'recover';
                    if (defended)
                        narration.push('Кабан срывается с места. Вы принимаете удар на стойку и удерживаетесь, пока зверь пролетает мимо.');
                    else
                        narration.push('Кабан срывается с места. Вы не успеваете полностью уйти с линии броска, и удар сбивает дыхание.');
                }
                else if (combat.enemy_intent === 'recover') {
                    combat.enemy_state = 'ready';
                    combat.enemy_intent = 'charge';
                    narration.push('Кабан отступает на пару шагов, снова разворачивается к вам и опускает голову.');
                }
                else {
                    combat.enemy_state = 'ready';
                    combat.enemy_intent = 'charge';
                }
                combat.turn_no += 1;
                if (travel)
                    travel.health_current = Math.max(0, combat.player_hp);
                setNarration();
                await client.query(`update combat_sessions set turn_no=$1,player_hp=$2,enemy_hp=$3,enemy_state=$4,enemy_intent=$5,combat_flags=$6,updated_at=now() where id=$7`, [combat.turn_no, combat.player_hp, combat.enemy_hp, combat.enemy_state, combat.enemy_intent, combat.combat_flags, combat.id]);
                if (travel)
                    await client.query(`update travel_runs set health_current=$1,updated_at=now() where id=$2`, [travel.health_current, travel.id]);
                else {
                    life.health = Math.max(0, combat.player_hp);
                    await client.query(`update lives set health=$1,updated_at=now() where id=$2`, [Math.max(0, combat.player_hp), life.id]);
                }
                if (combat.player_hp <= 0) {
                    combat.player_hp = 10;
                    combat.combat_flags = { ...(combat.combat_flags ?? {}), lastActionText: narration.join(' ') + ' Вы отползаете с тропы прежде, чем зверь успевает развернуться снова.' };
                    if (travel) {
                        travel.health_current = 10;
                        await client.query(`update combat_sessions set status='player_defeated',player_hp=10,combat_flags=$2,updated_at=now() where id=$1`, [combat.id, combat.combat_flags]);
                        await addFlag(client, life, 'grove_boar_overpowered_player');
                        await analytics(client, life, 'combat_ended', { outcome: 'player_defeated' });
                        await finishTravel(client, life, travel, 'combat_defeat', true);
                    }
                    else {
                        life.health = 10;
                        await client.query(`update combat_sessions set player_hp=10,combat_flags=$2,updated_at=now() where id=$1`, [combat.id, combat.combat_flags]);
                        await combatEndToOpenLife(client, life, combat, 'player_defeated');
                        await analytics(client, life, 'open_combat_ended', { outcome: 'player_defeated', health: 10, locationId: life.current_location_id });
                    }
                }
            }
        }
        await bumpVersion(client, life);
        const result = await buildView(client, life);
        await storeProcessed(client, actionId, life, 'combat_action', result);
        return result;
    });
}
async function inventoryView(client, lifeId) {
    return (await inventoryViews(client, lifeId)).inventory;
}
async function lootView(client, travelId) {
    const r = await client.query(`select item_id,quantity from travel_loot where travel_id=$1 and quantity>0 order by item_id`, [travelId]);
    return r.rows.map((row) => { const item = content.items.get(row.item_id); return { id: row.item_id, name: item?.name ?? row.item_id, description: item?.description, quantity: Number(row.quantity) }; });
}
async function journalView(client, lifeId) {
    const [rumors, knowledge, biography] = await Promise.all([
        client.query(`select rumor_id,state,source_npc_id,heard_world_day,updated_world_day from life_rumors where life_id=$1 order by updated_world_day desc`, [lifeId]),
        client.query(`select topic_id,stage,updated_world_day from life_knowledge where life_id=$1 order by updated_world_day desc`, [lifeId]),
        client.query(`select world_day,entry_type,content_id,text from life_log where life_id=$1 order by world_day,created_at`, [lifeId])
    ]);
    return { rumors: rumors.rows, knowledge: knowledge.rows, biography: biography.rows };
}
async function buildEventScreen(client, life) {
    const active = await getActiveEvent(client, life);
    const def = content.event(active.definition_id);
    const origin = life.origin_id;
    const [skills, flags] = await Promise.all([getSkills(client, life.id), getFlags(client, life.id)]);
    const baseBody = originText(def.body, def.bodyByOrigin, origin);
    return {
        type: 'EVENT',
        eventId: def.id,
        title: originText(def.title ?? '', def.titleByOrigin, origin),
        visualTheme: originText(def.visualTheme ?? 'home', def.visualThemeByOrigin, origin),
        body: appendConditionalBodies(baseBody, def.bodyAdditions, life, skills, flags),
        choices: def.choices
            .filter((choice) => requirementsMet(choice.requirements, life, skills, flags))
            .map((choice) => ({ id: choice.id, label: originText(choice.label, choice.labelByOrigin, origin) }))
    };
}
async function buildTravelScreen(client, life) {
    const travel = await getTravel(client, life);
    const def = content.travel(travel.location_definition_id);
    const node = def.nodes.find((x) => x.id === travel.current_node_id);
    if (!node)
        throw new Error(`Missing node ${travel.current_node_id}`);
    const [skills, flags] = await Promise.all([getSkills(client, life.id), getFlags(client, life.id)]);
    const baseBody = originText(node.body, node.bodyByOrigin, life.origin_id);
    return {
        type: 'TRAVEL', travelId: travel.id, title: def.title, nodeId: node.id, nodeTitle: node.title,
        body: appendConditionalBodies(baseBody, node.bodyAdditions, life, skills, flags, travel.run_flags ?? {}),
        health: travel.health_current, maxHealth: life.max_health,
        loot: await lootView(client, travel.id),
        choices: node.choices
            .filter((x) => travelChoiceAvailable(x, life, travel, skills, flags))
            .map((choice) => ({ id: choice.id, label: originText(choice.label, choice.labelByOrigin, life.origin_id) }))
    };
}
async function buildCombatScreen(client, life) {
    const combat = await getCombat(client, life);
    const enemy = content.enemy(combat.enemy_definition_id);
    const skills = await getSkills(client, life.id);
    const invRows = await client.query(`select item_id,quantity from life_inventory where life_id=$1 and quantity>0`, [life.id]);
    const inv = new Map(invRows.rows.map((row) => [String(row.item_id), Number(row.quantity)]));
    const equipped = await equippedItemIds(client, life.id);
    const actions = [
        { id: 'ATTACK', label: 'Атаковать' },
        { id: 'DEFEND', label: 'Защищаться' },
        { id: 'RETREAT', label: 'Отступить' }
    ];
    if (combat.enemy_state === 'off_balance')
        actions.splice(2, 0, { id: 'DRIVE_OFF', label: 'Спугнуть, пока он уязвим', kind: 'special' });
    if ((skills.tracking ?? 0) >= 1 && equipped.get('main_hand') === 'short_bow' && !Boolean(combat.combat_flags?.aimedLegUsed))
        actions.splice(1, 0, { id: 'AIM_LEG', label: 'Выстрелить по передней ноге', kind: 'special' });
    if ((skills.herbalism ?? 0) >= 1 && (inv.get('healing_salve') ?? 0) > 0)
        actions.splice(actions.length - 1, 0, { id: 'USE_SALVE', label: 'Быстро обработать рану', kind: 'special' });
    return {
        type: 'COMBAT', combatId: combat.id,
        player: { hp: combat.player_hp, maxHp: life.max_health },
        enemy: { id: enemy.id, name: enemy.name, hp: combat.enemy_hp, maxHp: enemy.maxHp, state: combat.enemy_state, intent: intentLabel(combat.enemy_intent) },
        turn: combat.turn_no,
        narration: String(combat.combat_flags?.lastActionText ?? ''),
        actions
    };
}
async function conditionView(client, lifeId) {
    const [states, health] = await Promise.all([
        client.query(`select state_key,value from life_state where life_id=$1 and scope='PERSONAL' and target_id='conditions'`, [lifeId]),
        client.query(`select health,max_health from lives where id=$1`, [lifeId])
    ]);
    const out = states.rows.filter((row) => row.value?.active !== false).map((row) => String(row.state_key));
    if (health.rows[0] && Number(health.rows[0].health) < Number(health.rows[0].max_health) && !out.includes('wounded'))
        out.push('wounded');
    return out;
}
async function noticeRows(client, lifeId, unreadOnly, limit) {
    const r = await client.query(`select id,notice_kind,title,message,details,world_day,created_at from open_life_notices where life_id=$1 and notice_kind<>'world' ${unreadOnly ? 'and read_at is null' : ''} order by id ${unreadOnly ? 'asc' : 'desc'} limit $2`, [lifeId, limit]);
    return r.rows.map((row) => ({
        id: Number(row.id), kind: String(row.notice_kind), title: String(row.title || 'Цинхэ'), message: String(row.message),
        details: (row.details && typeof row.details === 'object') ? row.details : {}, worldDay: row.world_day == null ? null : Number(row.world_day), createdAt: new Date(row.created_at).toISOString()
    }));
}
async function unreadNoticeView(client, lifeId) { return noticeRows(client, lifeId, true, 8); }
async function recentNoticeView(client, lifeId) { return noticeRows(client, lifeId, false, 10); }
export async function buildView(client, life) {
    // refresh mutable columns after side effects
    const fresh = await client.query(`select * from lives where id=$1`, [life.id]);
    const current = fresh.rows[0];
    Object.assign(life, current);
    await ensureBaseEquipment(client, life);
    let screen;
    if (life.mode === 'EVENT')
        screen = await buildEventScreen(client, life);
    else if (life.mode === 'TRAVEL')
        screen = await buildTravelScreen(client, life);
    else if (life.mode === 'COMBAT')
        screen = await buildCombatScreen(client, life);
    else {
        await prepareOpenLife(client, life);
        screen = await buildOpenLifeScreen(client, life);
    }
    const ageDays = life.current_world_day - life.birth_world_day;
    const itemState = await inventoryViews(client, life.id);
    return {
        life: { id: life.id, phase: life.phase, mode: life.mode, originId: life.origin_id, ageYears: Math.floor(ageDays / 365), ageDays, worldDay: life.current_world_day, birthWorldDay: life.birth_world_day, health: life.health, maxHealth: life.max_health, money: life.money, stateVersion: life.state_version, guidedSlot: life.guided_slot, locationId: life.current_location_id },
        screen,
        journal: await journalView(client, life.id),
        inventory: itemState.inventory,
        equipment: itemState.equipment,
        homeStorage: life.phase === 'OPEN_LIFE' && life.current_location_id === 'home_qinghe' && !screen?.move ? itemState.storage : [],
        conditions: await conditionView(client, life.id),
        notices: await unreadNoticeView(client, life.id),
        recent: life.phase === 'OPEN_LIFE' ? await recentNoticeView(client, life.id) : [],
        skills: await getSkills(client, life.id),
        navigation: {
            locked: life.mode !== 'FREE',
            visible: life.mode !== 'FREE'
                ? []
                : (screen?.move
                    ? ['LIFE', 'WORLD', 'JOURNAL', 'INVENTORY', 'HERO']
                    : ['LIFE', 'WORLD', 'JOURNAL', 'INVENTORY', 'HERO'])
        }
    };
}
export async function bootstrap(playerId) {
    return inTransaction(async (client) => {
        const life = await getLife(client, playerId, true);
        return await buildView(client, life);
    });
}
export async function logSessionEnded(playerId, reason) {
    const client = await (await import('../db.js')).pool.connect();
    try {
        const life = await getLife(client, playerId);
        let activeEvent = null;
        if (life.active_event_id) {
            const r = await client.query(`select definition_id from active_events where id=$1`, [life.active_event_id]);
            activeEvent = r.rows[0]?.definition_id ?? null;
        }
        let travelState = null;
        if (life.active_travel_id) {
            const r = await client.query(`select current_node_id,health_current,status from travel_runs where id=$1 and life_id=$2`, [life.active_travel_id, life.id]);
            if (r.rows[0])
                travelState = { node: r.rows[0].current_node_id, health: Number(r.rows[0].health_current), status: r.rows[0].status };
        }
        let combatState = null;
        if (life.active_combat_id) {
            const r = await client.query(`select turn_no,player_hp,enemy_hp,enemy_intent,status from combat_sessions where id=$1 and life_id=$2`, [life.active_combat_id, life.id]);
            if (r.rows[0])
                combatState = { turn: Number(r.rows[0].turn_no), playerHp: Number(r.rows[0].player_hp), enemyHp: Number(r.rows[0].enemy_hp), intent: r.rows[0].enemy_intent, status: r.rows[0].status };
        }
        let openMoveState = null;
        let openActivityState = null;
        if (life.phase === 'OPEN_LIFE') {
            const [move, activity] = await Promise.all([
                client.query(`select from_location_id,to_location_id,completes_at,status from open_life_moves where life_id=$1 and status='active' order by created_at desc limit 1`, [life.id]),
                client.query(`select activity_id,activity_kind,location_id,completes_at,status,pending_situation_id from open_life_activities where life_id=$1 and status in ('active','situation') order by created_at desc limit 1`, [life.id])
            ]);
            if (move.rows[0])
                openMoveState = move.rows[0];
            if (activity.rows[0])
                openActivityState = activity.rows[0];
        }
        await analytics(client, life, 'session_ended', { reason, mode: life.mode, slot: life.guided_slot, health: life.health, activeEvent, travel: travelState, combat: combatState, openMove: openMoveState, openActivity: openActivityState, locationId: life.current_location_id });
    }
    finally {
        client.release();
    }
}
export async function resetDevLife(playerId) {
    if (config.NODE_ENV === 'production')
        throw new HttpError(404, 'not_found', 'Not found');
    return inTransaction(async (client) => {
        await client.query(`update lives set alive=false,updated_at=now() where player_id=$1 and alive=true`, [playerId]);
        const nextNoResult = await client.query(`select coalesce(max(life_number),0)+1 as n from lives where player_id=$1`, [playerId]);
        const nextNo = Number(nextNoResult.rows[0].n);
        const lifeResult = await client.query(`insert into lives(player_id,life_number,content_version,guided_slot,mode) values($1,$2,$3,'BIRTH','EVENT') returning *`, [playerId, nextNo, config.CONTENT_VERSION]);
        const life = lifeResult.rows[0];
        await client.query(`insert into life_locations(life_id,location_id,state,discovered_world_day,first_visited_world_day) values($1,'qinghe','visited',0,0)`, [life.id]);
        await activateGuidedSlot(client, life);
        return buildView(client, life);
    });
}
export async function logUiEvent(playerId, eventName) {
    const client = await (await import('../db.js')).pool.connect();
    try {
        const life = await getLife(client, playerId);
        await analytics(client, life, eventName, { mode: life.mode, slot: life.guided_slot, origin: life.origin_id });
    }
    finally {
        client.release();
    }
}

import { inTransaction } from '../db.js';
import { HttpError } from '../utils/http.js';
import { equipInstance, unequipSlot, moveInstanceHome, retrieveInstanceHome, storeStack, retrieveStack } from './itemService.js';
async function getLife(client, playerId, lock = false) {
    const r = await client.query(`select * from lives where player_id=$1 and alive=true order by life_number desc limit 1${lock ? ' for update' : ''}`, [playerId]);
    if (!r.rows[0])
        throw new HttpError(404, 'life_not_found', 'Active life not found');
    return r.rows[0];
}
function assertVersion(life, expected) { if (life.state_version !== expected)
    throw new HttpError(409, 'stale_game_state', 'Game state changed', { currentStateVersion: life.state_version }); }
async function duplicate(client, id, playerId) { const r = await client.query(`select result from processed_actions where client_action_id=$1 and player_id=$2`, [id, playerId]); return r.rows[0]?.result ?? null; }
async function bump(client, life) { life.state_version += 1; await client.query(`update lives set state_version=$1,updated_at=now() where id=$2`, [life.state_version, life.id]); }
async function store(client, id, playerId, life, type, result) { await client.query(`insert into processed_actions(client_action_id,player_id,life_id,action_type,result) values($1,$2,$3,$4,$5)`, [id, playerId, life.id, type, result]); }
async function analytics(client, life, eventName, payload) { await client.query(`insert into analytics_events(player_id,life_id,event_name,payload,world_day) select player_id,id,$2,$3,current_world_day from lives where id=$1`, [life.id, eventName, payload]); }
async function assertHomeStorageNotInTransit(client, life) {
    const r = await client.query(`select 1 from open_life_moves where life_id=$1 and status='active' limit 1`, [life.id]);
    if (r.rows[0])
        throw new HttpError(409, 'home_storage_unavailable', 'Домашний сундук остался позади, пока вы в пути');
}
function assertEquipmentAllowed(life) {
    if (life.phase !== 'OPEN_LIFE')
        throw new HttpError(409, 'equipment_busy', 'Снаряжение станет доступно после первого жизненного отрезка');
    if (life.mode !== 'FREE')
        throw new HttpError(409, 'equipment_busy', 'Сейчас менять снаряжение нельзя');
}
export async function equipOpenItem(playerId, instanceId, slot, actionId, expected) {
    return inTransaction(async (client) => { const prev = await duplicate(client, actionId, playerId); if (prev)
        return prev; const life = await getLife(client, playerId, true); assertVersion(life, expected); assertEquipmentAllowed(life); await equipInstance(client, life, instanceId, slot); await analytics(client, life, 'item_equipped', { instanceId, slot }); await bump(client, life); const result = { ok: true, stateVersion: life.state_version }; await store(client, actionId, playerId, life, 'item_equip', result); return result; });
}
export async function unequipOpenItem(playerId, slot, actionId, expected) {
    return inTransaction(async (client) => { const prev = await duplicate(client, actionId, playerId); if (prev)
        return prev; const life = await getLife(client, playerId, true); assertVersion(life, expected); assertEquipmentAllowed(life); if (slot === 'outfit' || slot === 'footwear')
        throw new HttpError(409, 'base_clothing_required', 'Базовую одежду нельзя просто снять; сначала нужна замена'); await unequipSlot(client, life, slot); await analytics(client, life, 'item_unequipped', { slot }); await bump(client, life); const result = { ok: true, stateVersion: life.state_version }; await store(client, actionId, playerId, life, 'item_unequip', result); return result; });
}
export async function storeOpenItem(playerId, instanceId, actionId, expected) {
    return inTransaction(async (client) => { const prev = await duplicate(client, actionId, playerId); if (prev)
        return prev; const life = await getLife(client, playerId, true); assertVersion(life, expected); assertEquipmentAllowed(life); await assertHomeStorageNotInTransit(client, life); await moveInstanceHome(client, life, instanceId); await analytics(client, life, 'item_stored_home', { instanceId }); await bump(client, life); const result = { ok: true, stateVersion: life.state_version }; await store(client, actionId, playerId, life, 'item_store', result); return result; });
}
export async function retrieveOpenItem(playerId, instanceId, actionId, expected) {
    return inTransaction(async (client) => { const prev = await duplicate(client, actionId, playerId); if (prev)
        return prev; const life = await getLife(client, playerId, true); assertVersion(life, expected); assertEquipmentAllowed(life); await assertHomeStorageNotInTransit(client, life); await retrieveInstanceHome(client, life, instanceId); await analytics(client, life, 'item_retrieved_home', { instanceId }); await bump(client, life); const result = { ok: true, stateVersion: life.state_version }; await store(client, actionId, playerId, life, 'item_retrieve', result); return result; });
}
export async function storeOpenStack(playerId, itemId, quantity, actionId, expected) {
    return inTransaction(async (client) => { const prev = await duplicate(client, actionId, playerId); if (prev)
        return prev; const life = await getLife(client, playerId, true); assertVersion(life, expected); assertEquipmentAllowed(life); await assertHomeStorageNotInTransit(client, life); await storeStack(client, life, itemId, quantity); await analytics(client, life, 'item_stack_stored_home', { itemId, quantity }); await bump(client, life); const result = { ok: true, stateVersion: life.state_version }; await store(client, actionId, playerId, life, 'item_stack_store', result); return result; });
}
export async function retrieveOpenStack(playerId, itemId, quantity, actionId, expected) {
    return inTransaction(async (client) => { const prev = await duplicate(client, actionId, playerId); if (prev)
        return prev; const life = await getLife(client, playerId, true); assertVersion(life, expected); assertEquipmentAllowed(life); await assertHomeStorageNotInTransit(client, life); await retrieveStack(client, life, itemId, quantity); await analytics(client, life, 'item_stack_retrieved_home', { itemId, quantity }); await bump(client, life); const result = { ok: true, stateVersion: life.state_version }; await store(client, actionId, playerId, life, 'item_stack_retrieve', result); return result; });
}

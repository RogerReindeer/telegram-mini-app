import { content } from '../content/loader.js';
import { HttpError } from '../utils/http.js';
function def(itemId) {
    const value = content.items.get(itemId);
    if (!value)
        throw new Error(`Unknown item ${itemId}`);
    return value;
}
export async function addItem(client, life, itemId, quantity, originData = {}) {
    if (quantity <= 0)
        return;
    const item = def(itemId);
    if (item.instance) {
        for (let i = 0; i < quantity; i++) {
            await client.query(`insert into life_item_instances(life_id,item_id,location_type,condition,story_kind,protected,origin_data,acquired_world_day)
         values($1,$2,'CARRIED','good',$3,$4,$5,$6)`, [life.id, itemId, item.storyKind ?? 'normal', Boolean(item.protected), originData, life.current_world_day]);
        }
        return;
    }
    await client.query(`insert into life_inventory(life_id,item_id,quantity) values($1,$2,$3)
     on conflict(life_id,item_id) do update set quantity=life_inventory.quantity+excluded.quantity`, [life.id, itemId, quantity]);
}
export async function removeItem(client, life, itemId, quantity) {
    if (quantity <= 0)
        return;
    const item = def(itemId);
    if (item.instance) {
        const rows = await client.query(`select i.id,i.protected from life_item_instances i
       left join life_equipment e on e.item_instance_id=i.id
       where i.life_id=$1 and i.item_id=$2 and i.location_type='CARRIED' and e.item_instance_id is null
       order by i.created_at asc for update`, [life.id, itemId]);
        const removable = rows.rows.filter((r) => !r.protected).slice(0, quantity);
        if (removable.length < quantity)
            throw new HttpError(409, 'not_enough_items', `Not enough ${itemId}`);
        await client.query(`delete from life_item_instances where id=any($1::uuid[])`, [removable.map((r) => r.id)]);
        return;
    }
    const current = await client.query(`select quantity from life_inventory where life_id=$1 and item_id=$2 for update`, [life.id, itemId]);
    const next = Number(current.rows[0]?.quantity ?? 0) - quantity;
    if (next < 0)
        throw new HttpError(409, 'not_enough_items', `Not enough ${itemId}`);
    if (next === 0)
        await client.query(`delete from life_inventory where life_id=$1 and item_id=$2`, [life.id, itemId]);
    else
        await client.query(`update life_inventory set quantity=$3 where life_id=$1 and item_id=$2`, [life.id, itemId, next]);
}
export async function ensureBaseEquipment(client, life) {
    for (const [slot, itemId] of [['outfit', 'simple_clothes'], ['footwear', 'work_shoes']]) {
        const equipped = await client.query(`select 1 from life_equipment where life_id=$1 and slot=$2`, [life.id, slot]);
        if (equipped.rows[0])
            continue;
        let inst = await client.query(`select id from life_item_instances where life_id=$1 and item_id=$2 and location_type='CARRIED' order by created_at limit 1`, [life.id, itemId]);
        if (!inst.rows[0]) {
            await addItem(client, life, itemId, 1, { source: 'base_clothing' });
            inst = await client.query(`select id from life_item_instances where life_id=$1 and item_id=$2 and location_type='CARRIED' order by created_at desc limit 1`, [life.id, itemId]);
        }
        await equipInstance(client, life, String(inst.rows[0].id), slot);
    }
}
export async function equipInstance(client, life, instanceId, slot) {
    const row = await client.query(`select * from life_item_instances where id=$1 and life_id=$2 for update`, [instanceId, life.id]);
    const instance = row.rows[0];
    if (!instance)
        throw new HttpError(404, 'item_not_found', 'Item not found');
    if (instance.location_type !== 'CARRIED' && instance.location_type !== 'EQUIPPED')
        throw new HttpError(409, 'item_not_carried', 'Item is not carried');
    const item = def(String(instance.item_id));
    if (!(item.equipSlots ?? []).includes(slot))
        throw new HttpError(409, 'slot_unavailable', 'This item cannot be equipped there');
    const old = await client.query(`select item_instance_id from life_equipment where life_id=$1 and slot=$2 for update`, [life.id, slot]);
    if (old.rows[0]?.item_instance_id && String(old.rows[0].item_instance_id) !== instanceId) {
        await client.query(`update life_item_instances set location_type='CARRIED',location_key=null,updated_at=now() where id=$1`, [old.rows[0].item_instance_id]);
    }
    await client.query(`insert into life_equipment(life_id,slot,item_instance_id) values($1,$2,$3)
     on conflict(life_id,slot) do update set item_instance_id=excluded.item_instance_id,equipped_at=now()`, [life.id, slot, instanceId]);
    await client.query(`update life_item_instances set location_type='EQUIPPED',location_key=$2,updated_at=now() where id=$1`, [instanceId, slot]);
}
export async function equipFirstByItemId(client, life, itemId, slot) {
    const r = await client.query(`select id from life_item_instances where life_id=$1 and item_id=$2 and location_type='CARRIED' order by created_at desc limit 1`, [life.id, itemId]);
    if (!r.rows[0])
        throw new HttpError(409, 'item_not_found', `Missing ${itemId}`);
    await equipInstance(client, life, String(r.rows[0].id), slot);
}
export async function unequipSlot(client, life, slot) {
    const r = await client.query(`delete from life_equipment where life_id=$1 and slot=$2 returning item_instance_id`, [life.id, slot]);
    if (!r.rows[0])
        return;
    await client.query(`update life_item_instances set location_type='CARRIED',location_key=null,updated_at=now() where id=$1`, [r.rows[0].item_instance_id]);
}
export async function moveInstanceHome(client, life, instanceId) {
    if (life.current_location_id !== 'home_qinghe' && life.current_location_id !== 'qinghe')
        throw new HttpError(409, 'home_storage_unavailable', 'Home storage is only available at home');
    const r = await client.query(`select location_type,protected from life_item_instances where id=$1 and life_id=$2 for update`, [instanceId, life.id]);
    if (!r.rows[0])
        throw new HttpError(404, 'item_not_found', 'Item not found');
    if (r.rows[0].location_type === 'EQUIPPED') {
        const equipped = await client.query(`select slot from life_equipment where life_id=$1 and item_instance_id=$2`, [life.id, instanceId]);
        const slot = String(equipped.rows[0]?.slot ?? '');
        if (slot === 'outfit' || slot === 'footwear')
            throw new HttpError(409, 'base_clothing_required', 'Базовую одежду нельзя оставить в сундуке, пока она на вас');
        await client.query(`delete from life_equipment where item_instance_id=$1`, [instanceId]);
    }
    await client.query(`update life_item_instances set location_type='HOME',location_key='home_chest',updated_at=now() where id=$1`, [instanceId]);
}
export async function retrieveInstanceHome(client, life, instanceId) {
    if (life.current_location_id !== 'home_qinghe' && life.current_location_id !== 'qinghe')
        throw new HttpError(409, 'home_storage_unavailable', 'Home storage is only available at home');
    const r = await client.query(`update life_item_instances set location_type='CARRIED',location_key=null,updated_at=now() where id=$1 and life_id=$2 and location_type='HOME' returning id`, [instanceId, life.id]);
    if (!r.rows[0])
        throw new HttpError(404, 'item_not_found', 'Stored item not found');
}
export async function storeStack(client, life, itemId, quantity) {
    if (life.current_location_id !== 'home_qinghe' && life.current_location_id !== 'qinghe')
        throw new HttpError(409, 'home_storage_unavailable', 'Home storage is only available at home');
    if (quantity <= 0)
        throw new HttpError(400, 'invalid_quantity', 'Invalid quantity');
    const r = await client.query(`select quantity from life_inventory where life_id=$1 and item_id=$2 for update`, [life.id, itemId]);
    const have = Number(r.rows[0]?.quantity ?? 0);
    if (have < quantity)
        throw new HttpError(409, 'not_enough_items', 'Not enough items');
    if (have === quantity)
        await client.query(`delete from life_inventory where life_id=$1 and item_id=$2`, [life.id, itemId]);
    else
        await client.query(`update life_inventory set quantity=$3 where life_id=$1 and item_id=$2`, [life.id, itemId, have - quantity]);
    await client.query(`insert into life_storage(life_id,storage_id,item_id,quantity) values($1,'home_chest',$2,$3) on conflict(life_id,storage_id,item_id) do update set quantity=life_storage.quantity+excluded.quantity`, [life.id, itemId, quantity]);
}
export async function retrieveStack(client, life, itemId, quantity) {
    if (life.current_location_id !== 'home_qinghe' && life.current_location_id !== 'qinghe')
        throw new HttpError(409, 'home_storage_unavailable', 'Home storage is only available at home');
    if (quantity <= 0)
        throw new HttpError(400, 'invalid_quantity', 'Invalid quantity');
    const r = await client.query(`select quantity from life_storage where life_id=$1 and storage_id='home_chest' and item_id=$2 for update`, [life.id, itemId]);
    const have = Number(r.rows[0]?.quantity ?? 0);
    if (have < quantity)
        throw new HttpError(409, 'not_enough_items', 'Not enough stored items');
    if (have === quantity)
        await client.query(`delete from life_storage where life_id=$1 and storage_id='home_chest' and item_id=$2`, [life.id, itemId]);
    else
        await client.query(`update life_storage set quantity=$3 where life_id=$1 and storage_id='home_chest' and item_id=$2`, [life.id, itemId, have - quantity]);
    await client.query(`insert into life_inventory(life_id,item_id,quantity) values($1,$2,$3) on conflict(life_id,item_id) do update set quantity=life_inventory.quantity+excluded.quantity`, [life.id, itemId, quantity]);
}
export async function equipmentMap(client, lifeId) {
    const r = await client.query(`select e.slot,i.id instance_id,i.item_id,i.condition,i.story_kind,i.protected,i.origin_data from life_equipment e join life_item_instances i on i.id=e.item_instance_id where e.life_id=$1`, [lifeId]);
    const out = { outfit: null, outerwear: null, head: null, footwear: null, main_hand: null, off_hand: null, belt: null, carry: null };
    for (const row of r.rows) {
        const item = def(String(row.item_id));
        out[row.slot] = { instanceId: String(row.instance_id), id: item.id, name: item.name, description: item.description, quantity: 1, condition: row.condition, storyKind: row.story_kind, protected: Boolean(row.protected), locationType: 'EQUIPPED', locationKey: row.slot, equippedSlot: row.slot, equipSlots: item.equipSlots ?? [], originText: originText(row.origin_data) };
    }
    return out;
}
function originText(originData) {
    if (!originData || typeof originData !== 'object')
        return null;
    if (typeof originData.note === 'string')
        return originData.note;
    if (typeof originData.source === 'string')
        return `Получено: ${originData.source}`;
    return null;
}
export async function inventoryViews(client, lifeId) {
    const [stacks, instances, equipment, storedStacks, storedInstances] = await Promise.all([
        client.query(`select item_id,quantity from life_inventory where life_id=$1 and quantity>0 order by item_id`, [lifeId]),
        client.query(`select i.*,e.slot equipped_slot from life_item_instances i left join life_equipment e on e.item_instance_id=i.id where i.life_id=$1 and i.location_type in ('CARRIED','EQUIPPED') order by i.created_at`, [lifeId]),
        equipmentMap(client, lifeId),
        client.query(`select item_id,quantity from life_storage where life_id=$1 and storage_id='home_chest' and quantity>0 order by item_id`, [lifeId]),
        client.query(`select * from life_item_instances where life_id=$1 and location_type='HOME' order by created_at`, [lifeId])
    ]);
    const inventory = [];
    for (const row of stacks.rows) {
        const item = def(String(row.item_id));
        inventory.push({ id: item.id, name: item.name, description: item.description, quantity: Number(row.quantity), storyKind: item.storyKind ?? 'normal', protected: Boolean(item.protected), tags: item.tags ?? [] });
    }
    for (const row of instances.rows) {
        const item = def(String(row.item_id));
        inventory.push({ instanceId: String(row.id), id: item.id, name: item.name, description: item.description, quantity: 1, condition: row.condition, storyKind: row.story_kind, protected: Boolean(row.protected), locationType: row.location_type, locationKey: row.location_key, equippedSlot: row.equipped_slot ?? null, equipSlots: item.equipSlots ?? [], originText: originText(row.origin_data) });
    }
    const storage = [];
    for (const row of storedStacks.rows) {
        const item = def(String(row.item_id));
        storage.push({ id: item.id, name: item.name, description: item.description, quantity: Number(row.quantity), storyKind: item.storyKind ?? 'normal', protected: Boolean(item.protected), tags: item.tags ?? [] });
    }
    for (const row of storedInstances.rows) {
        const item = def(String(row.item_id));
        storage.push({ instanceId: String(row.id), id: item.id, name: item.name, description: item.description, quantity: 1, condition: row.condition, storyKind: row.story_kind, protected: Boolean(row.protected), locationType: 'HOME', locationKey: 'home_chest', equippedSlot: null, equipSlots: item.equipSlots ?? [], originText: originText(row.origin_data) });
    }
    return { inventory, equipment, storage };
}
export async function equippedItemIds(client, lifeId) {
    const r = await client.query(`select i.item_id,e.slot from life_equipment e join life_item_instances i on i.id=e.item_instance_id where e.life_id=$1`, [lifeId]);
    return new Map(r.rows.map((x) => [x.slot, String(x.item_id)]));
}
export async function visibleEquipmentDescription(client, lifeId) {
    const r = await client.query(`select i.item_id from life_equipment e join life_item_instances i on i.id=e.item_instance_id where e.life_id=$1 order by case e.slot when 'outerwear' then 1 when 'main_hand' then 2 when 'belt' then 3 when 'carry' then 4 else 9 end`, [lifeId]);
    return r.rows.map((x) => def(String(x.item_id)).visibleWhenEquipped).filter((x) => Boolean(x)).slice(0, 4);
}
export async function createWorkpiece(client, life, itemId, workplace, activityId) {
    const existing = await client.query(`select id from life_item_instances where life_id=$1 and item_id=$2 and location_type='WORKPLACE' and location_key=$3 limit 1`, [life.id, itemId, workplace]);
    if (existing.rows[0])
        return;
    const item = def(itemId);
    await client.query(`insert into life_item_instances(life_id,item_id,location_type,location_key,story_kind,protected,origin_data,acquired_world_day) values($1,$2,'WORKPLACE',$3,$4,$5,$6,$7)`, [life.id, itemId, workplace, item.storyKind ?? 'temporary', Boolean(item.protected), { activityId }, life.current_world_day]);
}
export async function removeWorkpiece(client, life, itemId, workplace) {
    await client.query(`delete from life_item_instances where life_id=$1 and item_id=$2 and location_type='WORKPLACE' and location_key=$3`, [life.id, itemId, workplace]);
}

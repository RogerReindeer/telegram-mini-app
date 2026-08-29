import { inTransaction, pool } from '../db.js';
import { content } from '../content/loader.js';
import { HttpError } from '../utils/http.js';

export async function getAdminOverview() {
  const [summary, origins, slots, locations, funnel, recent] = await Promise.all([
    pool.query(`
      select
        (select count(*)::int from players) as players_total,
        (select count(*)::int from players where last_seen_at >= now() - interval '24 hours') as players_24h,
        (select count(*)::int from lives where alive=true) as active_lives,
        (select count(*)::int from lives where alive=true and phase='OPEN_LIFE') as completed_slice,
        (select count(*)::int from analytics_events where created_at >= now() - interval '24 hours') as events_24h,
        (select count(*)::int from open_life_presence where last_seen_at >= now() - interval '2 minutes') as online_now,
        (select count(*)::int from open_life_moves where status='active') as active_moves,
        (select count(*)::int from open_life_activities where status in ('active','situation')) as active_activities,
        (select count(*)::int from local_chat_messages where created_at >= now() - interval '24 hours') as chat_24h
    `),
    pool.query(`select coalesce(origin_id,'not_selected') as label,count(*)::int as count from lives where alive=true group by 1 order by count desc`),
    pool.query(`select guided_slot as label,count(*)::int as count from lives where alive=true and phase='GUIDED_LIFE' group by guided_slot order by count desc`),
    pool.query(`select current_location_id as label,count(*)::int as count from lives where alive=true and phase='OPEN_LIFE' group by current_location_id order by count desc`),
    pool.query(`
      with steps(step, ord) as (values
        ('life_created',1),('travel_started',2),('combat_started',3),('continue_deeper_selected',4),('whiteback_seen',5),('guided_open_life_reached',6)
      )
      select s.step as label, count(distinct a.life_id)::int as count, s.ord
      from steps s left join analytics_events a on a.event_name=s.step
      group by s.step,s.ord order by s.ord
    `),
    pool.query(`
      select a.created_at,a.event_name,a.world_day,a.payload,p.telegram_user_id,p.telegram_username
      from analytics_events a
      left join players p on p.id=a.player_id
      order by a.created_at desc limit 40
    `)
  ]);
  const clock=await pool.query(`select base_real_at,base_world_day,world_days_per_real_day,updated_at from world_clock where id=1`).catch(()=>({rows:[]} as any));
  return {
    summary: summary.rows[0],
    origins: origins.rows,
    slots: slots.rows,
    locations: locations.rows,
    funnel: funnel.rows.map(({ label, count }: {label:string;count:number}) => ({ label, count })),
    recentEvents: recent.rows,
    worldClock: clock.rows[0] ?? null
  };
}

export async function searchAdminPlayers(search = '', limit = 50) {
  const term = search.trim();
  const result = await pool.query(`
    select p.id,p.telegram_user_id,p.telegram_username,p.created_at,p.last_seen_at,
      l.id as life_id,l.life_number,l.phase,l.mode,l.origin_id,l.birth_world_day,l.current_world_day,l.health,l.max_health,l.money,
      l.guided_slot,l.current_location_id,l.updated_at,l.state_version
    from players p
    left join lateral (
      select * from lives where player_id=p.id and alive=true order by life_number desc limit 1
    ) l on true
    where ($1='' or coalesce(p.telegram_username,'') ilike '%'||$1||'%' or p.telegram_user_id::text like '%'||$1||'%')
    order by p.last_seen_at desc
    limit $2
  `, [term, Math.max(1, Math.min(100, limit))]);
  return result.rows;
}

export async function getAdminPlayer(playerId: string) {
  const playerResult = await pool.query(`select id,telegram_user_id,telegram_username,created_at,last_seen_at from players where id=$1`, [playerId]);
  if (!playerResult.rows[0]) throw new HttpError(404, 'player_not_found', 'Player not found');
  const lifeResult = await pool.query(`select * from lives where player_id=$1 and alive=true order by life_number desc limit 1`, [playerId]);
  const life = lifeResult.rows[0] ?? null;
  if (!life) return { player: playerResult.rows[0], life: null };

  const [skills, inventory, flags, knowledge, rumors, biography, analytics, travel, combat, openMove, openActivity] = await Promise.all([
    pool.query(`select skill_id,level from life_skills where life_id=$1 order by skill_id`, [life.id]),
    pool.query(`select item_id,quantity from life_inventory where life_id=$1 order by item_id`, [life.id]),
    pool.query(`select flag_id,created_world_day from life_flags where life_id=$1 order by created_world_day,flag_id`, [life.id]),
    pool.query(`select topic_id,stage,updated_world_day from life_knowledge where life_id=$1 order by updated_world_day desc`, [life.id]),
    pool.query(`select rumor_id,state,source_npc_id,heard_world_day,updated_world_day from life_rumors where life_id=$1 order by updated_world_day desc`, [life.id]),
    pool.query(`select world_day,entry_type,content_id,choice_id,text,created_at from life_log where life_id=$1 order by world_day desc,created_at desc limit 30`, [life.id]),
    pool.query(`select event_name,payload,world_day,created_at from analytics_events where life_id=$1 order by created_at desc limit 50`, [life.id]),
    life.active_travel_id ? pool.query(`select id,status,current_node_id,health_start,health_current,run_flags,visited_nodes,updated_at from travel_runs where id=$1`, [life.active_travel_id]) : Promise.resolve({ rows: [] } as any),
    life.active_combat_id ? pool.query(`select id,status,turn_no,player_hp,enemy_hp,enemy_state,enemy_intent,combat_flags,updated_at from combat_sessions where id=$1`, [life.active_combat_id]) : Promise.resolve({ rows: [] } as any),
    pool.query(`select id,from_location_id,to_location_id,started_at,completes_at,status from open_life_moves where life_id=$1 and status='active' order by created_at desc limit 1`,[life.id]),
    pool.query(`select id,activity_id,activity_kind,location_id,started_at,completes_at,status,pending_situation_id from open_life_activities where life_id=$1 and status in ('active','situation') order by created_at desc limit 1`,[life.id])
  ]);

  const inventoryMap = new Map(inventory.rows.map((x: any) => [x.item_id, Number(x.quantity)]));
  const itemCatalog = [...content.items.values()].map((item: any) => ({ id: item.id, name: item.name, description: item.description, quantity: inventoryMap.get(item.id) ?? 0 }));

  return {
    player: playerResult.rows[0],
    life,
    skills: skills.rows,
    inventory: itemCatalog,
    flags: flags.rows,
    knowledge: knowledge.rows,
    rumors: rumors.rows,
    biography: biography.rows,
    analytics: analytics.rows,
    activeTravel: travel.rows[0] ?? null,
    activeCombat: combat.rows[0] ?? null,
    activeOpenMove: openMove.rows[0] ?? null,
    activeOpenActivity: openActivity.rows[0] ?? null
  };
}

export async function updateAdminLife(lifeId: string, patch: { health?: number; maxHealth?: number; money?: number; currentWorldDay?: number }) {
  return inTransaction(async (client) => {
    const r = await client.query(`select * from lives where id=$1 and alive=true for update`, [lifeId]);
    const life = r.rows[0];
    if (!life) throw new HttpError(404, 'life_not_found', 'Active life not found');
    const maxHealth = patch.maxHealth ?? Number(life.max_health);
    const health = patch.health ?? Number(life.health);
    if (health > maxHealth) throw new HttpError(400, 'invalid_health', 'Health cannot exceed max health');
    const money = patch.money ?? Number(life.money);
    if (life.phase === 'OPEN_LIFE' && patch.currentWorldDay !== undefined) throw new HttpError(400, 'world_day_read_only', 'OPEN_LIFE age is controlled by the shared world clock');
    const currentWorldDay = patch.currentWorldDay ?? Number(life.current_world_day);

    await client.query(`
      update lives set health=$1,max_health=$2,money=$3,current_world_day=$4,state_version=state_version+1,updated_at=now() where id=$5
    `, [health, maxHealth, money, currentWorldDay, lifeId]);
    await client.query(`insert into analytics_events(player_id,life_id,event_name,payload,world_day) select player_id,id,'admin_edit',$2,current_world_day from lives where id=$1`, [lifeId, { section: 'life', patch }]);

    if (life.active_travel_id && patch.health !== undefined) {
      await client.query(`update travel_runs set health_current=$1,updated_at=now() where id=$2`, [health, life.active_travel_id]);
    }
    if (life.active_combat_id && patch.health !== undefined) {
      await client.query(`update combat_sessions set player_hp=$1,updated_at=now() where id=$2`, [health, life.active_combat_id]);
    }
    return { ok: true };
  });
}

export async function updateAdminSkill(lifeId: string, skillId: string, level: number) {
  await inTransaction(async (client) => {
    const exists = await client.query(`select id from lives where id=$1 and alive=true`, [lifeId]);
    if (!exists.rows[0]) throw new HttpError(404, 'life_not_found', 'Active life not found');
    if (level === 0) await client.query(`delete from life_skills where life_id=$1 and skill_id=$2`, [lifeId, skillId]);
    else await client.query(`insert into life_skills(life_id,skill_id,level) values($1,$2,$3) on conflict(life_id,skill_id) do update set level=excluded.level`, [lifeId, skillId, level]);
    await client.query(`update lives set state_version=state_version+1,updated_at=now() where id=$1`, [lifeId]);
    await client.query(`insert into analytics_events(player_id,life_id,event_name,payload,world_day) select player_id,id,'admin_edit',$2,current_world_day from lives where id=$1`, [lifeId, { section: 'skill', skillId, level }]);
  });
  return { ok: true };
}

export async function updateAdminInventory(lifeId: string, itemId: string, quantity: number) {
  if (!content.items.has(itemId)) throw new HttpError(400, 'unknown_item', 'Unknown item');
  await inTransaction(async (client) => {
    const exists = await client.query(`select id from lives where id=$1 and alive=true`, [lifeId]);
    if (!exists.rows[0]) throw new HttpError(404, 'life_not_found', 'Active life not found');
    if (quantity === 0) await client.query(`delete from life_inventory where life_id=$1 and item_id=$2`, [lifeId, itemId]);
    else await client.query(`insert into life_inventory(life_id,item_id,quantity) values($1,$2,$3) on conflict(life_id,item_id) do update set quantity=excluded.quantity`, [lifeId, itemId, quantity]);
    await client.query(`update lives set state_version=state_version+1,updated_at=now() where id=$1`, [lifeId]);
    await client.query(`insert into analytics_events(player_id,life_id,event_name,payload,world_day) select player_id,id,'admin_edit',$2,current_world_day from lives where id=$1`, [lifeId, { section: 'inventory', itemId, quantity }]);
  });
  return { ok: true };
}

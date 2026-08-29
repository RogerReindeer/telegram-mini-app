import crypto from 'node:crypto';
import { inTransaction } from '../db.js';
import { config } from '../config.js';
import { content } from '../content/loader.js';
import { openLifeContent } from '../content/openLife.js';
import { HttpError } from '../utils/http.js';
import { addItem, createWorkpiece, removeWorkpiece, visibleEquipmentDescription, equippedItemIds } from './itemService.js';
// Technical rhythm only. Canonical content lives in world_events.json.
// LIFE entries deliberately dominate ANOMALY entries so ordinary life remains the baseline.
const WORLD_EVENT_SEQUENCE = [
    'flood', 'guard_order', 'grain_price', 'animal_routes',
    'travelling_troupe', 'merchant_feud', 'luo_injured', 'unusual_plant',
    'yan_needs_help', 'large_caravan', 'flood', 'night_bell',
    'guard_order', 'grain_price', 'travelling_troupe', 'whiteback_story',
    'merchant_feud', 'large_caravan', 'yan_needs_help', 'old_quarry_rumor'
];
function nowMs() { return Date.now(); }
function asMs(v) { return new Date(v).getTime(); }
function secondsRemaining(v) { return Math.max(0, Math.ceil((asMs(v) - nowMs()) / 1000)); }
function hash100(...parts) {
    const h = crypto.createHash('sha256').update(parts.join('|')).digest();
    return h.readUInt32BE(0) % 100;
}
async function getLife(client, playerId, lock = false) {
    const r = await client.query(`select * from lives where player_id=$1 and alive=true order by life_number desc limit 1${lock ? ' for update' : ''}`, [playerId]);
    if (!r.rows[0])
        throw new HttpError(404, 'life_not_found', 'Active life not found');
    return r.rows[0];
}
function assertOpenLife(life) {
    if (life.phase !== 'OPEN_LIFE')
        throw new HttpError(409, 'open_life_unavailable', 'OPEN_LIFE is not available yet');
    if (life.mode !== 'FREE')
        throw new HttpError(409, 'open_life_busy', 'Finish the current activity first');
}
async function worldDay(client) {
    const r = await client.query(`select base_real_at,base_world_day,world_days_per_real_day from world_clock where id=1`);
    if (!r.rows[0])
        throw new Error('world_clock missing; apply 002_open_life_v03.sql');
    const row = r.rows[0];
    const elapsedDays = (Date.now() - new Date(row.base_real_at).getTime()) / 86_400_000;
    return Math.floor(Number(row.base_world_day) + elapsedDays * Number(row.world_days_per_real_day));
}
function availabilityTime() {
    const utc = new Date();
    const hour = (utc.getUTCHours() + config.AVAILABILITY_UTC_OFFSET + 24) % 24;
    if (hour >= 5 && hour < 11)
        return { id: 'morning', label: 'утро' };
    if (hour >= 11 && hour < 17)
        return { id: 'day', label: 'день' };
    if (hour >= 17 && hour < 22)
        return { id: 'evening', label: 'вечер' };
    return { id: 'night', label: 'ночь' };
}
const SEASON_EPOCH_MS = Date.UTC(2026, 0, 1);
function seasonFromContext() {
    const seasonIndex = Math.floor((Date.now() - SEASON_EPOCH_MS) / (Math.max(1, config.SEASON_REAL_DAYS) * 86_400_000));
    return ['весна', 'лето', 'осень', 'зима'][((seasonIndex % 4) + 4) % 4];
}
function weatherFromContext(season) {
    const realBucket = Math.floor(Date.now() / (3 * 3_600_000));
    return hash100(realBucket, season, 'qinghe-weather') < (season === 'лето' ? 24 : season === 'весна' ? 20 : 16) ? 'rain' : 'clear';
}
async function shiftLifeWorldDays(client, lifeId, threshold, offset) {
    if (offset === 0)
        return;
    const statements = [
        [`update life_log set world_day=world_day+$2 where life_id=$1 and world_day<$3`, [lifeId, offset, threshold]],
        [`update life_flags set created_world_day=created_world_day+$2 where life_id=$1 and created_world_day<$3`, [lifeId, offset, threshold]],
        [`update life_knowledge set updated_world_day=updated_world_day+$2 where life_id=$1 and updated_world_day<$3`, [lifeId, offset, threshold]],
        [`update life_rumors set heard_world_day=case when heard_world_day is not null and heard_world_day<$3 then heard_world_day+$2 else heard_world_day end,updated_world_day=case when updated_world_day<$3 then updated_world_day+$2 else updated_world_day end where life_id=$1`, [lifeId, offset, threshold]],
        [`update life_locations set discovered_world_day=case when discovered_world_day<$3 then discovered_world_day+$2 else discovered_world_day end,first_visited_world_day=case when first_visited_world_day is not null and first_visited_world_day<$3 then first_visited_world_day+$2 else first_visited_world_day end where life_id=$1`, [lifeId, offset, threshold]],
        [`update life_relationships set updated_world_day=updated_world_day+$2 where life_id=$1 and updated_world_day<$3`, [lifeId, offset, threshold]],
        [`update life_state set updated_world_day=updated_world_day+$2 where life_id=$1 and updated_world_day<$3`, [lifeId, offset, threshold]],
        [`update travel_runs set started_world_day=started_world_day+$2 where life_id=$1 and started_world_day<$3`, [lifeId, offset, threshold]],
        [`update analytics_events set world_day=world_day+$2 where life_id=$1 and world_day is not null and world_day<$3`, [lifeId, offset, threshold]],
        [`update life_item_instances set acquired_world_day=acquired_world_day+$2 where life_id=$1 and acquired_world_day is not null and acquired_world_day<$3`, [lifeId, offset, threshold]]
    ];
    for (const [sql, args] of statements)
        await client.query(sql, [...args]);
}
async function syncOpenLifeAge(client, life, wd) {
    const row = life;
    if (row.open_life_joined_world_day == null || row.open_life_age_day_at_join == null) {
        const ageDay = Math.max(0, life.current_world_day - life.birth_world_day);
        row.open_life_joined_world_day = wd;
        row.open_life_age_day_at_join = ageDay;
        await client.query(`update lives set open_life_joined_world_day=$1,open_life_age_day_at_join=$2,current_location_id=case when current_location_id in ('qinghe','bamboo_grove') then 'home_qinghe' else current_location_id end,updated_at=now() where id=$3`, [wd, ageDay, life.id]);
        if (life.current_location_id === 'qinghe' || life.current_location_id === 'bamboo_grove')
            life.current_location_id = 'home_qinghe';
    }
    if (!row.open_life_world_time_normalized) {
        const joined = Number(row.open_life_joined_world_day), ageAtJoin = Number(row.open_life_age_day_at_join);
        const oldBirth = Number(life.birth_world_day), newBirth = joined - ageAtJoin, offset = newBirth - oldBirth;
        await shiftLifeWorldDays(client, life.id, newBirth, offset);
        life.birth_world_day = newBirth;
        life.current_world_day = wd;
        row.open_life_world_time_normalized = true;
        await client.query(`update lives set birth_world_day=$1,current_world_day=$2,open_life_world_time_normalized=true,updated_at=now() where id=$3`, [newBirth, wd, life.id]);
        return;
    }
    if (life.current_world_day !== wd) {
        life.current_world_day = wd;
        await client.query(`update lives set current_world_day=$1,updated_at=now() where id=$2`, [wd, life.id]);
    }
}
async function getSkills(client, lifeId) {
    const r = await client.query(`select skill_id,level from life_skills where life_id=$1`, [lifeId]);
    return Object.fromEntries(r.rows.map(x => [String(x.skill_id), Number(x.level)]));
}
async function getKnowledge(client, lifeId) {
    const r = await client.query(`select topic_id,stage from life_knowledge where life_id=$1`, [lifeId]);
    return new Map(r.rows.map(x => [String(x.topic_id), String(x.stage)]));
}
async function getFlags(client, lifeId) {
    const r = await client.query(`select flag_id from life_flags where life_id=$1`, [lifeId]);
    return new Set(r.rows.map(x => String(x.flag_id)));
}
async function anomalyCount(client, lifeId) {
    const r = await client.query(`select count(*)::int c from life_knowledge where life_id=$1 and topic_id in ('whiteback','white_back','unusual_plant','night_bell','blue_iron','old_quarry')`, [lifeId]);
    return Number(r.rows[0]?.c ?? 0);
}
async function hasCarriedItem(client, lifeId, itemId) {
    const [stack, instance] = await Promise.all([
        client.query(`select 1 from life_inventory where life_id=$1 and item_id=$2 and quantity>0`, [lifeId, itemId]),
        client.query(`select 1 from life_item_instances where life_id=$1 and item_id=$2 and location_type in ('CARRIED','EQUIPPED') limit 1`, [lifeId, itemId])
    ]);
    return Boolean(stack.rows[0] || instance.rows[0]);
}
async function analyticsOpen(client, life, eventName, payload = {}) {
    await client.query(`insert into analytics_events(player_id,life_id,event_name,payload,world_day) select player_id,id,$2,$3,current_world_day from lives where id=$1`, [life.id, eventName, payload]);
}
async function pushOpenNotice(client, life, payload) {
    const text = payload.message.trim();
    if (!text)
        return;
    await client.query(`insert into open_life_notices(life_id,notice_kind,title,message,details,world_day) values($1,$2,$3,$4,$5,$6)`, [life.id, payload.kind ?? 'activity', payload.title, text, payload.details ?? {}, payload.worldDay ?? life.current_world_day]);
}
function activityNoticeTitle(def) {
    if (def.kind === 'WORK')
        return 'Работа завершена';
    if (def.kind === 'PRACTICE')
        return 'Практика завершена';
    if (def.kind === 'TREATMENT')
        return 'Лечение завершено';
    if (def.kind === 'REST')
        return def.id === 'catch_breath_home' ? 'Вы перевели дух' : 'Вы хорошо отдохнули';
    return 'Занятие завершено';
}
function skillDisplayName(id) { return { blacksmithing: 'Кузнечное дело', herbalism: 'Травничество', tracking: 'Следопытство', trade: 'Торговля' }[id] ?? id; }
function skillDisplayStage(level) { return { 1: 'Начальные знания', 2: 'Уверенно', 3: 'Мастерство' }[level] ?? String(level); }
const WORLD_EVENT_EPOCH_MS = Date.UTC(2026, 0, 1);
function worldEventDurationMs(event) { return Math.max(60_000, event.durationWorldDays * config.WORLD_EVENT_REAL_MINUTES_PER_WORLD_DAY * 60_000); }
function worldEventTimeline() {
    const cycle = WORLD_EVENT_SEQUENCE.map(id => openLifeContent.worldEvents.get(id)).filter(Boolean);
    const total = cycle.reduce((sum, event) => sum + worldEventDurationMs(event), 0);
    let cursor = ((Date.now() - WORLD_EVENT_EPOCH_MS) % total + total) % total;
    for (let index = 0; index < cycle.length; index++) {
        const event = cycle[index], span = worldEventDurationMs(event);
        if (cursor < span) {
            const previous = cycle[(index - 1 + cycle.length) % cycle.length];
            return { event, previous, elapsedMs: cursor, durationMs: span };
        }
        cursor -= span;
    }
    return { event: cycle[0], previous: cycle[cycle.length - 1], elapsedMs: 0, durationMs: worldEventDurationMs(cycle[0]) };
}
function activeWorldEvent(_wd) { return worldEventTimeline().event; }
function recentWorldAftermath(locationId) {
    const timeline = worldEventTimeline();
    const text = timeline.previous.aftermath?.[locationId];
    if (!text)
        return null;
    const windowMs = Math.min(2 * 60 * 60 * 1000, Math.max(20 * 60 * 1000, timeline.durationMs * 0.25));
    return timeline.elapsedMs <= windowMs ? text : null;
}
function recentRainAftermath(season, weather, locationId) {
    if (weather === 'rain' || !['market_street', 'craft_street', 'north_outskirts', 'old_bridge'].includes(locationId))
        return null;
    const bucket = Math.floor(Date.now() / (3 * 3_600_000));
    const previousRain = hash100(bucket - 1, season, 'qinghe-weather') < (season === 'лето' ? 24 : season === 'весна' ? 20 : 16);
    return previousRain ? 'В колеях ещё стоит вода после недавнего дождя.' : null;
}
async function activeMove(client, lifeId, lock = false) {
    const r = await client.query(`select * from open_life_moves where life_id=$1 and status='active' order by created_at desc limit 1${lock ? ' for update' : ''}`, [lifeId]);
    return r.rows[0] ?? null;
}
async function activeActivity(client, lifeId, lock = false) {
    const r = await client.query(`select * from open_life_activities where life_id=$1 and status in ('active','situation') order by created_at desc limit 1${lock ? ' for update' : ''}`, [lifeId]);
    return r.rows[0] ?? null;
}
async function pausedActivityAtLocation(client, lifeId, locationId, lock = false) {
    const r = await client.query(`select * from open_life_activities where life_id=$1 and location_id=$2 and status='paused' order by updated_at desc limit 1${lock ? ' for update' : ''}`, [lifeId, locationId]);
    return r.rows[0] ?? null;
}
function activityElapsedSeconds(row) {
    const stored = Math.max(0, Number(row.elapsed_seconds ?? 0));
    if (row.status !== 'active' || !row.segment_started_at)
        return stored;
    return stored + Math.max(0, Math.floor((nowMs() - asMs(row.segment_started_at)) / 1000));
}
function activityTotalSeconds(row, def) {
    return Math.max(1, Number(row.total_duration_seconds ?? Math.round(def.durationSeconds * config.ACTION_TIME_SCALE)));
}
function activityStage(def, elapsed, total) {
    if (!def.stages?.length)
        return null;
    const progress = Math.max(0, Math.min(1, elapsed / Math.max(1, total)));
    let cursor = 0;
    for (let index = 0; index < def.stages.length; index++) {
        const stage = def.stages[index];
        const start = cursor;
        cursor += stage.share;
        if (progress < cursor || index === def.stages.length - 1) {
            return { stage, index, startFraction: start, endFraction: cursor };
        }
    }
    return null;
}
function effectiveInterrupt(def, row) {
    const elapsed = activityElapsedSeconds(row), total = activityTotalSeconds(row, def), stage = activityStage(def, elapsed, total);
    return {
        policy: stage?.stage.interruptPolicy ?? def.interruptPolicy,
        preview: stage?.stage.interruptPreview ?? def.interruptPreview,
        stage,
        elapsed,
        total,
        progress: Math.max(0, Math.min(1, elapsed / Math.max(1, total)))
    };
}
async function addSkillPractice(client, life, skillId, practiceUnits) {
    // Internal scale: one full practice unit = 100. The player never sees these numbers.
    // Keeping fractional progress as integers prevents the old exploit where 45% of a lesson
    // granted almost the same progression as completing it.
    const units = Math.max(0, Math.floor(practiceUnits));
    if (units <= 0)
        return null;
    const current = await client.query(`select level from life_skills where life_id=$1 and skill_id=$2 for update`, [life.id, skillId]);
    const level = Number(current.rows[0]?.level ?? 0);
    if (level >= 3)
        return null;
    const pr = await client.query(`insert into life_skill_practice(life_id,skill_id,practice_points) values($1,$2,$3) on conflict(life_id,skill_id) do update set practice_points=life_skill_practice.practice_points+$3 returning practice_points`, [life.id, skillId, units]);
    let practice = Number(pr.rows[0].practice_points);
    const threshold = [300, 500, 800][level] ?? 999999;
    if (practice >= threshold) {
        practice -= threshold;
        const next = Math.min(3, level + 1);
        await client.query(`insert into life_skills(life_id,skill_id,level) values($1,$2,1) on conflict(life_id,skill_id) do update set level=least(3,life_skills.level+1)`, [life.id, skillId]);
        await client.query(`update life_skill_practice set practice_points=$3 where life_id=$1 and skill_id=$2`, [life.id, skillId, practice]);
        return next;
    }
    return null;
}
async function applyActivityRewards(client, life, row, def) {
    const wasTired = Boolean(await getPersonalState(client, life.id, 'conditions', 'tired'));
    const wasRested = Boolean(await getPersonalState(client, life.id, 'conditions', 'rested'));
    if (def.money > 0) {
        const next = Math.max(0, life.money + def.money);
        life.money = next;
        await client.query(`update lives set money=$1 where id=$2`, [next, life.id]);
    }
    let actualHeal = 0;
    if (def.heal) {
        const before = life.health;
        const next = Math.min(life.max_health, before + def.heal);
        actualHeal = Math.max(0, next - before);
        life.health = next;
        if (next !== before)
            await client.query(`update lives set health=$1 where id=$2`, [next, life.id]);
    }
    const newSkillLevel = def.skill ? await addSkillPractice(client, life, def.skill, (def.practice ?? 1) * 100) : null;
    if (def.kind === 'REST') {
        await client.query(`delete from life_state where life_id=$1 and scope='PERSONAL' and target_id='conditions' and state_key='tired'`, [life.id]);
        if (def.id === 'rest_home')
            await setPersonalState(client, life, 'conditions', 'rested', { active: true, acquiredAt: new Date().toISOString() });
    }
    if (def.kind === 'WORK' || def.kind === 'PRACTICE')
        await setPersonalState(client, life, 'conditions', 'tired', { active: true, acquiredAt: new Date().toISOString() });
    if (def.kind === 'TREATMENT')
        await setPersonalState(client, life, 'conditions', 'under_treatment', { active: false, endedAt: new Date().toISOString() });
    if (def.pausedItemId)
        await removeWorkpiece(client, life, def.pausedItemId, def.locationId);
    const result = { money: Math.max(0, def.money), cost: def.money < 0 ? Math.abs(def.money) : 0, heal: actualHeal, skill: def.skill ?? null, newSkillLevel, text: def.completedText ?? null };
    await client.query(`update open_life_activities set status='completed',elapsed_seconds=coalesce(total_duration_seconds,elapsed_seconds),segment_started_at=null,result=$2,updated_at=now() where id=$1`, [row.id, result]);
    await client.query(`insert into open_life_activity_history(life_id,activity_id,location_id,result) values($1,$2,$3,$4)`, [life.id, def.id, def.locationId, result]);
    const details = { completedAt: new Date(row.completes_at).toISOString(), recapEligible: true };
    if (def.money > 0)
        details.money = def.money;
    if (def.money < 0)
        details.cost = Math.abs(def.money);
    if (actualHeal > 0)
        details.heal = actualHeal;
    if ((def.kind === 'WORK' || def.kind === 'PRACTICE') && !wasTired)
        details.state = 'Уставший';
    if (def.kind === 'REST' && def.id === 'rest_home' && !wasRested)
        details.state = 'Отдохнувший';
    if (newSkillLevel && def.skill) {
        details.skillName = skillDisplayName(def.skill);
        details.skillStage = skillDisplayStage(newSkillLevel);
    }
    await pushOpenNotice(client, life, { kind: def.kind.toLowerCase(), title: activityNoticeTitle(def), message: def.completedText ?? `${def.name} завершено.`, details });
    await analyticsOpen(client, life, 'open_activity_completed', { activityId: def.id, locationId: def.locationId, kind: def.kind, newSkillLevel });
}
async function finalizeTimedState(client, life) {
    let changed = false;
    const move = await activeMove(client, life.id, true);
    if (move && asMs(move.completes_at) <= nowMs()) {
        const destination = move.turning_back ? move.from_location_id : move.to_location_id;
        life.current_location_id = destination;
        await client.query(`update open_life_moves set status='completed',updated_at=now() where id=$1 and status='active'`, [move.id]);
        await client.query(`update lives set current_location_id=$1,updated_at=now() where id=$2`, [destination, life.id]);
        await client.query(`insert into life_locations(life_id,location_id,state,discovered_world_day,first_visited_world_day) values($1,$2,'visited',$3,$3) on conflict(life_id,location_id) do update set state='visited',first_visited_world_day=coalesce(life_locations.first_visited_world_day,excluded.first_visited_world_day)`, [life.id, destination, life.current_world_day]);
        await analyticsOpen(client, life, 'open_move_completed', { from: move.from_location_id, to: destination, turnedBack: Boolean(move.turning_back) });
        changed = true;
    }
    const activity = await activeActivity(client, life.id, true);
    if (activity && activity.status === 'active' && asMs(activity.completes_at) <= nowMs()) {
        const def = openLifeContent.activity(activity.activity_id);
        const total = activityTotalSeconds(activity, def);
        activity.elapsed_seconds = total;
        await client.query(`update open_life_activities set elapsed_seconds=$2,segment_started_at=null,stage_id=null,updated_at=now() where id=$1`, [activity.id, total]);
        if (def.situationId) {
            const history = await client.query(`select count(*)::int c from open_life_activity_history where life_id=$1 and activity_id=$2`, [life.id, def.id]);
            const count = Number(history.rows[0]?.c ?? 0);
            if ((count + 1) % 3 === 0) {
                await client.query(`update open_life_activities set status='situation',pending_situation_id=$2,updated_at=now() where id=$1 and status='active'`, [activity.id, def.situationId]);
                await analyticsOpen(client, life, 'open_professional_situation', { activityId: def.id, situationId: def.situationId, locationId: def.locationId });
            }
            else
                await applyActivityRewards(client, life, activity, def);
        }
        else
            await applyActivityRewards(client, life, activity, def);
        changed = true;
    }
    if (changed)
        await bump(client, life);
    return changed;
}
function npcCurrentLocation(npc, availabilityBucket, period, event) {
    if (npc.id === 'sun_qi' && event.id === 'flood')
        return 'old_bridge';
    if (npc.id === 'mao_jie' && period === 'day' && availabilityBucket % 5 === 0)
        return 'market_street';
    if (npc.id === 'luo_shan') {
        if (event.id === 'luo_injured')
            return 'north_outskirts';
        if (period === 'day' && availabilityBucket % 4 === 1)
            return null; // ушёл к силкам
    }
    if (npc.id === 'he_ren' && period !== 'evening' && period !== 'night' && availabilityBucket % 3 !== 0)
        return null;
    if (period === 'night' && ['zhang_bo', 'madam_yan', 'luo_shan', 'sun_qi'].includes(npc.id))
        return null;
    return npc.primaryLocation;
}
function absentNpcAmbient(locationId, period, npcLocations) {
    const lines = [];
    if (locationId === 'craft_street' && npcLocations.get('zhang_bo') !== 'craft_street' && period === 'night')
        lines.push('В кузнице темно. Сегодня здесь уже закончили работу.');
    if (locationId === 'yan_courtyard' && npcLocations.get('madam_yan') !== 'yan_courtyard')
        lines.push('Во дворе сейчас никого нет.');
    if (locationId === 'north_outskirts' && npcLocations.get('luo_shan') !== 'north_outskirts' && period === 'day')
        lines.push('Ло Шаня сейчас не видно. Он мог уйти к северным силкам.');
    if (locationId === 'three_willows' && npcLocations.get('mao_jie') !== 'three_willows')
        lines.push('Мао Цзе сейчас не за стойкой.');
    return lines;
}
async function visibleNpcTopics(client, life, npc, skills, knowledge, event) {
    const anomaly = await anomalyCount(client, life.id);
    const out = [];
    const states = await client.query(`select topic_id,available_after from npc_topic_state where life_id=$1 and npc_id=$2`, [life.id, npc.id]);
    const cooldowns = new Map(states.rows.map((r) => [String(r.topic_id), r.available_after ? new Date(r.available_after).getTime() : 0]));
    for (const t of npc.topics) {
        if (t.requiresKnowledge && knowledge.get(t.requiresKnowledge.topic) !== t.requiresKnowledge.stage)
            continue;
        if (t.requiresWorldEvent && event.id !== t.requiresWorldEvent)
            continue;
        if (t.requiresSkillMin && (skills[t.requiresSkillMin.skill] ?? 0) < t.requiresSkillMin.level)
            continue;
        if (t.requiresSkillMax && (skills[t.requiresSkillMax.skill] ?? 0) > t.requiresSkillMax.level)
            continue;
        if (t.requiresHealthBelowMax && life.health >= life.max_health)
            continue;
        if (t.requiresAnomalyCount != null && anomaly < t.requiresAnomalyCount)
            continue;
        if (t.requiresItem && !(await hasCarriedItem(client, life.id, t.requiresItem)))
            continue;
        if ((cooldowns.get(t.id) ?? 0) > Date.now())
            continue;
        out.push({ id: t.id, label: t.label });
    }
    return out;
}
function actionAvailable(action, skills) {
    if (action.requiresSkillMin && (skills[action.requiresSkillMin.skill] ?? 0) < action.requiresSkillMin.level)
        return false;
    if (action.requiresSkillMax && (skills[action.requiresSkillMax.skill] ?? 0) > action.requiresSkillMax.level)
        return false;
    return true;
}
function microSceneFor(locationId, availabilityBucket) {
    const loc = openLifeContent.location(locationId);
    const list = loc.microScenes ?? [];
    if (!list.length)
        return null;
    const key = hash100(locationId, availabilityBucket, 'micro');
    return key < 32 ? list[key % list.length] : null;
}
function unknownTravellerName(lifeId) {
    const variants = ['Незнакомый путник', 'Путник в дорожной одежде', 'Путник в выцветшей куртке', 'Путник с плетёной корзиной'];
    return variants[hash100(lifeId, 'appearance') % variants.length];
}
function playerVisibleDescription(skills) {
    const entries = Object.entries(skills).sort((a, b) => b[1] - a[1]);
    const top = entries[0];
    if (!top || top[1] <= 0)
        return 'Молодой человек в простой городской одежде. По виду трудно понять, чем он занимается.';
    if (top[0] === 'blacksmithing')
        return 'На рукавах и ладонях заметны мелкие следы угольной пыли.';
    if (top[0] === 'herbalism')
        return 'От одежды едва заметно пахнет сушёными травами. В руках плетёная корзина.';
    if (top[0] === 'tracking')
        return 'Одежда удобна для дороги, а обувь испачкана землёй с северных троп.';
    if (top[0] === 'trade')
        return 'Одежда аккуратная и неброская. При нём небольшая сумка для мелких вещей.';
    return 'Путник в простой городской одежде.';
}
async function playerCardData(client, lifeId, locationId) {
    const r = await client.query(`select l.id,l.character_name,l.current_world_day,l.birth_world_day from lives l where l.id=$1 and l.alive=true`, [lifeId]);
    if (!r.rows[0])
        throw new HttpError(404, 'player_not_found', 'Player not found');
    const skills = await getSkills(client, lifeId);
    const row = r.rows[0];
    const equipmentLines = await visibleEquipmentDescription(client, lifeId);
    let activityLine = '';
    const ar = await client.query(`select activity_id,activity_kind from open_life_activities where life_id=$1 and location_id=$2 and status in ('active','situation') order by created_at desc limit 1`, [lifeId, locationId]);
    if (ar.rows[0]) {
        const def = openLifeContent.activities.get(String(ar.rows[0].activity_id));
        if (def?.kind === 'WORK' && def.locationId === 'craft_street')
            activityLine = 'Сейчас занят у горна.';
        else if (def?.kind === 'WORK' && def.locationId === 'yan_courtyard')
            activityLine = 'Сейчас помогает во дворе госпожи Янь.';
        else if (def?.kind === 'WORK' && def.locationId === 'market_street')
            activityLine = 'Сейчас занят работой на рынке.';
        else if (def?.kind === 'PRACTICE' && def.locationId === 'north_outskirts')
            activityLine = 'Сейчас занят с охотничьими снастями.';
        else if (def?.kind === 'WORK')
            activityLine = 'Сейчас занят работой неподалёку.';
    }
    const description = [playerVisibleDescription(skills), ...equipmentLines, activityLine].filter(Boolean).join(' ');
    return { id: row.id, name: row.character_name || unknownTravellerName(lifeId), ageYears: Math.max(0, Math.floor((Number(row.current_world_day) - Number(row.birth_world_day)) / 365)), description, locationId };
}
async function markPresence(client, life, moving) {
    if (moving) {
        await client.query(`delete from open_life_presence where life_id=$1`, [life.id]);
        return;
    }
    await client.query(`insert into open_life_presence(life_id,location_id,last_seen_at) values($1,$2,now()) on conflict(life_id) do update set location_id=excluded.location_id,last_seen_at=now()`, [life.id, life.current_location_id]);
}
async function getPersonalState(client, lifeId, targetId, key) {
    const r = await client.query(`select value,updated_world_day from life_state where life_id=$1 and scope='PERSONAL' and target_id=$2 and state_key=$3`, [lifeId, targetId, key]);
    return r.rows[0] ?? null;
}
async function setPersonalState(client, life, targetId, key, value, openWorldDay) {
    await client.query(`insert into life_state(life_id,scope,target_id,state_key,value,updated_world_day) values($1,'PERSONAL',$2,$3,$4,$5) on conflict(life_id,scope,target_id,state_key) do update set value=excluded.value,updated_world_day=excluded.updated_world_day`, [life.id, targetId, key, value, openWorldDay ?? life.current_world_day]);
}
async function clearRested(client, lifeId) {
    await client.query(`delete from life_state where life_id=$1 and scope='PERSONAL' and target_id='conditions' and state_key='rested'`, [lifeId]);
}
function resolveBoarState(lifeId, locationId, wd, availabilityBucket) {
    if (!openLifeContent.grove.boar.locations.includes(locationId))
        return 'none';
    const seasonBucket = Math.floor(wd / 91);
    const score = hash100(lifeId, locationId, seasonBucket, availabilityBucket, 'boar');
    const thresholds = locationId === 'grove_deep' ? [50, 68, 81, 91] : locationId === 'grove_stream' ? [58, 77, 88, 96] : [52, 72, 84, 94];
    if (score < thresholds[0])
        return 'none';
    if (score < thresholds[1])
        return 'tracks';
    if (score < thresholds[2])
        return 'sound';
    if (score < thresholds[3])
        return 'distant';
    return 'danger';
}
async function boarAvoided(client, life, locationId, availabilityBucket) {
    const s = await getPersonalState(client, life.id, locationId, 'boar_avoided');
    return Number(s?.value?.availabilityBucket ?? -1) === availabilityBucket;
}
async function boarRecentlyResolved(client, life, locationId) {
    const r = await client.query(`select 1 from combat_sessions where life_id=$1 and travel_id is null and status<>'active' and combat_flags->>'returnLocationId'=$2 and updated_at>now()-interval '1 hour' limit 1`, [life.id, locationId]);
    return Boolean(r.rows[0]);
}
async function resourceView(client, life, loc, skills, wd) {
    const actions = [];
    const depleted = [];
    for (const r of loc.resources ?? []) {
        if (r.skill && (skills[r.skill] ?? 0) < (r.minLevel ?? 0))
            continue;
        const state = await getPersonalState(client, life.id, loc.id, `resource:${r.id}`);
        const last = state ? Number(state.updated_world_day) : -Infinity;
        if (wd - last >= r.cooldownWorldDays)
            actions.push({ id: `resource:${r.id}`, label: r.label, kind: 'resource' });
        else
            depleted.push(r.depletedText);
    }
    return { actions, depleted };
}
function perceptionView(loc, skills, skipIds) {
    const out = [];
    for (const group of loc.perceptionGroups ?? []) {
        if (skipIds.has(group.id))
            continue;
        const level = skills[group.skill] ?? 0;
        const candidate = [...group.levels].filter(x => x.minLevel <= level).sort((a, b) => b.minLevel - a.minLevel)[0];
        if (candidate)
            out.push({ id: group.id, text: candidate.text });
    }
    return out;
}
async function recentPlayerTrace(client, life, loc, availabilityBucket) {
    if (loc.kind !== 'wild' || hash100(life.id, loc.id, availabilityBucket, 'player-trace') > 55)
        return false;
    const r = await client.query(`select 1 from open_life_moves m where m.life_id<>$1 and m.status='completed' and (m.from_location_id=$2 or m.to_location_id=$2) and m.updated_at>now()-interval '15 minutes' limit 1`, [life.id, loc.id]);
    return Boolean(r.rows[0]);
}
function whitebackLayer(life, locId, wd, availabilityBucket, event, knowledge) {
    const g = openLifeContent.grove.whiteback;
    if (!g.locations.includes(locId))
        return null;
    const remembered = knowledge.get('whiteback') === 'witnessed' || knowledge.get('white_back') === 'witnessed';
    const contextBoost = event.id === 'whiteback_story' || event.id === 'animal_routes';
    const score = hash100(life.id, locId, Math.floor(wd / 91), availabilityBucket, event.id, 'whiteback');
    // Contextual rarity only. The player never sees these numbers and the creature is not a farmable encounter.
    if (score < (contextBoost ? 14 : 8))
        return { level: 1, text: g.level1[hash100(life.id, wd, locId, 'whiteback-l1') % g.level1.length] };
    if (score > 93 && score <= 96)
        return { level: 2, text: g.level2 };
    if (score > 98)
        return { level: 3, text: `${remembered ? `${g.remembered} ` : ''}${g.level3}` };
    return null;
}
async function personalLocationLayers(client, life, loc, wd, flags) {
    const lines = [];
    if (loc.id === 'home_qinghe' && life.health <= life.max_health - 20) {
        lines.push('Мать смотрит сначала на ваше лицо, потом на одежду. «Даже спрашивать не буду». Пауза. «Нет. Буду. Что случилось?»');
    }
    if (loc.id === 'grove_cart') {
        if (flags.has('grove_cart_examined'))
            lines.push('Верёвки больше нет. Остальное лежит так же, как вы его оставили.');
        const joined = Number(life.open_life_joined_world_day ?? wd);
        if (wd - joined >= 365)
            lines.push('Дерево потемнело от дождей. Один из бортов окончательно перекосился.');
    }
    return lines;
}
function hashUnit(...parts) {
    const h = crypto.createHash('sha256').update(parts.join('|')).digest();
    return h.readUInt32BE(0) / 0xffffffff;
}
function routeLocationTags(locationId, kind) {
    const tags = new Set([kind, kind === 'town' ? 'town' : 'grove']);
    const map = {
        home_qinghe: ['home'],
        market_street: ['market'],
        three_willows: ['tea'],
        craft_street: ['forge', 'craft'],
        yan_courtyard: ['healer', 'herbs'],
        old_bridge: ['bridge', 'river'],
        north_outskirts: ['north', 'outskirts', 'road'],
        east_gate: ['gate', 'road', 'east'],
        grove_edge: ['grove', 'edge', 'north'],
        grove_north_path: ['grove', 'north', 'road'],
        grove_stream: ['grove', 'stream', 'river'],
        grove_cart: ['grove', 'cart'],
        grove_deep: ['grove', 'deep_grove'],
        stone_gully: ['grove', 'ravine', 'deep_grove']
    };
    for (const tag of map[locationId] ?? [])
        tags.add(tag);
    return tags;
}
function travelRouteMatches(entry, fromId, toId) {
    if (!entry.allowedRoutes?.length)
        return true;
    return entry.allowedRoutes.some(route => {
        if (route.includes('<>')) {
            const [a, b] = route.split('<>');
            return (a === fromId && b === toId) || (a === toId && b === fromId);
        }
        const [a, b] = route.split('>');
        return a === fromId && b === toId;
    });
}
function knowledgeRuleMatches(rule, knowledge) {
    const stage = knowledge.get(rule.topic) ?? knowledge.get(rule.topic === 'whiteback' ? 'white_back' : rule.topic === 'white_back' ? 'whiteback' : rule.topic);
    if (!stage)
        return false;
    return !rule.stages?.length || rule.stages.includes(stage);
}
function travelFlavorEligible(entry, ctx) {
    if (!travelRouteMatches(entry, ctx.from.id, ctx.to.id))
        return false;
    if (entry.minDuration != null && ctx.duration < entry.minDuration)
        return false;
    if (entry.maxDuration != null && ctx.duration > entry.maxDuration)
        return false;
    if (entry.periods?.length && !entry.periods.includes(ctx.period))
        return false;
    if (entry.seasons?.length && !entry.seasons.includes(ctx.season))
        return false;
    if (entry.weather?.length && !entry.weather.includes(ctx.weather))
        return false;
    if (entry.requiredWorldEvents?.length && !entry.requiredWorldEvents.includes(ctx.event.id))
        return false;
    if (entry.requiredSkills?.some(r => (ctx.skills[r.skill] ?? 0) < r.minLevel))
        return false;
    if (entry.requiredKnowledge?.some(r => !knowledgeRuleMatches(r, ctx.knowledge)))
        return false;
    if (entry.forbiddenKnowledge?.some(r => knowledgeRuleMatches(r, ctx.knowledge)))
        return false;
    if (entry.requiredFlagsAll?.some(flag => !ctx.flags.has(flag)))
        return false;
    if (entry.requiredFlagsAny?.length && !entry.requiredFlagsAny.some(flag => ctx.flags.has(flag)))
        return false;
    if (entry.forbiddenFlags?.some(flag => ctx.flags.has(flag)))
        return false;
    if (entry.locationTags?.length) {
        const routeTags = new Set([...routeLocationTags(ctx.from.id, ctx.from.kind), ...routeLocationTags(ctx.to.id, ctx.to.kind)]);
        if (!entry.locationTags.some(tag => routeTags.has(tag)))
            return false;
    }
    return true;
}
function travelFlavorCandidates(move, period, season, weather, skills, knowledge, flags, event) {
    const targetId = move.turning_back ? move.from_location_id : move.to_location_id;
    const routeFromId = move.turning_back ? move.to_location_id : move.from_location_id;
    const from = openLifeContent.location(routeFromId);
    const to = openLifeContent.location(targetId);
    const duration = Math.max(1, Number(move.leg_total_seconds ?? Math.ceil((asMs(move.completes_at) - asMs(move.started_at)) / 1000)));
    const eligible = [...openLifeContent.travelFlavor.values()].filter(entry => travelFlavorEligible(entry, { from, to, duration, period, season, weather, skills, knowledge, flags, event }));
    return eligible
        .map(entry => ({ entry, score: hashUnit(move.id, move.turning_back ? 'back' : 'forward', entry.id) / (entry.weight || 1) }))
        .sort((a, b) => a.score - b.score)
        .slice(0, 18)
        .map(({ entry }) => ({ id: entry.id, type: entry.type, text: entry.text, cooldownSeconds: entry.cooldownSeconds }));
}
async function recentRouteTravelFlavor(client, life, move, weather) {
    const a = move.from_location_id, b = move.to_location_id;
    const wild = openLifeContent.location(a).kind === 'wild' || openLifeContent.location(b).kind === 'wild';
    if (!wild || weather !== 'rain')
        return null;
    const r = await client.query(`select 1 from open_life_moves
     where life_id<>$1 and status='completed' and updated_at>now()-interval '12 minutes'
       and ((from_location_id=$2 and to_location_id=$3) or (from_location_id=$3 and to_location_id=$2))
     limit 1`, [life.id, a, b]);
    if (!r.rows[0])
        return null;
    return { id: `recent_route_trace:${[a, b].sort().join(':')}`, type: 'OBSERVATION', text: 'На размокшей дороге заметны свежие человеческие следы. Кто именно прошёл здесь, отсюда не понять.', cooldownSeconds: 1200 };
}
async function syncWorldEventMemory(client, life, event, wd) {
    // Remember the shared-world transition for server logic, but do not turn it into an
    // omniscient personal notification. The player learns world news from visible places,
    // NPCs, chat and other in-world channels.
    const state = await getPersonalState(client, life.id, 'world_meta', 'last_world_event');
    const previous = typeof state?.value?.id === 'string' ? String(state.value.id) : null;
    if (previous === event.id)
        return;
    await setPersonalState(client, life, 'world_meta', 'last_world_event', { id: event.id, changedAt: new Date().toISOString() }, wd);
}
export async function prepareOpenLife(client, life) {
    if (life.phase !== 'OPEN_LIFE' || life.mode !== 'FREE')
        return;
    const wd = await worldDay(client);
    await syncOpenLifeAge(client, life, wd);
    await finalizeTimedState(client, life);
    await syncWorldEventMemory(client, life, activeWorldEvent(wd), wd);
}
export async function buildOpenLifeScreen(client, life) {
    assertOpenLife(life);
    const wd = await worldDay(client);
    await syncOpenLifeAge(client, life, wd);
    await finalizeTimedState(client, life);
    const period = availabilityTime();
    const season = seasonFromContext();
    const weather = weatherFromContext(season);
    const event = activeWorldEvent(wd);
    const availabilityBucket = Math.floor(Date.now() / 3_600_000);
    await syncWorldEventMemory(client, life, event, wd);
    const move = await activeMove(client, life.id);
    const activity = await activeActivity(client, life.id);
    const pausedActivity = await pausedActivityAtLocation(client, life.id, life.current_location_id);
    const moving = Boolean(move);
    await markPresence(client, life, moving);
    const loc = openLifeContent.location(life.current_location_id);
    // While travelling, the old location must not continue to behave as if the player is still standing there.
    if (move) {
        const target = move.turning_back ? move.from_location_id : move.to_location_id;
        const skills = await getSkills(client, life.id);
        const knowledge = await getKnowledge(client, life.id);
        const flags = await getFlags(client, life.id);
        let flavor = travelFlavorCandidates(move, period.id, season, weather, skills, knowledge, flags, event);
        const routeTrace = await recentRouteTravelFlavor(client, life, move, weather);
        if (routeTrace)
            flavor = [routeTrace, ...flavor];
        return {
            type: 'OPEN_LIFE_LOCATION', location: { id: loc.id, name: loc.name, kind: loc.kind },
            time: { period: period.id, periodLabel: period.label, season, weather, worldDay: wd }, description: [], currentState: [], observations: [],
            familiarFaces: [], travelers: [], actions: [], exits: [], chat: { title: 'Разговоры рядом', enabled: false, messages: [] },
            activity: null, pausedActivity: null,
            move: { id: move.id, toLocationId: target, toName: openLifeContent.location(target).name, secondsRemaining: secondsRemaining(move.completes_at), totalSeconds: Math.max(1, Number(move.leg_total_seconds ?? Math.ceil((asMs(move.completes_at) - asMs(move.started_at)) / 1000))), turningBack: Boolean(move.turning_back), canTurnBack: !move.turning_back && Math.max(1, Number(move.leg_total_seconds ?? 0)) > 15, flavor }, situation: null
        };
    }
    const skills = await getSkills(client, life.id);
    const knowledge = await getKnowledge(client, life.id);
    const flags = await getFlags(client, life.id);
    const description = [...loc.base, weather === 'rain' && loc.ambient.rain ? loc.ambient.rain : loc.ambient[period.id]];
    const currentState = [];
    const eventText = event.locations[loc.id];
    if (eventText)
        currentState.push(eventText);
    const aftermathText = recentWorldAftermath(loc.id);
    if (aftermathText && !currentState.includes(aftermathText))
        currentState.push(aftermathText);
    const rainAftermath = recentRainAftermath(season, weather, loc.id);
    if (rainAftermath)
        currentState.push(rainAftermath);
    currentState.push(...await personalLocationLayers(client, life, loc, wd, flags));
    const micro = microSceneFor(loc.id, availabilityBucket);
    if (micro)
        currentState.push(micro.text);
    const resource = await resourceView(client, life, loc, skills, wd);
    currentState.push(...resource.depleted);
    const skipPerception = new Set();
    if (loc.id === 'grove_stream' && resource.depleted.some(Boolean))
        skipPerception.add('stream_plants');
    const observations = [
        ...(loc.observations ?? []).filter(o => (skills[o.skill] ?? 0) >= o.minLevel).map(o => ({ id: o.id, text: o.text, action: o.action })),
        ...perceptionView(loc, skills, skipPerception)
    ];
    if (await recentPlayerTrace(client, life, loc, availabilityBucket))
        observations.push({ id: 'recent_player_trace', text: openLifeContent.grove.recentPlayerTrace });
    const boar = resolveBoarState(life.id, loc.id, wd, availabilityBucket);
    const avoided = (await boarAvoided(client, life, loc.id, availabilityBucket)) || (await boarRecentlyResolved(client, life, loc.id));
    if (boar === 'tracks')
        observations.push({ id: 'boar_tracks', text: openLifeContent.grove.boar.texts.tracks });
    if (boar === 'sound')
        observations.push({ id: 'boar_sound', text: openLifeContent.grove.boar.texts.sound });
    if (boar === 'distant')
        observations.push({ id: 'boar_distant', text: openLifeContent.grove.boar.texts.distant });
    if (boar === 'danger' && !avoided) {
        if ((skills.tracking ?? 0) >= 2)
            observations.push({ id: 'boar_warning', text: openLifeContent.grove.boar.texts.trackingWarning, action: { id: 'avoid_boar', label: openLifeContent.grove.boar.texts.avoidLabel } });
        else
            observations.push({ id: 'boar_sound', text: openLifeContent.grove.boar.texts.sound });
    }
    if (openLifeContent.grove.silence.locations.includes(loc.id) && hash100(life.id, loc.id, wd, availabilityBucket, 'silence') > 92) {
        const t = openLifeContent.grove.silence.texts;
        const tracking = skills.tracking ?? 0;
        const line = tracking >= 2 ? t.tracking2 : tracking >= 1 ? t.tracking1 : t.base;
        observations.push({ id: 'wrong_silence', text: line });
        if (knowledge.get('whiteback') === 'witnessed' || knowledge.get('white_back') === 'witnessed')
            observations.push({ id: 'remembered_silence', text: t.remembered });
    }
    const routes = openLifeContent.grove.animalRoutes;
    if (event.id === routes.eventId && routes.locations.includes(loc.id) && (skills[routes.skill] ?? 0) >= routes.minLevel)
        observations.push({ id: 'changed_animal_routes', text: routes.text });
    const wb = whitebackLayer(life, loc.id, wd, availabilityBucket, event, knowledge);
    if (wb) {
        observations.push({ id: `whiteback_manifestation_${wb.level}`, text: wb.text });
        const seen = await getPersonalState(client, life.id, loc.id, `whiteback_manifestation:${availabilityBucket}:${wb.level}`);
        if (!seen) {
            await setPersonalState(client, life, loc.id, `whiteback_manifestation:${availabilityBucket}:${wb.level}`, { seen: true }, wd);
            await analyticsOpen(client, life, 'open_whiteback_manifestation', { locationId: loc.id, level: wb.level });
        }
    }
    const npcList = [];
    const npcLocations = new Map();
    for (const npc of openLifeContent.npcs.values()) {
        const npcLocation = npcCurrentLocation(npc, availabilityBucket, period.id, event);
        npcLocations.set(npc.id, npcLocation);
        if (npcLocation === loc.id)
            npcList.push({ id: npc.id, name: npc.name, description: npc.description, topics: await visibleNpcTopics(client, life, npc, skills, knowledge, event) });
    }
    currentState.push(...absentNpcAmbient(loc.id, period.id, npcLocations));
    const presence = await client.query(`select p.life_id from open_life_presence p where p.location_id=$1 and p.life_id<>$2 and p.last_seen_at>now()-($3::int*interval '1 second') order by p.last_seen_at desc limit 6`, [loc.id, life.id, config.PRESENCE_TTL_SECONDS]);
    const travelers = [];
    for (const row of presence.rows)
        travelers.push(await playerCardData(client, String(row.life_id), loc.id));
    const chatScope = loc.kind === 'town' ? 'qinghe_city' : loc.id;
    const chatScopes = loc.kind === 'town' ? [chatScope, ...[...openLifeContent.locations.values()].filter(location => location.kind === 'town').map(location => location.id)] : [chatScope];
    const chatRows = await client.query(`select m.id,m.life_id,m.message,m.created_at,l.character_name from local_chat_messages m join lives l on l.id=m.life_id where m.location_id=any($1::text[]) and m.created_at>now()-interval '6 hours' order by m.id desc limit 40`, [chatScopes]);
    const chat = chatRows.rows.reverse().map((r) => ({ id: Number(r.id), lifeId: String(r.life_id), name: r.character_name || unknownTravellerName(String(r.life_id)), message: String(r.message), createdAt: new Date(r.created_at).toISOString() }));
    const exits = activity ? [] : loc.exits.map(x => ({ ...x }));
    const actions = activity ? [] : loc.actions.filter(a => {
        if (a.kind === 'ambient')
            return false;
        if (a.kind === 'treatment' && life.health >= life.max_health)
            return false;
        if (a.requiresNpcId && !npcList.some(n => n.id === a.requiresNpcId))
            return false;
        if (!actionAvailable(a, skills))
            return false;
        return true;
    }).map(a => ({ id: a.id, label: a.label, kind: a.kind, activityId: a.activityId }));
    if (micro?.action && !activity)
        actions.push({ id: micro.action.id, label: micro.action.label, kind: 'micro', activityId: undefined });
    actions.push(...resource.actions);
    const situation = activity?.status === 'situation' && activity.pending_situation_id ? openLifeContent.situation(activity.pending_situation_id) : null;
    const activeDef = activity ? openLifeContent.activity(activity.activity_id) : null;
    const activeInterrupt = activity && activeDef ? effectiveInterrupt(activeDef, activity) : null;
    const pausedDef = pausedActivity ? openLifeContent.activity(pausedActivity.activity_id) : null;
    const pausedInfo = pausedActivity && pausedDef ? effectiveInterrupt(pausedDef, pausedActivity) : null;
    return {
        type: 'OPEN_LIFE_LOCATION', location: { id: loc.id, name: loc.name, kind: loc.kind },
        time: { period: period.id, periodLabel: period.label, season, weather, worldDay: wd }, description, currentState, observations,
        familiarFaces: npcList, travelers, actions, exits,
        chat: { title: loc.kind === 'town' ? 'Разговор в городе' : 'Разговоры рядом', enabled: true, messages: chat },
        activity: activity && activeDef && activeInterrupt ? {
            id: activity.id, name: activeDef.name, kind: activity.activity_kind, status: activity.status,
            secondsRemaining: activity.status === 'active' ? secondsRemaining(activity.completes_at) : 0,
            elapsedSeconds: activeInterrupt.elapsed, totalSeconds: activeInterrupt.total, progress: activeInterrupt.progress,
            completesAt: activity.status === 'active' ? new Date(activity.completes_at).toISOString() : null,
            interruptPolicy: activeInterrupt.policy, interruptPreview: activeInterrupt.preview,
            stage: activeInterrupt.stage ? { id: activeInterrupt.stage.stage.id, name: activeInterrupt.stage.stage.name, index: activeInterrupt.stage.index } : null
        } : null,
        pausedActivity: pausedActivity && pausedDef && pausedInfo ? {
            id: pausedActivity.id, name: pausedDef.name, kind: pausedActivity.activity_kind, status: 'paused', elapsedSeconds: pausedInfo.elapsed, totalSeconds: pausedInfo.total, progress: pausedInfo.progress,
            interruptPolicy: 'PAUSABLE', interruptPreview: pausedDef.interruptPreview,
            stage: pausedInfo.stage ? { id: pausedInfo.stage.stage.id, name: pausedInfo.stage.stage.name, index: pausedInfo.stage.index } : null,
            pauseExpiresAt: pausedActivity.pause_expires_at ? new Date(pausedActivity.pause_expires_at).toISOString() : null
        } : null,
        move: null,
        situation: situation ? { id: situation.id, title: situation.title, text: situation.text, choices: situation.choices.map(c => ({ id: c.id, label: c.label })) } : null
    };
}
function assertVersion(life, expected) { if (life.state_version !== expected)
    throw new HttpError(409, 'stale_game_state', 'Game state changed', { currentStateVersion: life.state_version }); }
async function bump(client, life) { life.state_version += 1; await client.query(`update lives set state_version=$1,updated_at=now() where id=$2`, [life.state_version, life.id]); }
async function already(client, id, playerId) { const r = await client.query(`select result from processed_actions where client_action_id=$1 and player_id=$2`, [id, playerId]); return r.rows[0]?.result ?? null; }
async function store(client, id, life, playerId, type, result) { await client.query(`insert into processed_actions(client_action_id,player_id,life_id,action_type,result) values($1,$2,$3,$4,$5)`, [id, playerId, life.id, type, result]); }
async function actionAck(life, extra = {}) { return { ok: true, stateVersion: life.state_version, ...extra }; }
async function startOpenBoarCombat(client, life, attemptedToLocationId) {
    const enemy = content.enemy('wild_boar');
    const result = await client.query(`insert into combat_sessions(life_id,travel_id,enemy_definition_id,content_version,player_hp,enemy_hp,enemy_state,enemy_intent,combat_flags) values($1,null,$2,$3,$4,$5,$6,$7,$8) returning id`, [
        life.id, enemy.id, life.content_version, life.health, enemy.maxHp, enemy.initialState, enemy.initialIntent,
        { openLife: true, returnLocationId: life.current_location_id, attemptedToLocationId, lastActionText: 'Вы подходите слишком близко. Кабан резко разворачивается, и между вами остаётся слишком мало места, чтобы просто разойтись.' }
    ]);
    life.mode = 'COMBAT';
    life.active_combat_id = String(result.rows[0].id);
    await client.query(`update lives set mode='COMBAT',active_combat_id=$1,updated_at=now() where id=$2`, [life.active_combat_id, life.id]);
    await client.query(`delete from open_life_presence where life_id=$1`, [life.id]);
    await analyticsOpen(client, life, 'open_combat_started', { enemyId: enemy.id, locationId: life.current_location_id, attemptedToLocationId });
}
export async function startOpenMove(playerId, toLocationId, actionId, expected) {
    return inTransaction(async (client) => {
        const prev = await already(client, actionId, playerId);
        if (prev)
            return prev;
        const life = await getLife(client, playerId, true);
        assertOpenLife(life);
        await prepareOpenLife(client, life);
        assertVersion(life, expected);
        if (await activeMove(client, life.id, true) || await activeActivity(client, life.id, true))
            throw new HttpError(409, 'open_life_busy', 'Another activity is already in progress');
        const loc = openLifeContent.location(life.current_location_id);
        const exit = loc.exits.find(x => x.to === toLocationId);
        if (!exit)
            throw new HttpError(409, 'move_unavailable', 'This transition is unavailable');
        const wd = await worldDay(client), bucket = Math.floor(Date.now() / 3_600_000);
        const boar = resolveBoarState(life.id, loc.id, wd, bucket);
        const dangerous = (openLifeContent.grove.boar.dangerousExits[loc.id] ?? []).includes(toLocationId);
        if (boar === 'danger' && dangerous && !(await boarAvoided(client, life, loc.id, bucket)) && !(await boarRecentlyResolved(client, life, loc.id))) {
            await startOpenBoarCombat(client, life, toLocationId);
            await bump(client, life);
            const result = await actionAck(life, { combatStarted: true });
            await store(client, actionId, life, playerId, 'open_move_encounter', result);
            return result;
        }
        const seconds = Math.max(2, Math.round(exit.seconds));
        await clearRested(client, life.id);
        await client.query(`insert into open_life_moves(life_id,from_location_id,to_location_id,completes_at,leg_total_seconds,turning_back) values($1,$2,$3,now()+($4::int*interval '1 second'),$4,false)`, [life.id, loc.id, toLocationId, seconds]);
        await client.query(`delete from open_life_presence where life_id=$1`, [life.id]);
        await analyticsOpen(client, life, 'open_move_started', { from: loc.id, to: toLocationId, seconds });
        await bump(client, life);
        const result = await actionAck(life);
        await store(client, actionId, life, playerId, 'open_move', result);
        return result;
    });
}
export async function startOpenActivity(playerId, activityId, actionId, expected) {
    return inTransaction(async (client) => {
        const prev = await already(client, actionId, playerId);
        if (prev)
            return prev;
        const life = await getLife(client, playerId, true);
        assertOpenLife(life);
        await prepareOpenLife(client, life);
        assertVersion(life, expected);
        if (await activeMove(client, life.id, true) || await activeActivity(client, life.id, true))
            throw new HttpError(409, 'open_life_busy', 'Another activity is already in progress');
        if (await pausedActivityAtLocation(client, life.id, life.current_location_id, true))
            throw new HttpError(409, 'paused_activity_exists', 'Finish or abandon the work already left here');
        const def = openLifeContent.activity(activityId);
        if (def.locationId !== life.current_location_id)
            throw new HttpError(409, 'activity_unavailable', 'This activity is unavailable here');
        const loc = openLifeContent.location(life.current_location_id);
        const skills = await getSkills(client, life.id);
        const action = loc.actions.find(a => a.activityId === activityId);
        if (!action || !actionAvailable(action, skills))
            throw new HttpError(409, 'activity_unavailable', 'This activity is unavailable here');
        if (action.requiresNpcId) {
            const wd = await worldDay(client), period = availabilityTime(), event = activeWorldEvent(wd), bucket = Math.floor(Date.now() / 3_600_000);
            const npc = openLifeContent.npc(action.requiresNpcId);
            if (npcCurrentLocation(npc, bucket, period.id, event) !== life.current_location_id)
                throw new HttpError(409, 'activity_unavailable', 'This activity is unavailable while the person you need is away');
        }
        if (def.money < 0 && life.money < Math.abs(def.money))
            throw new HttpError(409, 'not_enough_money', 'Not enough money');
        if (def.money < 0) {
            life.money -= Math.abs(def.money);
            await client.query(`update lives set money=$1 where id=$2`, [life.money, life.id]);
        }
        if (def.kind !== 'REST')
            await clearRested(client, life.id);
        if (def.kind === 'TREATMENT')
            await setPersonalState(client, life, 'conditions', 'under_treatment', { active: true, startedAt: new Date().toISOString() });
        const seconds = Math.max(5, Math.round(def.durationSeconds * config.ACTION_TIME_SCALE));
        const stageId = def.stages?.[0]?.id ?? null;
        await client.query(`insert into open_life_activities(life_id,activity_id,activity_kind,location_id,completes_at,interrupt_policy,total_duration_seconds,elapsed_seconds,segment_started_at,stage_id,stage_index,activity_state) values($1,$2,$3,$4,now()+($5::int*interval '1 second'),$6,$5,0,now(),$7,0,$8)`, [life.id, def.id, def.kind, def.locationId, seconds, def.interruptPolicy, stageId, { costPaid: def.money < 0 ? Math.abs(def.money) : 0 }]);
        await analyticsOpen(client, life, 'open_activity_started', { activityId: def.id, locationId: def.locationId, kind: def.kind, seconds, interruptPolicy: def.interruptPolicy });
        await bump(client, life);
        const result = await actionAck(life);
        await store(client, actionId, life, playerId, 'open_activity', result);
        return result;
    });
}
async function recordInterruptedActivity(client, life, row, def, result, status) {
    await client.query(`update open_life_activities set status=$2,result=$3,updated_at=now() where id=$1`, [row.id, status, result]);
    if (status !== 'paused')
        await client.query(`insert into open_life_activity_history(life_id,activity_id,location_id,result) values($1,$2,$3,$4)`, [life.id, def.id, def.locationId, result]);
    await analyticsOpen(client, life, status === 'paused' ? 'open_activity_paused' : 'open_activity_interrupted', { activityId: def.id, locationId: def.locationId, kind: def.kind, status, progress: result.progress, policy: result.policy });
}
function interruptionResultText(def, progress) {
    if (def.kind === 'REST') {
        if (progress < 0.25)
            return 'Вы немного перевели дух.';
        if (progress < 0.75)
            return 'Усталость немного отступила, но полноценного отдыха не получилось.';
        return 'Вы успели отдохнуть, но встали раньше, чем действительно восстановились.';
    }
    if (def.kind === 'TREATMENT') {
        if (progress < 0.35)
            return 'Лечение только началось. Вы уходите раньше, и его эффект будет заметно слабее.';
        if (progress < 0.8)
            return 'Часть лечения уже подействовала, но вы уходите раньше назначенного времени.';
        return 'Основная часть лечения уже завершена. Потеря от раннего ухода будет небольшой.';
    }
    return def.partialText ?? 'Вы заканчиваете раньше.';
}
export async function interruptOpenActivity(playerId, actionId, expected) {
    return inTransaction(async (client) => {
        const prev = await already(client, actionId, playerId);
        if (prev)
            return prev;
        const life = await getLife(client, playerId, true);
        assertOpenLife(life);
        await prepareOpenLife(client, life);
        assertVersion(life, expected);
        const row = await activeActivity(client, life.id, true);
        if (!row || row.status !== 'active')
            throw new HttpError(409, 'activity_missing', 'No active activity');
        const def = openLifeContent.activity(row.activity_id);
        const info = effectiveInterrupt(def, row);
        const elapsed = Math.min(info.total, info.elapsed);
        let text = interruptionResultText(def, info.progress);
        const noticeDetails = {};
        if (info.policy === 'PAUSABLE') {
            await client.query(`update open_life_activities set status='paused',elapsed_seconds=$2,segment_started_at=null,paused_at=now(),pause_expires_at=case when $3::int is null then null else now()+($3::int*interval '1 second') end,stage_id=$4,stage_index=$5,result=$6,updated_at=now() where id=$1`, [
                row.id, elapsed, def.pauseExpiresSeconds ?? null, info.stage?.stage.id ?? null, info.stage?.index ?? 0, { progress: info.progress, policy: info.policy, text }
            ]);
            if (def.pausedItemId)
                await createWorkpiece(client, life, def.pausedItemId, def.locationId, def.id);
            await analyticsOpen(client, life, 'open_activity_paused', { activityId: def.id, locationId: def.locationId, progress: info.progress, stage: info.stage?.stage.id ?? null });
        }
        else if (info.policy === 'RISKY' && def.stages && def.pausedItemId && info.stage) {
            const rollback = Math.max(0, Math.floor(info.stage.startFraction * info.total));
            text = `${def.partialText ?? 'Работа остановлена.'} ${info.preview}`;
            await client.query(`update open_life_activities set status='paused',elapsed_seconds=$2,segment_started_at=null,paused_at=now(),stage_id=$3,stage_index=$4,result=$5,updated_at=now() where id=$1`, [
                row.id, rollback, info.stage.stage.id, info.stage.index, { progress: rollback / info.total, policy: info.policy, text, rolledBackFrom: elapsed }
            ]);
            await createWorkpiece(client, life, def.pausedItemId, def.locationId, def.id);
            await analyticsOpen(client, life, 'open_activity_paused_risky', { activityId: def.id, locationId: def.locationId, fromElapsed: elapsed, toElapsed: rollback, stage: info.stage.stage.id });
        }
        else {
            let heal = 0, practice = 0;
            if (def.kind === 'REST' && def.heal) {
                heal = Math.max(0, Math.floor(def.heal * info.progress));
            }
            if (def.kind === 'TREATMENT' && def.heal) {
                heal = Math.max(0, Math.floor(def.heal * info.progress * 0.75));
            }
            if (def.skill && def.practice && info.progress > 0) {
                practice = Math.floor(def.practice * 100 * info.progress);
                await addSkillPractice(client, life, def.skill, practice);
            }
            if (heal > 0) {
                life.health = Math.min(life.max_health, life.health + heal);
                await client.query(`update lives set health=$1 where id=$2`, [life.health, life.id]);
                noticeDetails.heal = heal;
            }
            if (def.kind === 'REST' && info.progress >= 0.5)
                await client.query(`delete from life_state where life_id=$1 and scope='PERSONAL' and target_id='conditions' and state_key='tired'`, [life.id]);
            const result = { progress: info.progress, policy: info.policy, heal, practice, money: 0, text };
            await client.query(`update open_life_activities set status='cancelled',elapsed_seconds=$2,segment_started_at=null,result=$3,updated_at=now() where id=$1`, [row.id, elapsed, result]);
            await client.query(`insert into open_life_activity_history(life_id,activity_id,location_id,result) values($1,$2,$3,$4)`, [life.id, def.id, def.locationId, result]);
            await analyticsOpen(client, life, 'open_activity_interrupted', { activityId: def.id, locationId: def.locationId, kind: def.kind, progress: info.progress, policy: info.policy, heal, practice });
        }
        if (def.kind === 'TREATMENT')
            await setPersonalState(client, life, 'conditions', 'under_treatment', { active: false, endedAt: new Date().toISOString() });
        const noticeTitle = info.policy === 'PAUSABLE' || (info.policy === 'RISKY' && def.pausedItemId) ? 'Работа отложена' : def.kind === 'REST' ? 'Отдых прерван' : def.kind === 'TREATMENT' ? 'Лечение прервано' : 'Занятие прервано';
        await pushOpenNotice(client, life, { kind: def.kind.toLowerCase(), title: noticeTitle, message: text, details: noticeDetails });
        await bump(client, life);
        const result = await actionAck(life, { resultText: text });
        await store(client, actionId, life, playerId, 'open_activity_interrupt', result);
        return result;
    });
}
export async function resumeOpenActivity(playerId, activityRowId, actionId, expected) {
    return inTransaction(async (client) => {
        const prev = await already(client, actionId, playerId);
        if (prev)
            return prev;
        const life = await getLife(client, playerId, true);
        assertOpenLife(life);
        await prepareOpenLife(client, life);
        assertVersion(life, expected);
        if (await activeMove(client, life.id, true) || await activeActivity(client, life.id, true))
            throw new HttpError(409, 'open_life_busy', 'Another activity is already in progress');
        const r = await client.query(`select * from open_life_activities where id=$1 and life_id=$2 and location_id=$3 and status='paused' for update`, [activityRowId, life.id, life.current_location_id]);
        const row = r.rows[0];
        if (!row)
            throw new HttpError(404, 'paused_activity_missing', 'Paused activity not found here');
        if (row.pause_expires_at && asMs(row.pause_expires_at) <= nowMs()) {
            await client.query(`update open_life_activities set status='abandoned',updated_at=now() where id=$1`, [row.id]);
            const def = openLifeContent.activity(row.activity_id);
            if (def.pausedItemId)
                await removeWorkpiece(client, life, def.pausedItemId, def.locationId);
            throw new HttpError(409, 'paused_activity_expired', 'This work can no longer be continued');
        }
        const def = openLifeContent.activity(row.activity_id);
        const total = activityTotalSeconds(row, def), elapsed = Math.min(total, Number(row.elapsed_seconds ?? 0)), remaining = Math.max(2, total - elapsed);
        const stage = activityStage(def, elapsed, total);
        await client.query(`update open_life_activities set status='active',segment_started_at=now(),completes_at=now()+($2::int*interval '1 second'),paused_at=null,pause_expires_at=null,stage_id=$3,stage_index=$4,updated_at=now() where id=$1`, [row.id, remaining, stage?.stage.id ?? null, stage?.index ?? 0]);
        await analyticsOpen(client, life, 'open_activity_resumed', { activityId: def.id, locationId: def.locationId, elapsed, total });
        await bump(client, life);
        const result = await actionAck(life);
        await store(client, actionId, life, playerId, 'open_activity_resume', result);
        return result;
    });
}
export async function abandonPausedActivity(playerId, activityRowId, actionId, expected) {
    return inTransaction(async (client) => {
        const prev = await already(client, actionId, playerId);
        if (prev)
            return prev;
        const life = await getLife(client, playerId, true);
        assertOpenLife(life);
        await prepareOpenLife(client, life);
        assertVersion(life, expected);
        const r = await client.query(`select * from open_life_activities where id=$1 and life_id=$2 and location_id=$3 and status='paused' for update`, [activityRowId, life.id, life.current_location_id]);
        const row = r.rows[0];
        if (!row)
            throw new HttpError(404, 'paused_activity_missing', 'Paused activity not found here');
        const def = openLifeContent.activity(row.activity_id);
        await client.query(`update open_life_activities set status='abandoned',result=$2,updated_at=now() where id=$1`, [row.id, { text: 'Вы отказываетесь от незаконченной работы.', progress: Number(row.elapsed_seconds ?? 0) / Math.max(1, activityTotalSeconds(row, def)) }]);
        if (def.pausedItemId)
            await removeWorkpiece(client, life, def.pausedItemId, def.locationId);
        await analyticsOpen(client, life, 'open_activity_abandoned', { activityId: def.id, locationId: def.locationId });
        await pushOpenNotice(client, life, { kind: def.kind.toLowerCase(), title: 'Работа оставлена', message: 'Вы отказались от незаконченной работы. Оставшийся результат потерян.' });
        await bump(client, life);
        const result = await actionAck(life, { resultText: 'Незаконченная работа оставлена.' });
        await store(client, actionId, life, playerId, 'open_activity_abandon', result);
        return result;
    });
}
export async function turnBackOpenMove(playerId, actionId, expected) {
    return inTransaction(async (client) => {
        const prev = await already(client, actionId, playerId);
        if (prev)
            return prev;
        const life = await getLife(client, playerId, true);
        assertOpenLife(life);
        await prepareOpenLife(client, life);
        assertVersion(life, expected);
        const move = await activeMove(client, life.id, true);
        if (!move)
            throw new HttpError(409, 'move_missing', 'No active movement');
        if (move.turning_back)
            throw new HttpError(409, 'already_turning_back', 'You are already returning');
        const total = Math.max(1, Number(move.leg_total_seconds ?? Math.ceil((asMs(move.completes_at) - asMs(move.started_at)) / 1000)));
        const elapsed = Math.max(2, Math.min(total, Math.floor((nowMs() - asMs(move.started_at)) / 1000)));
        await client.query(`update open_life_moves set turning_back=true,started_at=now(),completes_at=now()+($2::int*interval '1 second'),leg_total_seconds=$2,updated_at=now() where id=$1`, [move.id, elapsed]);
        await analyticsOpen(client, life, 'open_move_turned_back', { from: move.from_location_id, toward: move.to_location_id, returnSeconds: elapsed });
        await bump(client, life);
        const result = await actionAck(life);
        await store(client, actionId, life, playerId, 'open_move_turn_back', result);
        return result;
    });
}
export async function resolveOpenSituation(playerId, choiceId, actionId, expected) {
    return inTransaction(async (client) => {
        const prev = await already(client, actionId, playerId);
        if (prev)
            return prev;
        const life = await getLife(client, playerId, true);
        assertOpenLife(life);
        await prepareOpenLife(client, life);
        assertVersion(life, expected);
        const row = await activeActivity(client, life.id, true);
        if (!row || row.status !== 'situation' || !row.pending_situation_id)
            throw new HttpError(409, 'situation_missing', 'No professional situation');
        const sit = openLifeContent.situation(row.pending_situation_id);
        const choice = sit.choices.find(c => c.id === choiceId);
        if (!choice)
            throw new HttpError(409, 'choice_unavailable', 'Choice unavailable');
        const baseDef = openLifeContent.activity(row.activity_id);
        const def = { ...baseDef };
        if (sit.id === 'oddjob_underpay' && choiceId === 'accept')
            def.money = Math.max(0, baseDef.money - 2);
        if (sit.id === 'oddjob_underpay' && choiceId === 'leave')
            def.money = 0;
        if (sit.id === 'herbalist_wrong_leaf' && choiceId === 'ask_yan')
            await client.query(`insert into life_relationships(life_id,npc_id,familiarity,updated_world_day) values($1,'madam_yan',1,$2) on conflict(life_id,npc_id) do update set familiarity=life_relationships.familiarity+1,updated_world_day=excluded.updated_world_day`, [life.id, life.current_world_day]);
        if (sit.id === 'blacksmith_crack' && choiceId === 'show')
            await client.query(`insert into life_relationships(life_id,npc_id,familiarity,updated_world_day) values($1,'zhang_bo',1,$2) on conflict(life_id,npc_id) do update set familiarity=life_relationships.familiarity+1,updated_world_day=excluded.updated_world_day`, [life.id, life.current_world_day]);
        await applyActivityRewards(client, life, row, def);
        await client.query(`update open_life_activity_history set result=result||$2::jsonb where id=(select id from open_life_activity_history where life_id=$1 order by id desc limit 1)`, [life.id, JSON.stringify({ situation: sit.id, choice: choiceId, resultText: choice.result ?? null })]);
        await analyticsOpen(client, life, 'open_professional_choice', { situationId: sit.id, choiceId, activityId: row.activity_id });
        await bump(client, life);
        const result = await actionAck(life, { resultText: choice.result ?? null });
        await store(client, actionId, life, playerId, 'open_situation', result);
        return result;
    });
}
export async function talkOpenNpc(playerId, npcId, topicId, actionId, expected) {
    return inTransaction(async (client) => {
        const prev = await already(client, actionId, playerId);
        if (prev)
            return prev;
        const life = await getLife(client, playerId, true);
        assertOpenLife(life);
        await prepareOpenLife(client, life);
        assertVersion(life, expected);
        if (await activeMove(client, life.id))
            throw new HttpError(409, 'open_life_busy', 'You are on the road');
        const wd = await worldDay(client), period = availabilityTime(), event = activeWorldEvent(wd), availabilityBucket = Math.floor(Date.now() / 3_600_000), npc = openLifeContent.npc(npcId);
        if (npcCurrentLocation(npc, availabilityBucket, period.id, event) !== life.current_location_id)
            throw new HttpError(409, 'npc_unavailable', 'This person is not here now');
        const skills = await getSkills(client, life.id), knowledge = await getKnowledge(client, life.id);
        const visible = await visibleNpcTopics(client, life, npc, skills, knowledge, event);
        if (!visible.some(x => x.id === topicId))
            throw new HttpError(409, 'topic_unavailable', 'This topic is unavailable');
        const topic = npc.topics.find(t => t.id === topicId);
        const state = await client.query(`select times_used,available_after from npc_topic_state where life_id=$1 and npc_id=$2 and topic_id=$3`, [life.id, npcId, topicId]);
        const times = Number(state.rows[0]?.times_used ?? 0);
        const repeat = times > 0 && topic.repeatLines;
        const lines = repeat ? topic.repeatLines : topic.lines;
        const cooldown = topic.cooldownMinutes ?? 10;
        await client.query(`insert into npc_topic_state(life_id,npc_id,topic_id,times_used,available_after,last_used_at) values($1,$2,$3,1,now()+($4::int*interval '1 minute'),now()) on conflict(life_id,npc_id,topic_id) do update set times_used=npc_topic_state.times_used+1,available_after=excluded.available_after,last_used_at=now()`, [life.id, npcId, topicId, cooldown]);
        await analyticsOpen(client, life, 'open_npc_talk', { npcId, topicId, locationId: life.current_location_id, repeat: Boolean(repeat) });
        await bump(client, life);
        const result = await actionAck(life, { dialogue: { npcId, npcName: npc.name, lines } });
        await store(client, actionId, life, playerId, 'open_talk', result);
        return result;
    });
}
export async function doOpenContextAction(playerId, action, actionId, expected) {
    return inTransaction(async (client) => {
        const prev = await already(client, actionId, playerId);
        if (prev)
            return prev;
        const life = await getLife(client, playerId, true);
        assertOpenLife(life);
        await prepareOpenLife(client, life);
        assertVersion(life, expected);
        if (await activeMove(client, life.id) || await activeActivity(client, life.id))
            throw new HttpError(409, 'open_life_busy', 'Another activity is already in progress');
        let resultText = null;
        if (action === 'catch_chicken' && life.current_location_id === 'market_street')
            resultText = '— Спасибо! Через минуту мальчик снова выпускает её.';
        else if (action === 'help_stuck_cart' && life.current_location_id === 'grove_north_path') {
            const equipped = await equippedItemIds(client, life.id);
            const hasRope = ['work_rope', 'rope'].includes(equipped.get('belt') ?? '');
            resultText = hasRope
                ? 'Вы закрепляете верёвку за раму. Втроём тележку удаётся вытащить из колеи без особой красоты, зато с первой попытки.'
                : 'Вы упираетесь плечом в борт. После нескольких попыток колесо наконец выходит из размокшей колеи. Советчик всё это время продолжает давать советы.';
            await analyticsOpen(client, life, 'open_micro_help', { locationId: life.current_location_id, microScene: 'stuck_cart', usedRope: hasRope });
        }
        else if (action === 'avoid_boar' && openLifeContent.grove.boar.locations.includes(life.current_location_id)) {
            const bucket = Math.floor(Date.now() / 3_600_000);
            const skills = await getSkills(client, life.id);
            const wd = await worldDay(client);
            if ((skills.tracking ?? 0) < 2 || resolveBoarState(life.id, life.current_location_id, wd, bucket) !== 'danger')
                throw new HttpError(409, 'action_unavailable', 'This action is unavailable');
            await setPersonalState(client, life, life.current_location_id, 'boar_avoided', { availabilityBucket: bucket }, wd);
            resultText = openLifeContent.grove.boar.texts.avoidResult;
            await analyticsOpen(client, life, 'open_boar_avoided', { locationId: life.current_location_id });
        }
        else if (action.startsWith('resource:')) {
            const resourceId = action.slice('resource:'.length);
            const loc = openLifeContent.location(life.current_location_id);
            const r = (loc.resources ?? []).find(x => x.id === resourceId);
            if (!r)
                throw new HttpError(409, 'action_unavailable', 'This resource is unavailable');
            const skills = await getSkills(client, life.id);
            if (r.skill && (skills[r.skill] ?? 0) < (r.minLevel ?? 0))
                throw new HttpError(409, 'action_unavailable', 'This resource is unavailable');
            const wd = await worldDay(client);
            const state = await getPersonalState(client, life.id, loc.id, `resource:${r.id}`);
            if (state && wd - Number(state.updated_world_day) < r.cooldownWorldDays)
                throw new HttpError(409, 'action_unavailable', 'This resource has not recovered yet');
            await addItem(client, life, r.itemId, r.quantity, { source: `resource:${loc.id}:${r.id}` });
            await setPersonalState(client, life, loc.id, `resource:${r.id}`, { collected: true }, wd);
            const item = content.items.get(r.itemId);
            const equipped = await equippedItemIds(client, life.id);
            const basket = equipped.get('carry') === 'herbalist_basket';
            resultText = basket && ['ironwort', 'unknown_silver_herb'].includes(r.itemId)
                ? `Вы аккуратно укладываете ${item?.name ?? r.itemId} в корзину, не сминая листья.`
                : `Вы забираете с собой: ${item?.name ?? r.itemId} ×${r.quantity}.`;
            await analyticsOpen(client, life, 'open_resource_collected', { locationId: loc.id, resourceId: r.id, itemId: r.itemId, quantity: r.quantity });
            await pushOpenNotice(client, life, { kind: 'finding', title: 'Находка', message: resultText, details: { itemName: item?.name ?? r.itemId, quantity: r.quantity } });
        }
        else
            throw new HttpError(409, 'action_unavailable', 'This action is unavailable');
        await bump(client, life);
        const result = await actionAck(life, { resultText });
        await store(client, actionId, life, playerId, 'open_context', result);
        return result;
    });
}
export async function postLocalChat(playerId, message) {
    return inTransaction(async (client) => {
        const life = await getLife(client, playerId, true);
        assertOpenLife(life);
        await prepareOpenLife(client, life);
        if (await activeMove(client, life.id))
            throw new HttpError(409, 'chat_unavailable', 'You cannot speak in a location while travelling');
        const clean = message.trim().replace(/\s+/g, ' ');
        if (!clean)
            throw new HttpError(400, 'chat_empty', 'Message is empty');
        if (clean.length > 300)
            throw new HttpError(400, 'chat_too_long', 'Message is too long');
        const recent = await client.query(`select created_at from local_chat_messages where life_id=$1 order by id desc limit 1`, [life.id]);
        if (recent.rows[0] && Date.now() - new Date(recent.rows[0].created_at).getTime() < 1500)
            throw new HttpError(429, 'chat_rate_limited', 'Please wait before sending another message');
        const loc = openLifeContent.location(life.current_location_id);
        const chatScope = loc.kind === 'town' ? 'qinghe_city' : loc.id;
        await markPresence(client, life, false);
        await client.query(`insert into local_chat_messages(location_id,life_id,message) values($1,$2,$3)`, [chatScope, life.id, clean]);
        await analyticsOpen(client, life, 'open_local_chat', { locationId: life.current_location_id, length: clean.length });
        return { ok: true };
    });
}
export async function getOpenPlayerCard(playerId, targetLifeId) {
    return inTransaction(async (client) => {
        const life = await getLife(client, playerId);
        assertOpenLife(life);
        await prepareOpenLife(client, life);
        if (await activeMove(client, life.id))
            throw new HttpError(409, 'player_unavailable', 'You are travelling');
        const p = await client.query(`select 1 from open_life_presence where life_id=$1 and location_id=$2 and last_seen_at>now()-($3::int*interval '1 second')`, [targetLifeId, life.current_location_id, config.PRESENCE_TTL_SECONDS]);
        if (!p.rows[0])
            throw new HttpError(404, 'player_not_here', 'This traveller is no longer here');
        return playerCardData(client, targetLifeId, life.current_location_id);
    });
}
export async function readOpenNotices(playerId, noticeIds) {
    if (!noticeIds.length)
        return { ok: true };
    return inTransaction(async (client) => {
        const life = await getLife(client, playerId);
        await client.query(`update open_life_notices set read_at=now() where life_id=$1 and id=any($2::bigint[]) and read_at is null`, [life.id, noticeIds]);
        return { ok: true };
    });
}
export async function openLifeRefresh(playerId) {
    return inTransaction(async (client) => { const life = await getLife(client, playerId); assertOpenLife(life); return { screen: await buildOpenLifeScreen(client, life), life }; });
}

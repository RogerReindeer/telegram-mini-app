import { Router } from 'express';
import { z } from 'zod';
import { requireAuth } from '../auth/middleware.js';
import { asyncRoute } from '../utils/http.js';
import { equipOpenItem, unequipOpenItem, storeOpenItem, retrieveOpenItem, storeOpenStack, retrieveOpenStack } from '../services/materialityService.js';
import { bootstrap, chooseEvent, chooseTravel, combatAction, logSessionEnded, resetDevLife, logUiEvent } from '../services/gameService.js';
import { startOpenMove, turnBackOpenMove, startOpenActivity, interruptOpenActivity, resumeOpenActivity, abandonPausedActivity, resolveOpenSituation, talkOpenNpc, postLocalChat, getOpenPlayerCard, doOpenContextAction, readOpenNotices } from '../services/openLifeService.js';
export const gameRouter = Router();
gameRouter.use(requireAuth);
const actionBase = z.object({
    client_action_id: z.string().uuid(),
    expected_state_version: z.number().int().positive()
});
gameRouter.get('/bootstrap', asyncRoute(async (req, res) => {
    res.json(await bootstrap(req.auth.playerId));
}));
gameRouter.post('/event/choose', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ choice_id: z.string().min(1) }).parse(req.body);
    res.json(await chooseEvent(req.auth.playerId, body.choice_id, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/travel/choose', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ choice_id: z.string().min(1) }).parse(req.body);
    res.json(await chooseTravel(req.auth.playerId, body.choice_id, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/combat/action', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ action: z.string().min(1) }).parse(req.body);
    res.json(await combatAction(req.auth.playerId, body.action, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/ui-event', asyncRoute(async (req, res) => {
    const body = z.object({ event: z.enum(['journal_opened', 'inventory_opened', 'world_opened', 'hero_opened']) }).parse(req.body);
    await logUiEvent(req.auth.playerId, body.event);
    res.status(204).end();
}));
gameRouter.post('/session/end', asyncRoute(async (req, res) => {
    const body = z.object({ reason: z.string().default('client_hidden') }).parse(req.body ?? {});
    await logSessionEnded(req.auth.playerId, body.reason);
    res.status(204).end();
}));
gameRouter.post('/dev/reset', asyncRoute(async (req, res) => {
    res.json(await resetDevLife(req.auth.playerId));
}));
gameRouter.post('/open-life/move', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ to_location_id: z.string().min(1) }).parse(req.body);
    res.json(await startOpenMove(req.auth.playerId, body.to_location_id, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/open-life/move/turn-back', asyncRoute(async (req, res) => {
    const body = actionBase.parse(req.body);
    res.json(await turnBackOpenMove(req.auth.playerId, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/open-life/activity/start', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ activity_id: z.string().min(1) }).parse(req.body);
    res.json(await startOpenActivity(req.auth.playerId, body.activity_id, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/open-life/activity/interrupt', asyncRoute(async (req, res) => {
    const body = actionBase.parse(req.body);
    res.json(await interruptOpenActivity(req.auth.playerId, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/open-life/activity/resume', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ activity_row_id: z.string().uuid() }).parse(req.body);
    res.json(await resumeOpenActivity(req.auth.playerId, body.activity_row_id, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/open-life/activity/abandon', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ activity_row_id: z.string().uuid() }).parse(req.body);
    res.json(await abandonPausedActivity(req.auth.playerId, body.activity_row_id, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/open-life/situation/choose', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ choice_id: z.string().min(1) }).parse(req.body);
    res.json(await resolveOpenSituation(req.auth.playerId, body.choice_id, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/open-life/npc/talk', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ npc_id: z.string().min(1), topic_id: z.string().min(1) }).parse(req.body);
    res.json(await talkOpenNpc(req.auth.playerId, body.npc_id, body.topic_id, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/open-life/context-action', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ action: z.string().min(1) }).parse(req.body);
    res.json(await doOpenContextAction(req.auth.playerId, body.action, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/items/equip', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ instance_id: z.string().uuid(), slot: z.enum(['outfit', 'outerwear', 'head', 'footwear', 'main_hand', 'off_hand', 'belt', 'carry']) }).parse(req.body);
    res.json(await equipOpenItem(req.auth.playerId, body.instance_id, body.slot, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/items/unequip', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ slot: z.enum(['outfit', 'outerwear', 'head', 'footwear', 'main_hand', 'off_hand', 'belt', 'carry']) }).parse(req.body);
    res.json(await unequipOpenItem(req.auth.playerId, body.slot, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/items/store', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ instance_id: z.string().uuid() }).parse(req.body);
    res.json(await storeOpenItem(req.auth.playerId, body.instance_id, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/items/retrieve', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ instance_id: z.string().uuid() }).parse(req.body);
    res.json(await retrieveOpenItem(req.auth.playerId, body.instance_id, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/items/stack/store', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ item_id: z.string().min(1), quantity: z.number().int().positive() }).parse(req.body);
    res.json(await storeOpenStack(req.auth.playerId, body.item_id, body.quantity, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/items/stack/retrieve', asyncRoute(async (req, res) => {
    const body = actionBase.extend({ item_id: z.string().min(1), quantity: z.number().int().positive() }).parse(req.body);
    res.json(await retrieveOpenStack(req.auth.playerId, body.item_id, body.quantity, body.client_action_id, body.expected_state_version));
}));
gameRouter.post('/open-life/notices/read', asyncRoute(async (req, res) => {
    const body = z.object({ ids: z.array(z.number().int().positive()).max(20) }).parse(req.body);
    res.json(await readOpenNotices(req.auth.playerId, body.ids));
}));
gameRouter.post('/open-life/chat', asyncRoute(async (req, res) => {
    const body = z.object({ message: z.string().min(1).max(300) }).parse(req.body);
    res.json(await postLocalChat(req.auth.playerId, body.message));
}));
gameRouter.get('/open-life/player/:lifeId', asyncRoute(async (req, res) => {
    res.json(await getOpenPlayerCard(req.auth.playerId, z.string().uuid().parse(req.params.lifeId)));
}));

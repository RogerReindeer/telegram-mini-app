import { z } from 'zod';

const originIds = ['blacksmith_family','herbalist_family','hunter_family','merchant_family'] as const;
const visualThemes = ['rain','festival','night','work','tea','rooftops','home','grove','forge','herbs','outskirts','market','sickroom'] as const;
const guidedSlots = [
  'BIRTH','ORIGIN','EARLY_CHILDHOOD','CHILDHOOD_FAMILY_EVENT','ADOLESCENT_ACTIVITY',
  'FIRST_WORLD_RUMOR','EARLY_ADULTHOOD','FIRST_INDEPENDENT_TRAVEL','FIRST_RETURN'
] as const;

const requirementsSchema = z.object({
  flagPresent: z.string().optional(),
  flagAbsent: z.string().optional(),
  flagsAll: z.array(z.string()).min(1).optional(),
  flagsNone: z.array(z.string()).min(1).optional(),
  skillMin: z.object({ skillId: z.string(), level: z.number().int().min(0).max(3) }).optional(),
  skillMax: z.object({ skillId: z.string(), level: z.number().int().min(0).max(3) }).optional(),
  originId: z.enum(originIds).optional(),
  originNot: z.enum(originIds).optional(),
  runFlagAbsent: z.string().optional()
}).optional();

const effectSchema: z.ZodTypeAny = z.discriminatedUnion('type', [
  z.object({ type: z.literal('SET_ORIGIN'), originId: z.union([z.enum(originIds), z.literal('RANDOM')]) }),
  z.object({ type: z.literal('ADD_FLAG'), flagId: z.string() }),
  z.object({ type: z.literal('SET_KNOWLEDGE'), topicId: z.string(), stage: z.string() }),
  z.object({ type: z.literal('SET_RUMOR'), rumorId: z.string(), state: z.string(), sourceNpcId: z.string().optional() }),
  z.object({ type: z.literal('CHANGE_MONEY'), amount: z.number().int() }),
  z.object({ type: z.literal('CHANGE_HEALTH'), amount: z.number().int() }),
  z.object({ type: z.literal('CHANGE_SKILL'), skillId: z.string(), amount: z.number().int() }),
  z.object({ type: z.literal('CHANGE_RELATIONSHIP'), npcId: z.string(), familiarity: z.number().int().optional(), status: z.string().optional() }),
  z.object({ type: z.literal('ADD_ITEM'), itemId: z.string(), quantity: z.number().int().positive(), originNote: z.string().optional() }),
  z.object({ type: z.literal('REMOVE_ITEM'), itemId: z.string(), quantity: z.number().int().positive() }),
  z.object({ type: z.literal('EQUIP_ITEM'), itemId: z.string(), slot: z.enum(['outfit','outerwear','head','footwear','main_hand','off_hand','belt','carry']) }),
  z.object({ type: z.literal('ADVANCE_TIME'), days: z.number().int().nonnegative() }),
  z.object({ type: z.literal('SET_LOCATION'), locationId: z.string() }),
  z.object({ type: z.literal('DISCOVER_LOCATION'), locationId: z.string(), state: z.enum(['known','visited']).optional() }),
  z.object({ type: z.literal('SET_STATE'), scope: z.enum(['PERSONAL','LOCAL','REGIONAL']), targetId: z.string(), key: z.string(), value: z.unknown() }),
  z.object({ type: z.literal('START_EVENT'), eventId: z.string(), carryGuidedSlot: z.boolean().optional() }),
  z.object({ type: z.literal('START_TRAVEL'), locationId: z.string() }),
  z.object({ type: z.literal('START_COMBAT'), enemyId: z.string() })
]);

const biographySchema = z.object({
  importance: z.enum(['normal','major']),
  entry: z.string(),
  entryByOrigin: z.record(z.enum(originIds), z.string()).optional()
});

const conditionalBodySchema = z.object({
  requirements: requirementsSchema,
  body: z.array(z.string()).min(1)
});

export const eventSchema = z.object({
  id: z.string(),
  category: z.enum(['LIFE','GOAL','ANOMALY']),
  trigger: z.enum(['GUIDED','DIRECT','CONTEXTUAL','DIRECTOR']),
  title: z.string().optional(),
  titleByOrigin: z.record(z.enum(originIds), z.string()).optional(),
  body: z.array(z.string()),
  bodyByOrigin: z.record(z.enum(originIds), z.array(z.string())).optional(),
  bodyAdditions: z.array(conditionalBodySchema).optional(),
  visualTheme: z.enum(visualThemes).optional(),
  visualThemeByOrigin: z.record(z.enum(originIds), z.enum(visualThemes)).optional(),
  completeGuidedSlot: z.boolean().optional(),
  biography: biographySchema.optional(),
  choices: z.array(z.object({
    id: z.string(),
    label: z.string(),
    labelByOrigin: z.record(z.enum(originIds), z.string()).optional(),
    requirements: requirementsSchema,
    effects: z.array(effectSchema).optional(),
    effectsByOrigin: z.record(z.enum(originIds), z.array(effectSchema)).optional(),
    biography: biographySchema.optional()
  })).min(1)
});

const travelEffectSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('GO_TO_NODE'), nodeId: z.string() }),
  z.object({ type: z.literal('ADD_RUN_FLAG'), key: z.string(), value: z.unknown() }),
  z.object({ type: z.literal('ADD_TRAVEL_LOOT'), itemId: z.string(), quantity: z.number().int().positive() }),
  z.object({ type: z.literal('CHANGE_TRAVEL_HEALTH'), amount: z.number().int() }),
  z.object({ type: z.literal('START_COMBAT'), enemyId: z.string() }),
  z.object({ type: z.literal('RETURN_HOME'), reason: z.string().optional() }),
  z.object({ type: z.literal('ADD_FLAG'), flagId: z.string() }),
  z.object({ type: z.literal('SET_KNOWLEDGE'), topicId: z.string(), stage: z.string() }),
  z.object({ type: z.literal('SET_RUMOR'), rumorId: z.string(), state: z.string(), sourceNpcId: z.string().optional() })
]);

export const travelSchema = z.object({
  id: z.string(),
  title: z.string(),
  entryNodeId: z.string(),
  nodes: z.array(z.object({
    id: z.string(),
    title: z.string().optional(),
    body: z.array(z.string()),
    bodyByOrigin: z.record(z.enum(originIds), z.array(z.string())).optional(),
    bodyAdditions: z.array(conditionalBodySchema).optional(),
    choices: z.array(z.object({
      id: z.string(),
      label: z.string(),
      labelByOrigin: z.record(z.enum(originIds), z.string()).optional(),
      effects: z.array(travelEffectSchema),
      requirements: requirementsSchema,
      biography: biographySchema.optional()
    })).min(1)
  })).min(1)
});

export const enemySchema = z.object({
  id: z.string(),
  name: z.string(),
  maxHp: z.number().int().positive(),
  initialState: z.string(),
  initialIntent: z.string(),
  attackDamage: z.number().int().nonnegative(),
  chargeDamage: z.number().int().nonnegative(),
  defendedChargeDamage: z.number().int().nonnegative(),
  loot: z.array(z.object({ itemId: z.string(), quantity: z.number().int().positive() }))
});

export const guidedSchema = z.object({
  contentVersion: z.string(),
  slots: z.record(z.enum(guidedSlots), z.object({
    eventId: z.string(),
    nextSlot: z.enum(guidedSlots).optional(),
    opensLife: z.boolean().optional()
  }))
});

export const itemsSchema = z.array(z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().optional(),
  instance: z.boolean().optional().default(false),
  equipSlots: z.array(z.enum(['outfit','outerwear','head','footwear','main_hand','off_hand','belt','carry'])).optional(),
  visibleWhenEquipped: z.string().optional(),
  conditionable: z.boolean().optional().default(false),
  storyKind: z.enum(['normal','critical','evidence','temporary']).optional().default('normal'),
  protected: z.boolean().optional().default(false),
  tags: z.array(z.string()).optional().default([])
}));

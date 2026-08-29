export type LifePhase = 'GUIDED_LIFE' | 'OPEN_LIFE';
export type RuntimeMode = 'FREE' | 'EVENT' | 'TRAVEL' | 'COMBAT';

export type GuidedSlot =
  | 'BIRTH'
  | 'ORIGIN'
  | 'EARLY_CHILDHOOD'
  | 'CHILDHOOD_FAMILY_EVENT'
  | 'ADOLESCENT_ACTIVITY'
  | 'FIRST_WORLD_RUMOR'
  | 'EARLY_ADULTHOOD'
  | 'FIRST_INDEPENDENT_TRAVEL'
  | 'FIRST_RETURN';

export type OriginId = 'blacksmith_family' | 'herbalist_family' | 'hunter_family' | 'merchant_family';

export interface LifeRow {
  id: string;
  player_id: string;
  life_number: number;
  phase: LifePhase;
  mode: RuntimeMode;
  origin_id: OriginId | null;
  birth_world_day: number;
  current_world_day: number;
  biological_age_days: number;
  health: number;
  max_health: number;
  money: number;
  home_location_id: string;
  current_location_id: string;
  guided_slot: GuidedSlot;
  active_event_id: string | null;
  active_travel_id: string | null;
  active_combat_id: string | null;
  alive: boolean;
  content_version: string;
  pending_content_version: string | null;
  open_life_joined_world_day?: number | null;
  open_life_age_day_at_join?: number | null;
  open_life_world_time_normalized?: boolean;
  character_name?: string | null;
  state_version: number;
}

export interface ContentRequirements {
  flagPresent?: string;
  flagAbsent?: string;
  flagsAll?: string[];
  flagsNone?: string[];
  skillMin?: { skillId: string; level: number };
  skillMax?: { skillId: string; level: number };
  originId?: OriginId;
  originNot?: OriginId;
  runFlagAbsent?: string;
}

export type GameEffect =
  | { type: 'SET_ORIGIN'; originId: OriginId | 'RANDOM' }
  | { type: 'ADD_FLAG'; flagId: string }
  | { type: 'SET_KNOWLEDGE'; topicId: string; stage: string }
  | { type: 'SET_RUMOR'; rumorId: string; state: string; sourceNpcId?: string }
  | { type: 'CHANGE_MONEY'; amount: number }
  | { type: 'CHANGE_HEALTH'; amount: number }
  | { type: 'CHANGE_SKILL'; skillId: string; amount: number }
  | { type: 'CHANGE_RELATIONSHIP'; npcId: string; familiarity?: number; status?: string }
  | { type: 'ADD_ITEM'; itemId: string; quantity: number; originNote?: string }
  | { type: 'REMOVE_ITEM'; itemId: string; quantity: number }
  | { type: 'EQUIP_ITEM'; itemId: string; slot: 'outfit'|'outerwear'|'head'|'footwear'|'main_hand'|'off_hand'|'belt'|'carry' }
  | { type: 'ADVANCE_TIME'; days: number }
  | { type: 'SET_LOCATION'; locationId: string }
  | { type: 'DISCOVER_LOCATION'; locationId: string; state?: 'known' | 'visited' }
  | { type: 'SET_STATE'; scope: 'PERSONAL' | 'LOCAL' | 'REGIONAL'; targetId: string; key: string; value: unknown }
  | { type: 'START_EVENT'; eventId: string; carryGuidedSlot?: boolean }
  | { type: 'START_TRAVEL'; locationId: string }
  | { type: 'START_COMBAT'; enemyId: string };

export interface BiographyDefinition {
  importance: 'normal' | 'major';
  entry: string;
  entryByOrigin?: Partial<Record<OriginId, string>>;
}

export interface ConditionalBody {
  requirements?: ContentRequirements;
  body: string[];
}

export interface EventChoice {
  id: string;
  label: string;
  labelByOrigin?: Partial<Record<OriginId, string>>;
  requirements?: ContentRequirements;
  effects?: GameEffect[];
  effectsByOrigin?: Partial<Record<OriginId, GameEffect[]>>;
  biography?: BiographyDefinition;
}

export type VisualTheme = 'rain' | 'festival' | 'night' | 'work' | 'tea' | 'rooftops' | 'home' | 'grove' | 'forge' | 'herbs' | 'outskirts' | 'market' | 'sickroom';

export interface EventDefinition {
  id: string;
  category: 'LIFE' | 'GOAL' | 'ANOMALY';
  trigger: 'GUIDED' | 'DIRECT' | 'CONTEXTUAL' | 'DIRECTOR';
  title?: string;
  titleByOrigin?: Partial<Record<OriginId, string>>;
  body: string[];
  bodyByOrigin?: Partial<Record<OriginId, string[]>>;
  bodyAdditions?: ConditionalBody[];
  visualTheme?: VisualTheme;
  visualThemeByOrigin?: Partial<Record<OriginId, VisualTheme>>;
  choices: EventChoice[];
  completeGuidedSlot?: boolean;
  biography?: BiographyDefinition;
}

export interface GuidedManifest {
  contentVersion: string;
  slots: Record<GuidedSlot, { eventId: string; nextSlot?: GuidedSlot; opensLife?: boolean }>;
}

export type TravelEffect =
  | { type: 'GO_TO_NODE'; nodeId: string }
  | { type: 'ADD_RUN_FLAG'; key: string; value: unknown }
  | { type: 'ADD_TRAVEL_LOOT'; itemId: string; quantity: number }
  | { type: 'CHANGE_TRAVEL_HEALTH'; amount: number }
  | { type: 'START_COMBAT'; enemyId: string }
  | { type: 'RETURN_HOME'; reason?: string }
  | { type: 'ADD_FLAG'; flagId: string }
  | { type: 'SET_KNOWLEDGE'; topicId: string; stage: string }
  | { type: 'SET_RUMOR'; rumorId: string; state: string; sourceNpcId?: string };

export interface TravelChoice {
  id: string;
  label: string;
  labelByOrigin?: Partial<Record<OriginId, string>>;
  effects: TravelEffect[];
  requirements?: ContentRequirements;
  biography?: BiographyDefinition;
}

export interface TravelNode {
  id: string;
  title?: string;
  body: string[];
  bodyByOrigin?: Partial<Record<OriginId, string[]>>;
  bodyAdditions?: ConditionalBody[];
  choices: TravelChoice[];
}

export interface TravelDefinition {
  id: string;
  title: string;
  entryNodeId: string;
  nodes: TravelNode[];
}

export interface EnemyDefinition {
  id: string;
  name: string;
  maxHp: number;
  initialState: string;
  initialIntent: string;
  attackDamage: number;
  chargeDamage: number;
  defendedChargeDamage: number;
  loot: Array<{ itemId: string; quantity: number }>;
}

// Icons for impact levels and change types. Kept out of lib/ so that lib/
// stays free of React and UI libraries.

import {
  Ban,
  BusFront,
  CircleDot,
  CircleSlash,
  Link,
  MapPinPlus,
  Timer,
  TrendingDown,
  TrendingUp,
  Unlink,
  X,
  type LucideIcon,
} from 'lucide-react'

import type { ImpactLevel } from '../lib/impact'
import type { ChangeType } from '../types/scenario'

export const IMPACT_ICONS: Record<ImpactLevel, LucideIcon> = {
  closed: CircleSlash,
  impossible: X,
  slower: TrendingUp,
  faster: TrendingDown,
  unaffected: CircleDot,
}

export const CHANGE_ICONS: Record<ChangeType, LucideIcon> = {
  close_stop: Ban,
  remove_connection: Unlink,
  change_travel_time: Timer,
  change_frequency: BusFront,
  add_connection: Link,
  add_stop: MapPinPlus,
}

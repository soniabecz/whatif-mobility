// Aliases for types generated from the backend's OpenAPI schema
// (backend/app/schemas/network.py). Regenerate with `npm run gen:types`.

import type { components } from './api.gen'

type Schemas = components['schemas']

export type Stop = Schemas['StopOut']
export type Route = Schemas['RouteOut']

/** A directed link between two consecutive stops on one route. */
export type Connection = Schemas['ConnectionOut']

export type Network = Schemas['NetworkOut']

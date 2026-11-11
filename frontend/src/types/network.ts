// Mirrors backend/app/schemas/network.py

export interface Stop {
  id: string
  name: string
  lat: number
  lon: number
}

export interface Route {
  id: string
  name: string
  color: string
}

/** A directed link between two consecutive stops on one route. */
export interface Connection {
  id: number
  route_id: string
  from_stop_id: string
  to_stop_id: string
  travel_time_min: number
}

export interface Network {
  stops: Stop[]
  routes: Route[]
  connections: Connection[]
}

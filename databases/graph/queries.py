"""
TransitFlow — Neo4j Graph Database Layer
=========================================
This module handles all queries to Neo4j.

GRAPH ROLE:
  - Model the dual transit network (city metro M1–M4 + national rail NR1–NR2)
  - Find fastest routes (Dijkstra by travel_time_min via APOC)
  - Find cheapest routes (Dijkstra by fare via APOC)
  - Find alternative routes avoiding a given station
  - Find cross-network interchange paths (metro → rail or rail → metro)
  - Show delay ripple: which stations are affected within N hops

STUDENT TASK
------------
Design your graph schema (node labels, relationship types, properties)
based on the data in train-mock-data/, seed it with skeleton/seed_neo4j.py,
then implement the query_ functions below.

Functions prefixed with `query_` are called by the agent (skeleton/agent.py).
"""

from __future__ import annotations

from typing import Optional

from neo4j import GraphDatabase

from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def _driver():
    """Return a Neo4j driver. Caller is responsible for closing."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


# ── Example ───────────────────────────────────────────────────────────────────
# The block below shows the query pattern: open a session, run Cypher, return data.

def example_count_nodes() -> int:
    """Example: count all nodes currently in the graph."""
    with _driver() as driver:
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS total")
            return result.single()["total"]

# TODO: Implement the query_ functions below.
# ─────────────────────────────────────────────────────────────────────────────


# ── FASTEST ROUTE (Dijkstra by travel_time_min) ───────────────────────────────

def query_shortest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
) -> dict:
    """
    Find the fastest path between two stations, minimising total travel time.

    Args:
        origin_id: Origin station ID, e.g. "MS01" or "NR01".
        destination_id: Destination station ID, e.g. "MS09" or "NR05".
        network: "metro", "rail", or "auto".

    Returns:
        dict with keys: found, origin_id, destination_id,
        total_time_min, path, legs.
    """
    network = (network or "auto").lower()

    if network not in {"auto", "metro", "rail", "national_rail"}:
        network = "auto"

    cypher = """
        MATCH (origin), (destination)
        WHERE origin.station_id = $origin_id
          AND destination.station_id = $destination_id
          AND (origin:MetroStation OR origin:NationalRailStation)
          AND (destination:MetroStation OR destination:NationalRailStation)
        
        // 呼叫 APOC Dijkstra 演算法 (以 travel_time_min 作為權重)
        CALL apoc.algo.dijkstra(
            origin, 
            destination, 
            'METRO_LINK|RAIL_LINK|INTERCHANGE_TO', 
            'travel_time_min'
        ) YIELD path, weight AS total_time_min
        
        RETURN 
            total_time_min, 
            nodes(path) AS path_nodes, 
            relationships(path) AS path_relationships
    """

    with _driver() as driver:
        with driver.session() as session:
            record = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
                network=network,
            ).single()

            if record is None:
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "total_time_min": None,
                    "path": [],
                    "legs": [],
                }

            path_nodes = record["path_nodes"]
            path_relationships = record["path_relationships"]

            stations = []

            for node in path_nodes:
                labels = list(node.labels)

                if "MetroStation" in labels:
                    network_type = "metro"
                elif "NationalRailStation" in labels:
                    network_type = "national_rail"
                else:
                    network_type = "unknown"

                stations.append(
                    {
                        "station_id": node.get("station_id"),
                        "name": node.get("name"),
                        "network_type": network_type,
                        "lines": node.get("lines", []),
                    }
                )

            legs = []

            for index, rel in enumerate(path_relationships):
                from_station = stations[index]
                to_station = stations[index + 1]

                travel_time_min = rel.get("travel_time_min")
                transfer_time_min = rel.get("transfer_time_min")

                legs.append(
                    {
                        "from_station_id": from_station["station_id"],
                        "from_name": from_station["name"],
                        "to_station_id": to_station["station_id"],
                        "to_name": to_station["name"],
                        "relationship_type": rel.type,
                        "line": rel.get("line"),
                        "travel_time_min": (
                            travel_time_min
                            if travel_time_min is not None
                            else transfer_time_min
                        ),
                    }
                )

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "total_time_min": record["total_time_min"],
                "path": stations,
                "legs": legs,
            }

# ── CHEAPEST ROUTE (Dijkstra by fare) ────────────────────────────────────────

def query_cheapest_route(
    origin_id: str,
    destination_id: str,
    network: str = "auto",
    fare_class: str = "standard",
) -> dict:
    """
    Find the cheapest path between two stations, minimising estimated fare.

    Args:
        origin_id: Origin station ID, e.g. "NR01" or "MS01".
        destination_id: Destination station ID, e.g. "NR05" or "MS09".
        network: "metro", "rail", or "auto".
        fare_class: "standard" or "first" for national rail estimates.

    Returns:
        dict with found, total_fare_usd, stations, and legs.
    """
    network = (network or "auto").lower()
    fare_class = (fare_class or "standard").lower()

    if network not in {"auto", "metro", "rail", "national_rail"}:
        network = "auto"

    if fare_class not in {"standard", "first"}:
        fare_class = "standard"

    cypher = """
        MATCH (origin), (destination)
        WHERE origin.station_id = $origin_id
          AND destination.station_id = $destination_id
          AND (origin:MetroStation OR origin:NationalRailStation)
          AND (destination:MetroStation OR destination:NationalRailStation)
        
        // 根據使用者選擇的艙等，動態決定要讀取哪一個票價屬性
        WITH origin, destination,
             CASE WHEN $fare_class = 'first' THEN 'first_class_fare_usd' 
                  ELSE 'standard_fare_usd' 
             END AS weight_property
        
        // 呼叫 APOC Dijkstra 演算法 (以票價作為權重)
        CALL apoc.algo.dijkstra(
            origin, 
            destination, 
            'METRO_LINK|RAIL_LINK|INTERCHANGE_TO', 
            weight_property
        ) YIELD path, weight AS total_fare_usd
        
        // 算出這條最便宜路線的總行駛時間
        WITH path, total_fare_usd,
             reduce(
                 total = 0, 
                 r IN relationships(path) | 
                 total + coalesce(r.travel_time_min, r.transfer_time_min, 0)
             ) AS total_time_min
        
        RETURN 
            total_fare_usd, 
            total_time_min, 
            nodes(path) AS path_nodes, 
            relationships(path) AS path_relationships
    """

    with _driver() as driver:
        with driver.session() as session:
            record = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
                network=network,
                fare_class=fare_class,
            ).single()

            if record is None:
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "total_fare_usd": None,
                    "total_time_min": None,
                    "stations": [],
                    "legs": [],
                }

            path_nodes = record["path_nodes"]
            path_relationships = record["path_relationships"]

            stations = []

            for node in path_nodes:
                labels = list(node.labels)

                if "MetroStation" in labels:
                    network_type = "metro"
                elif "NationalRailStation" in labels:
                    network_type = "national_rail"
                else:
                    network_type = "unknown"

                stations.append(
                    {
                        "station_id": node.get("station_id"),
                        "name": node.get("name"),
                        "network_type": network_type,
                        "lines": node.get("lines", []),
                    }
                )

            legs = []

            for index, rel in enumerate(path_relationships):
                from_station = stations[index]
                to_station = stations[index + 1]

                travel_time_min = rel.get("travel_time_min")
                transfer_time_min = rel.get("transfer_time_min")

                if rel.type == "INTERCHANGE_TO":
                    estimated_fare_usd = 0.0
                elif (
                    from_station["network_type"] == "metro"
                    and to_station["network_type"] == "metro"
                ):
                    estimated_fare_usd = 0.30
                elif (
                    from_station["network_type"] == "national_rail"
                    and to_station["network_type"] == "national_rail"
                    and fare_class == "first"
                ):
                    estimated_fare_usd = 3.00
                elif (
                    from_station["network_type"] == "national_rail"
                    and to_station["network_type"] == "national_rail"
                ):
                    estimated_fare_usd = 1.50
                else:
                    estimated_fare_usd = 0.0

                legs.append(
                    {
                        "from_station_id": from_station["station_id"],
                        "from_name": from_station["name"],
                        "to_station_id": to_station["station_id"],
                        "to_name": to_station["name"],
                        "relationship_type": rel.type,
                        "line": rel.get("line"),
                        "travel_time_min": (
                            travel_time_min
                            if travel_time_min is not None
                            else transfer_time_min
                        ),
                        "estimated_fare_usd": estimated_fare_usd,
                    }
                )

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "fare_class": fare_class,
                "total_fare_usd": round(float(record["total_fare_usd"]), 2),
                "total_time_min": record["total_time_min"],
                "stations": stations,
                "legs": legs,
            }
        
# ── ALTERNATIVE ROUTES (avoiding a station) ───────────────────────────────────

def query_alternative_routes(
    origin_id,
    destination_id,
    avoid_station_id,
    network="auto",
    max_routes=3,
) -> list[list[dict]]:
    """
    Find paths between two stations that avoid a specific intermediate station.
    Useful for routing around a delayed or closed station.

    Args:
        origin_id: Origin station ID, e.g. "NR01".
        destination_id: Destination station ID, e.g. "NR05".
        avoid_station_id: Station ID to avoid, e.g. "NR03".
        network: "metro", "rail", or "auto".
        max_routes: Maximum number of alternative routes to return.

    Returns:
        List of routes, each route is a list of leg dictionaries.
    """
    network = (network or "auto").lower()

    if network not in {"auto", "metro", "rail", "national_rail"}:
        network = "auto"

    safe_max_routes = max(1, min(int(max_routes), 10))

    if avoid_station_id in {origin_id, destination_id}:
        return []

    cypher = """
        MATCH (origin), (destination)
        WHERE origin.station_id = $origin_id
          AND destination.station_id = $destination_id
          AND (
                origin:MetroStation
                OR origin:NationalRailStation
              )
          AND (
                destination:MetroStation
                OR destination:NationalRailStation
              )
          AND (
                $network = 'auto'
                OR ($network = 'metro'
                    AND origin:MetroStation
                    AND destination:MetroStation)
                OR ($network IN ['rail', 'national_rail']
                    AND origin:NationalRailStation
                    AND destination:NationalRailStation)
              )

        MATCH path = (origin)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..8]-(destination)

        WHERE none(n IN nodes(path) WHERE n.station_id = $avoid_station_id)

          AND all(
                n IN nodes(path)
                WHERE single(m IN nodes(path) WHERE m.station_id = n.station_id)
              )

          AND (
                $network = 'auto'
                OR (
                    $network = 'metro'
                    AND all(n IN nodes(path) WHERE n:MetroStation)
                    AND all(r IN relationships(path) WHERE type(r) = 'METRO_LINK')
                )
                OR (
                    $network IN ['rail', 'national_rail']
                    AND all(n IN nodes(path) WHERE n:NationalRailStation)
                    AND all(r IN relationships(path) WHERE type(r) = 'RAIL_LINK')
                )
              )

        WITH
            path,
            reduce(
                total = 0,
                r IN relationships(path) |
                total +
                coalesce(r.travel_time_min, r.transfer_time_min, 0)
            ) AS total_time_min

        ORDER BY total_time_min ASC, length(path) ASC
        LIMIT $max_routes

        RETURN
            total_time_min,
            nodes(path) AS path_nodes,
            relationships(path) AS path_relationships
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
                avoid_station_id=avoid_station_id,
                network=network,
                max_routes=safe_max_routes,
            )

            routes = []

            for record in result:
                path_nodes = record["path_nodes"]
                path_relationships = record["path_relationships"]

                stations = []

                for node in path_nodes:
                    labels = list(node.labels)

                    if "MetroStation" in labels:
                        network_type = "metro"
                    elif "NationalRailStation" in labels:
                        network_type = "national_rail"
                    else:
                        network_type = "unknown"

                    stations.append(
                        {
                            "station_id": node.get("station_id"),
                            "name": node.get("name"),
                            "network_type": network_type,
                            "lines": node.get("lines", []),
                        }
                    )

                legs = []

                for index, rel in enumerate(path_relationships):
                    from_station = stations[index]
                    to_station = stations[index + 1]

                    travel_time_min = rel.get("travel_time_min")
                    transfer_time_min = rel.get("transfer_time_min")

                    leg_time = (
                        travel_time_min
                        if travel_time_min is not None
                        else transfer_time_min
                    )

                    legs.append(
                        {
                            "from_station_id": from_station["station_id"],
                            "from_name": from_station["name"],
                            "to_station_id": to_station["station_id"],
                            "to_name": to_station["name"],
                            "relationship_type": rel.type,
                            "line": rel.get("line"),
                            "travel_time_min": leg_time,
                            "total_route_time_min": record["total_time_min"],
                        }
                    )

                routes.append(legs)

            return routes


# ── CROSS-NETWORK INTERCHANGE PATH ───────────────────────────────────────────

def query_interchange_path(origin_id: str, destination_id: str) -> dict:
    """
    Find a path between a metro station and a national rail station,
    or vice versa, crossing the network boundary via interchange relationships.

    Args:
        origin_id: Origin station ID, e.g. "MS03" or "NR05".
        destination_id: Destination station ID, e.g. "NR05" or "MS09".

    Returns:
        dict with found, stations list, interchange points, and total_time_min.
    """
    cypher = """
        MATCH (origin), (destination)
        WHERE origin.station_id = $origin_id
          AND destination.station_id = $destination_id
          AND (
                origin:MetroStation
                OR origin:NationalRailStation
              )
          AND (
                destination:MetroStation
                OR destination:NationalRailStation
              )

        MATCH path = shortestPath((origin)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..20]-(destination))

        WHERE any(
            r IN relationships(path)
            WHERE type(r) = 'INTERCHANGE_TO'
        )

        WITH
            path,
            reduce(
                total = 0,
                r IN relationships(path) |
                total +
                coalesce(r.travel_time_min, r.transfer_time_min, 0)
            ) AS total_time_min

        ORDER BY total_time_min ASC, length(path) ASC
        LIMIT 1

        RETURN
            total_time_min,
            nodes(path) AS path_nodes,
            relationships(path) AS path_relationships
    """

    with _driver() as driver:
        with driver.session() as session:
            record = session.run(
                cypher,
                origin_id=origin_id,
                destination_id=destination_id,
            ).single()

            if record is None:
                return {
                    "found": False,
                    "origin_id": origin_id,
                    "destination_id": destination_id,
                    "stations": [],
                    "interchange_points": [],
                    "total_time_min": None,
                    "legs": [],
                }

            path_nodes = record["path_nodes"]
            path_relationships = record["path_relationships"]

            stations = []

            for node in path_nodes:
                labels = list(node.labels)

                if "MetroStation" in labels:
                    network_type = "metro"
                elif "NationalRailStation" in labels:
                    network_type = "national_rail"
                else:
                    network_type = "unknown"

                stations.append(
                    {
                        "station_id": node.get("station_id"),
                        "name": node.get("name"),
                        "network_type": network_type,
                        "lines": node.get("lines", []),
                    }
                )

            legs = []
            interchange_points = []

            for index, rel in enumerate(path_relationships):
                from_station = stations[index]
                to_station = stations[index + 1]

                travel_time_min = rel.get("travel_time_min")
                transfer_time_min = rel.get("transfer_time_min")

                leg_time = (
                    travel_time_min
                    if travel_time_min is not None
                    else transfer_time_min
                )

                relationship_type = rel.type

                legs.append(
                    {
                        "from_station_id": from_station["station_id"],
                        "from_name": from_station["name"],
                        "to_station_id": to_station["station_id"],
                        "to_name": to_station["name"],
                        "relationship_type": relationship_type,
                        "line": rel.get("line"),
                        "travel_time_min": leg_time,
                    }
                )

                if relationship_type == "INTERCHANGE_TO":
                    interchange_points.append(
                        {
                            "from_station_id": from_station["station_id"],
                            "from_name": from_station["name"],
                            "from_network_type": from_station["network_type"],
                            "to_station_id": to_station["station_id"],
                            "to_name": to_station["name"],
                            "to_network_type": to_station["network_type"],
                            "transfer_time_min": leg_time,
                        }
                    )

            return {
                "found": True,
                "origin_id": origin_id,
                "destination_id": destination_id,
                "stations": stations,
                "interchange_points": interchange_points,
                "total_time_min": record["total_time_min"],
                "legs": legs,
            }


# ── DELAY RIPPLE ANALYSIS ─────────────────────────────────────────────────────

def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]:
    """
    Find all stations within N hops of a delayed or disrupted station.
    Works on both metro and national rail networks.

    Args:
        delayed_station_id: Station ID, e.g. "NR03" or "MS01".
        hops: Number of graph connections outward to search.

    Returns:
        List of dicts: {station_id, name, hops_away, lines_affected}.
    """
    safe_hops = max(0, min(int(hops), 10))

    cypher = f"""
        MATCH (start)
        WHERE start.station_id = $delayed_station_id
          AND (
                start:MetroStation
                OR start:NationalRailStation
              )

        MATCH path = (start)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*0..{safe_hops}]-(affected)

        WHERE affected.station_id <> $delayed_station_id

        WITH
            affected,
            min(length(path)) AS hops_away,
            collect(path) AS paths

        RETURN
            affected.station_id AS station_id,
            affected.name AS name,
            labels(affected) AS labels,
            affected.lines AS station_lines,
            hops_away,
            paths
        ORDER BY
            hops_away,
            station_id
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                cypher,
                delayed_station_id=delayed_station_id,
            )

            affected_stations = []

            for record in result:
                labels = record["labels"] or []

                if "MetroStation" in labels:
                    network_type = "metro"
                elif "NationalRailStation" in labels:
                    network_type = "national_rail"
                else:
                    network_type = "unknown"

                lines_affected = set(record["station_lines"] or [])

                for path in record["paths"]:
                    for rel in path.relationships:
                        line = rel.get("line")
                        if line:
                            lines_affected.add(line)

                        if rel.type == "INTERCHANGE_TO":
                            lines_affected.add("interchange")

                affected_stations.append(
                    {
                        "station_id": record["station_id"],
                        "name": record["name"],
                        "network_type": network_type,
                        "hops_away": record["hops_away"],
                        "lines_affected": sorted(lines_affected),
                    }
                )

            return affected_stations
# ── STATION CONNECTIONS ───────────────────────────────────────────────────────
def query_station_connections(station_id: str) -> list[dict]:
    """
    List all direct connections from a given station.

    Args:
        station_id: Station ID, e.g. "MS01" or "NR01".

    Returns:
        List of direct connection dictionaries.
    """
    cypher = """
        MATCH (s)-[r:METRO_LINK|RAIL_LINK|INTERCHANGE_TO]-(neighbor)
        WHERE s.station_id = $station_id
          AND (
                s:MetroStation
                OR s:NationalRailStation
              )
        RETURN
            neighbor.station_id AS station_id,
            neighbor.name AS name,
            labels(neighbor) AS labels,
            neighbor.lines AS lines,
            type(r) AS relationship_type,
            r.line AS line,
            r.travel_time_min AS travel_time_min,
            r.transfer_time_min AS transfer_time_min
        ORDER BY
            relationship_type,
            line,
            station_id
    """

    with _driver() as driver:
        with driver.session() as session:
            result = session.run(cypher, station_id=station_id)

            connections = []

            for record in result:
                labels = record["labels"] or []

                if "MetroStation" in labels:
                    network_type = "metro"
                elif "NationalRailStation" in labels:
                    network_type = "national_rail"
                else:
                    network_type = "unknown"

                travel_time_min = (
                    record["travel_time_min"]
                    if record["travel_time_min"] is not None
                    else record["transfer_time_min"]
                )

                connections.append(
                    {
                        "station_id": record["station_id"],
                        "name": record["name"],
                        "network_type": network_type,
                        "labels": labels,
                        "lines": record["lines"] or [],
                        "relationship_type": record["relationship_type"],
                        "line": record["line"],
                        "travel_time_min": travel_time_min,
                    }
                )

            return connections
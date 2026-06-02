"""
TransitFlow — Neo4j Seeder
Run once after starting Docker:
    python skeleton/seed_neo4j.py

Loads station and network data from train-mock-data/:
  - metro_stations.json         — city metro stations and adjacencies
  - national_rail_stations.json — national rail stations and adjacencies

Design your graph schema (node labels, relationship types, properties)
based on the data in these files, then implement the seed() function below.
"""

import json
import os
import sys

sys.path.insert(0, ".")

from neo4j import GraphDatabase
from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "train-mock-data")
)


def _load(filename):
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def seed():
    metro_stations = _load("metro_stations.json")
    rail_stations  = _load("national_rail_stations.json")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:

        session.run("MATCH (n) DETACH DELETE n")
        print("  Cleared existing graph data")

        # 1. 建立 MetroStation 節點
        session.run("""
            UNWIND $stations AS s
            MERGE (m:MetroStation {station_id: s.station_id})
            SET m.name = s.name,
                m.lines = s.lines,
                m.is_interchange_metro = s.is_interchange_metro,
                m.is_interchange_national_rail = s.is_interchange_national_rail
        """, stations=metro_stations)
        print("  Created MetroStation nodes")

        # 2. 建立 NationalRailStation 節點
        session.run("""
            UNWIND $stations AS s
            MERGE (n:NationalRailStation {station_id: s.station_id})
            SET n.name = s.name,
                n.lines = s.lines,
                n.is_interchange_national_rail = s.is_interchange_national_rail,
                n.is_interchange_metro = s.is_interchange_metro
        """, stations=rail_stations)
        print("  Created NationalRailStation nodes")

        # 3. 建立 Metro 內部的 CONNECTED_TO 關係 (含 line 與 travel_time_min 屬性)
        session.run("""
            UNWIND $stations AS s
            MATCH (a:MetroStation {station_id: s.station_id})
            UNWIND s.adjacent_stations AS adj
            MATCH (b:MetroStation {station_id: adj.station_id})
            MERGE (a)-[r:CONNECTED_TO {line: adj.line, travel_time_min: adj.travel_time_min}]->(b)
        """, stations=metro_stations)
        print("  Created Metro CONNECTED_TO relationships")

        # 4. 建立 National Rail 內部的 CONNECTED_TO 關係 (含 line 與 travel_time_min 屬性)
        session.run("""
            UNWIND $stations AS s
            MATCH (a:NationalRailStation {station_id: s.station_id})
            UNWIND s.adjacent_stations AS adj
            MATCH (b:NationalRailStation {station_id: adj.station_id})
            MERGE (a)-[r:CONNECTED_TO {line: adj.line, travel_time_min: adj.travel_time_min}]->(b)
        """, stations=rail_stations)
        print("  Created National Rail CONNECTED_TO relationships")

        # 5. 建立跨系統轉乘的 INTERCHANGES_WITH 關係 (捷運 <-> 台鐵)
        # 根據 Schema 約定，加入預設屬性 transfer_time_min: 5
        session.run("""
            UNWIND $stations AS s
            WITH s WHERE s.is_interchange_national_rail = true AND s.interchange_national_rail_station_id IS NOT NULL
            MATCH (m:MetroStation {station_id: s.station_id})
            MATCH (n:NationalRailStation {station_id: s.interchange_national_rail_station_id})
            MERGE (m)-[:INTERCHANGES_WITH {transfer_time_min: 5}]->(n)
            MERGE (n)-[:INTERCHANGES_WITH {transfer_time_min: 5}]->(m)
        """, stations=metro_stations)
        print("  Created INTERCHANGES_WITH relationships (transfer_time_min: 5)")
        
        
    driver.close()
    print("\nNeo4j graph seeded successfully.")
    print("   Open http://localhost:7475 to explore the graph.")


if __name__ == "__main__":
    print("Connecting to Neo4j...")
    seed()

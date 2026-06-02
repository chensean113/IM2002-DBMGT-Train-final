# AI Session Context — TransitFlow

**How to use this file:**
At the start of every AI coding session, paste the full contents of this file as your first message to your AI assistant. This gives the AI the context it needs to produce code that fits your codebase and is consistent with your teammates' work.

**Who maintains this file:**
Whoever makes a schema change or architectural decision updates this file in the same commit. Treat it like a team contract.

---

## Project Overview

TransitFlow is a Python-based AI chat assistant for a fictional transit operator. It queries three databases — PostgreSQL (relational + vector), Neo4j (graph) — and uses an LLM to answer user questions. Our task as students is to design the database schema and implement the query functions in `databases/relational/queries.py` and `databases/graph/queries.py`.

## Tech Stack

- Language: Python 3.11+
- Relational DB: PostgreSQL via `psycopg2` with `RealDictCursor`
- Graph DB: Neo4j via the `neo4j` Python driver
- Vector search: `pgvector` extension (already implemented — do not modify)
- Web UI: Gradio
- LLM: Google Gemini or local Ollama (configured via `.env`)

## Coding Conventions

- **Naming:** `snake_case` for all Python names and SQL identifiers
- **Docstrings:** All functions must have a docstring with `Args:` and `Returns:` sections
- **Return types:** Use type hints. Read-only functions return `list[dict]` or `Optional[dict]`
- **Empty results:** Return `[]` or `None` (as documented), never raise an exception for "not found"
- **SQL:** Use `%s` placeholders for all user inputs — never string-format into SQL
- **Relational pattern:** Use `_connect()` helper + `psycopg2.extras.RealDictCursor`:
  ```python
  with _connect() as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
          cur.execute("SELECT ...", (param,))
          return [dict(row) for row in cur.fetchall()]
  ```
- **Graph pattern:** Use `_driver()` helper + session:
  ```python
  with _driver() as driver:
      with driver.session() as session:
          result = session.run("MATCH ...", station_id=station_id)
          return [dict(record) for record in result]
  ```

## Agreed Relational Schema

### Relational Schema Progress

- Current progress: PostgreSQL schema design is complete and has been merged into `main`; the active development branch is `feature/sean/seed-postgres`.
- Key decisions: keep the schema highly normalized, leave graph relationships to Neo4j, use `transaction_ref` for polymorphic relationships, and use `DEFERRABLE INITIALLY DEFERRED` to resolve the circular foreign key between metro and national rail stations.
- Next step: implement `seed_postgres.py` using the provided `insert_many` helper function (which already handles `ON CONFLICT DO NOTHING`) to load JSON data into PostgreSQL.

<!-- ============================================================
  FILL THIS IN after your team completes the schema design workshop.
  Paste your final CREATE TABLE statements here.
  ============================================================ -->

```sql
-- ============================================================
-- TransitFlow PostgreSQL Schema
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ------------------------------------------------------------
-- 1. Users 基礎個資表
CREATE TABLE users (
    user_id         VARCHAR(10) PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    full_name       TEXT NOT NULL,
    phone           VARCHAR(20) NOT NULL,
    date_of_birth   DATE NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

--  使用者密碼表 (與 users 表一對一關聯)
CREATE TABLE user_passwords (
    user_id         VARCHAR(10) PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    password        TEXT NOT NULL,
    salt            TEXT
);

--  使用者安全提示表 (與 users 表一對一關聯)
CREATE TABLE user_security_questions (
    user_id         VARCHAR(10) PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    secret_question TEXT NOT NULL,
    secret_answer   TEXT NOT NULL
);

-- ------------------------------------------------------------
-- 2. Station master data
-- ------------------------------------------------------------
CREATE TABLE metro_stations (
  station_id                           VARCHAR(10) PRIMARY KEY,
  name                                 TEXT NOT NULL,
  is_interchange_metro                 BOOLEAN NOT NULL DEFAULT FALSE,
  is_interchange_national_rail         BOOLEAN NOT NULL DEFAULT FALSE,
  interchange_national_rail_station_id VARCHAR(10)
);

CREATE TABLE national_rail_stations (
  station_id                   VARCHAR(10) PRIMARY KEY,
  name                         TEXT NOT NULL,
  is_interchange_national_rail BOOLEAN NOT NULL DEFAULT FALSE,
  is_interchange_metro         BOOLEAN NOT NULL DEFAULT FALSE,
  interchange_metro_station_id VARCHAR(10)
);

ALTER TABLE metro_stations
  ADD CONSTRAINT fk_metro_stations_interchange_rail
  FOREIGN KEY (interchange_national_rail_station_id)
  REFERENCES national_rail_stations(station_id)
  DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE national_rail_stations
  ADD CONSTRAINT fk_national_rail_stations_interchange_metro
  FOREIGN KEY (interchange_metro_station_id)
  REFERENCES metro_stations(station_id)
  DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE metro_station_lines (
  station_id VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id) ON DELETE CASCADE,
  line       VARCHAR(10) NOT NULL,
  PRIMARY KEY (station_id, line)
);

CREATE TABLE metro_station_adjacent_stations (
  station_id           VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id) ON DELETE CASCADE,
  adjacent_station_id  VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id) ON DELETE CASCADE,
  line                 VARCHAR(10) NOT NULL,
  travel_time_min      INTEGER NOT NULL CHECK (travel_time_min > 0),
  PRIMARY KEY (station_id, adjacent_station_id, line),
  CHECK (station_id <> adjacent_station_id)
);

CREATE TABLE national_rail_station_lines (
  station_id VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE CASCADE,
  line       VARCHAR(10) NOT NULL,
  PRIMARY KEY (station_id, line)
);

CREATE TABLE national_rail_station_adjacent_stations (
  station_id           VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE CASCADE,
  adjacent_station_id  VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE CASCADE,
  line                 VARCHAR(10) NOT NULL,
  travel_time_min      INTEGER NOT NULL CHECK (travel_time_min > 0),
  PRIMARY KEY (station_id, adjacent_station_id, line),
  CHECK (station_id <> adjacent_station_id)
);

-- ------------------------------------------------------------
-- 3. Schedules and fares
-- ------------------------------------------------------------
CREATE TABLE metro_schedules (
  schedule_id            VARCHAR(20) PRIMARY KEY,
  line                   TEXT NOT NULL,
  direction              TEXT NOT NULL,
  origin_station_id      VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id),
  destination_station_id VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id),
  first_train_time       TIME NOT NULL,
  last_train_time        TIME NOT NULL,
  base_fare_usd          NUMERIC(10,2) NOT NULL,
  per_stop_rate_usd      NUMERIC(10,2) NOT NULL,
  frequency_min          INTEGER NOT NULL CHECK (frequency_min > 0),
  CHECK (origin_station_id <> destination_station_id)
);

CREATE TABLE metro_schedule_stops (
  schedule_id                 VARCHAR(20) NOT NULL REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
  stop_order                  INTEGER NOT NULL CHECK (stop_order > 0),
  station_id                  VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id),
  travel_time_from_origin_min INTEGER NOT NULL CHECK (travel_time_from_origin_min >= 0),
  PRIMARY KEY (schedule_id, stop_order)
);

CREATE TABLE metro_schedule_operating_days (
  schedule_id VARCHAR(20) NOT NULL REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
  day_of_week VARCHAR(3) NOT NULL,
  PRIMARY KEY (schedule_id, day_of_week)
);

CREATE TABLE national_rail_schedules (
  schedule_id            VARCHAR(20) PRIMARY KEY,
  line                   TEXT NOT NULL,
  service_type           TEXT NOT NULL,
  direction              TEXT NOT NULL,
  origin_station_id      VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id),
  destination_station_id VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id),
  first_train_time       TIME NOT NULL,
  last_train_time        TIME NOT NULL,
  frequency_min          INTEGER NOT NULL CHECK (frequency_min > 0),
  CHECK (service_type IN ('normal', 'express')),
  CHECK (origin_station_id <> destination_station_id)
);

CREATE TABLE national_rail_schedule_stops (
  schedule_id                 VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
  stop_order                  INTEGER NOT NULL CHECK (stop_order > 0),
  station_id                  VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id),
  travel_time_from_origin_min INTEGER NOT NULL CHECK (travel_time_from_origin_min >= 0),
  PRIMARY KEY (schedule_id, stop_order)
);

CREATE TABLE national_rail_schedule_passed_through_stations (
  schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
  station_id  VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id),
  PRIMARY KEY (schedule_id, station_id)
);

CREATE TABLE national_rail_schedule_fares (
  schedule_id       VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
  fare_class        VARCHAR(20) NOT NULL,
  base_fare_usd     NUMERIC(10,2) NOT NULL,
  per_stop_rate_usd NUMERIC(10,2) NOT NULL,
  PRIMARY KEY (schedule_id, fare_class)
);

CREATE TABLE national_rail_schedule_operating_days (
  schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
  day_of_week VARCHAR(3) NOT NULL,
  PRIMARY KEY (schedule_id, day_of_week)
);

-- ------------------------------------------------------------
-- 4. National rail seating
-- ------------------------------------------------------------
CREATE TABLE national_rail_seat_layouts (
  layout_id   VARCHAR(20) PRIMARY KEY,
  schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE
);

CREATE TABLE national_rail_coaches (
  schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
  coach       VARCHAR(5) NOT NULL,
  layout_id   VARCHAR(20) NOT NULL REFERENCES national_rail_seat_layouts(layout_id) ON DELETE CASCADE,
  fare_class  TEXT NOT NULL,
  PRIMARY KEY (schedule_id, coach)
);

CREATE TABLE national_rail_seats (
  schedule_id VARCHAR(20) NOT NULL,
  coach       VARCHAR(5) NOT NULL,
  seat_id     VARCHAR(10) NOT NULL,
  row_number  INTEGER NOT NULL CHECK (row_number > 0),
  seat_column TEXT NOT NULL,
  PRIMARY KEY (schedule_id, coach, seat_id),
  FOREIGN KEY (schedule_id, coach)
    REFERENCES national_rail_coaches(schedule_id, coach)
    ON DELETE CASCADE
);

-- ------------------------------------------------------------
-- 5. Tickets, bookings, trips, payments, feedback
-- ------------------------------------------------------------
CREATE TABLE ticket_types (
  ticket_type  VARCHAR(50) PRIMARY KEY,
  display_name  TEXT NOT NULL,
  description   TEXT NOT NULL
);

CREATE TABLE ticket_type_networks (
  ticket_type  VARCHAR(50) NOT NULL REFERENCES ticket_types(ticket_type) ON DELETE CASCADE,
  network_type TEXT NOT NULL,
  PRIMARY KEY (ticket_type, network_type)
);

CREATE TABLE ticket_type_rules (
  ticket_type  VARCHAR(50) NOT NULL REFERENCES ticket_types(ticket_type) ON DELETE CASCADE,
  network_type TEXT NOT NULL,
  rules        JSONB NOT NULL,
  PRIMARY KEY (ticket_type, network_type)
);

CREATE TABLE bookings (
  booking_id             VARCHAR(15) PRIMARY KEY,
  user_id                VARCHAR(10) NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
  schedule_id            VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id),
  origin_station_id      VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id),
  destination_station_id VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id),
  travel_date            DATE NOT NULL,
  departure_time         TIME NOT NULL,
  ticket_type            VARCHAR(50) NOT NULL REFERENCES ticket_types(ticket_type),
  fare_class             TEXT NOT NULL,
  coach                  VARCHAR(5) NOT NULL,
  seat_id                VARCHAR(10) NOT NULL,
  stops_travelled        INTEGER NOT NULL CHECK (stops_travelled >= 0),
  amount_usd             NUMERIC(10,2) NOT NULL CHECK (amount_usd >= 0),
  status                 TEXT NOT NULL,
  booked_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  travelled_at           TIMESTAMPTZ,
  FOREIGN KEY (schedule_id, coach, seat_id)
    REFERENCES national_rail_seats(schedule_id, coach, seat_id),
  CHECK (status IN ('confirmed', 'completed', 'cancelled')),
  CHECK (origin_station_id <> destination_station_id)
);

CREATE UNIQUE INDEX bookings_unique_seat_per_trip
  ON bookings (schedule_id, travel_date, coach, seat_id)
  WHERE status <> 'cancelled';

CREATE TABLE metro_travel_history (
  trip_id                VARCHAR(15) PRIMARY KEY,
  user_id                VARCHAR(10) NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
  schedule_id            VARCHAR(20) NOT NULL REFERENCES metro_schedules(schedule_id),
  origin_station_id      VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id),
  destination_station_id VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id),
  travel_date            DATE NOT NULL,
  ticket_type            VARCHAR(50) NOT NULL REFERENCES ticket_types(ticket_type),
  day_pass_ref           VARCHAR(15) REFERENCES metro_travel_history(trip_id) ON DELETE SET NULL,
  stops_travelled        INTEGER,
  amount_usd             NUMERIC(10,2) NOT NULL CHECK (amount_usd >= 0),
  status                 TEXT NOT NULL,
  purchased_at           TIMESTAMPTZ,
  travelled_at           TIMESTAMPTZ,
  CHECK (origin_station_id <> destination_station_id)
);

CREATE TABLE payments (
  payment_id      VARCHAR(15) PRIMARY KEY,
  transaction_ref VARCHAR(15) NOT NULL,
  amount_usd      NUMERIC(10,2) NOT NULL CHECK (amount_usd >= 0),
  method          TEXT NOT NULL,
  status          TEXT NOT NULL,
  paid_at         TIMESTAMPTZ NOT NULL
);

CREATE TABLE feedback (
  feedback_id     VARCHAR(15) PRIMARY KEY,
  transaction_ref VARCHAR(15) NOT NULL,
  user_id         VARCHAR(10) NOT NULL REFERENCES users(user_id),
  rating          INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  comment         TEXT,
  submitted_at    TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_bookings_user_id ON bookings(user_id);
CREATE INDEX idx_metro_travel_history_user_id ON metro_travel_history(user_id);
CREATE INDEX idx_payments_transaction_ref ON payments(transaction_ref);
CREATE INDEX idx_feedback_transaction_ref ON feedback(transaction_ref);

-- ------------------------------------------------------------
-- 6. Refund policy data
-- ------------------------------------------------------------
CREATE TABLE refund_policies (
  policy_id           VARCHAR(20) PRIMARY KEY,
  label               TEXT NOT NULL,
  network_type        TEXT NOT NULL,
  service_type        TEXT,
  return_ticket_notes TEXT,
  no_show_policy      TEXT,
  notes               TEXT,
  exclusions          TEXT
);

CREATE TABLE refund_policy_ticket_types (
  policy_id   VARCHAR(20) NOT NULL REFERENCES refund_policies(policy_id) ON DELETE CASCADE,
  ticket_type VARCHAR(50) NOT NULL REFERENCES ticket_types(ticket_type) ON DELETE CASCADE,
  PRIMARY KEY (policy_id, ticket_type)
);

CREATE TABLE refund_policy_cancellation_windows (
  window_id                  VARCHAR(20) PRIMARY KEY,
  policy_id                  VARCHAR(20) NOT NULL REFERENCES refund_policies(policy_id) ON DELETE CASCADE,
  label                      TEXT NOT NULL,
  condition                  TEXT NOT NULL,
  hours_before_departure_min INTEGER,
  hours_before_departure_max INTEGER,
  refund_percent             NUMERIC(5,2) NOT NULL CHECK (refund_percent >= 0 AND refund_percent <= 100),
  admin_fee_usd              NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (admin_fee_usd >= 0)
);

CREATE TABLE policy_documents (
  id          SERIAL PRIMARY KEY,
  title       VARCHAR(200) NOT NULL,
  category    VARCHAR(50) NOT NULL,
  content     TEXT NOT NULL,
  embedding   VECTOR(768),
  source_file VARCHAR(200),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_policy_documents_embedding
  ON policy_documents USING hnsw (embedding vector_cosine_ops);
```

## Agreed Graph Schema

<!-- ============================================================
  FILL THIS IN after your team agrees on Neo4j node labels and
  relationship types.
  ============================================================ -->

Node labels:
- `MetroStation`: Represents a station in the metro network.
- `NationalRailStation`: Represents a station in the national rail network.

Relationship types:
- `CONNECTED_TO`: Connects two adjacent stations within the same network.
  - **Properties**: `line` (String, the line connecting them), `travel_time_min` (Integer, the travel time between them).
- `INTERCHANGES_WITH`: Connects a `MetroStation` and a `NationalRailStation` to map transfer points.
  - **Properties**: `transfer_time_min` (Integer, estimated walking transfer time, default 5).

Key properties:
- `MetroStation`:
`station_id` (String, unique identifier),
`name` (String),
`lines` (List of Strings, lines serving the station),
`is_interchange_metro` (Boolean),
`is_interchange_national_rail` (Boolean).

- `NationalRailStation`:
`station_id` (String, unique identifier),
`name` (String),
`lines` (List of Strings, lines serving the station),
`is_interchange_national_rail` (Boolean),
`is_interchange_metro` (Boolean).

## Function Signatures We Are Implementing

These are fixed contracts. AI-generated code must match these signatures exactly.

### Relational (`databases/relational/queries.py`)

```python
# Read-only
def query_national_rail_availability(origin_id: str, destination_id: str, travel_date: Optional[str] = None) -> list[dict]: ...
def query_national_rail_fare(schedule_id: str, fare_class: str, stops_travelled: int) -> Optional[dict]: ...
def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]: ...
def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]: ...
def query_available_seats(schedule_id: str, travel_date: str, fare_class: str) -> list[dict]: ...
def query_user_profile(user_email: str) -> Optional[dict]: ...
def query_user_bookings(user_email: str) -> dict: ...  # returns {"national_rail": [...], "metro": [...]}
def query_payment_info(booking_id: str) -> Optional[dict]: ...

# Write operations
def execute_booking(user_id, schedule_id, origin_station_id, destination_station_id, travel_date, fare_class, seat_id, ticket_type="single") -> tuple[bool, dict | str]: ...
def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]: ...

# Auth
def register_user(email, first_name, surname, year_of_birth, password, secret_question, secret_answer) -> tuple[bool, str]: ...
def login_user(email: str, password: str) -> Optional[dict]: ...
def get_user_secret_question(email: str) -> Optional[str]: ...
def verify_secret_answer(email: str, answer: str) -> bool: ...
def update_password(email: str, new_password: str) -> bool: ...
```

### Graph (`databases/graph/queries.py`)

```python
def query_shortest_route(origin_id: str, destination_id: str, network: str = "auto") -> dict: ...
def query_cheapest_route(origin_id: str, destination_id: str, network: str = "auto", fare_class: str = "standard") -> dict: ...
def query_alternative_routes(origin_id, destination_id, avoid_station_id, network="auto", max_routes=3) -> list[list[dict]]: ...
def query_interchange_path(origin_id: str, destination_id: str) -> dict: ...
def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]: ...
def query_station_connections(station_id: str) -> list[dict]: ...
```

## Team Decisions Log

<!-- Add entries as you make decisions. Format: "Decision: X. Why: Y." -->

* [x] **Schema design (Users):** 為了提升資安層級並隔離敏感資料，我們決定偏離原始的 schema.pdf，將使用者資料拆分為 `users`、`user_passwords` 與 `user_security_questions` 三張表，並新增了 `salt` 欄位供後續密碼雜湊使用。查詢使用者驗證資訊時需透過 `user_id` 進行 JOIN。
* [x] **Schema design (Foreign Keys):** 針對 metro_stations 與 national_rail_stations 之間的互相轉乘循環依賴，我們使用 `DEFERRABLE INITIALLY DEFERRED` 約束來解決寫入衝突。

- [ ] Graph schema: TODO — add your node label and relationship type decisions here
- [ ] (example) Metro schedule stop ordering: using `jsonb_array_elements` approach — easier to debug than containment operators

## Prompts That Worked

<!-- Share prompts that produced good output so teammates can reuse them. -->

### Schema design prompt that worked:
```
TODO — add a prompt here after your schema design workshop
```

### Query implementation prompt that worked:
```
TODO — add after implementing your first function
```
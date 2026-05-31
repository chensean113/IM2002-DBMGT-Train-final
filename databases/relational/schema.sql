-- ============================================================
-- TransitFlow PostgreSQL Schema
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ------------------------------------------------------------
-- 1. Users and authentication
-- ------------------------------------------------------------
CREATE TABLE users (
    user_id         VARCHAR(10) PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    first_name      TEXT NOT NULL,
    surname         TEXT NOT NULL,
    full_name       TEXT GENERATED ALWAYS AS (trim(first_name || ' ' || surname)) STORED,
    phone           VARCHAR(20) NOT NULL,
    date_of_birth   DATE NOT NULL,
    password        TEXT NOT NULL,
    secret_question TEXT NOT NULL,
    secret_answer   TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
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

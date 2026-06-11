-- ============================================================
-- TransitFlow PostgreSQL Schema
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ------------------------------------------------------------
-- 1. Users 基礎個資表
CREATE TABLE users (
    -- PK 選擇 VARCHAR(10)：為了符合既有系統 ID 規範 (如 RU001)，且具備一定的人類可讀性，利於除錯與手動查詢。
    user_id         VARCHAR(10) PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    full_name       TEXT NOT NULL,
    phone           VARCHAR(20) NOT NULL,
    date_of_birth   DATE NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

--  使用者密碼表 (與 users 表一對一關聯)
--  採用 bcrypt 演算法進行密碼雜湊，並存儲 Salt 以增強安全性。密碼欄位使用 TEXT 類型以適應 bcrypt 生成的長度。
CREATE TABLE user_passwords (
    -- FK 選擇 ON DELETE CASCADE：基於個資保護與資料一致性，當使用者帳號被刪除時，其密碼雜湊與 Salt 應同步永久移除，不應單獨留存。
    user_id         VARCHAR(10) PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    password        TEXT NOT NULL,
    salt            TEXT
);

--  使用者安全提示表 (與 users 表一對一關聯)
CREATE TABLE user_security_questions (
    -- FK 選擇 ON DELETE CASCADE：安全提問屬於帳號附屬機敏資訊，隨使用者帳號同步清理以符合資料去識別化要求。
    user_id         VARCHAR(10) PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    secret_question TEXT NOT NULL,
    secret_answer   TEXT NOT NULL
);

-- ------------------------------------------------------------
-- 2. Station master data
-- ------------------------------------------------------------
CREATE TABLE metro_stations (
    -- PK 選擇 VARCHAR(10)：車站 ID 通常遵循交通業標準代碼 (如 MS01)，使用定長字串可直接與實體地圖、廣播系統對照。
    station_id                           VARCHAR(10) PRIMARY KEY,
    name                                 TEXT NOT NULL,
    is_interchange_metro                 BOOLEAN NOT NULL DEFAULT FALSE,
    is_interchange_national_rail         BOOLEAN NOT NULL DEFAULT FALSE,
    interchange_national_rail_station_id VARCHAR(10)
);

CREATE TABLE national_rail_stations (
    -- PK 選擇 VARCHAR(10)：國鐵車站代碼為固定格式字串，有利於多系統間的資料交換與一致性識別。
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
    -- 此處採預設 RESTRICT 並延遲檢查：車站為基礎設施主資料，必須確保轉乘站兩端資料完整，禁止任意刪除有關聯的車站。
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE national_rail_stations
    ADD CONSTRAINT fk_national_rail_stations_interchange_metro
    FOREIGN KEY (interchange_metro_station_id)
    REFERENCES metro_stations(station_id)
    -- 此處採預設 RESTRICT 並延遲檢查：確保雙向轉乘指標在系統運行期間皆為有效連結。
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE metro_station_lines (
    -- FK 選擇 ON DELETE CASCADE：路線歸屬資料為車站的附屬屬性，當車站主資料移除時，對應的路線標籤已無意義，應一併清理。
    station_id VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id) ON DELETE CASCADE,
    line       VARCHAR(10) NOT NULL,
    PRIMARY KEY (station_id, line)
);

CREATE TABLE metro_station_adjacent_stations (
    -- FK 選擇 ON DELETE CASCADE：路網拓樸關係（相鄰站）必須隨車站存在而存在，若其中一個車站被移除，該段連結即失效，應自動刪除。
    station_id           VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id) ON DELETE CASCADE,
    adjacent_station_id  VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id) ON DELETE CASCADE,
    line                 VARCHAR(10) NOT NULL,
    travel_time_min      INTEGER NOT NULL CHECK (travel_time_min > 0),
    PRIMARY KEY (station_id, adjacent_station_id, line),
    CHECK (station_id <> adjacent_station_id)
);

CREATE TABLE national_rail_station_lines (
    -- FK 選擇 ON DELETE CASCADE：車站營運線路資訊隨車站主檔同步更新或清理，以維持資料庫瘦身。
    station_id VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE CASCADE,
    line       VARCHAR(10) NOT NULL,
    PRIMARY KEY (station_id, line)
);

CREATE TABLE national_rail_station_adjacent_stations (
    -- FK 選擇 ON DELETE CASCADE：國鐵相鄰關係與捷運相同，屬於邊 (Edge) 的概念，隨端點 (Node/Station) 刪除而同步CASCADE。
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
    -- PK 選擇 VARCHAR(20)：時刻表 ID 結合了路線與編號資訊 (如 MS_SCH01)，使用字串可直接攜帶部分業務語意。
    schedule_id            VARCHAR(20) PRIMARY KEY,
    line                   TEXT NOT NULL,
    direction              TEXT NOT NULL,
    -- FK 採預設 RESTRICT：禁止刪除尚有運行時刻表關聯的起訖站點，確保班次資訊的完整性。
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
    -- FK 選擇 ON DELETE CASCADE：時刻表停靠細項是時刻表的從屬資料，時刻表本身若刪除，細項不應單獨存在。
    schedule_id                 VARCHAR(20) NOT NULL REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    stop_order                  INTEGER NOT NULL CHECK (stop_order > 0),
    -- FK 採預設 RESTRICT：防止刪除中途停靠站點，避免時刻表數據出現邏輯斷層。
    station_id                  VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id),
    travel_time_from_origin_min INTEGER NOT NULL CHECK (travel_time_from_origin_min >= 0),
    PRIMARY KEY (schedule_id, stop_order)
);

CREATE TABLE metro_schedule_operating_days (
    -- FK 選擇 ON DELETE CASCADE：營運日資訊與時刻表為強耦合關係，隨時刻表刪除而連帶清理。
    schedule_id VARCHAR(20) NOT NULL REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    day_of_week VARCHAR(3) NOT NULL,
    PRIMARY KEY (schedule_id, day_of_week)
);

CREATE TABLE national_rail_schedules (
    -- PK 選擇 VARCHAR(20)：國鐵時刻表 ID 包含服務類別區分，字串格式利於對接外部調度系統。
    schedule_id            VARCHAR(20) PRIMARY KEY,
    line                   TEXT NOT NULL,
    service_type           TEXT NOT NULL,
    direction              TEXT NOT NULL,
    -- FK 採預設 RESTRICT：基礎車站資料在有運行班次的情況下嚴禁刪除，以維持路網穩定性。
    origin_station_id      VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id),
    destination_station_id VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id),
    first_train_time       TIME NOT NULL,
    last_train_time        TIME NOT NULL,
    frequency_min          INTEGER NOT NULL CHECK (frequency_min > 0),
    CHECK (service_type IN ('normal', 'express')),
    CHECK (origin_station_id <> destination_station_id)
);

CREATE TABLE national_rail_schedule_stops (
    -- FK 選擇 ON DELETE CASCADE：停靠站順序資訊與主時刻表生命週期一致。
    schedule_id                 VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    stop_order                  INTEGER NOT NULL CHECK (stop_order > 0),
    station_id                  VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id),
    travel_time_from_origin_min INTEGER NOT NULL CHECK (travel_time_from_origin_min >= 0),
    PRIMARY KEY (schedule_id, stop_order)
);

CREATE TABLE national_rail_schedule_passed_through_stations (
    -- FK 選擇 ON DELETE CASCADE：通過站點資訊僅對應特定班次，班次移除則此對應資訊隨之 CASCADE。
    schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    station_id  VARCHAR(10) NOT NULL REFERENCES national_rail_stations(station_id),
    PRIMARY KEY (schedule_id, station_id)
);

CREATE TABLE national_rail_schedule_fares (
    -- FK 選擇 ON DELETE CASCADE：運價設定與時刻表（班次）連動，若班次取消營運，運價設定亦應連帶刪除。
    schedule_id       VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    fare_class        VARCHAR(20) NOT NULL,
    base_fare_usd     NUMERIC(10,2) NOT NULL,
    per_stop_rate_usd NUMERIC(10,2) NOT NULL,
    PRIMARY KEY (schedule_id, fare_class)
);

CREATE TABLE national_rail_schedule_operating_days (
    -- FK 選擇 ON DELETE CASCADE：時刻表營運天數資料與主表為組成關係，隨時刻表同步清理。
    schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    day_of_week VARCHAR(3) NOT NULL,
    PRIMARY KEY (schedule_id, day_of_week)
);

-- ------------------------------------------------------------
-- 4. National rail seating
-- ------------------------------------------------------------
CREATE TABLE national_rail_seat_layouts (
    -- PK 選擇 VARCHAR(20)：座位配置 ID 可能包含車型資訊，字串格式利於區分不同車種的內裝配置。
    layout_id   VARCHAR(20) PRIMARY KEY,
    -- FK 選擇 ON DELETE CASCADE：時刻表與配置之連結屬於操作層次，時刻表變更時對應的配置索引應隨之清理。
    schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE
);

CREATE TABLE national_rail_coaches (
    -- FK 選擇 ON DELETE CASCADE：車廂編制歸屬於班次（時刻表），班次移除則其下所有車廂配置應一併 CASCADE。
    schedule_id VARCHAR(20) NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    coach       VARCHAR(5) NOT NULL,
    -- FK 選擇 ON DELETE CASCADE：若座位配置檔被刪除，則引用該配置的車廂資訊已不完整，應同步移除。
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
    -- FK 選擇 ON DELETE CASCADE：具體座位屬於車廂的一部分，當車廂從班次中移除時，座位資料必須隨之連帶刪除。
    FOREIGN KEY (schedule_id, coach)
        REFERENCES national_rail_coaches(schedule_id, coach)
        ON DELETE CASCADE
);

-- ------------------------------------------------------------
-- 5. Tickets, bookings, trips, payments, feedback
-- ------------------------------------------------------------
CREATE TABLE ticket_types (
    -- PK 選擇 VARCHAR(50)：使用具業務語意的字串 (如 single_ticket) 作為自然主鍵，可增加 SQL 查詢的可讀性與開發直覺性。
    ticket_type  VARCHAR(50) PRIMARY KEY,
    display_name  TEXT NOT NULL,
    description   TEXT NOT NULL
);

CREATE TABLE ticket_type_networks (
    -- FK 選擇 ON DELETE CASCADE：票種與路網的適配關係隨票種主資料同步清理。
    ticket_type  VARCHAR(50) NOT NULL REFERENCES ticket_types(ticket_type) ON DELETE CASCADE,
    network_type TEXT NOT NULL,
    PRIMARY KEY (ticket_type, network_type)
);

CREATE TABLE ticket_type_rules (
    -- FK 選擇 ON DELETE CASCADE：特定的票價或退改簽規則在票種刪除後已無意義，應連帶清除。
    ticket_type  VARCHAR(50) NOT NULL REFERENCES ticket_types(ticket_type) ON DELETE CASCADE,
    network_type TEXT NOT NULL,
    rules        JSONB NOT NULL,
    PRIMARY KEY (ticket_type, network_type)
);

CREATE TABLE bookings (
    -- PK 選擇 VARCHAR(15)：訂單號 ID (如 BK-123456) 通常需展示給用戶看，字串格式利於加入檢查碼或前綴以提升用戶體驗。
    booking_id             VARCHAR(15) PRIMARY KEY,
    -- FK 選擇 ON DELETE RESTRICT：限制刪除！為確保財務審計與法律合規（搭乘紀錄追蹤），禁止刪除尚有訂單關聯的使用者。
    user_id                VARCHAR(10) NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    -- FK 採預設 RESTRICT：當已有用戶訂位時，嚴禁刪除對應的班次时刻表，以防止用戶權益受損。
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
    -- FK 採預設 RESTRICT：防止刪除已被訂位的座位資料，確保訂單對象的穩定性。
    FOREIGN KEY (schedule_id, coach, seat_id)
        REFERENCES national_rail_seats(schedule_id, coach, seat_id),
    CHECK (status IN ('confirmed', 'completed', 'cancelled')),
    CHECK (origin_station_id <> destination_station_id)
);

CREATE UNIQUE INDEX bookings_unique_seat_per_trip
    ON bookings (schedule_id, travel_date, coach, seat_id)
    WHERE status <> 'cancelled';

CREATE TABLE metro_travel_history (
    -- PK 選擇 VARCHAR(15)：乘車紀錄 ID 採字串格式，方便與實體感應卡或電子錢包的交易序號對接。
    trip_id                VARCHAR(15) PRIMARY KEY,
    -- FK 選擇 ON DELETE RESTRICT：禁止刪除有乘車歷史的使用者，這在處理交通爭議、帳務核銷時至關重要。
    user_id                VARCHAR(10) NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    schedule_id            VARCHAR(20) NOT NULL REFERENCES metro_schedules(schedule_id),
    origin_station_id      VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id),
    destination_station_id VARCHAR(10) NOT NULL REFERENCES metro_stations(station_id),
    travel_date            DATE NOT NULL,
    ticket_type            VARCHAR(50) NOT NULL REFERENCES ticket_types(ticket_type),
    -- FK 選擇 ON DELETE SET NULL：當引用的日票 (Day Pass) 資料因存檔期限被移除時，個別行程紀錄應保留並將參照設為空值，以維護歷史數據完整性。
    day_pass_ref           VARCHAR(15) REFERENCES metro_travel_history(trip_id) ON DELETE SET NULL,
    stops_travelled        INTEGER,
    amount_usd             NUMERIC(10,2) NOT NULL CHECK (amount_usd >= 0),
    status                 TEXT NOT NULL,
    purchased_at           TIMESTAMPTZ,
    travelled_at           TIMESTAMPTZ,
    CHECK (origin_station_id <> destination_station_id)
);

CREATE TABLE payments (
    -- PK 選擇 VARCHAR(15)：支付編號採字串格式，可容納第三方金流傳回的交易代碼前綴。
    payment_id      VARCHAR(15) PRIMARY KEY,
    transaction_ref VARCHAR(15) NOT NULL,
    amount_usd      NUMERIC(10,2) NOT NULL CHECK (amount_usd >= 0),
    method          TEXT NOT NULL,
    status          TEXT NOT NULL,
    paid_at         TIMESTAMPTZ NOT NULL
);

CREATE TABLE feedback (
    -- PK 選擇 VARCHAR(15)：回饋 ID 採字串，方便未來擴充多語系或分類前綴。
    feedback_id     VARCHAR(15) PRIMARY KEY,
    transaction_ref VARCHAR(15) NOT NULL,
    -- FK 採預設 RESTRICT：當評論存在時，應保留對應的使用者帳號，以便後續客服聯繫或追蹤負評。
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
    -- PK 選擇 VARCHAR(20)：政策 ID (如 RF001) 使用字串，便於與法律條款、官方文件之代碼直接對應。
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
    -- FK 選擇 ON DELETE CASCADE：當退票政策主檔移除時，其票種關聯設定已失效，應連帶 CASCADE。
    policy_id   VARCHAR(20) NOT NULL REFERENCES refund_policies(policy_id) ON DELETE CASCADE,
    -- FK 選擇 ON DELETE CASCADE：當票種被廢止刪除時，其退票政策的適用性也隨之解除。
    ticket_type VARCHAR(50) NOT NULL REFERENCES ticket_types(ticket_type) ON DELETE CASCADE,
    PRIMARY KEY (policy_id, ticket_type)
);

CREATE TABLE refund_policy_cancellation_windows (
    -- PK 選擇 VARCHAR(20)：視窗 ID 採字串，利於描述特定的時間條件段。
    window_id                  VARCHAR(20) PRIMARY KEY,
    -- FK 選擇 ON DELETE CASCADE：退票時間窗口屬於政策的附屬規則，主政策刪除時，對應的視窗規則必須連帶清理。
    policy_id                  VARCHAR(20) NOT NULL REFERENCES refund_policies(policy_id) ON DELETE CASCADE,
    label                      TEXT NOT NULL,
    condition                  TEXT NOT NULL,
    hours_before_departure_min INTEGER,
    hours_before_departure_max INTEGER,
    refund_percent             NUMERIC(5,2) NOT NULL CHECK (refund_percent >= 0 AND refund_percent <= 100),
    admin_fee_usd              NUMERIC(10,2) NOT NULL DEFAULT 0 CHECK (admin_fee_usd >= 0)
);

CREATE TABLE policy_documents (
    -- PK 選擇 SERIAL：知識庫文件屬於純內部後台管理，不涉及外部業務語意對照，使用自動遞增整數效能最高且實作最簡單。
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
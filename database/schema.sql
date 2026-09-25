CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    phone TEXT,
    address TEXT,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    brand TEXT NOT NULL,
    model_number TEXT,
    serial_number TEXT NOT NULL,
    purchase_date TEXT,
    purchase_price REAL,
    retailer TEXT,
    warranty_duration INTEGER,
    created_at TEXT NOT NULL,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
);


CREATE TABLE IF NOT EXISTS warranties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    warranty_type TEXT NOT NULL,
    provider TEXT,
    start_date TEXT NOT NULL,
    expiry_date TEXT NOT NULL,
    coverage_conditions TEXT,
    exclusions TEXT,
    service_center_details TEXT,
    status TEXT,
    created_at TEXT NOT NULL,

    FOREIGN KEY (product_id)
        REFERENCES products(id)
);


CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    warranty_id INTEGER,
    product_age REAL,
    fault_occurrence_date TEXT,
    fault_description TEXT NOT NULL,
    fault_category TEXT,
    damage_type TEXT,
    claim_amount REAL,
    warranty_conditions TEXT,
    service_history TEXT,
    previous_replacement_details TEXT,
    submission_date TEXT,
    status TEXT NOT NULL,
    final_result TEXT,
    created_at TEXT NOT NULL,

    FOREIGN KEY (user_id)
        REFERENCES users(id),

    FOREIGN KEY (product_id)
        REFERENCES products(id),

    FOREIGN KEY (warranty_id)
        REFERENCES warranties(id)
);


CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    product_id INTEGER,
    claim_id INTEGER,
    document_type TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_hash TEXT,
    uploaded_at TEXT NOT NULL,

    FOREIGN KEY (user_id)
        REFERENCES users(id),

    FOREIGN KEY (product_id)
        REFERENCES products(id),

    FOREIGN KEY (claim_id)
        REFERENCES claims(id)
);


CREATE TABLE IF NOT EXISTS repairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    claim_id INTEGER,
    repair_date TEXT NOT NULL,
    repair_center TEXT,
    replaced_parts TEXT,
    repair_outcome TEXT,
    repair_cost REAL,
    authorized INTEGER NOT NULL,
    created_at TEXT NOT NULL,

    FOREIGN KEY (product_id)
        REFERENCES products(id),

    FOREIGN KEY (claim_id)
        REFERENCES claims(id)
);


CREATE TABLE IF NOT EXISTS model_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_type TEXT NOT NULL,
    version TEXT NOT NULL,
    model_file TEXT,
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,

    UNIQUE(model_type, version)
);


CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    model_version_id INTEGER NOT NULL,
    model_type TEXT NOT NULL,
    predicted_class TEXT NOT NULL,
    valid_conf REAL NOT NULL,
    invalid_conf REAL NOT NULL,
    manual_conf REAL NOT NULL,
    top_conf REAL NOT NULL,
    created_at TEXT NOT NULL,

    FOREIGN KEY (claim_id)
        REFERENCES claims(id),

    FOREIGN KEY (model_version_id)
        REFERENCES model_versions(id)
);


CREATE TABLE IF NOT EXISTS rule_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    rule_name TEXT NOT NULL,
    result TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL,

    FOREIGN KEY (claim_id)
        REFERENCES claims(id)
);


CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    claim_id INTEGER,
    notification_type TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,

    FOREIGN KEY (user_id)
        REFERENCES users(id),

    FOREIGN KEY (claim_id)
        REFERENCES claims(id)
);


CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    claim_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL,

    FOREIGN KEY (user_id)
        REFERENCES users(id),

    FOREIGN KEY (claim_id)
        REFERENCES claims(id)
);
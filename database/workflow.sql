CREATE TABLE IF NOT EXISTS claim_reviews (
 id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id INTEGER NOT NULL REFERENCES claims(id),
 reviewer_id INTEGER NOT NULL REFERENCES users(id), action TEXT NOT NULL,
 comment TEXT NOT NULL, previous_status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extracted_documents (
 document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
 raw_text TEXT NOT NULL DEFAULT '', extracted_json TEXT NOT NULL DEFAULT '{}',
 verified_json TEXT NOT NULL DEFAULT '{}', verified_by INTEGER REFERENCES users(id),
 verified_at TEXT, extraction_status TEXT NOT NULL DEFAULT 'Not scanned'
);
CREATE TABLE IF NOT EXISTS employee_customers (
 employee_id INTEGER NOT NULL REFERENCES users(id), customer_id INTEGER NOT NULL REFERENCES users(id),
 PRIMARY KEY(employee_id, customer_id)
);
CREATE TABLE IF NOT EXISTS security_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL, subject TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claims_user ON claims(user_id, status);
CREATE INDEX IF NOT EXISTS idx_claims_product ON claims(product_id);
CREATE INDEX IF NOT EXISTS idx_documents_claim ON documents(claim_id);
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(file_hash);
CREATE INDEX IF NOT EXISTS idx_audit_claim ON audit(claim_id, id);
CREATE INDEX IF NOT EXISTS idx_security_subject ON security_events(subject, created_at);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read);
CREATE TABLE IF NOT EXISTS evaluations (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 claim_id INTEGER NOT NULL REFERENCES claims(id),
 result TEXT NOT NULL,
 consistency TEXT NOT NULL,
 difference REAL,
 details TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evaluations_claim ON evaluations(claim_id, id);
CREATE TRIGGER IF NOT EXISTS keep_prediction_update BEFORE UPDATE ON predictions
BEGIN SELECT RAISE(ABORT, 'Recorded predictions cannot be changed.'); END;
CREATE TRIGGER IF NOT EXISTS keep_prediction_delete BEFORE DELETE ON predictions
BEGIN SELECT RAISE(ABORT, 'Recorded predictions cannot be removed.'); END;
CREATE TRIGGER IF NOT EXISTS keep_evaluation_update BEFORE UPDATE ON evaluations
BEGIN SELECT RAISE(ABORT, 'Recorded evaluations cannot be changed.'); END;
CREATE TRIGGER IF NOT EXISTS keep_evaluation_delete BEFORE DELETE ON evaluations
BEGIN SELECT RAISE(ABORT, 'Recorded evaluations cannot be removed.'); END;

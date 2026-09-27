CREATE TABLE IF NOT EXISTS students (
    usn TEXT PRIMARY KEY,
    name TEXT,
    department TEXT DEFAULT 'ISE',
    semester TEXT DEFAULT 'Sem 3',
    email TEXT UNIQUE,
    password TEXT,
    student_group TEXT DEFAULT 'Group 1',
    is_active INTEGER DEFAULT 1,
    qr_id TEXT
);

CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    student_usn TEXT,
    name TEXT,
    status TEXT,
    date TEXT,
    time TEXT,
    subject TEXT,
    method TEXT,
    reason TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS scan_sessions (
    session_id TEXT PRIMARY KEY,
    date TEXT,
    time TEXT,
    subject TEXT,
    downloaded INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS admin_config (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,
    password TEXT,
    email TEXT
);

INSERT OR REPLACE INTO admin_config (id, username, password, email) 
VALUES (1, 'admin', 'admin123', 'YOUR_GMAIL_ADDRESS_HERE');

CREATE TABLE IF NOT EXISTS shared_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    title TEXT,
    target_group TEXT DEFAULT 'All Groups',
    upload_date TEXT
);

CREATE TABLE IF NOT EXISTS component_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_usn TEXT,
    student_name TEXT,
    student_group TEXT,
    component_name TEXT,
    quantity INTEGER DEFAULT 1,
    notes TEXT,
    status TEXT DEFAULT 'PENDING',
    requested_date TEXT,
    approved_date TEXT
);

CREATE TABLE IF NOT EXISTS group_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_group TEXT,
    sender_usn TEXT,
    sender_name TEXT,
    message TEXT,
    timestamp TEXT
);

CREATE TABLE IF NOT EXISTS private_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_usn TEXT,
    receiver_usn TEXT,
    sender_name TEXT,
    message TEXT,
    timestamp TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_type TEXT,
    target_group TEXT,
    recipient_usn TEXT,
    title TEXT,
    message TEXT,
    created_at TEXT,
    is_read INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS otp_tokens (
    email TEXT PRIMARY KEY,
    otp TEXT,
    expiry REAL
);


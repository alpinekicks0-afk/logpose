// Database schema for accounts. The Worker creates anything missing on its
// first request, so no separate migration step is needed for a new database.
// Add new statements at the end; every statement must be safe to run twice.

export const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS users (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     username TEXT NOT NULL UNIQUE COLLATE NOCASE,
     is_public INTEGER NOT NULL DEFAULT 0,
     instagram TEXT NOT NULL DEFAULT '',
     refs_url TEXT NOT NULL DEFAULT '',
     created_at INTEGER NOT NULL)`,
  // Sign-in identities. Only the provider's opaque account id is kept: no
  // email address, name or avatar is requested or stored.
  `CREATE TABLE IF NOT EXISTS identities (
     provider TEXT NOT NULL, provider_id TEXT NOT NULL, user_id INTEGER NOT NULL,
     PRIMARY KEY (provider, provider_id))`,
  `CREATE INDEX IF NOT EXISTS identities_user ON identities(user_id)`,
  `CREATE TABLE IF NOT EXISTS sessions (
     token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
     created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id)`,
  `CREATE TABLE IF NOT EXISTS pending_signups (
     token_hash TEXT PRIMARY KEY, provider TEXT NOT NULL, provider_id TEXT NOT NULL,
     expires_at INTEGER NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS wishlist (
     user_id INTEGER NOT NULL, card_id TEXT NOT NULL, created_at INTEGER NOT NULL,
     PRIMARY KEY (user_id, card_id))`,
  `CREATE INDEX IF NOT EXISTS wishlist_card ON wishlist(card_id)`,
  `CREATE TABLE IF NOT EXISTS collection (
     id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, card_id TEXT NOT NULL,
     grader TEXT NOT NULL, grade TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS collection_user ON collection(user_id)`,
  `CREATE INDEX IF NOT EXISTS collection_card ON collection(card_id)`,
  // One row per (wisher, owner, card). Each side accepts or declines on its own.
  `CREATE TABLE IF NOT EXISTS matches (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     wisher_id INTEGER NOT NULL, owner_id INTEGER NOT NULL, card_id TEXT NOT NULL,
     wisher_status TEXT NOT NULL DEFAULT 'pending', owner_status TEXT NOT NULL DEFAULT 'pending',
     created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
     UNIQUE (wisher_id, owner_id, card_id))`,
  `CREATE INDEX IF NOT EXISTS matches_owner ON matches(owner_id)`,
  // One chat per pair of people, however many cards connected them.
  `CREATE TABLE IF NOT EXISTS chats (
     id INTEGER PRIMARY KEY AUTOINCREMENT, user_lo INTEGER NOT NULL, user_hi INTEGER NOT NULL,
     created_at INTEGER NOT NULL, UNIQUE (user_lo, user_hi))`,
  `CREATE INDEX IF NOT EXISTS chats_hi ON chats(user_hi)`,
  `CREATE TABLE IF NOT EXISTS messages (
     id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, sender_id INTEGER,
     kind TEXT NOT NULL DEFAULT 'text', body TEXT NOT NULL, created_at INTEGER NOT NULL)`,
  `CREATE INDEX IF NOT EXISTS messages_chat ON messages(chat_id, id)`,
  `CREATE TABLE IF NOT EXISTS chat_reads (
     chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, last_read_id INTEGER NOT NULL DEFAULT 0,
     PRIMARY KEY (chat_id, user_id))`,
  `CREATE TABLE IF NOT EXISTS friendships (
     user_lo INTEGER NOT NULL, user_hi INTEGER NOT NULL, requested_by INTEGER NOT NULL,
     status TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL,
     PRIMARY KEY (user_lo, user_hi))`,
  `CREATE INDEX IF NOT EXISTS friendships_hi ON friendships(user_hi)`,
  `CREATE TABLE IF NOT EXISTS blocks (
     blocker_id INTEGER NOT NULL, blocked_id INTEGER NOT NULL, created_at INTEGER NOT NULL,
     PRIMARY KEY (blocker_id, blocked_id))`,
  `CREATE INDEX IF NOT EXISTS blocks_blocked ON blocks(blocked_id)`,
  `CREATE TABLE IF NOT EXISTS reports (
     id INTEGER PRIMARY KEY AUTOINCREMENT, reporter_id INTEGER, reported_id INTEGER,
     reported_name TEXT NOT NULL DEFAULT '', chat_id INTEGER, reason TEXT NOT NULL,
     created_at INTEGER NOT NULL, resolved INTEGER NOT NULL DEFAULT 0)`,
  `CREATE TABLE IF NOT EXISTS rate (k TEXT PRIMARY KEY, w INTEGER NOT NULL, n INTEGER NOT NULL)`,
];

let ready = null;

export function ensureSchema(db) {
  if (!ready) {
    ready = db.batch(SCHEMA.map(sql => db.prepare(sql))).catch(err => {
      ready = null;
      throw err;
    });
  }
  return ready;
}

// For tests that start from a fresh database in the same process.
export function resetSchemaCache() {
  ready = null;
}

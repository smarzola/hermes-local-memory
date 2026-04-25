from __future__ import annotations

SCHEMA_VERSION = 1

SCHEMA_SQL = """
pragma foreign_keys = on;
pragma journal_mode = wal;

create table if not exists meta (
  key text primary key,
  value text not null
);

create table if not exists profiles (
  id text primary key,
  display_name text not null,
  created_at text not null default (datetime('now'))
);

create table if not exists peers (
  id text primary key,
  display_name text not null,
  kind text not null check (kind in ('human', 'ai', 'group', 'system')),
  created_at text not null default (datetime('now')),
  metadata_json text not null default '{}'
);

create table if not exists peer_aliases (
  alias text primary key,
  peer_id text not null references peers(id) on delete cascade,
  source text,
  confidence real not null default 1.0,
  verified integer not null default 0,
  created_at text not null default (datetime('now'))
);

create table if not exists sessions (
  id text primary key,
  profile_id text not null references profiles(id) on delete cascade,
  platform text,
  external_id text,
  title text,
  scope text not null default 'private',
  created_at text not null default (datetime('now')),
  updated_at text not null default (datetime('now')),
  metadata_json text not null default '{}'
);

create table if not exists session_peers (
  session_id text not null references sessions(id) on delete cascade,
  peer_id text not null references peers(id) on delete cascade,
  role text not null default 'participant',
  joined_at text not null default (datetime('now')),
  left_at text,
  primary key (session_id, peer_id)
);

create table if not exists messages (
  id integer primary key autoincrement,
  session_id text not null references sessions(id) on delete cascade,
  peer_id text not null references peers(id) on delete restrict,
  role text not null,
  content text not null,
  created_at text not null default (datetime('now')),
  source_message_id text,
  metadata_json text not null default '{}'
);

create unique index if not exists messages_source_message_id_uq
on messages(source_message_id)
where source_message_id is not null;

create virtual table if not exists messages_fts using fts5(
  content,
  content='messages',
  content_rowid='id'
);

create trigger if not exists messages_ai after insert on messages begin
  insert into messages_fts(rowid, content) values (new.id, new.content);
end;

create trigger if not exists messages_ad after delete on messages begin
  insert into messages_fts(messages_fts, rowid, content) values ('delete', old.id, old.content);
end;

create trigger if not exists messages_au after update of content on messages begin
  insert into messages_fts(messages_fts, rowid, content) values ('delete', old.id, old.content);
  insert into messages_fts(rowid, content) values (new.id, new.content);
end;

create table if not exists facts (
  id text primary key,
  subject_peer_id text not null references peers(id) on delete cascade,
  observer_peer_id text not null references peers(id) on delete cascade,
  scope text not null default 'global',
  scope_id text,
  kind text not null default 'note',
  content text not null,
  confidence real not null default 1.0,
  status text not null default 'active' check (
    status in ('active', 'superseded', 'retracted', 'candidate')
  ),
  source text not null default 'manual',
  evidence_json text not null default '[]',
  created_at text not null default (datetime('now')),
  updated_at text not null default (datetime('now'))
);

create virtual table if not exists facts_fts using fts5(
  content,
  content='facts',
  content_rowid='rowid'
);

create trigger if not exists facts_ai after insert on facts begin
  insert into facts_fts(rowid, content) values (new.rowid, new.content);
end;

create trigger if not exists facts_ad after delete on facts begin
  insert into facts_fts(facts_fts, rowid, content) values ('delete', old.rowid, old.content);
end;

create trigger if not exists facts_au after update of content on facts begin
  insert into facts_fts(facts_fts, rowid, content) values ('delete', old.rowid, old.content);
  insert into facts_fts(rowid, content) values (new.rowid, new.content);
end;

create table if not exists cards (
  subject_peer_id text not null references peers(id) on delete cascade,
  observer_peer_id text not null references peers(id) on delete cascade,
  scope text not null default 'global',
  scope_id text not null default '',
  content_json text not null,
  updated_at text not null default (datetime('now')),
  primary key (subject_peer_id, observer_peer_id, scope, scope_id)
);

create table if not exists summaries (
  id text primary key,
  scope text not null,
  scope_id text not null,
  content text not null,
  covered_from_message_id integer,
  covered_to_message_id integer,
  model text,
  created_at text not null default (datetime('now')),
  updated_at text not null default (datetime('now'))
);

insert or ignore into meta(key, value) values ('schema_version', '1');
insert or ignore into profiles(id, display_name) values ('default', 'Default');
"""

import { pgTable, uuid, text, timestamp, jsonb } from 'drizzle-orm/pg-core';

export const lines = pgTable('lines', {
  id: uuid('id').primaryKey().defaultRandom(),
  wheelId: text('wheel_id').notNull(),
  label: text('label').notNull(),
  status: text('status', { enum: ['active', 'archived', 'merged'] }).notNull(),
  createdAt: timestamp('created_at').defaultNow().notNull(),
  updatedAt: timestamp('updated_at').defaultNow().notNull(),
});

export const lineEvents = pgTable('line_events', {
  id: uuid('id').primaryKey().defaultRandom(),
  lineId: uuid('line_id').references(() => lines.id).notNull(),
  type: text('type', { enum: ['fork', 'merge', 'snapshot'] }).notNull(),
  forkId: uuid('fork_id'),
  sourceSessionId: text('source_session_id'),
  targetSessionId: text('target_session_id'),
  payload: jsonb('payload'),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});

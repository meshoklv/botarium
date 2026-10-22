-- Recurring tasks (used by Database.create_recurring_task / process_recurring_tasks)
CREATE TABLE IF NOT EXISTS recurring_tasks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(user_id),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    priority VARCHAR(10) DEFAULT 'medium',
    tags TEXT,
    category VARCHAR(100),
    recurrence_type VARCHAR(20) NOT NULL DEFAULT 'weekly',
    recurrence_interval INTEGER DEFAULT 1,
    next_due_date TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_recurring_tasks_due ON recurring_tasks(next_due_date) WHERE is_active;

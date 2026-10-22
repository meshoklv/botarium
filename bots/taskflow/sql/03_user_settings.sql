-- Создание таблицы настроек пользователей
CREATE TABLE IF NOT EXISTS user_settings (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    timezone VARCHAR(50) DEFAULT 'Europe/Moscow',
    language VARCHAR(10) DEFAULT 'ru',
    theme VARCHAR(20) DEFAULT 'light',
    notifications_enabled BOOLEAN DEFAULT TRUE,
    reminder_time INTEGER DEFAULT 60, -- минуты до дедлайна
    work_hours_start TIME DEFAULT '09:00',
    work_hours_end TIME DEFAULT '18:00',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание индекса для оптимизации
CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON user_settings(user_id);

COMMIT;
-- Добавление полей для кеширования AI анализа
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS ai_analysis JSONB;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS ai_analysis_date TIMESTAMP;

-- Создание индекса для оптимизации поиска
CREATE INDEX IF NOT EXISTS idx_tasks_ai_analysis ON tasks(id) WHERE ai_analysis IS NOT NULL;

COMMIT;
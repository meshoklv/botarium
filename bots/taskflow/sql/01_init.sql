-- Инициализация базы данных PostgreSQL для TaskFlow Bot
-- Выполните этот скрипт в Supabase SQL Editor (or let docker-compose apply it automatically)

-- Создание таблицы пользователей
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    settings JSONB DEFAULT '{}'
);

-- Создание таблицы проектов
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    owner_id BIGINT REFERENCES users(user_id),
    invite_code VARCHAR(10) UNIQUE,
    is_personal BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    settings JSONB DEFAULT '{}'
);

-- Создание таблицы участников проектов
CREATE TABLE IF NOT EXISTS project_members (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(user_id),
    role VARCHAR(50) DEFAULT 'member',
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, user_id)
);

-- Создание таблицы задач
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'pending',
    priority VARCHAR(10) DEFAULT 'medium',
    deadline TIMESTAMP,
    tags TEXT,
    category VARCHAR(100),
    assigned_to BIGINT REFERENCES users(user_id),
    time_estimate INTEGER, -- в минутах
    time_spent INTEGER DEFAULT 0, -- в минутах
    parent_task_id INTEGER REFERENCES tasks(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    is_recurring BOOLEAN DEFAULT FALSE,
    recurring_pattern JSONB,
    template_id INTEGER
);

-- Создание таблицы комментариев
CREATE TABLE IF NOT EXISTS task_comments (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(user_id),
    comment TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы истории задач
CREATE TABLE IF NOT EXISTS task_history (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(user_id),
    action VARCHAR(100) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы шаблонов задач
CREATE TABLE IF NOT EXISTS task_templates (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    priority VARCHAR(10) DEFAULT 'medium',
    tags TEXT,
    category VARCHAR(100),
    time_estimate INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы уведомлений
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы активности
CREATE TABLE IF NOT EXISTS activity_log (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id),
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание индексов для оптимизации
CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks(assigned_to);
CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members(user_id);
CREATE INDEX IF NOT EXISTS idx_project_members_project_id ON project_members(project_id);
CREATE INDEX IF NOT EXISTS idx_task_comments_task_id ON task_comments(task_id);
CREATE INDEX IF NOT EXISTS idx_task_history_task_id ON task_history(task_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_log_user_id ON activity_log(user_id);

-- Функция для автоматического создания персонального проекта
CREATE OR REPLACE FUNCTION create_personal_project()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO projects (name, description, owner_id, is_personal)
    VALUES (
        'Личные задачи',
        'Персональный проект для личных задач',
        NEW.user_id,
        TRUE
    );
    
    INSERT INTO project_members (project_id, user_id, role)
    VALUES (
        (SELECT id FROM projects WHERE owner_id = NEW.user_id AND is_personal = TRUE),
        NEW.user_id,
        'owner'
    );
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для автоматического создания персонального проекта
DROP TRIGGER IF EXISTS trigger_create_personal_project ON users;
CREATE TRIGGER trigger_create_personal_project
    AFTER INSERT ON users
    FOR EACH ROW
    EXECUTE FUNCTION create_personal_project();

-- Функция для генерации invite_code
CREATE OR REPLACE FUNCTION generate_invite_code()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.invite_code IS NULL AND NEW.is_personal = FALSE THEN
        NEW.invite_code := upper(substring(md5(random()::text) from 1 for 8));
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для генерации invite_code
DROP TRIGGER IF EXISTS trigger_generate_invite_code ON projects;
CREATE TRIGGER trigger_generate_invite_code
    BEFORE INSERT ON projects
    FOR EACH ROW
    EXECUTE FUNCTION generate_invite_code();

COMMIT;

-- Сообщение об успешной инициализации
SELECT 'База данных TaskFlow Bot успешно инициализирована!' as status;
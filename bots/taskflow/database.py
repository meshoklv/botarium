import os
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
import random
import string
import time
from datetime import datetime, timedelta
import json
from contextlib import contextmanager
from db_config import DATABASE_URL

logger = logging.getLogger(__name__)

def measure_time(func):
    """Декоратор для измерения времени выполнения методов базы данных"""
    def wrapper(self, *args, **kwargs):
        start_time = time.time()
        try:
            result = func(self, *args, **kwargs)
            execution_time = time.time() - start_time
            if execution_time > 1.0:  # Логируем запросы дольше 1 секунды
                logger.warning(f"Slow query detected - function: {func.__name__}, execution_time: {execution_time}")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Function execution error - function: {func.__name__}, execution_time: {execution_time}, error: {str(e)}")
            raise
    return wrapper

class Database:
    def __init__(self):
        # Используем конфигурацию из db_config.py или переменную окружения
        self.database_url = os.getenv('DATABASE_URL') or DATABASE_URL
        if not self.database_url:
            raise ValueError("DATABASE_URL is not configured. Check db_config.py or set environment variable")
        
        # Log only the host (never the full URL: it contains the password)
        try:
            from urllib.parse import urlparse
            logger.info(f"Database host: {urlparse(self.database_url).hostname}")
        except Exception:
            pass

        # Улучшенный пул соединений
        self._connection_pool = []
        self._pool_size = 10  # Увеличим размер пула
        self._active_connections = 0
        self._max_connections = 15
        
        # Кэш для частых запросов
        self._cache = {}
        self._cache_ttl = 30  # секунды
    
    def get_connection(self):
        import time
        start_time = time.time()
        
        # Попробуем получить соединение из пула
        for _ in range(3):  # Попробуем до 3 соединений из пула
            if self._connection_pool:
                conn = self._connection_pool.pop(0)
                try:
                    # Быстрая проверка соединения
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                    self._active_connections += 1
                    return conn
                except:
                    # Соединение мертво, попробуем следующее
                    try:
                        conn.close()
                    except:
                        pass
                    continue
        
        # Создаем новое соединение с оптимизацией
        try:
            # ДИАГНОСТИКА: Логируем начало подключения
            logger.info(f"🔌 Создаю новое подключение к базе данных - operation: db_connect")
            
            # Добавляем параметры для оптимизации соединения
            conn_params = self.database_url
            if "?" not in conn_params:
                conn_params += "?"
            else:
                conn_params += "&"
            
            # Параметры оптимизации PostgreSQL
            conn_params += "sslmode=require&connect_timeout=10&keepalives_idle=600&keepalives_interval=30&keepalives_count=3"
            
            conn = psycopg2.connect(conn_params, cursor_factory=RealDictCursor)
            
            # Настройки для быстрых запросов
            conn.autocommit = False
            
            connection_time = time.time() - start_time
            if connection_time > 0.5:
                logger.warning(f"Slow database connection - connection_time: {connection_time:.2f}s - operation: db_connect_slow")
            
            self._active_connections += 1
            return conn
        except Exception as e:
            logger.error(f"Database connection error - error: {str(e)} - operation: db_connect_error")
            raise
    
    def return_connection(self, conn):
        """Вернуть соединение в пул"""
        try:
            self._active_connections = max(0, self._active_connections - 1)
            if len(self._connection_pool) < self._pool_size and not conn.closed:
                # Проверим, что соединение все еще работает
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                    self._connection_pool.append(conn)
                    return
                except:
                    pass
            
            # Закрываем соединение если не можем добавить в пул
            conn.close()
        except:
            try:
                conn.close()
            except:
                pass
    
    @contextmanager
    def get_connection_ctx(self):
        """Контекстный менеджер для автоматического возврата соединений в пул"""
        conn = None
        try:
            conn = self.get_connection()
            yield conn
        finally:
            if conn:
                self.return_connection(conn)
    
    def create_user(self, user_id, username, first_name, last_name):
        """Создать или обновить пользователя"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, username, first_name, last_name)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET 
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name
                """, (user_id, username, first_name, last_name))
                conn.commit()
    
    def register_user(self, user_id, username, first_name, last_name):
        """Зарегистрировать пользователя (алиас для create_user)"""
        return self.create_user(user_id, username, first_name, last_name)
    
    @measure_time
    def add_task(self, user_id, title, description=None, project_id=None, deadline=None, 
                 priority='medium', tags=None, category=None, assigned_to=None, 
                 time_estimate=None, parent_task_id=None):
        """Добавить новую задачу с расширенными параметрами"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO tasks (user_id, title, description, project_id, deadline, 
                                     priority, tags, category, assigned_to, time_estimate, parent_task_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (user_id, title, description, project_id, deadline, priority, 
                      tags, category, assigned_to, time_estimate, parent_task_id))
                result = cur.fetchone()
                task_id = result['id'] if result else None
                
                # Записать в историю (в той же транзакции)
                if task_id:
                    cur.execute("""
                        INSERT INTO task_history (task_id, user_id, action, old_value, new_value)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (task_id, user_id, 'created', None, f"Создана задача: {title}"))
                
                conn.commit()
                # Очищаем кэш проектов пользователя
                self._invalidate_cache(f"get_user_projects:{user_id}")
                self._invalidate_cache(f"get_project_tasks:{project_id}")
                return task_id
    
    def get_tasks(self, user_id, completed=None):
        """Получить задачи пользователя"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if completed is None:
                    cur.execute("""
                        SELECT * FROM tasks 
                        WHERE user_id = %s 
                        ORDER BY created_at DESC
                    """, (user_id,))
                else:
                    if completed:
                        cur.execute("""
                            SELECT * FROM tasks 
                            WHERE user_id = %s AND completed_at IS NOT NULL 
                            ORDER BY created_at DESC
                        """, (user_id,))
                    else:
                        cur.execute("""
                            SELECT * FROM tasks 
                            WHERE user_id = %s AND completed_at IS NULL 
                            ORDER BY created_at DESC
                        """, (user_id,))
                return cur.fetchall()
    
    def complete_task(self, task_id, user_id):
        """Отметить задачу как выполненную"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE tasks 
                    SET completed_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND user_id = %s
                    RETURNING id
                """, (task_id, user_id))
                result = cur.fetchone()
                conn.commit()
                return result is not None
    
    def delete_task(self, task_id, user_id):
        """Удалить задачу"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM tasks 
                    WHERE id = %s AND user_id = %s
                    RETURNING id
                """, (task_id, user_id))
                result = cur.fetchone()
                conn.commit()
                return result is not None
    
    def get_user_stats(self, user_id):
        """Получить статистику пользователя"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_tasks,
                        COUNT(CASE WHEN completed_at IS NOT NULL THEN 1 END) as completed_tasks,
                        COUNT(CASE WHEN completed_at IS NULL THEN 1 END) as pending_tasks
                    FROM tasks 
                    WHERE user_id = %s
                """, (user_id,))
                return cur.fetchone()
    
    # === ПРОЕКТЫ ===
    
    def generate_invite_code(self):
        """Генерировать уникальный код приглашения"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    def create_project(self, owner_id, name, description=None):
        """Создать новый проект"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                invite_code = self.generate_invite_code()
                cur.execute("""
                    INSERT INTO projects (name, description, owner_id, invite_code)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (name, description, owner_id, invite_code))
                result = cur.fetchone()
                project_id = result['id'] if result else None
                
                # Добавить владельца как участника
                if project_id:
                    cur.execute("""
                        INSERT INTO project_members (project_id, user_id, role)
                        VALUES (%s, %s, 'owner')
                    """, (project_id, owner_id))
                
                conn.commit()
                return project_id
    
    def create_personal_project(self, user_id):
        """Создать персональный проект для пользователя"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO projects (name, description, owner_id, is_personal)
                    VALUES (%s, %s, %s, TRUE)
                    RETURNING id
                """, ("Мои задачи", "Персональные задачи", user_id))
                result = cur.fetchone()
                project_id = result['id'] if result else None
                
                if project_id:
                    cur.execute("""
                        INSERT INTO project_members (project_id, user_id, role)
                        VALUES (%s, %s, 'owner')
                    """, (project_id, user_id))
                
                conn.commit()
                return project_id
    
    def _get_cache_key(self, method_name, *args):
        """Создать ключ кэша"""
        return f"{method_name}:{':'.join(map(str, args))}"
    
    def _is_cache_valid(self, timestamp):
        """Проверить валидность кэша"""
        import time
        return time.time() - timestamp < self._cache_ttl
    
    def _invalidate_cache(self, pattern=None):
        """Очистить кэш (полностью или по паттерну)"""
        if pattern:
            keys_to_remove = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self._cache[key]
        else:
            self._cache.clear()
        logger.debug(f"Cache invalidated - pattern: {pattern} - operation: cache_invalidate")
    
    @measure_time
    def get_user_projects(self, user_id):
        """Получить проекты пользователя"""
        # Проверяем кэш
        cache_key = self._get_cache_key('get_user_projects', user_id)
        if cache_key in self._cache:
            cached_data, timestamp = self._cache[cache_key]
            if self._is_cache_valid(timestamp):
                logger.debug(f"Cache hit for get_user_projects - user_id: {user_id} - operation: cache_hit")
                return cached_data
        
        # Кэш промах - обращаемся к базе
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.*, pm.role,
                           (SELECT COUNT(*) FROM tasks WHERE project_id = p.id) as task_count,
                           (SELECT COUNT(*) FROM tasks WHERE project_id = p.id AND completed_at IS NOT NULL) as completed_count
                    FROM projects p
                    JOIN project_members pm ON p.id = pm.project_id
                    WHERE pm.user_id = %s
                    ORDER BY p.is_personal DESC, p.created_at DESC
                """, (user_id,))
                result = cur.fetchall()
                
                # Кэшируем результат
                import time
                self._cache[cache_key] = (result, time.time())
                logger.debug(f"Cached result for get_user_projects - user_id: {user_id} - operation: cache_store")
                
                return result
    
    def get_user_owned_projects(self, user_id):
        """Получить проекты, которыми владеет пользователь"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.*, pm.role,
                           (SELECT COUNT(*) FROM tasks WHERE project_id = p.id) as task_count,
                           (SELECT COUNT(*) FROM tasks WHERE project_id = p.id AND completed_at IS NOT NULL) as completed_count
                    FROM projects p
                    JOIN project_members pm ON p.id = pm.project_id
                    WHERE pm.user_id = %s AND pm.role = 'owner'
                    ORDER BY p.is_personal DESC, p.created_at DESC
                """, (user_id,))
                return cur.fetchall()
    
    def get_personal_project(self, user_id):
        """Получить персональный проект пользователя"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.* FROM projects p
                    JOIN project_members pm ON p.id = pm.project_id
                    WHERE pm.user_id = %s AND p.is_personal = TRUE
                    LIMIT 1
                """, (user_id,))
                result = cur.fetchone()
                
                # Если нет персонального проекта, создать его
                if not result:
                    project_id = self.create_personal_project(user_id)
                    cur.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
                    result = cur.fetchone()
                
                return result
    
    def join_project_by_code(self, user_id, invite_code):
        """Присоединиться к проекту по коду приглашения"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Найти проект по коду
                cur.execute("""
                    SELECT id, name FROM projects 
                    WHERE invite_code = %s AND is_personal = FALSE
                """, (invite_code,))
                project = cur.fetchone()
                
                if not project:
                    return False, "Проект не найден или код недействителен"
                
                # Проверить, не участвует ли уже пользователь
                cur.execute("""
                    SELECT id FROM project_members 
                    WHERE project_id = %s AND user_id = %s
                """, (project['id'], user_id))
                
                if cur.fetchone():
                    return False, "Вы уже участвуете в этом проекте"
                
                # Добавить пользователя в проект
                cur.execute("""
                    INSERT INTO project_members (project_id, user_id, role)
                    VALUES (%s, %s, 'member')
                """, (project['id'], user_id))
                
                conn.commit()
                return True, f"Успешно присоединились к проекту '{project['name']}'"
    
    def get_project_members(self, project_id):
        """Получить участников проекта"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT u.user_id, u.first_name, u.last_name, u.username, pm.role, pm.joined_at
                    FROM project_members pm
                    JOIN users u ON pm.user_id = u.user_id
                    WHERE pm.project_id = %s
                    ORDER BY pm.role = 'owner' DESC, pm.joined_at
                """, (project_id,))
                return cur.fetchall()
    
    def get_project_by_id(self, project_id, user_id=None):
        """Получить проект по ID"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if user_id:
                    # Проверить доступ пользователя к проекту
                    cur.execute("""
                        SELECT p.*, pm.role
                        FROM projects p
                        JOIN project_members pm ON p.id = pm.project_id
                        WHERE p.id = %s AND pm.user_id = %s
                    """, (project_id, user_id))
                else:
                    cur.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
                
                return cur.fetchone()
    
    def get_project_details(self, project_id, user_id):
        """Получить детали проекта с проверкой доступа пользователя"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.*, pm.role,
                           u.first_name as owner_name,
                           (SELECT COUNT(*) FROM tasks WHERE project_id = p.id) as task_count,
                           (SELECT COUNT(*) FROM tasks WHERE project_id = p.id AND completed_at IS NOT NULL) as completed_count,
                           (SELECT COUNT(*) FROM project_members WHERE project_id = p.id) as member_count
                    FROM projects p
                    JOIN project_members pm ON p.id = pm.project_id
                    JOIN users u ON p.owner_id = u.user_id
                    WHERE p.id = %s AND pm.user_id = %s
                """, (project_id, user_id))
                return cur.fetchone()
    
    def get_project_task_count(self, project_id, completed=None):
        """Получить количество задач в проекте"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if completed is None:
                    # Общее количество задач
                    cur.execute("""
                        SELECT COUNT(*) as count FROM tasks WHERE project_id = %s
                    """, (project_id,))
                elif completed:
                    # Количество выполненных задач
                    cur.execute("""
                        SELECT COUNT(*) as count FROM tasks 
                        WHERE project_id = %s AND completed_at IS NOT NULL
                    """, (project_id,))
                else:
                    # Количество активных задач
                    cur.execute("""
                        SELECT COUNT(*) as count FROM tasks 
                        WHERE project_id = %s AND completed_at IS NULL
                    """, (project_id,))
                
                result = cur.fetchone()
                return result['count'] if result else 0
    
    @measure_time
    def get_project_tasks(self, project_id, user_id, completed=None):
        """Получить задачи проекта"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Проверить доступ к проекту
                cur.execute("""
                    SELECT 1 FROM project_members 
                    WHERE project_id = %s AND user_id = %s
                """, (project_id, user_id))
                
                if not cur.fetchone():
                    return []
                
                # Получить задачи
                if completed is None:
                    cur.execute("""
                        SELECT t.*, u.first_name, u.username
                        FROM tasks t
                        JOIN users u ON t.user_id = u.user_id
                        WHERE t.project_id = %s 
                        ORDER BY t.created_at DESC
                    """, (project_id,))
                else:
                    if completed:
                        cur.execute("""
                            SELECT t.*, u.first_name, u.username
                            FROM tasks t
                            JOIN users u ON t.user_id = u.user_id
                            WHERE t.project_id = %s AND t.completed_at IS NOT NULL 
                            ORDER BY t.created_at DESC
                        """, (project_id,))
                    else:
                        cur.execute("""
                            SELECT t.*, u.first_name, u.username
                            FROM tasks t
                            JOIN users u ON t.user_id = u.user_id
                            WHERE t.project_id = %s AND t.completed_at IS NULL 
                            ORDER BY t.created_at DESC
                        """, (project_id,))
                
                return cur.fetchall()
    
    def complete_project_task(self, task_id, user_id):
        """Отметить задачу проекта как выполненную"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Проверить доступ к задаче через проект
                cur.execute("""
                    SELECT t.id FROM tasks t
                    JOIN project_members pm ON t.project_id = pm.project_id
                    WHERE t.id = %s AND pm.user_id = %s
                """, (task_id, user_id))
                
                if not cur.fetchone():
                    return False
                
                # Обновить задачу
                cur.execute("""
                    UPDATE tasks 
                    SET completed_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id
                """, (task_id,))
                result = cur.fetchone()
                conn.commit()
                return result is not None
    
    def delete_project_task(self, task_id, user_id):
        """Удалить задачу проекта"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Проверить права доступа (автор задачи или владелец проекта)
                cur.execute("""
                    SELECT t.id FROM tasks t
                    JOIN projects p ON t.project_id = p.id
                    JOIN project_members pm ON p.id = pm.project_id
                    WHERE t.id = %s AND pm.user_id = %s 
                    AND (t.user_id = %s OR pm.role = 'owner')
                """, (task_id, user_id, user_id))
                
                if not cur.fetchone():
                    return False
                
                cur.execute("DELETE FROM tasks WHERE id = %s RETURNING id", (task_id,))
                result = cur.fetchone()
                conn.commit()
                return result is not None
    
    def leave_project(self, project_id, user_id):
        """Покинуть проект"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Нельзя покинуть персональный проект
                cur.execute("""
                    SELECT is_personal, owner_id FROM projects 
                    WHERE id = %s
                """, (project_id,))
                project = cur.fetchone()
                
                if not project or project['is_personal']:
                    return False, "Нельзя покинуть персональный проект"
                
                if project['owner_id'] == user_id:
                    return False, "Владелец не может покинуть проект"
                
                cur.execute("""
                    DELETE FROM project_members 
                    WHERE project_id = %s AND user_id = %s
                    RETURNING id
                """, (project_id, user_id))
                
                result = cur.fetchone()
                conn.commit()
                return (result is not None), "Вы покинули проект" if result else "Ошибка при выходе"
    
    # === РАСШИРЕННЫЕ ФУНКЦИИ ЗАДАЧ ===
    
    def _add_history_entry(self, task_id, user_id, action, old_value=None, new_value=None):
        """Добавить запись в историю изменений"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO task_history (task_id, user_id, action, old_value, new_value)
                    VALUES (%s, %s, %s, %s, %s)
                """, (task_id, user_id, action, old_value, new_value))
                conn.commit()
    
    def update_task(self, task_id, user_id, **kwargs):
        """Обновить задачу с записью в историю"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Получить текущие значения
                cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
                current_task = cur.fetchone()
                
                if not current_task:
                    return False
                
                # Подготовить обновления
                updates = []
                values = []
                for field, value in kwargs.items():
                    if field in ['title', 'description', 'deadline', 'priority', 'tags', 
                               'category', 'assigned_to', 'time_estimate']:
                        updates.append(f"{field} = %s")
                        values.append(value)
                        
                        # Записать в историю если значение изменилось
                        old_value = current_task.get(field)
                        if old_value != value:
                            self._add_history_entry(task_id, user_id, f'updated_{field}', 
                                                  str(old_value), str(value))
                
                if updates:
                    values.append(task_id)
                    query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = %s"
                    cur.execute(query, values)
                
                conn.commit()
                return True
    
    def add_task_comment(self, task_id, user_id, comment_text):
        """Добавить комментарий к задаче"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO task_comments (task_id, user_id, comment_text)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (task_id, user_id, comment_text))
                result = cur.fetchone()
                
                # Записать в историю
                self._add_history_entry(task_id, user_id, 'commented', None, 
                                      f"Добавлен комментарий: {comment_text[:50]}...")
                
                conn.commit()
                return result['id'] if result else None
    
    def get_task_comments(self, task_id):
        """Получить комментарии к задаче"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT tc.*, u.first_name, u.username
                    FROM task_comments tc
                    JOIN users u ON tc.user_id = u.user_id
                    WHERE tc.task_id = %s
                    ORDER BY tc.created_at ASC
                """, (task_id,))
                return cur.fetchall()
    
    def get_task_history(self, task_id):
        """Получить историю изменений задачи"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT th.*, u.first_name, u.username
                    FROM task_history th
                    JOIN users u ON th.user_id = u.user_id
                    WHERE th.task_id = %s
                    ORDER BY th.created_at DESC
                """, (task_id,))
                return cur.fetchall()
    
    def get_tasks_with_deadlines(self, user_id, days_ahead=7):
        """Получить задачи с приближающимися дедлайнами"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                deadline_limit = datetime.now() + timedelta(days=days_ahead)
                cur.execute("""
                    SELECT t.*, p.name as project_name, u.first_name as assigned_first_name
                    FROM tasks t
                    JOIN projects p ON t.project_id = p.id
                    JOIN project_members pm ON p.id = pm.project_id
                    LEFT JOIN users u ON t.assigned_to = u.user_id
                    WHERE pm.user_id = %s 
                    AND t.deadline IS NOT NULL 
                    AND t.deadline <= %s 
                    AND t.completed_at IS NULL
                    ORDER BY t.deadline ASC
                """, (user_id, deadline_limit))
                return cur.fetchall()
    
    def assign_task(self, task_id, assigner_id, assignee_id):
        """Назначить задачу пользователю"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Проверить права доступа
                cur.execute("""
                    SELECT t.id, u.first_name as assignee_name
                    FROM tasks t
                    JOIN projects p ON t.project_id = p.id
                    JOIN project_members pm ON p.id = pm.project_id
                    LEFT JOIN users u ON u.user_id = %s
                    WHERE t.id = %s AND pm.user_id = %s
                """, (assignee_id, task_id, assigner_id))
                
                result = cur.fetchone()
                if not result:
                    return False, "Нет доступа к задаче или пользователь не найден"
                
                # Назначить задачу
                cur.execute("""
                    UPDATE tasks SET assigned_to = %s WHERE id = %s
                """, (assignee_id, task_id))
                
                # Записать в историю
                assignee_name = result['assignee_name'] or f"ID:{assignee_id}"
                self._add_history_entry(task_id, assigner_id, 'assigned', None, 
                                      f"Назначена пользователю: {assignee_name}")
                
                conn.commit()
                return True, f"Задача назначена пользователю {assignee_name}"
    
    def get_user_assigned_tasks(self, user_id, completed=False):
        """Получить задачи, назначенные пользователю"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT t.*, p.name as project_name, u.first_name as author_name
                    FROM tasks t
                    JOIN projects p ON t.project_id = p.id
                    JOIN users u ON t.user_id = u.user_id
                    WHERE t.assigned_to = %s AND (CASE WHEN %s THEN t.completed_at IS NOT NULL ELSE t.completed_at IS NULL END)
                    ORDER BY t.deadline ASC NULLS LAST, t.created_at DESC
                """, (user_id, completed))
                return cur.fetchall()
    
    # === ШАБЛОНЫ ЗАДАЧ ===
    
    def create_task_template(self, user_id, name, title_template, description_template=None,
                           default_priority='medium', default_tags=None, default_category=None,
                           default_time_estimate=None):
        """Создать шаблон задачи"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO task_templates (user_id, name, title_template, description_template,
                                              default_priority, default_tags, default_category, 
                                              default_time_estimate)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (user_id, name, title_template, description_template, default_priority,
                      default_tags, default_category, default_time_estimate))
                result = cur.fetchone()
                conn.commit()
                return result['id'] if result else None
    
    def get_user_templates(self, user_id):
        """Получить шаблоны пользователя"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM task_templates WHERE user_id = %s ORDER BY name
                """, (user_id,))
                return cur.fetchall()
    
    def create_task_from_template(self, template_id, user_id, project_id, custom_values=None):
        """Создать задачу из шаблона"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Получить шаблон
                cur.execute("SELECT * FROM task_templates WHERE id = %s AND user_id = %s", 
                          (template_id, user_id))
                template = cur.fetchone()
                
                if not template:
                    return None
                
                # Применить пользовательские значения
                values = custom_values or {}
                title = values.get('title', template['title_template'])
                description = values.get('description', template['description_template'])
                priority = values.get('priority', template['default_priority'])
                tags = values.get('tags', template['default_tags'])
                category = values.get('category', template['default_category'])
                time_estimate = values.get('time_estimate', template['default_time_estimate'])
                deadline = values.get('deadline')
                assigned_to = values.get('assigned_to')
                
                return self.add_task(user_id, title, description, project_id, deadline,
                                   priority, tags, category, assigned_to, time_estimate)
    
    # === ПОВТОРЯЮЩИЕСЯ ЗАДАЧИ ===
    
    def create_recurring_task(self, project_id, user_id, title, description=None,
                            priority='medium', tags=None, category=None,
                            recurrence_type='weekly', recurrence_interval=1):
        """Создать повторяющуюся задачу"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Рассчитать следующую дату
                next_due = self._calculate_next_due_date(recurrence_type, recurrence_interval)
                
                cur.execute("""
                    INSERT INTO recurring_tasks (project_id, user_id, title, description,
                                                priority, tags, category, recurrence_type,
                                                recurrence_interval, next_due_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (project_id, user_id, title, description, priority, tags, category,
                      recurrence_type, recurrence_interval, next_due))
                result = cur.fetchone()
                conn.commit()
                return result['id'] if result else None
    
    def _calculate_next_due_date(self, recurrence_type, interval=1):
        """Рассчитать следующую дату выполнения"""
        now = datetime.now()
        if recurrence_type == 'daily':
            return now + timedelta(days=interval)
        elif recurrence_type == 'weekly':
            return now + timedelta(weeks=interval)
        elif recurrence_type == 'monthly':
            return now + timedelta(days=30 * interval)
        return now + timedelta(days=1)
    
    def process_recurring_tasks(self):
        """Обработать повторяющиеся задачи (вызывать периодически)"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Найти задачи, которые нужно создать
                cur.execute("""
                    SELECT * FROM recurring_tasks 
                    WHERE is_active = TRUE AND next_due_date <= NOW()
                """)
                due_tasks = cur.fetchall()
                
                for task in due_tasks:
                    # Создать новую задачу
                    self.add_task(
                        user_id=task['user_id'],
                        title=task['title'],
                        description=task['description'],
                        project_id=task['project_id'],
                        priority=task['priority'],
                        tags=task['tags'],
                        category=task['category']
                    )
                    
                    # Обновить следующую дату
                    next_due = self._calculate_next_due_date(
                        task['recurrence_type'], 
                        task['recurrence_interval']
                    )
                    cur.execute("""
                        UPDATE recurring_tasks 
                        SET next_due_date = %s 
                        WHERE id = %s
                    """, (next_due, task['id']))
                
                conn.commit()
                return len(due_tasks)
    
    # === ПОЛЬЗОВАТЕЛЬСКИЕ НАСТРОЙКИ ===
    
    def get_user_settings(self, user_id):
        """Получить настройки пользователя"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM user_settings WHERE user_id = %s", (user_id,))
                result = cur.fetchone()
                
                if not result:
                    # Создать настройки по умолчанию
                    cur.execute("""
                        INSERT INTO user_settings (user_id) VALUES (%s)
                        RETURNING *
                    """, (user_id,))
                    result = cur.fetchone()
                    conn.commit()
                
                return result
    
    def update_user_settings(self, user_id, **kwargs):
        """Обновить настройки пользователя"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Убедиться, что настройки существуют
                self.get_user_settings(user_id)
                
                updates = []
                values = []
                for field, value in kwargs.items():
                    if field in ['timezone', 'language', 'theme', 'notifications_enabled',
                               'reminder_time', 'work_hours_start', 'work_hours_end']:
                        updates.append(f"{field} = %s")
                        values.append(value)
                
                if updates:
                    values.extend([datetime.now(), user_id])
                    query = f"""
                        UPDATE user_settings 
                        SET {', '.join(updates)}, updated_at = %s 
                        WHERE user_id = %s
                    """
                    cur.execute(query, values)
                    conn.commit()
                    return True
                return False
    
    def update_user_setting(self, user_id, field, value):
        """Обновить одну настройку пользователя"""
        return self.update_user_settings(user_id, **{field: value})
    
    # === АНАЛИТИКА ===
    
    def get_productivity_stats(self, user_id, days=30):
        """Получить статистику продуктивности за период"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                start_date = datetime.now() - timedelta(days=days)
                
                cur.execute("""
                    SELECT 
                        DATE(completed_at) as date,
                        COUNT(*) as completed_tasks,
                        SUM(time_spent) as total_time_spent
                    FROM tasks t
                    JOIN projects p ON t.project_id = p.id
                    JOIN project_members pm ON p.id = pm.project_id
                    WHERE pm.user_id = %s 
                    AND t.completed_at IS NOT NULL 
                    AND t.completed_at >= %s
                    GROUP BY DATE(completed_at)
                    ORDER BY date
                """, (user_id, start_date))
                
                return cur.fetchall()
    
    def get_category_stats(self, user_id):
        """Получить статистику по категориям"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COALESCE(category, 'Без категории') as category,
                        COUNT(*) as total_tasks,
                        COUNT(CASE WHEN completed = TRUE THEN 1 END) as completed_tasks,
                        AVG(time_spent) as avg_time_spent
                    FROM tasks t
                    JOIN projects p ON t.project_id = p.id
                    JOIN project_members pm ON p.id = pm.project_id
                    WHERE pm.user_id = %s
                    GROUP BY category
                    ORDER BY total_tasks DESC
                """, (user_id,))
                return cur.fetchall()
    
    def get_team_productivity(self, project_id):
        """Получить статистику команды по проекту"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        u.first_name,
                        u.username,
                        COUNT(*) as total_tasks,
                        COUNT(CASE WHEN t.completed_at IS NOT NULL THEN 1 END) as completed_tasks,
                        SUM(t.time_spent) as total_time_spent
                    FROM users u
                    JOIN tasks t ON u.user_id = t.user_id
                    WHERE t.project_id = %s
                    GROUP BY u.user_id, u.first_name, u.username
                    ORDER BY completed_tasks DESC
                """, (project_id,))
                return cur.fetchall()
    
    def get_project_team_stats(self, project_id):
        """Получить статистику команды проекта (алиас для get_team_productivity)"""
        return self.get_team_productivity(project_id)
    
    def get_task_details(self, task_id):
        """Получить детали задачи"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT t.*, p.name as project_name, u.first_name, u.username
                    FROM tasks t
                    JOIN projects p ON t.project_id = p.id
                    JOIN users u ON t.user_id = u.user_id
                    WHERE t.id = %s
                """, (task_id,))
                return cur.fetchone()
    
    def get_task_ai_analysis(self, task_id):
        """Получить сохраненный AI анализ задачи"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT ai_analysis, ai_analysis_date
                    FROM tasks 
                    WHERE id = %s AND ai_analysis IS NOT NULL
                """, (task_id,))
                return cur.fetchone()
    
    def save_task_ai_analysis(self, task_id, analysis_data):
        """Сохранить AI анализ задачи"""
        import json
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE tasks 
                    SET ai_analysis = %s, ai_analysis_date = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (json.dumps(analysis_data), task_id))
                conn.commit()
                return cur.rowcount > 0
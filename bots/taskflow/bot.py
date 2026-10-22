import os
from datetime import datetime, timedelta
import asyncio
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, ContextTypes, filters
from database import Database
from speech_recognition import SpeechRecognizer
from task_analyzer import analyze_task
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Импортируем новую систему логирования
from logger_config import StructuredLogger

# Импортируем модуль форматирования текста
from text_formatter import *

# Создаем структурированный логгер для бота
logger = StructuredLogger('TaskFlowBot')

# Состояния для ConversationHandler
(ADDING_TASK, CREATING_PROJECT, JOINING_PROJECT, SETTING_DEADLINE, 
 ADDING_TAGS, SETTING_PRIORITY, ADDING_COMMENT, CREATING_TEMPLATE,
 SETTING_RECURRING, ASSIGNING_TASK, ANALYZING_TASK) = range(11)

class TaskFlowBot:
    def __init__(self, token):
        self.token = token
        self.db = Database()
        self.application = Application.builder().token(token).job_queue(None).build()
        
        # Настройка планировщика для напоминаний
        self.scheduler = AsyncIOScheduler()
        
        # Инициализация модуля распознавания речи
        self.speech_recognizer = SpeechRecognizer()
        
        # Optional design-team mode (orders dashboard). Comma-separated Telegram ids in TEAM_USER_IDS;
        # leave empty to disable and run as a plain task manager.
        self.TEAM_IDS = {int(x) for x in os.getenv('TEAM_USER_IDS', '').replace(' ', '').split(',') if x}
        self.TEAM_NAME = os.getenv('TEAM_NAME', 'Design Team')
        
        # Статусы заказов для дизайн-команды
        self.ORDER_STATUSES = {
            'new': '🆕 Новый заказ',
            'in_progress': '🎨 В работе',
            'review': '👀 На проверке',
            'revision': '🔄 На доработке', 
            'completed': '✅ Завершён',
            'delivered': '🚀 Сдан клиенту',
            'paid': '💰 Оплачен'
        }
        
        # Типы дизайн-работ
        self.DESIGN_TYPES = {
            'logo': '🎯 Логотип',
            'branding': '🎨 Брендинг',
            'web_design': '💻 Веб-дизайн',
            'print': '📄 Полиграфия',
            'packaging': '📦 Упаковка',
            'ui_ux': '📱 UI/UX',
            'illustration': '🖼️ Иллюстрация',
            'social_media': '📱 SMM-дизайн'
        }
        
        self.setup_handlers()
    
    def is_team_member(self, user_id):
        """Проверить, является ли пользователь членом дизайн-команды"""
        return user_id in self.TEAM_IDS
    
    async def start_scheduler(self):
        """Запустить планировщик асинхронно"""
        if not self.scheduler.running:
            self.scheduler.start()
            
            # Настройка периодических задач
            self.scheduler.add_job(
                self.check_deadlines,
                CronTrigger(minute=0),  # Каждый час
                id='deadline_check'
            )
            
            self.scheduler.add_job(
                self.process_recurring_tasks,
                CronTrigger(hour=0, minute=0),  # Каждый день в полночь
                id='recurring_tasks'
            )
    
    def get_main_keyboard(self, user_id=None, context=None):
        """Расширенная основная клавиатура с переключением режимов для команды"""
        if user_id and self.is_team_member(user_id):
            # Проверяем текущий режим пользователя
            current_mode = 'orders'  # по умолчанию режим заказов
            if context and hasattr(context, 'user_data'):
                current_mode = context.user_data.get('mode', 'orders')
            
            if current_mode == 'orders':
                # Режим заказов для команды
                keyboard = [
                    ['🎨 Заказы', '➕ Новый заказ'],
                    ['📊 Дашборд команды', '👥 Команда'],
                    ['🔥 Активные заказы', '⏰ Дедлайны'],
                    ['💰 Оплаченные', '⚙️ Настройки'],
                    ['🔄 Режим задач']  # Кнопка переключения
                ]
            else:  # mode == 'tasks'
                # Режим обычных задач для команды
                keyboard = [
                    ['📂 Мои проекты', '➕ Создать проект'],
                    ['🔗 Присоединиться', '📊 Аналитика'],
                    ['🎯 Мои задачи', '⏰ Дедлайны'],
                    ['📋 Шаблоны', '⚙️ Настройки'],
                    ['🎨 Режим заказов']  # Кнопка переключения
                ]
        else:
            # Стандартная клавиатура для обычных пользователей
            keyboard = [
                ['📂 Мои проекты', '➕ Создать проект'],
                ['🔗 Присоединиться', '📊 Аналитика'],
                ['🎯 Мои задачи', '⏰ Дедлайны'],
                ['📋 Шаблоны', '⚙️ Настройки']
            ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    def get_projects_inline_keyboard(self, projects):
        """Создать inline клавиатуру для проектов"""
        keyboard = []
        for project in projects:
            if project['is_personal']:
                emoji = "👤"
                name = f"{emoji} {project['name']}"
            else:
                emoji = "👥"
                role_emoji = "👑" if project['role'] == 'owner' else "👨‍💻"
                name = f"{emoji} {project['name']} {role_emoji}"
            
            # Показать статистику задач
            task_info = f" ({project['task_count']}/{project['completed_count']})"
            button_text = f"{name}{task_info}"
            
            callback_data = f"project_{project['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        if not projects:
            keyboard.append([InlineKeyboardButton("📝 Нет проектов", callback_data="no_projects")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")])
        return InlineKeyboardMarkup(keyboard)
    
    def get_priority_emoji(self, priority):
        """Получить эмодзи для приоритета"""
        priority_emojis = {
            'low': '🟢',
            'medium': '🟡', 
            'high': '🔴',
            'urgent': '🚨'
        }
        return priority_emojis.get(priority, '⚪')
    
    def format_task_info(self, task):
        """Форматировать информацию о задаче"""
        priority_emoji = self.get_priority_emoji(task.get('priority', 'medium'))
        status_emoji = "✅" if task.get('completed_at') else ""
        
        # Дедлайн
        deadline_info = ""
        if task.get('deadline'):
            deadline = datetime.fromisoformat(str(task['deadline']).replace('Z', '+00:00'))
            now = datetime.now(deadline.tzinfo) if deadline.tzinfo else datetime.now()
            days_left = (deadline - now).days
            
            if days_left < 0:
                deadline_info = " 🔥ПРОСРОЧЕНО"
            elif days_left == 0:
                deadline_info = " ⚡СЕГОДНЯ"
            elif days_left <= 3:
                deadline_info = f" ⏰{days_left}д"
        
        # Назначение
        assigned_info = ""
        if task.get('assigned_to') and task.get('assigned_first_name'):
            assigned_info = f" 👤{task['assigned_first_name']}"
        
        # Теги
        tags_info = ""
        if task.get('tags'):
            tags = task['tags'].split(',')[:2]  # Показать первые 2 тега
            tags_info = f" #{'#'.join(tag.strip() for tag in tags)}"
        
        title = task['title'][:20] + "..." if len(task['title']) > 20 else task['title']
        
        return f"{status_emoji}{priority_emoji} {title}{deadline_info}{assigned_info}{tags_info}"
    
    # === ПЛАНИРОВЩИК И УВЕДОМЛЕНИЯ ===
    
    async def check_deadlines(self):
        """Проверить приближающиеся дедлайны и отправить уведомления"""
        try:
            # Получить всех пользователей с настройками
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT DISTINCT u.user_id, us.reminder_time, us.notifications_enabled
                        FROM users u
                        LEFT JOIN user_settings us ON u.user_id = us.user_id
                        WHERE COALESCE(us.notifications_enabled, TRUE) = TRUE
                    """)
                    users = cur.fetchall()
            
            for user in users:
                user_id = user['user_id']
                reminder_minutes = user.get('reminder_time', 60)  # По умолчанию за час
                
                # Получить задачи с приближающимися дедлайнами
                tasks_with_deadlines = self.db.get_tasks_with_deadlines(user_id, days_ahead=1)
                
                for task in tasks_with_deadlines:
                    deadline = datetime.fromisoformat(str(task['deadline']).replace('Z', '+00:00'))
                    now = datetime.now(deadline.tzinfo) if deadline.tzinfo else datetime.now()
                    minutes_until_deadline = (deadline - now).total_seconds() / 60
                    
                    # Отправить напоминание если время подошло
                    if 0 <= minutes_until_deadline <= reminder_minutes and not task.get('reminder_sent'):
                        await self.send_deadline_reminder(user_id, task)
                        
                        # Отметить что напоминание отправлено
                        with self.db.get_connection() as conn:
                            with conn.cursor() as cur:
                                cur.execute("""
                                    UPDATE tasks SET reminder_sent = TRUE WHERE id = %s
                                """, (task['id'],))
                                conn.commit()
                        
        except Exception as e:
            logger.error("Ошибка при проверке дедлайнов", error=str(e), operation="check_deadlines")
    
    async def send_deadline_reminder(self, user_id, task):
        """Отправить напоминание о дедлайне"""
        try:
            deadline = datetime.fromisoformat(str(task['deadline']).replace('Z', '+00:00'))
            deadline_str = deadline.strftime("%d.%m.%Y в %H:%M")
            
            message = f"""{bold('⏰ Напоминание о дедлайне!')}

{bold('📋 Задача:')} {task['title']}
{bold('📂 Проект:')} {task['project_name']}
{bold('⏰ Дедлайн:')} {deadline_str}

{italic('Не забудьте выполнить задачу вовремя!')} 🎯"""
            
            await self.application.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error("Ошибка отправки напоминания", error=str(e), user_id=user_id, operation="send_reminder")
    
    async def process_recurring_tasks(self):
        """Обработать повторяющиеся задачи"""
        try:
            created_count = self.db.process_recurring_tasks()
            logger.info("Повторяющиеся задачи обработаны", created_count=created_count)
        except Exception as e:
            logger.error("Ошибка обработки повторяющихся задач", error=str(e), operation="process_recurring")
    
    # === НОВЫЕ ОБРАБОТЧИКИ КОМАНД ===
    
    async def show_my_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать все задачи пользователя"""
        user_id = update.effective_user.id
        
        # Получить задачи, назначенные пользователю
        assigned_tasks = self.db.get_user_assigned_tasks(user_id, completed=False)
        
        if not assigned_tasks:
            await update.message.reply_text(
                f"{bold('🎯 Мои задачи')}\n\nУ вас нет назначенных задач.",
                parse_mode='HTML',
                reply_markup=self.get_main_keyboard()
            )
            return
        
        message = f"{bold('🎯 Мои назначенные задачи:')}\n\n"
        for task in assigned_tasks:
            priority_emoji = self.get_priority_emoji(task.get('priority', 'medium'))
            deadline_info = ""
            
            if task.get('deadline'):
                deadline = datetime.fromisoformat(str(task['deadline']).replace('Z', '+00:00'))
                now = datetime.now(deadline.tzinfo) if deadline.tzinfo else datetime.now()
                days_left = (deadline - now).days
                
                if days_left < 0:
                    deadline_info = f" {bold('🔥ПРОСРОЧЕНО')}"
                elif days_left == 0:
                    deadline_info = f" {bold('⚡СЕГОДНЯ')}"
                elif days_left <= 3:
                    deadline_info = f" {bold(f'⏰{days_left}д')}"
            
            message += f"{priority_emoji} {bold(task['title'])}{deadline_info}\n"
            message += f"{bold('📂')} {task['project_name']} | {bold('✍️')} {task['author_name']}\n"
            if task.get('description'):
                message += f"{bold('📝')} {task['description'][:50]}...\n"
            message += "\n"
        
        keyboard = [[InlineKeyboardButton("📋 Показать выполненные", callback_data="show_completed_assigned")]]
        
        await update.message.reply_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def show_deadlines(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать задачи с приближающимися дедлайнами"""
        user_id = update.effective_user.id
        
        # Получить задачи с дедлайнами
        tasks_with_deadlines = self.db.get_tasks_with_deadlines(user_id, days_ahead=7)
        
        if not tasks_with_deadlines:
            await update.message.reply_text(
                f"{bold('⏰ Дедлайны')}\n\nНет задач с дедлайнами на ближайшие 7 дней.",
                parse_mode='HTML',
                reply_markup=self.get_main_keyboard()
            )
            return
        
        message = f"{bold('⏰ Приближающиеся дедлайны:')}\n\n"
        
        # Группировать по статусу дедлайна
        overdue = []
        today = []
        soon = []
        later = []
        
        for task in tasks_with_deadlines:
            deadline = datetime.fromisoformat(str(task['deadline']).replace('Z', '+00:00'))
            now = datetime.now(deadline.tzinfo) if deadline.tzinfo else datetime.now()
            days_left = (deadline - now).days
            
            task_info = {
                'task': task,
                'deadline': deadline,
                'days_left': days_left
            }
            
            if days_left < 0:
                overdue.append(task_info)
            elif days_left == 0:
                today.append(task_info)
            elif days_left <= 3:
                soon.append(task_info)
            else:
                later.append(task_info)
        
        # Показать по группам
        if overdue:
            message += f"{bold('🔥 ПРОСРОЧЕННЫЕ:')}\n"
            for item in overdue:
                task = item['task']
                deadline_str = item['deadline'].strftime("%d.%m %H:%M")
                message += f"• {task['title']} ({deadline_str})\n"
            message += "\n"
        
        if today:
            message += f"{bold('⚡ СЕГОДНЯ:')}\n"
            for item in today:
                task = item['task']
                deadline_str = item['deadline'].strftime("%H:%M")
                message += f"• {task['title']} ({deadline_str})\n"
            message += "\n"
        
        if soon:
            message += f"{bold('⏰ БЛИЖАЙШИЕ ДНИ:')}\n"
            for item in soon:
                task = item['task']
                deadline_str = item['deadline'].strftime("%d.%m %H:%M")
                days_text = f"{item['days_left']}д"
                message += f"• {task['title']} ({deadline_str}, {days_text})\n"
            message += "\n"
        
        if later:
            message += f"{bold('📅 НА НЕДЕЛЕ:')}\n"
            for item in later:
                task = item['task']
                deadline_str = item['deadline'].strftime("%d.%m")
                message += f"• {task['title']} ({deadline_str})\n"
        
        await update.message.reply_text(
            message,
            parse_mode='HTML',
            reply_markup=self.get_main_keyboard()
        )
    
    async def show_analytics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать аналитику и статистику"""
        user_id = update.effective_user.id
        
        # Получить статистику продуктивности
        productivity_stats = self.db.get_productivity_stats(user_id, days=30)
        category_stats = self.db.get_category_stats(user_id)
        
        message = f"{bold('📊 Аналитика за 30 дней')}\n\n"
        
        # Общая статистика
        total_completed = sum(stat['completed_tasks'] for stat in productivity_stats)
        total_time = sum(stat['total_time_spent'] or 0 for stat in productivity_stats)
        
        message += f"{bold('✅ Выполнено задач:')} {bold(str(total_completed))}\n"
        if total_time:
            hours = total_time // 60
            minutes = total_time % 60
            message += f"{bold('⏱ Потрачено времени:')} {bold(f'{hours}ч {minutes}м')}\n"
        
        # Статистика по категориям
        if category_stats:
            message += f"\n{bold('📋 По категориям:')}\n"
            for stat in category_stats[:5]:  # Топ 5 категорий
                completion_rate = 0
                if stat['total_tasks'] > 0:
                    completion_rate = (stat['completed_tasks'] / stat['total_tasks']) * 100
                
                message += f"• {stat['category']}: {stat['completed_tasks']}/{stat['total_tasks']} ({completion_rate:.0f}%)\n"
        
        # Последняя активность
        if productivity_stats:
            recent_activity = productivity_stats[-7:]  # Последние 7 дней
            if recent_activity:
                message += f"\n{bold('📈 Активность по дням:')}\n"
                for stat in recent_activity:
                    date_str = stat['date'].strftime("%d.%m")
                    message += f"• {date_str}: {stat['completed_tasks']} задач\n"
        
        keyboard = [
            [InlineKeyboardButton("📊 Подробная статистика", callback_data="detailed_analytics")],
            [InlineKeyboardButton("👥 Статистика команды", callback_data="team_analytics")]
        ]
        
        await update.message.reply_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def show_templates(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать шаблоны задач"""
        user_id = update.effective_user.id
        
        templates = self.db.get_user_templates(user_id)
        
        message = f"{bold('📋 Шаблоны задач')}\n\n"
        
        if templates:
            message += f"{italic('Ваши шаблоны:')}\n"
            for template in templates:
                priority_emoji = self.get_priority_emoji(template.get('default_priority', 'medium'))
                message += f"{priority_emoji} {bold(template['name'])}\n"
                message += f"{bold('📝')} {template['title_template']}\n"
                if template.get('default_tags'):
                    message += f"{bold('🏷')} {template['default_tags']}\n"
                message += "\n"
        else:
            message += f"{italic('У вас пока нет шаблонов задач.')}\n\n"
        
        message += f"{italic('Используйте шаблоны для быстрого создания повторяющихся задач!')}"
        
        keyboard = [
            [InlineKeyboardButton("➕ Создать шаблон", callback_data="create_template")],
        ]
        
        if templates:
            keyboard.append([InlineKeyboardButton("🗑 Удалить шаблон", callback_data="delete_template")])
        
        await update.message.reply_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def show_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать настройки пользователя"""
        user_id = update.effective_user.id
        
        try:
            settings = self.db.get_user_settings(user_id)
            
            message = f"{bold('⚙️ Настройки')}\n\n"
            
            # Уведомления
            notifications_status = "✅ Включены" if settings.get('notifications_enabled', True) else "❌ Отключены"
            message += f"{bold('🔔 Уведомления:')} {notifications_status}\n"
            
            # Время напоминаний
            reminder_time = settings.get('reminder_time', 60)
            if reminder_time >= 60:
                hours = reminder_time // 60
                minutes = reminder_time % 60
                time_text = f"{hours}ч" + (f" {minutes}м" if minutes else "")
            else:
                time_text = f"{reminder_time}м"
            message += f"{bold('⏰ Напоминания за:')} {time_text}\n"
            
            # Часовой пояс
            timezone = settings.get('timezone', 'UTC')
            message += f"{bold('🌍 Часовой пояс:')} {timezone}\n"
            
            # Язык
            language = settings.get('language', 'ru')
            language_name = {'ru': 'Русский', 'en': 'English'}.get(language, language)
            message += f"{bold('🌐 Язык:')} {language_name}\n"
            
            # Тема
            theme = settings.get('theme', 'default')
            theme_name = {'default': 'По умолчанию', 'dark': 'Темная', 'light': 'Светлая'}.get(theme, theme)
            message += f"{bold('🎨 Тема:')} {theme_name}\n"
            
            keyboard = [
                [InlineKeyboardButton("🔔 Уведомления", callback_data="settings_notifications")],
                [InlineKeyboardButton("⏰ Напоминания", callback_data="settings_reminders")],
                [InlineKeyboardButton("🌍 Часовой пояс", callback_data="settings_timezone")],
                [InlineKeyboardButton("🌐 Язык", callback_data="settings_language")],
                [InlineKeyboardButton("🎨 Тема", callback_data="settings_theme")]
            ]
            
            await update.message.reply_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка получения настроек", error=str(e), user_id=user_id)
            await update.message.reply_text(
                "❌ Ошибка при загрузке настроек. Попробуйте позже.",
                reply_markup=self.get_main_keyboard()
            )
    
    # === ОСНОВНЫЕ ОБРАБОТЧИКИ ===
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        
        # Регистрируем пользователя в базе данных
        self.db.register_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        logger.info("Пользователь запустил бота", user_id=user.id, username=user.username)
        
        if self.is_team_member(user.id):
            # Специальное приветствие для дизайн-команды
            welcome_message = f"""{bold('🎨 Добро пожаловать в Design Hub!')}

{italic('Система управления заказами для дизайн-команды')}

{bold('🚀 Возможности для дизайнеров:')}
• 🎨 Управление заказами
• 📊 Дашборд команды  
• 🔥 Отслеживание активных проектов
• 💰 Контроль оплат
• ⏰ Управление дедлайнами
• 🎯 Типизированные дизайн-проекты
• 📈 Аналитика продуктивности

{bold('🎯 Добро пожаловать в команду!')}"""
        else:
            # Стандартное приветствие
            welcome_message = f"""{bold('🎯 Добро пожаловать в TaskFlow!')}

{italic('Ваш персональный помощник для управления задачами и проектами.')}

{bold('🚀 Возможности:')}
• 📂 Создание и управление проектами
• 🎯 Добавление и отслеживание задач
• 👥 Командная работа
• ⏰ Напоминания и дедлайны
• 📊 Аналитика продуктивности
• 🎙 Голосовые сообщения
• 🤖 AI-анализ задач

{bold('💡 Начните с создания проекта или добавления задачи!')}"""
        
        await update.message.reply_text(
            welcome_message,
            parse_mode='HTML',
            reply_markup=self.get_main_keyboard(user.id, context)
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = f"""{bold('📖 Справка по TaskFlow')}

{bold('🎯 Основные команды:')}
/start - Запуск бота
/help - Эта справка
/projects - Мои проекты
/tasks - Мои задачи
/analytics - Статистика

{bold('📂 Работа с проектами:')}
• Создавайте личные и командные проекты
• Приглашайте участников по коду
• Управляйте ролями и правами

{bold('🎯 Управление задачами:')}
• Добавляйте задачи с описанием
• Устанавливайте приоритеты и дедлайны
• Назначайте исполнителей
• Добавляйте теги и комментарии

{bold('🤖 AI-функции:')}
• Анализ сложности задач
• Автоматическое определение приоритета
• Рекомендации по выполнению

{bold('🎙 Голосовые сообщения:')}
• Отправляйте голосовые заметки
• Автоматическое распознавание речи
• Создание задач из аудио

{bold('📊 Аналитика:')}
• Статистика продуктивности
• Отчеты по проектам
• Анализ времени выполнения

{italic('Используйте кнопки меню для быстрого доступа к функциям!')}"""
        
        await update.message.reply_text(
            help_text,
            parse_mode='HTML',
            reply_markup=self.get_main_keyboard()
        )
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        text = update.message.text
        user_id = update.effective_user.id
        
        # Проверка состояния добавления задачи
        if context.user_data.get('adding_task_to_project'):
            project_id = context.user_data['adding_task_to_project']
            await self.process_new_task(update, context, project_id, text)
            return
        
        # Проверка состояния создания нового заказа для команды
        if self.is_team_member(user_id) and context.user_data.get('creating_order'):
            await self.process_new_order(update, context, text)
            return
        
        # Обработка переключения режимов для команды
        if self.is_team_member(user_id):
            if text == '🔄 Режим задач':
                context.user_data['mode'] = 'tasks'
                await update.message.reply_text(
                    "🔄 Переключено в режим управления задачами",
                    parse_mode='HTML',
                    reply_markup=self.get_main_keyboard(user_id, context)
                )
                return
            elif text == '🎨 Режим заказов':
                context.user_data['mode'] = 'orders'
                await update.message.reply_text(
                    "🎨 Переключено в режим управления заказами команды",
                    parse_mode='HTML',
                    reply_markup=self.get_main_keyboard(user_id, context)
                )
                return
        
        # Специальная обработка для дизайн-команды в режиме заказов
        if self.is_team_member(user_id) and context.user_data.get('mode', 'orders') == 'orders':
            if text == '🎨 Заказы':
                await self.show_team_orders(update, context)
                return
            elif text == '➕ Новый заказ':
                await self.start_new_order(update, context)
                return
            elif text == '📊 Дашборд команды':
                await self.show_team_dashboard(update, context)
                return
            elif text == '👥 Команда':
                await self.show_team_team(update, context)
                return
            elif text == '🔥 Активные заказы':
                await self.show_active_orders(update, context)
                return
            elif text == '💰 Оплаченные':
                await self.show_paid_orders(update, context)
                return
        
        # Обработка кнопок главного меню
        if text == '📂 Мои проекты':
            await self.show_projects(update, context)
        elif text == '➕ Создать проект':
            await self.start_create_project(update, context)
        elif text == '🔗 Присоединиться':
            await self.start_join_project(update, context)
        elif text == '📊 Аналитика':
            await self.show_analytics(update, context)
        elif text == '🎯 Мои задачи':
            await self.show_my_tasks(update, context)
        elif text == '⏰ Дедлайны':
            await self.show_deadlines(update, context)
        elif text == '📋 Шаблоны':
            await self.show_templates(update, context)
        elif text == '⚙️ Настройки':
            await self.show_settings(update, context)
        else:
            # Если текст не распознан как команда меню
            await update.message.reply_text(
                f"{italic('Используйте кнопки меню для навигации или отправьте /help для справки.')}",
                parse_mode='HTML',
                reply_markup=self.get_main_keyboard(user_id)
            )
    
    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик голосовых сообщений"""
        try:
            # Получаем файл голосового сообщения
            voice_file = await update.message.voice.get_file()
            
            # Отправляем сообщение о начале обработки
            processing_message = await update.message.reply_text(
                f"{italic('🎙 Обрабатываю голосовое сообщение...')}",
                parse_mode='HTML'
            )
            
            # Распознаем речь
            raw_text, success, processed_data = await self.speech_recognizer.recognize_voice_message(voice_file, voice_file.file_id)
            
            if success and raw_text:
                # Удаляем сообщение о обработке
                await processing_message.delete()
                
                # Используем обработанные данные если они есть, иначе анализируем сырой текст
                if processed_data:
                    analysis = processed_data
                else:
                    # Формируем данные для анализа
                    task_data = {'description': raw_text, 'title': None}
                    analysis = analyze_task(task_data) or {}
                
                # Формируем сообщение с AI-анализом только если есть полезные данные
                ai_parts = []
                
                title = analysis.get('title', '').strip()
                if title:
                    ai_parts.append(f"{bold('📋 Заголовок:')} {title}")
                
                description = analysis.get('description', '').strip()
                if description and description != raw_text:
                    ai_parts.append(f"{bold('📝 Описание:')} {description}")
                
                priority = analysis.get('priority', '').strip()
                if priority and priority != 'medium':
                    ai_parts.append(f"{bold('⚡ Приоритет:')} {priority}")
                
                tags = analysis.get('tags', '').strip()
                if tags and tags != 'Не определены':
                    ai_parts.append(f"{bold('🏷 Теги:')} {tags}")
                
                # Строим итоговое сообщение
                message = f"{bold('🎙 Распознанный текст:')}\n{italic(raw_text)}\n\n"
                
                if ai_parts:
                    message += f"{bold('🤖 AI-анализ:')}\n" + "\n".join(ai_parts) + "\n\n"
                
                message += italic('Хотите создать задачу на основе этого анализа?')
                
                keyboard = [
                    [InlineKeyboardButton("✅ Создать задачу", callback_data=f"create_task_from_voice_{analysis.get('title', 'Задача')}")],
                    [InlineKeyboardButton("❌ Отмена", callback_data="cancel_voice_task")]
                ]
                
                # Сохраняем анализ в контексте для последующего использования
                context.user_data['voice_analysis'] = analysis
                context.user_data['voice_text'] = raw_text
                
                await update.message.reply_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await processing_message.edit_text(
                    "❌ Не удалось распознать речь. Попробуйте еще раз."
                )
                
        except Exception as e:
            logger.error("Ошибка обработки голосового сообщения", error=str(e), user_id=update.effective_user.id)
            await update.message.reply_text(
                "❌ Ошибка при обработке голосового сообщения. Попробуйте позже.",
                reply_markup=self.get_main_keyboard()
            )
    
    # === ПРОЕКТЫ ===
    
    async def show_projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список проектов пользователя"""
        user_id = update.effective_user.id
        
        try:
            projects = self.db.get_user_projects(user_id)
            
            if not projects:
                message = f"""{bold('📂 Мои проекты')}

{italic('У вас пока нет проектов.')}

{bold('💡 Создайте свой первый проект:')}
• Личный проект для персональных задач
• Командный проект для совместной работы

{italic('Используйте кнопку "➕ Создать проект" в меню!')}"""
                
                await update.message.reply_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=self.get_main_keyboard()
                )
                return
            
            message = f"{bold('📂 Мои проекты:')}\n\n"
            
            # Группируем проекты
            personal_projects = [p for p in projects if p['is_personal']]
            team_projects = [p for p in projects if not p['is_personal']]
            
            if personal_projects:
                message += f"{bold('👤 Личные проекты:')}\n"
                for project in personal_projects:
                    progress = 0
                    if project['task_count'] > 0:
                        progress = (project['completed_count'] / project['task_count']) * 100
                    
                    message += f"• {bold(project['name'])} ({project['completed_count']}/{project['task_count']}, {progress:.0f}%)\n"
                message += "\n"
            
            if team_projects:
                message += f"{bold('👥 Командные проекты:')}\n"
                for project in team_projects:
                    role_emoji = "👑" if project['role'] == 'owner' else "👨‍💻"
                    progress = 0
                    if project['task_count'] > 0:
                        progress = (project['completed_count'] / project['task_count']) * 100
                    
                    message += f"• {role_emoji} {bold(project['name'])} ({project['completed_count']}/{project['task_count']}, {progress:.0f}%)\n"
                message += "\n"
            
            message += f"{italic('Выберите проект для просмотра задач:')}"
            
            await update.message.reply_text(
                message,
                parse_mode='HTML',
                reply_markup=self.get_projects_inline_keyboard(projects)
            )
            
        except Exception as e:
            logger.error("Ошибка получения проектов", error=str(e), user_id=user_id)
            await update.message.reply_text(
                "❌ Ошибка при загрузке проектов. Попробуйте позже.",
                reply_markup=self.get_main_keyboard()
            )
    
    async def start_create_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать создание нового проекта"""
        message = f"""{bold('➕ Создание нового проекта')}

{bold('Выберите тип проекта:')}

{bold('👤 Личный проект:')}
• Только для ваших задач
• Полный контроль
• Приватность

{bold('👥 Командный проект:')}
• Совместная работа
• Назначение задач
• Управление участниками

{italic('Какой тип проекта вы хотите создать?')}"""
        
        keyboard = [
            [InlineKeyboardButton("👤 Личный проект", callback_data="create_personal_project")],
            [InlineKeyboardButton("👥 Командный проект", callback_data="create_team_project")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]
        ]
        
        await update.message.reply_text(
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def start_join_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать присоединение к проекту"""
        message = f"""{bold('🔗 Присоединение к проекту')}

{italic('Отправьте код приглашения, который вам предоставил владелец проекта.')}

{bold('💡 Код выглядит примерно так:')} ABC123

{italic('Введите код приглашения:')}"""
        
        await update.message.reply_text(
            message,
            parse_mode='HTML'
        )
        
        return JOINING_PROJECT
    
    # === CALLBACK ОБРАБОТЧИКИ ===
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback запросов"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = update.effective_user.id
        
        try:
            if data == "back_to_menu":
                await query.edit_message_text(
                    f"{bold('🏠 Главное меню')}\n\n{italic('Выберите действие из меню ниже:')}",
                    parse_mode='HTML'
                )
                # Отправляем новое сообщение с клавиатурой
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Используйте кнопки меню:",
                    reply_markup=self.get_main_keyboard()
                )
            
            elif data.startswith("project_"):
                project_id = int(data.split("_")[1])
                await self.show_project_details(query, context, project_id)
            
            elif data == "create_personal_project":
                await self.handle_create_personal_project(query, context)
            
            elif data == "create_team_project":
                await self.handle_create_team_project(query, context)
            
            elif data.startswith("task_"):
                task_id = int(data.split("_")[1])
                await self.show_task_details(query, context, task_id)
            
            elif data.startswith("complete_task_"):
                task_id = int(data.split("_")[2])
                await self.complete_task(query, context, task_id)
            
            elif data.startswith("add_task_"):
                project_id = int(data.split("_")[2])
                await self.start_add_task(query, context, project_id)
            
            elif data == "show_completed_assigned":
                await self.show_completed_assigned_tasks(query, context)
            
            elif data.startswith("create_task_from_voice_"):
                await self.create_task_from_voice(query, context)
            
            elif data == "cancel_voice_task":
                await query.edit_message_text(
                    "❌ Создание задачи отменено.",
                    parse_mode='HTML'
                )
            
            elif data.startswith("voice_task_project_"):
                project_id = int(data.split("_")[-1])
                await self.create_voice_task_in_project(query, context, project_id)
            
            # team team callbacks
            elif data.startswith("team_"):
                await self.handle_team_callback(query, context, data)
            
            elif data.startswith("new_order_type_"):
                order_type = data.replace("new_order_type_", "")
                await self.handle_new_order_type(query, context, order_type)
            
            elif data == "cancel_new_order":
                user_id = query.from_user.id
                await query.edit_message_text(
                    "❌ Создание заказа отменено.",
                    parse_mode='HTML'
                )
            
            # Настройки
            elif data.startswith("settings_"):
                setting_type = data.split("_")[1]
                await self.handle_settings_callback(query, context, setting_type)
            
            # Аналитика
            elif data == "detailed_analytics":
                await self.show_detailed_analytics(query, context)
            
            elif data == "team_analytics":
                await self.show_team_analytics(query, context)
            
            # Шаблоны
            elif data == "create_template":
                await self.start_create_template(query, context)
            
            elif data == "delete_template":
                await self.start_delete_template(query, context)
            
            # Недостающие обработчики - исправление кнопок
            elif data == "no_projects":
                await self.show_projects_callback(query, context)
            
            elif data == "back_to_projects":
                await self.show_projects_callback(query, context)
            
            elif data.startswith("all_tasks_"):
                project_id = int(data.split("_")[2])
                await self.show_project_tasks(query, context, project_id, filter_type="all")
            
            elif data.startswith("completed_tasks_"):
                project_id = int(data.split("_")[2])
                await self.show_project_tasks(query, context, project_id, filter_type="completed")
            
            elif data == "back_to_my_tasks":
                await self.show_my_tasks_callback(query, context)
            
            elif data.startswith("members_"):
                project_id = int(data.split("_")[1])
                await self.show_project_members(query, context, project_id)
            
            elif data.startswith("project_settings_"):
                project_id = int(data.split("_")[2])
                await self.show_project_settings(query, context, project_id)
            
            elif data == "cancel_delete_template":
                await query.edit_message_text(
                    "❌ Удаление шаблона отменено.",
                    parse_mode='HTML'
                )
            
            # Настройки - конкретные значения
            elif data.startswith("reminder_time_"):
                minutes = int(data.split("_")[2])
                await self.handle_reminder_time_setting(query, context, minutes)
            
            elif data.startswith("timezone_"):
                timezone = data.split("_", 1)[1]
                await self.handle_timezone_setting(query, context, timezone)
            
            elif data.startswith("language_"):
                language = data.split("_")[1]
                await self.handle_language_setting(query, context, language)
            
            elif data.startswith("theme_"):
                theme = data.split("_")[1]
                await self.handle_theme_setting(query, context, theme)
            
            else:
                await query.edit_message_text(
                    "❌ Неизвестная команда.",
                    parse_mode='HTML'
                )
                
        except Exception as e:
            logger.error("Ошибка обработки callback", error=str(e), user_id=user_id, callback_data=data)
            await query.edit_message_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML'
            )
    
    async def show_projects_callback(self, query, context):
        """Показать проекты пользователя (callback version)"""
        user_id = query.from_user.id
        
        try:
            projects = self.db.get_user_projects(user_id)
            
            if not projects:
                message = f"{bold('📂 Мои проекты')}\n\n{italic('У вас пока нет проектов.')}"
                keyboard = [
                    [InlineKeyboardButton("➕ Создать проект", callback_data="create_personal_project")],
                    [InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]
                ]
                
                await query.edit_message_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return
            
            message = f"{bold('📂 Мои проекты:')}\n\n"
            keyboard = []
            
            # Группируем проекты
            personal_projects = [p for p in projects if p['is_personal']]
            team_projects = [p for p in projects if not p['is_personal']]
            
            if personal_projects:
                message += f"{bold('👤 Личные проекты:')}\n"
                for project in personal_projects:
                    progress = 0
                    if project['task_count'] > 0:
                        progress = (project['completed_count'] / project['task_count']) * 100
                    
                    message += f"• {bold(project['name'])} ({project['completed_count']}/{project['task_count']}, {progress:.0f}%)\n"
                    keyboard.append([InlineKeyboardButton(f"👤 {project['name']}", callback_data=f"project_{project['id']}")])
                message += "\n"
            
            if team_projects:
                message += f"{bold('👥 Командные проекты:')}\n"
                for project in team_projects:
                    progress = 0
                    if project['task_count'] > 0:
                        progress = (project['completed_count'] / project['task_count']) * 100
                    
                    role_emoji = "👑" if project['role'] == 'owner' else "👨‍💻"
                    message += f"• {role_emoji} {bold(project['name'])} ({project['completed_count']}/{project['task_count']}, {progress:.0f}%)\n"
                    keyboard.append([InlineKeyboardButton(f"👥 {project['name']}", callback_data=f"project_{project['id']}")])
            
            keyboard.append([InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")])
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка показа проектов", error=str(e), user_id=user_id)
            await query.edit_message_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML'
            )
    
    async def show_my_tasks_callback(self, query, context):
        """Показать мои задачи (callback version)"""
        user_id = query.from_user.id
        
        try:
            assigned_tasks = self.db.get_user_assigned_tasks(user_id, completed=False)
            
            if not assigned_tasks:
                message = f"{bold('📋 Мои задачи')}\n\n{italic('У вас нет назначенных задач.')}"
                keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]]
                
                await query.edit_message_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return
            
            message = f"{bold('📋 Назначенные мне задачи:')}\n\n"
            keyboard = []
            
            for task in assigned_tasks[:10]:  # Показать первые 10 задач
                priority = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task.get('priority', 'medium'), "🟡")
                deadline = ""
                if task.get('deadline'):
                    deadline = f" ⏰ {task['deadline'].strftime('%d.%m')}"
                
                message += f"{priority} {bold(task['title'])} ({task['project_name']}){deadline}\n"
                keyboard.append([InlineKeyboardButton(f"{priority} {task['title']}", callback_data=f"task_{task['id']}")])
            
            if len(assigned_tasks) > 10:
                message += f"\n{italic(f'... и еще {len(assigned_tasks) - 10} задач')}"
            
            keyboard.append([InlineKeyboardButton("✅ Выполненные", callback_data="show_completed_assigned")])
            keyboard.append([InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")])
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка показа моих задач", error=str(e), user_id=user_id)
            await query.edit_message_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML'
            )
    
    async def show_project_tasks(self, query, context, project_id, filter_type="active"):
        """Показать задачи проекта с фильтром"""
        user_id = query.from_user.id
        
        try:
            project = self.db.get_project_by_id(project_id, user_id)
            if not project:
                await query.edit_message_text(
                    "❌ Проект не найден или у вас нет доступа.",
                    parse_mode='HTML'
                )
                return
            
            # Определить фильтр
            if filter_type == "active":
                tasks = self.db.get_project_tasks(project_id, user_id, completed=False)
                filter_name = "активные"
            elif filter_type == "completed":
                tasks = self.db.get_project_tasks(project_id, user_id, completed=True)
                filter_name = "выполненные"
            else:  # all
                tasks = self.db.get_project_tasks(project_id, user_id)
                filter_name = "все"
            
            project_emoji = "👤" if project['is_personal'] else "👥"
            
            project_name = project['name']
            message = f"{bold(f'{project_emoji} {project_name} - {filter_name} задачи')}\n\n"
            
            if tasks:
                for task in tasks[:10]:  # Первые 10 задач
                    status = "✅" if task.get('completed_at') else "⏳"
                    priority = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task.get('priority', 'medium'), "🟡")
                    message += f"{status} {priority} {bold(task['title'])}\n"
                    
                    # Добавляем кнопки действий для активных задач
                    if filter_type == "active":
                        keyboard.append([InlineKeyboardButton(f"{status} {priority} {task['title']}", callback_data=f"task_{task['id']}")])
                
                if len(tasks) > 10:
                    message += f"\n{italic(f'... и еще {len(tasks) - 10} задач')}"
            else:
                message += f"{italic('Задач не найдено.')}"
            
            keyboard = [
                [InlineKeyboardButton("➕ Добавить задачу", callback_data=f"add_task_{project_id}")]
            ]
            
            # Добавляем фильтры только если есть задачи
            if tasks:
                if filter_type == "active":
                    keyboard.append([InlineKeyboardButton("✅ Выполненные", callback_data=f"completed_tasks_{project_id}")])
                elif filter_type == "completed":
                    keyboard.append([InlineKeyboardButton("⏳ Активные", callback_data=f"all_tasks_{project_id}")])
                else:
                    keyboard.append([InlineKeyboardButton("⏳ Активные", callback_data=f"all_tasks_{project_id}")])
                    keyboard.append([InlineKeyboardButton("✅ Выполненные", callback_data=f"completed_tasks_{project_id}")])
            
            keyboard.append([InlineKeyboardButton("📂 К проектам", callback_data="back_to_projects")])
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка показа задач проекта", error=str(e), project_id=project_id, filter_type=filter_type)
            await query.edit_message_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML'
            )
    
    async def show_project_members(self, query, context, project_id):
        """Показать участников проекта"""
        user_id = query.from_user.id
        
        try:
            project = self.db.get_project_by_id(project_id, user_id)
            if not project:
                await query.edit_message_text(
                    "❌ Проект не найден или у вас нет доступа.",
                    parse_mode='HTML'
                )
                return
            
            members = self.db.get_project_members(project_id)
            
            project_name = project['name']
            message = f"{bold(f'👥 Участники проекта \"{project_name}\"')}\n"
            
            for member in members:
                role_emoji = "👑" if member['role'] == 'owner' else "👨‍💻"
                name = member['first_name'] or member['username'] or f"ID:{member['user_id']}"
                message += f"{role_emoji} {bold(name)} ({member['role']})\n"
            
            keyboard = [
                [InlineKeyboardButton("📂 К проекту", callback_data=f"project_{project_id}")],
                [InlineKeyboardButton("📂 К проектам", callback_data="back_to_projects")]
            ]
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка показа участников проекта", error=str(e), project_id=project_id)
            await query.edit_message_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML'
            )
    
    async def show_project_settings(self, query, context, project_id):
        """Показать настройки проекта"""
        user_id = query.from_user.id
        
        try:
            project = self.db.get_project_by_id(project_id, user_id)
            if not project or project['role'] != 'owner':
                await query.edit_message_text(
                    "❌ У вас нет прав для изменения настроек этого проекта.",
                    parse_mode='HTML'
                )
                return
            
            project_name = project['name']
            message = f"{bold(f'⚙️ Настройки проекта \"{project_name}\"\n')}\n"
            message += f"{bold('🔗 Код приглашения:')} {project.get('invite_code', 'Не найден')}\n"
            message += f"{bold('📝 Описание:')} {project.get('description', 'Нет описания')}\n"
            
            keyboard = [
                [InlineKeyboardButton("📂 К проекту", callback_data=f"project_{project_id}")],
                [InlineKeyboardButton("📂 К проектам", callback_data="back_to_projects")]
            ]
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка показа настроек проекта", error=str(e), project_id=project_id)
            await query.edit_message_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML'
            )
    
    async def handle_reminder_time_setting(self, query, context, minutes):
        """Обработать настройку времени напоминания"""
        user_id = query.from_user.id
        
        try:
            self.db.update_user_setting(user_id, 'reminder_time', minutes)
            
            time_text = {
                15: "15 минут",
                30: "30 минут", 
                60: "1 час",
                120: "2 часа",
                1440: "1 день"
            }.get(minutes, f"{minutes} минут")
            
            await query.edit_message_text(
                f"✅ Время напоминания установлено: {bold(time_text)}",
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error("Ошибка настройки времени напоминания", error=str(e), minutes=minutes)
            await query.edit_message_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML'
            )
    
    async def handle_timezone_setting(self, query, context, timezone):
        """Обработать настройку часового пояса"""
        user_id = query.from_user.id
        
        try:
            self.db.update_user_setting(user_id, 'timezone', timezone)
            
            timezone_names = {
                "Europe/Moscow": "UTC+3 (Москва)",
                "Europe/London": "UTC+0 (Лондон)",
                "America/New_York": "UTC-5 (Нью-Йорк)",
                "Asia/Shanghai": "UTC+8 (Пекин)"
            }
            
            timezone_text = timezone_names.get(timezone, timezone)
            
            await query.edit_message_text(
                f"✅ Часовой пояс установлен: {bold(timezone_text)}",
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error("Ошибка настройки часового пояса", error=str(e), timezone=timezone)
            await query.edit_message_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML'
            )
    
    async def handle_language_setting(self, query, context, language):
        """Обработать настройку языка"""
        user_id = query.from_user.id
        
        try:
            self.db.update_user_setting(user_id, 'language', language)
            
            language_names = {
                "ru": "🇷🇺 Русский",
                "en": "🇺🇸 English"
            }
            
            language_text = language_names.get(language, language)
            
            await query.edit_message_text(
                f"✅ Язык установлен: {bold(language_text)}",
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error("Ошибка настройки языка", error=str(e), language=language)
            await query.edit_message_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML'
            )
    
    async def handle_theme_setting(self, query, context, theme):
        """Обработать настройку темы"""
        user_id = query.from_user.id
        
        try:
            self.db.update_user_setting(user_id, 'theme', theme)
            
            theme_names = {
                "default": "🌟 По умолчанию",
                "dark": "🌙 Темная",
                "light": "☀️ Светлая"
            }
            
            theme_text = theme_names.get(theme, theme)
            
            await query.edit_message_text(
                f"✅ Тема установлена: {bold(theme_text)}",
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error("Ошибка настройки темы", error=str(e), theme=theme)
            await query.edit_message_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML'
            )
    
    async def start_add_task(self, query, context, project_id):
        """Начать процесс добавления задачи в проект"""
        user_id = query.from_user.id
        
        try:
            project = self.db.get_project_by_id(project_id, user_id)
            if not project:
                await query.edit_message_text(
                    "❌ Проект не найден или у вас нет доступа.",
                    parse_mode='HTML'
                )
                return
            
            project_name = project['name']
            message = f"{bold(f'➕ Добавление задачи в проект \"{project_name}\"')}\n\n"
            message += f"{italic('Отправьте сообщение с описанием задачи или запишите голосовое сообщение.')}"
            
            keyboard = [
                [InlineKeyboardButton("❌ Отмена", callback_data=f"project_{project_id}")]
            ]
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # Сохраним состояние для следующего сообщения
            context.user_data['adding_task_to_project'] = project_id
            
        except Exception as e:
            logger.error("Ошибка начала добавления задачи", error=str(e), project_id=project_id)
            await query.edit_message_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML'
            )
    
    async def process_new_task(self, update, context, project_id, task_text):
        """Обработать создание новой задачи из текста"""
        user_id = update.effective_user.id
        
        try:
            # Очищаем состояние
            context.user_data.pop('adding_task_to_project', None)
            
            # Проверяем проект
            project = self.db.get_project_by_id(project_id, user_id)
            if not project:
                await update.message.reply_text(
                    "❌ Проект не найден или у вас нет доступа.",
                    parse_mode='HTML',
                    reply_markup=self.get_main_keyboard()
                )
                return
            
            # Создаем задачу
            task_id = self.db.add_task(
                user_id=user_id,
                title=task_text.strip(),
                description=None,
                project_id=project_id,
                priority='medium'
            )
            
            if task_id:
                project_name = project['name']
                message = f"✅ {bold('Задача создана!')}\n\n"
                message += f"{bold('📂 Проект:')} {project_name}\n"
                message += f"{bold('📋 Задача:')} {task_text.strip()}\n"
                
                # Кнопки для быстрых действий
                keyboard = [
                    [InlineKeyboardButton("📂 К проекту", callback_data=f"project_{project_id}")],
                    [InlineKeyboardButton("➕ Добавить еще", callback_data=f"add_task_{project_id}")],
                    [InlineKeyboardButton("🔙 К проектам", callback_data="back_to_projects")]
                ]
                
                await update.message.reply_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.message.reply_text(
                    "❌ Произошла ошибка при создании задачи. Попробуйте позже.",
                    parse_mode='HTML',
                    reply_markup=self.get_main_keyboard()
                )
                
        except Exception as e:
            logger.error("Ошибка создания задачи из текста", error=str(e), user_id=user_id, project_id=project_id)
            context.user_data.pop('adding_task_to_project', None)
            await update.message.reply_text(
                "❌ Произошла ошибка при создании задачи. Попробуйте позже.",
                parse_mode='HTML',
                reply_markup=self.get_main_keyboard()
            )
    
    async def process_new_order(self, update, context, order_title):
        """Обработать создание нового заказа для команды"""
        user_id = update.effective_user.id
        
        try:
            # Получаем тип заказа из контекста
            order_type = context.user_data.get('new_order_type', 'design')
            type_name = self.DESIGN_TYPES.get(order_type, 'Дизайн-работа')
            
            # Создаем проект с дизайн-ориентированными тегами
            project_data = {
                'name': order_title,
                'description': f"Заказ типа: {type_name}",
                'is_personal': False,  # Все заказы команды являются командными
                'status': 'new',
                'tags': f"team,{order_type},заказ"
            }
            
            # Создаем проект в базе данных
            if project_data['is_personal']:
                project_id = self.db.create_personal_project(user_id)
                if project_id:
                    # Обновляем название персонального проекта
                    self.db.update_project(project_id, name=project_data['name'], description=project_data['description'])
            else:
                project_id = self.db.create_project(
                    owner_id=user_id,
                    name=project_data['name'],
                    description=project_data['description']
                )
            
            if project_id:
                # Очищаем состояние создания заказа
                context.user_data.pop('creating_order', None)
                context.user_data.pop('new_order_type', None)
                
                message = f"""{bold('🎨 Заказ создан успешно!')}

{bold('📋 Название:')} {order_title}
{bold('🎯 Тип работы:')} {type_name}  
{bold('📊 Статус:')} {self.ORDER_STATUSES['new']}

{italic('Заказ добавлен в систему. Добавьте задачи вручную при необходимости.')}"""
                
                keyboard = [
                    [InlineKeyboardButton("📂 К заказу", callback_data=f"project_{project_id}")],
                    [InlineKeyboardButton("🎨 Все заказы", callback_data="team_all_orders")],
                    [InlineKeyboardButton("📊 Дашборд", callback_data="team_dashboard")]
                ]
                
                await update.message.reply_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                # Очищаем состояние при ошибке
                context.user_data.pop('creating_order', None)
                context.user_data.pop('new_order_type', None)
                
                await update.message.reply_text(
                    "❌ Произошла ошибка при создании заказа. Попробуйте позже.",
                    parse_mode='HTML',
                    reply_markup=self.get_main_keyboard(user_id)
                )
                
        except Exception as e:
            logger.error("Ошибка создания нового заказа", error=str(e), user_id=user_id, order_title=order_title)
            # Очищаем состояние при ошибке
            context.user_data.pop('creating_order', None)
            context.user_data.pop('new_order_type', None)
            
            await update.message.reply_text(
                "❌ Произошла ошибка при создании заказа. Попробуйте позже.",
                parse_mode='HTML',
                reply_markup=self.get_main_keyboard(user_id)
            )
    
    async def show_task_details(self, query, context, task_id):
        """Показать детали задачи"""
        user_id = query.from_user.id
        
        try:
            # Найдем задачу через все проекты пользователя
            projects = self.db.get_user_projects(user_id)
            task = None
            project = None
            
            for proj in projects:
                tasks = self.db.get_project_tasks(proj['id'], user_id)
                found_task = next((t for t in tasks if t['id'] == task_id), None)
                if found_task:
                    task = found_task
                    project = proj
                    break
            
            if not task or not project:
                await query.edit_message_text(
                    "❌ Задача не найдена или у вас нет доступа.",
                    parse_mode='HTML'
                )
                return
            
            # Статус задачи
            status = "✅ Выполнена" if task.get('completed_at') else "⏳ В работе"
            priority = {"high": "🔴 Высокий", "medium": "🟡 Средний", "low": "🟢 Низкий"}.get(task.get('priority', 'medium'), "🟡 Средний")
            
            task_title = task['title']
            message = f"{bold(f'📋 {task_title}')}\n\n"
            message += f"{bold('📂 Проект:')} {project['name']}\n"
            message += f"{bold('📊 Статус:')} {status}\n"
            message += f"{bold('⚡ Приоритет:')} {priority}\n"
            
            if task.get('description'):
                message += f"\n{bold('📝 Описание:')}\n{task['description']}\n"
            
            if task.get('deadline'):
                deadline_str = task['deadline'].strftime('%d.%m.%Y %H:%M')
                message += f"\n{bold('⏰ Дедлайн:')} {deadline_str}\n"
            
            if task.get('assigned_to'):
                message += f"\n{bold('👤 Назначена:')} {task.get('assigned_first_name', 'Пользователь')}\n"
            
            keyboard = []
            
            if not task.get('completed_at'):
                keyboard.append([InlineKeyboardButton("✅ Завершить", callback_data=f"complete_task_{task_id}")])
            
            keyboard.append([InlineKeyboardButton("📂 К проекту", callback_data=f"project_{project['id']}")])
            keyboard.append([InlineKeyboardButton("📂 К проектам", callback_data="back_to_projects")])
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка показа деталей задачи", error=str(e), task_id=task_id)
            await query.edit_message_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                parse_mode='HTML'
            )
    
    async def show_project_details(self, query, context, project_id):
        """Показать детали проекта"""
        user_id = query.from_user.id
        
        try:
            project = self.db.get_project_details(project_id, user_id)
            if not project:
                await query.edit_message_text(
                    "❌ Проект не найден или у вас нет доступа.",
                    parse_mode='HTML'
                )
                return
            
            tasks = self.db.get_project_tasks(project_id, user_id, completed=False)
            
            # Статистика проекта
            total_tasks = self.db.get_project_task_count(project_id)
            completed_tasks = self.db.get_project_task_count(project_id, completed=True)
            progress = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
            
            message = f"""{bold(f'📂 {project["name"]}')}

{bold('📊 Статистика:')}
• Всего задач: {total_tasks}
• Выполнено: {completed_tasks}
• Прогресс: {progress:.0f}%

"""
            
            if project.get('description'):
                message += f"{bold('📝 Описание:')} {project['description']}\n\n"
            
            if not project['is_personal']:
                message += f"{bold('👑 Владелец:')} {project['owner_name']}\n"
                message += f"{bold('🔗 Код приглашения:')} {project['invite_code']}\n\n"
            
            if tasks:
                message += f"{bold('🎯 Активные задачи:')}\n"
                for task in tasks[:5]:  # Показать первые 5 задач
                    task_info = self.format_task_info(task)
                    message += f"• {task_info}\n"
                
                if len(tasks) > 5:
                    message += f"\n{italic(f'... и еще {len(tasks) - 5} задач')}"
            else:
                message += f"{italic('В проекте пока нет активных задач.')}"
            
            keyboard = [
                [InlineKeyboardButton("➕ Добавить задачу", callback_data=f"add_task_{project_id}")],
                [InlineKeyboardButton("📋 Все задачи", callback_data=f"all_tasks_{project_id}")],
                [InlineKeyboardButton("✅ Выполненные", callback_data=f"completed_tasks_{project_id}")]
            ]
            
            if not project['is_personal'] and project['role'] == 'owner':
                keyboard.append([InlineKeyboardButton("👥 Участники", callback_data=f"members_{project_id}")])
                keyboard.append([InlineKeyboardButton("⚙️ Настройки", callback_data=f"project_settings_{project_id}")])
            
            keyboard.append([InlineKeyboardButton("🔙 К проектам", callback_data="back_to_projects")])
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка показа деталей проекта", error=str(e), project_id=project_id)
            await query.edit_message_text(
                "❌ Ошибка при загрузке проекта.",
                parse_mode='HTML'
            )
    
    async def handle_create_personal_project(self, query, context):
        """Обработать создание личного проекта"""
        message = f"""{bold('👤 Создание личного проекта')}

{italic('Введите название для вашего личного проекта:')}

{bold('💡 Примеры:')}
• "Мои задачи"
• "Личные дела"
• "Саморазвитие"
• "Домашние дела"

{italic('Название проекта:')}"""
        
        await query.edit_message_text(
            message,
            parse_mode='HTML'
        )
        
        context.user_data['creating_project_type'] = 'personal'
        return CREATING_PROJECT
    
    async def handle_create_team_project(self, query, context):
        """Обработать создание командного проекта"""
        message = f"""{bold('👥 Создание командного проекта')}

{italic('Введите название для командного проекта:')}

{bold('💡 Примеры:')}
• "Разработка приложения"
• "Маркетинговая кампания"
• "Исследовательский проект"
• "Командные задачи"

{italic('Название проекта:')}"""
        
        await query.edit_message_text(
            message,
            parse_mode='HTML'
        )
        
        context.user_data['creating_project_type'] = 'team'
        return CREATING_PROJECT
    
    async def complete_task(self, query, context, task_id):
        """Отметить задачу как выполненную"""
        user_id = query.from_user.id
        
        try:
            success = self.db.complete_task(task_id, user_id)
            
            if success:
                await query.edit_message_text(
                    f"{bold('✅ Задача выполнена!')}\n\n{italic('Поздравляем с завершением задачи!')}",
                    parse_mode='HTML'
                )
                
                # Логируем выполнение задачи
                logger.info("Задача выполнена", task_id=task_id, user_id=user_id)
            else:
                await query.edit_message_text(
                    "❌ Не удалось отметить задачу как выполненную.",
                    parse_mode='HTML'
                )
                
        except Exception as e:
            logger.error("Ошибка выполнения задачи", error=str(e), task_id=task_id, user_id=user_id)
            await query.edit_message_text(
                "❌ Ошибка при выполнении задачи.",
                parse_mode='HTML'
            )
    
    async def show_completed_assigned_tasks(self, query, context):
        """Показать выполненные назначенные задачи"""
        user_id = query.from_user.id
        
        try:
            completed_tasks = self.db.get_user_assigned_tasks(user_id, completed=True, limit=10)
            
            if not completed_tasks:
                await query.edit_message_text(
                    f"{bold('📋 Выполненные задачи')}\n\nУ вас нет выполненных задач.",
                    parse_mode='HTML'
                )
                return
            
            message = f"{bold('📋 Последние выполненные задачи:')}\n\n"
            
            for task in completed_tasks:
                completed_date = datetime.fromisoformat(str(task['completed_at']).replace('Z', '+00:00'))
                date_str = completed_date.strftime("%d.%m.%Y")
                
                message += f"✅ {bold(task['title'])}\n"
                message += f"{bold('📂')} {task['project_name']} | {bold('📅')} {date_str}\n"
                if task.get('description'):
                    message += f"{bold('📝')} {task['description'][:50]}...\n"
                message += "\n"
            
            keyboard = [[InlineKeyboardButton("🔙 К моим задачам", callback_data="back_to_my_tasks")]]
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка показа выполненных задач", error=str(e), user_id=user_id)
            await query.edit_message_text(
                "❌ Ошибка при загрузке выполненных задач.",
                parse_mode='HTML'
            )
    
    async def create_task_from_voice(self, query, context):
        """Создать задачу из голосового сообщения"""
        user_id = query.from_user.id
        
        try:
            # Получаем анализ из контекста
            analysis = context.user_data.get('voice_analysis', {})
            voice_text = context.user_data.get('voice_text', '')
            
            if not analysis:
                await query.edit_message_text(
                    "❌ Данные анализа не найдены. Попробуйте еще раз.",
                    parse_mode='HTML'
                )
                return
            
            # Получаем проекты пользователя для выбора
            projects = self.db.get_user_projects(user_id)
            
            if not projects:
                await query.edit_message_text(
                    f"{bold('❌ Нет проектов')}\n\nСначала создайте проект для добавления задач.",
                    parse_mode='HTML'
                )
                return
            
            message = f"""{bold('📂 Выберите проект для задачи:')}

{bold('🎙 Задача:')} {analysis.get('title', 'Без названия')}
{bold('📝 Описание:')} {analysis.get('description', voice_text[:100])}

{italic('В какой проект добавить задачу?')}"""
            
            keyboard = []
            for project in projects:
                emoji = "👤" if project['is_personal'] else "👥"
                button_text = f"{emoji} {project['name']}"
                callback_data = f"voice_task_project_{project['id']}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_voice_task")])
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка создания задачи из голоса", error=str(e), user_id=user_id)
            await query.edit_message_text(
                "❌ Ошибка при создании задачи.",
                parse_mode='HTML'
            )
    
    async def create_voice_task_in_project(self, query, context, project_id):
        """Создать задачу из голосового сообщения в выбранном проекте"""
        user_id = query.from_user.id
        
        try:
            # Получаем анализ из контекста
            analysis = context.user_data.get('voice_analysis', {})
            voice_text = context.user_data.get('voice_text', '')
            
            if not analysis:
                await query.edit_message_text(
                    "❌ Данные анализа не найдены. Попробуйте еще раз.",
                    parse_mode='HTML'
                )
                return
            
            # Получаем данные для задачи
            title = analysis.get('title', '') or voice_text[:50] or 'Задача из голосового сообщения'
            description = analysis.get('description', '') or voice_text
            priority = analysis.get('priority', 'medium')
            
            # Создаем задачу
            task_id = self.db.add_task(
                user_id=user_id,
                title=title,
                description=description,
                project_id=project_id,
                assigned_to=user_id,
                priority=priority
            )
            
            if task_id:
                # Очищаем данные из контекста
                context.user_data.pop('voice_analysis', None)
                context.user_data.pop('voice_text', None)
                
                # Получаем информацию о проекте
                project = self.db.get_project_details(project_id, user_id)
                project_name = project['name'] if project else 'Проект'
                
                await query.edit_message_text(
                    f"""{bold('✅ Задача создана!')}

{bold('📋 Название:')} {title}
{bold('📂 Проект:')} {project_name}
{bold('📝 Описание:')} {description}
{bold('⚡ Приоритет:')} {priority}

{italic('Задача успешно добавлена в ваш проект.')}""",
                    parse_mode='HTML'
                )
            else:
                await query.edit_message_text(
                    "❌ Ошибка при создании задачи. Попробуйте позже.",
                    parse_mode='HTML'
                )
                
        except Exception as e:
            logger.error("Ошибка создания задачи в проекте", error=str(e), user_id=user_id, project_id=project_id)
            await query.edit_message_text(
                "❌ Ошибка при создании задачи.",
                parse_mode='HTML'
            )
    
    # === TEAM DESIGN TEAM METHODS ===
    
    async def show_team_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать все заказы команды"""
        user_id = update.effective_user.id
        
        try:
            # Определяем, какой тип обновления пришел
            if update.callback_query:
                query = update.callback_query
                await query.answer()  # Отвечаем на callback_query
                message_obj = query.message
            else:
                message_obj = update.message
            
            # Получаем все проекты команды
            projects = []
            for team_user_id in self.TEAM_IDS:
                user_projects = self.db.get_user_projects(team_user_id)
                projects.extend(user_projects)
            
            if not projects:
                await message_obj.reply_text(
                    f"{bold('🎨 Заказы команды')}\n\nУ команды пока нет заказов.",
                    parse_mode='HTML',
                    reply_markup=self.get_main_keyboard(user_id)
                )
                return
            
            message = f"{bold('🎨 Все заказы команды:')}\n\n"
            
            # Группируем по статусам
            status_groups = {}
            for project in projects:
                status = project.get('status', 'in_progress')
                if status not in status_groups:
                    status_groups[status] = []
                status_groups[status].append(project)
            
            for status, status_projects in status_groups.items():
                status_emoji = self.ORDER_STATUSES.get(status, f"📋 {status}")
                message += f"\n{bold(status_emoji)} ({len(status_projects)}):\n"
                
                for project in status_projects[:5]:  # Показываем максимум 5 заказов на статус
                    tasks_count = self.db.get_project_task_count(project['id'], completed=False)
                    completed_count = self.db.get_project_task_count(project['id'], completed=True) 
                    
                    message += f"• {project['name']} ({completed_count}/{completed_count + tasks_count})\n"
                
                if len(status_projects) > 5:
                    message += f"... и еще {len(status_projects) - 5}\n"
            
            keyboard = [
                [InlineKeyboardButton("🔥 Активные", callback_data="team_active"),
                 InlineKeyboardButton("✅ Завершённые", callback_data="team_completed")],
                [InlineKeyboardButton("💰 Оплаченные", callback_data="team_paid"),
                 InlineKeyboardButton("📊 Дашборд", callback_data="team_dashboard")]
            ]
            
            await message_obj.reply_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка показа заказов команды", error=str(e), user_id=user_id)
            # Определяем объект для отправки сообщения об ошибке
            if update.callback_query:
                message_obj = update.callback_query.message
            else:
                message_obj = update.message
            
            await message_obj.reply_text(
                "❌ Ошибка при загрузке заказов.",
                parse_mode='HTML',
                reply_markup=self.get_main_keyboard(user_id)
            )
    
    async def show_team_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать дашборд команды"""
        user_id = update.effective_user.id
        
        try:
            # Определяем объект для отправки сообщения
            if update.callback_query:
                message_obj = update.callback_query.message
                await update.callback_query.answer()
            else:
                message_obj = update.effective_message
            
            # Собираем статистику по всей команде
            total_projects = 0
            active_projects = 0
            completed_projects = 0
            total_revenue = 0
            
            team_stats = {}
            
            for team_user_id in self.TEAM_IDS:
                # Используем ID в качестве имени, так как get_user_by_id недоступен
                user_name = f'Участник {team_user_id}'
                
                projects = self.db.get_user_projects(team_user_id)
                user_projects = len(projects)
                user_active = len([p for p in projects if p.get('status', 'in_progress') in ['new', 'in_progress', 'review', 'revision']])
                user_completed = len([p for p in projects if p.get('status', 'in_progress') in ['completed', 'delivered', 'paid']])
                
                total_projects += user_projects
                active_projects += user_active
                completed_projects += user_completed
                
                team_stats[user_name] = {
                    'projects': user_projects,
                    'active': user_active,
                    'completed': user_completed
                }
            
            # Вычисляем конверсию отдельно
            conversion_rate = (completed_projects/total_projects*100) if total_projects > 0 else 0
            conversion_text = f"{conversion_rate:.1f}%" if total_projects > 0 else "N/A"
            
            message = f"""{bold('📊 Дашборд команды')}

{bold('📈 Общая статистика:')}
• 📋 Всего заказов: {total_projects}
• 🔥 Активных: {active_projects}
• ✅ Завершённых: {completed_projects}
• 💰 Конверсия: {conversion_text}

{bold('👥 Статистика по участникам:')}"""
            
            for name, stats in team_stats.items():
                message += f"\n• {name}: {stats['active']} активных, {stats['completed']} завершённых"
            
            keyboard = [
                [InlineKeyboardButton("🎨 Все заказы", callback_data="team_all_orders"),
                 InlineKeyboardButton("🔥 Активные", callback_data="team_active")],
                [InlineKeyboardButton("📈 Аналитика", callback_data="team_analytics"),
                 InlineKeyboardButton("👥 Команда", callback_data="team_team_info")]
            ]
            
            await message_obj.reply_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка показа дашборда команды", error=str(e), user_id=user_id)
            # Определяем объект для отправки сообщения об ошибке
            if update.callback_query:
                message_obj = update.callback_query.message
            else:
                message_obj = update.effective_message
            
            await message_obj.reply_text(
                "❌ Ошибка при загрузке дашборда.",
                parse_mode='HTML',
                reply_markup=self.get_main_keyboard(user_id)
            )
    
    async def start_new_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начать создание нового заказа для команды"""
        user_id = update.effective_user.id
        
        try:
            # Определяем объект для отправки сообщения
            if update.callback_query:
                message_obj = update.callback_query.message
                await update.callback_query.answer()
            else:
                message_obj = update.effective_message
            
            message = f"""{bold('➕ Создание нового заказа')}

{bold('🎯 Выберите тип дизайн-работы:')}"""
            
            keyboard = []
            # Создаем кнопки для типов дизайн-работ
            design_types = list(self.DESIGN_TYPES.items())
            for i in range(0, len(design_types), 2):
                row = []
                row.append(InlineKeyboardButton(design_types[i][1], callback_data=f"new_order_type_{design_types[i][0]}"))
                if i + 1 < len(design_types):
                    row.append(InlineKeyboardButton(design_types[i + 1][1], callback_data=f"new_order_type_{design_types[i + 1][0]}"))
                keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_new_order")])
            
            await message_obj.reply_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка создания нового заказа", error=str(e), user_id=user_id)
            # Определяем объект для отправки сообщения об ошибке
            if update.callback_query:
                message_obj = update.callback_query.message
            else:
                message_obj = update.effective_message
            
            await message_obj.reply_text(
                "❌ Ошибка при создании заказа.",
                parse_mode='HTML',
                reply_markup=self.get_main_keyboard(user_id)
            )
    
    async def show_team_team(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать информацию о команде"""
        user_id = update.effective_user.id
        
        try:
            # Определяем объект для отправки сообщения
            if update.callback_query:
                message_obj = update.callback_query.message
                await update.callback_query.answer()
            else:
                message_obj = update.effective_message
            
            message = f"""{bold('👥 Команда')}

{italic('Дизайн-студия полного цикла')}

{bold('Участники команды:')}"""
            
            for team_user_id in self.TEAM_IDS:
                # Упрощённое отображение пользователей без доступа к деталям
                name = f'Участник {team_user_id}'
                projects_count = len(self.db.get_user_projects(team_user_id))
                message += f"\n• {name} - {projects_count} заказов"
            
            message += f"""\n\n{bold('🎯 Специализация:')}
• Логотипы и брендинг
• Веб-дизайн и UI/UX  
• Полиграфия и упаковка
• Иллюстрации и SMM

{bold('📊 Рабочие процессы:')}
• Новый заказ → В работе → На проверке
• На доработке → Завершён → Сдан клиенту → Оплачен"""
            
            keyboard = [
                [InlineKeyboardButton("📊 Дашборд", callback_data="team_dashboard"),
                 InlineKeyboardButton("🎨 Заказы", callback_data="team_all_orders")]
            ]
            
            await message_obj.reply_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка показа команды", error=str(e), user_id=user_id)
            # Определяем объект для отправки сообщения об ошибке
            if update.callback_query:
                message_obj = update.callback_query.message
            else:
                message_obj = update.effective_message
            
            await message_obj.reply_text(
                "❌ Ошибка при загрузке информации о команде.",
                parse_mode='HTML',
                reply_markup=self.get_main_keyboard(user_id)
            )
    
    async def show_active_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать активные заказы команды"""
        user_id = update.effective_user.id
        
        try:
            # Определяем объект для отправки сообщения
            if update.callback_query:
                message_obj = update.callback_query.message
                await update.callback_query.answer()
            else:
                message_obj = update.effective_message
            
            active_projects = []
            for team_user_id in self.TEAM_IDS:
                projects = self.db.get_user_projects(team_user_id)
                active = [p for p in projects if p.get('status', 'in_progress') in ['new', 'in_progress', 'review', 'revision']]
                active_projects.extend(active)
            
            if not active_projects:
                await message_obj.reply_text(
                    f"{bold('🔥 Активные заказы')}\n\nНет активных заказов.",
                    parse_mode='HTML',
                    reply_markup=self.get_main_keyboard(user_id)
                )
                return
            
            message = f"{bold('🔥 Активные заказы (' + str(len(active_projects)) + '):')}\n\n"
            
            for project in active_projects[:10]:  # Показываем максимум 10
                status_emoji = self.ORDER_STATUSES.get(project.get('status', 'in_progress'), '📋')
                tasks_count = self.db.get_project_task_count(project['id'], completed=False)
                completed_count = self.db.get_project_task_count(project['id'], completed=True)
                
                message += f"{status_emoji} {bold(project['name'])}\n"
                message += f"   Прогресс: {completed_count}/{completed_count + tasks_count}\n"
                message += f"   Статус: {project.get('status', 'in_progress')}\n\n"
            
            keyboard = [
                [InlineKeyboardButton("📊 Дашборд", callback_data="team_dashboard"),
                 InlineKeyboardButton("🎨 Все заказы", callback_data="team_all_orders")]
            ]
            
            await message_obj.reply_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка показа активных заказов", error=str(e), user_id=user_id)
            # Определяем объект для отправки сообщения об ошибке
            if update.callback_query:
                message_obj = update.callback_query.message
            else:
                message_obj = update.effective_message
            
            await message_obj.reply_text(
                "❌ Ошибка при загрузке активных заказов.",
                parse_mode='HTML',
                reply_markup=self.get_main_keyboard(user_id)
            )
    
    async def show_paid_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать оплаченные заказы команды"""
        user_id = update.effective_user.id
        
        try:
            # Определяем объект для отправки сообщения
            if update.callback_query:
                message_obj = update.callback_query.message
                await update.callback_query.answer()
            else:
                message_obj = update.effective_message
            
            paid_projects = []
            for team_user_id in self.TEAM_IDS:
                projects = self.db.get_user_projects(team_user_id)
                paid = [p for p in projects if p.get('status', 'in_progress') == 'paid']
                paid_projects.extend(paid)
            
            if not paid_projects:
                await message_obj.reply_text(
                    f"{bold('💰 Оплаченные заказы')}\n\nПока нет оплаченных заказов.",
                    parse_mode='HTML',
                    reply_markup=self.get_main_keyboard(user_id)
                )
                return
            
            message = f"{bold('💰 Оплаченные заказы (' + str(len(paid_projects)) + '):')}\n\n"
            
            total_revenue = 0
            for project in paid_projects[:15]:  # Показываем максимум 15
                message += f"✅ {bold(project['name'])}\n"
                # Здесь можно добавить информацию о сумме если она есть в базе
                message += f"   Завершён: {project.get('updated_at', 'N/A')}\n\n"
            
            message += f"{bold('📈 Итого оплаченных заказов: ' + str(len(paid_projects)))}"
            
            keyboard = [
                [InlineKeyboardButton("📊 Дашборд", callback_data="team_dashboard"),
                 InlineKeyboardButton("🔥 Активные", callback_data="team_active")]
            ]
            
            await message_obj.reply_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка показа оплаченных заказов", error=str(e), user_id=user_id)
            # Определяем объект для отправки сообщения об ошибке
            if update.callback_query:
                message_obj = update.callback_query.message
            else:
                message_obj = update.effective_message
            
            await message_obj.reply_text(
                "❌ Ошибка при загрузке оплаченных заказов.",
                parse_mode='HTML',
                reply_markup=self.get_main_keyboard(user_id)
            )
    
    async def handle_team_callback(self, query, context, data):
        """Обработчик callback кнопок для команды"""
        user_id = query.from_user.id
        
        # Проверяем, что пользователь из команды
        if not self.is_team_member(user_id):
            await query.answer("❌ Доступ только для команды")
            return
        
        try:
            if data == "team_active":
                await self.show_active_orders_callback(query, context)
            
            elif data == "team_completed":
                await self.show_team_completed_orders(query, context)
            
            elif data == "team_paid":
                await self.show_paid_orders_callback(query, context)
            
            elif data == "team_dashboard":
                await self.show_team_dashboard_callback(query, context)
            
            elif data == "team_all_orders":
                await self.show_team_orders_callback(query, context)
            
            elif data == "team_team_info":
                await self.show_team_team_callback(query, context)
                
        except Exception as e:
            logger.error("Ошибка обработки team callback", error=str(e), user_id=user_id, callback_data=data)
            await query.answer("❌ Ошибка обработки команды")
    
    async def show_team_completed_orders(self, query, context):
        """Показать завершённые заказы команды"""
        user_id = query.from_user.id
        
        try:
            completed_projects = []
            for team_user_id in self.TEAM_IDS:
                projects = self.db.get_user_projects(team_user_id)
                completed = [p for p in projects if p.get('status', 'in_progress') in ['completed', 'delivered']]
                completed_projects.extend(completed)
            
            if not completed_projects:
                await query.edit_message_text(
                    f"{bold('✅ Завершённые заказы')}\n\nНет завершённых заказов.",
                    parse_mode='HTML'
                )
                return
            
            message = f"{bold('✅ Завершённые заказы (' + str(len(completed_projects)) + '):')}\n\n"
            
            for project in completed_projects[:12]:  # Показываем максимум 12
                message += f"✅ {bold(project['name'])}\n"
                message += f"   Статус: {project.get('status', 'completed')}\n"
                message += f"   Обновлён: {project.get('updated_at', 'N/A')}\n\n"
            
            keyboard = [
                [InlineKeyboardButton("📊 Дашборд", callback_data="team_dashboard"),
                 InlineKeyboardButton("🔥 Активные", callback_data="team_active")],
                [InlineKeyboardButton("💰 Оплаченные", callback_data="team_paid"),
                 InlineKeyboardButton("🎨 Все заказы", callback_data="team_all_orders")]
            ]
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error("Ошибка показа завершённых заказов", error=str(e), user_id=user_id)
            await query.edit_message_text(
                "❌ Ошибка при загрузке завершённых заказов.",
                parse_mode='HTML'
            )
    
    async def handle_new_order_type(self, query, context, order_type):
        """Обработать выбор типа нового заказа"""
        user_id = query.from_user.id
        
        try:
            type_name = self.DESIGN_TYPES.get(order_type, order_type)
            
            # Сохраняем тип заказа в контексте
            context.user_data['new_order_type'] = order_type
            context.user_data['creating_order'] = True
            
            message = f"""{bold('➕ Новый заказ: ' + type_name)}

{bold('📝 Введите название заказа:')}

{italic('Например: "Логотип для кафе Утро" или "Веб-дизайн интернет-магазина"')}

{bold('💡 Советы:')}
• Укажите тип работы
• Добавьте краткое описание
• Упомяните клиента если нужно"""
            
            await query.edit_message_text(
                message,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error("Ошибка обработки типа заказа", error=str(e), user_id=user_id, order_type=order_type)
            await query.edit_message_text(
                "❌ Ошибка при создании заказа.",
                parse_mode='HTML'
            )
    
    # Callback версии методов team для inline кнопок
    async def show_active_orders_callback(self, query, context):
        """Callback версия показа активных заказов"""
        user_id = query.from_user.id
        try:
            active_projects = []
            for team_user_id in self.TEAM_IDS:
                projects = self.db.get_user_projects(team_user_id)
                active = [p for p in projects if p.get('status', 'in_progress') in ['new', 'in_progress', 'review', 'revision']]
                active_projects.extend(active)
            
            if not active_projects:
                await query.edit_message_text(
                    f"{bold('🔥 Активные заказы')}\n\nНет активных заказов.",
                    parse_mode='HTML'
                )
                return
            
            message = f"{bold('🔥 Активные заказы (' + str(len(active_projects)) + '):')}\n\n"
            
            for project in active_projects[:10]:
                status_emoji = self.ORDER_STATUSES.get(project.get('status', 'in_progress'), '📋')
                tasks_count = self.db.get_project_task_count(project['id'], completed=False)
                completed_count = self.db.get_project_task_count(project['id'], completed=True)
                
                message += f"{status_emoji} {bold(project['name'])}\n"
                message += f"   Прогресс: {completed_count}/{completed_count + tasks_count}\n\n"
            
            # Создаем кнопки для каждого заказа
            order_buttons = []
            for project in active_projects[:10]:
                order_buttons.append([
                    InlineKeyboardButton(f"📋 {project['name']}", callback_data=f"order_details_{project['id']}"),
                    InlineKeyboardButton(f"📝 Задачи", callback_data=f"order_tasks_{project['id']}"),
                    InlineKeyboardButton(f"✅ Завершить", callback_data=f"complete_order_{project['id']}")
                ])
            
            keyboard = order_buttons + [
                [InlineKeyboardButton("📊 Дашборд", callback_data="team_dashboard"),
                 InlineKeyboardButton("🎨 Все заказы", callback_data="team_all_orders")]
            ]
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error("Ошибка показа активных заказов", error=str(e), user_id=user_id)
            await query.edit_message_text("❌ Ошибка при загрузке активных заказов.", parse_mode='HTML')
    
    async def show_paid_orders_callback(self, query, context):
        """Callback версия показа оплаченных заказов"""
        user_id = query.from_user.id
        try:
            paid_projects = []
            for team_user_id in self.TEAM_IDS:
                projects = self.db.get_user_projects(team_user_id)
                paid = [p for p in projects if p.get('status', 'in_progress') == 'paid']
                paid_projects.extend(paid)
            
            if not paid_projects:
                await query.edit_message_text(
                    f"{bold('💰 Оплаченные заказы')}\n\nПока нет оплаченных заказов.",
                    parse_mode='HTML'
                )
                return
            
            message = f"{bold('💰 Оплаченные заказы (' + str(len(paid_projects)) + '):')}\n\n"
            
            # Создаем кнопки для каждого заказа
            order_buttons = []
            
            for project in paid_projects[:15]:
                tasks_count = self.db.get_project_task_count(project['id'], completed=False)
                completed_count = self.db.get_project_task_count(project['id'], completed=True)
                message += f"✅ {bold(project['name'])} ({completed_count}/{completed_count + tasks_count})\n"
                message += f"   Завершён: {project.get('updated_at', 'N/A')}\n\n"
                
                # Добавляем кнопки для каждого заказа
                order_buttons.append([
                    InlineKeyboardButton(f"📋 {project['name']}", callback_data=f"order_details_{project['id']}"),
                    InlineKeyboardButton(f"📝 Задачи", callback_data=f"order_tasks_{project['id']}"),
                    InlineKeyboardButton(f"🔄 Активировать", callback_data=f"activate_order_{project['id']}")
                ])
            
            keyboard = order_buttons + [
                [InlineKeyboardButton("📊 Дашборд", callback_data="team_dashboard"),
                 InlineKeyboardButton("🔥 Активные", callback_data="team_active")]
            ]
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error("Ошибка показа оплаченных заказов", error=str(e), user_id=user_id)
            await query.edit_message_text("❌ Ошибка при загрузке оплаченных заказов.", parse_mode='HTML')
    
    async def show_team_dashboard_callback(self, query, context):
        """Callback версия дашборда команды"""
        user_id = query.from_user.id
        try:
            total_projects = 0
            active_projects = 0
            completed_projects = 0
            team_stats = {}
            
            for team_user_id in self.TEAM_IDS:
                # Используем ID в качестве имени, так как get_user_by_id недоступен
                user_name = f'Участник {team_user_id}'
                
                projects = self.db.get_user_projects(team_user_id)
                user_projects = len(projects)
                user_active = len([p for p in projects if p.get('status', 'in_progress') in ['new', 'in_progress', 'review', 'revision']])
                user_completed = len([p for p in projects if p.get('status', 'in_progress') in ['completed', 'delivered', 'paid']])
                
                total_projects += user_projects
                active_projects += user_active
                completed_projects += user_completed
                
                team_stats[user_name] = {
                    'projects': user_projects,
                    'active': user_active,
                    'completed': user_completed
                }
            
            conversion_rate = (completed_projects/total_projects*100) if total_projects > 0 else 0
            conversion_text = f"{conversion_rate:.1f}%" if total_projects > 0 else "N/A"
            
            message = f"""{bold('📊 Дашборд команды')}

{bold('📈 Общая статистика:')}
• 📋 Всего заказов: {total_projects}
• 🔥 Активных: {active_projects}
• ✅ Завершённых: {completed_projects}
• 💰 Конверсия: {conversion_text}

{bold('👥 Статистика по участникам:')}"""
            
            for name, stats in team_stats.items():
                message += f"\n• {name}: {stats['active']} активных, {stats['completed']} завершённых"
            
            keyboard = [
                [InlineKeyboardButton("🎨 Все заказы", callback_data="team_all_orders"),
                 InlineKeyboardButton("🔥 Активные", callback_data="team_active")],
                [InlineKeyboardButton("💰 Оплаченные", callback_data="team_paid"),
                 InlineKeyboardButton("👥 Команда", callback_data="team_team_info")]
            ]
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error("Ошибка показа дашборда", error=str(e), user_id=user_id)
            await query.edit_message_text("❌ Ошибка при загрузке дашборда.", parse_mode='HTML')
    
    async def show_team_orders_callback(self, query, context):
        """Callback версия показа всех заказов"""
        user_id = query.from_user.id
        try:
            projects = []
            for team_user_id in self.TEAM_IDS:
                user_projects = self.db.get_user_projects(team_user_id)
                projects.extend(user_projects)
            
            if not projects:
                await query.edit_message_text(
                    f"{bold('🎨 Заказы команды')}\n\nУ команды пока нет заказов.",
                    parse_mode='HTML'
                )
                return
            
            message = f"{bold('🎨 Все заказы команды:')}\n\n"
            
            status_groups = {}
            for project in projects:
                status = project.get('status', 'in_progress')
                if status not in status_groups:
                    status_groups[status] = []
                status_groups[status].append(project)
            
            # Создаем кнопки для каждого заказа
            order_buttons = []
            
            for status, status_projects in status_groups.items():
                status_emoji = self.ORDER_STATUSES.get(status, f"📋 {status}")
                message += f"\n{bold(status_emoji)} ({len(status_projects)}):\n"
                
                for project in status_projects[:3]:
                    tasks_count = self.db.get_project_task_count(project['id'], completed=False)
                    completed_count = self.db.get_project_task_count(project['id'], completed=True) 
                    message += f"• {project['name']} ({completed_count}/{completed_count + tasks_count})\n"
                    
                    # Добавляем кнопки для каждого заказа
                    order_buttons.append([
                        InlineKeyboardButton(f"📋 {project['name']}", callback_data=f"order_details_{project['id']}"),
                        InlineKeyboardButton(f"📝 Задачи", callback_data=f"order_tasks_{project['id']}")
                    ])
                    
                    # Добавляем кнопку завершения только для активных заказов
                    if status in ['new', 'in_progress', 'review', 'revision']:
                        order_buttons[-1].append(InlineKeyboardButton(f"✅ Завершить", callback_data=f"complete_order_{project['id']}"))
                    elif status in ['completed', 'delivered']:
                        order_buttons[-1].append(InlineKeyboardButton(f"💰 Активировать", callback_data=f"activate_order_{project['id']}"))
                
                if len(status_projects) > 3:
                    message += f"... и еще {len(status_projects) - 3}\n\n"
            
            keyboard = order_buttons + [
                [InlineKeyboardButton("🔥 Активные", callback_data="team_active"),
                 InlineKeyboardButton("✅ Завершённые", callback_data="team_completed")],
                [InlineKeyboardButton("💰 Оплаченные", callback_data="team_paid"),
                 InlineKeyboardButton("📊 Дашборд", callback_data="team_dashboard")]
            ]
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error("Ошибка показа заказов", error=str(e), user_id=user_id)
            await query.edit_message_text("❌ Ошибка при загрузке заказов.", parse_mode='HTML')
    
    async def show_team_team_callback(self, query, context):
        """Callback версия показа команды"""
        user_id = query.from_user.id
        try:
            message = f"""{bold('👥 Команда')}

{italic('Дизайн-студия полного цикла')}

{bold('Участники команды:')}"""
            
            for team_user_id in self.TEAM_IDS:
                # Упрощённое отображение пользователей без доступа к деталям
                name = f'Участник {team_user_id}'
                projects_count = len(self.db.get_user_projects(team_user_id))
                message += f"\n• {name} - {projects_count} заказов"
            
            message += f"""\n\n{bold('🎯 Специализация:')}
• Логотипы и брендинг
• Веб-дизайн и UI/UX  
• Полиграфия и упаковка
• Иллюстрации и SMM

{bold('📊 Рабочие процессы:')}
• Новый заказ → В работе → На проверке
• На доработке → Завершён → Сдан клиенту → Оплачен"""
            
            keyboard = [
                [InlineKeyboardButton("📊 Дашборд", callback_data="team_dashboard"),
                 InlineKeyboardButton("🎨 Заказы", callback_data="team_all_orders")]
            ]
            
            await query.edit_message_text(
                message,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error("Ошибка показа команды", error=str(e), user_id=user_id)
            await query.edit_message_text("❌ Ошибка при загрузке информации о команде.", parse_mode='HTML')
    
    # === CONVERSATION HANDLERS ===
    
    async def handle_project_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработать создание проекта"""
        user_id = update.effective_user.id
        project_name = update.message.text.strip()
        project_type = context.user_data.get('creating_project_type', 'personal')
        
        if len(project_name) < 2:
            await update.message.reply_text(
                "❌ Название проекта должно содержать минимум 2 символа. Попробуйте еще раз:"
            )
            return CREATING_PROJECT
        
        if len(project_name) > 100:
            await update.message.reply_text(
                "❌ Название проекта слишком длинное (максимум 100 символов). Попробуйте еще раз:"
            )
            return CREATING_PROJECT
        
        try:
            is_personal = project_type == 'personal'
            project_id = self.db.create_project(
                name=project_name,
                owner_id=user_id,
                is_personal=is_personal
            )
            
            if project_id:
                emoji = "👤" if is_personal else "👥"
                project_type_text = "личный" if is_personal else "командный"
                
                message = f"""{bold(f'✅ {emoji} Проект создан!')}

{bold('📂 Название:')} {project_name}
{bold('📋 Тип:')} {project_type_text.capitalize()}

"""
                
                if not is_personal:
                    project = self.db.get_project_details(project_id, user_id)
                    invite_code = project.get('invite_code', 'Не найден')
                    message += f"{bold('🔗 Код приглашения:')} {bold(invite_code)}\n"
                    message += f"{italic('Поделитесь этим кодом с участниками команды!')}\n\n"
                
                message += f"{italic('Теперь вы можете добавлять задачи в проект!')}"
                
                keyboard = [
                    [InlineKeyboardButton("➕ Добавить задачу", callback_data=f"add_task_{project_id}")],
                    [InlineKeyboardButton("📂 К проектам", callback_data="back_to_projects")]
                ]
                
                await update.message.reply_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                logger.info("Проект создан", project_id=project_id, user_id=user_id, name=project_name)
            else:
                await update.message.reply_text(
                    "❌ Ошибка при создании проекта. Попробуйте позже.",
                    reply_markup=self.get_main_keyboard()
                )
                
        except Exception as e:
            logger.error("Ошибка создания проекта", error=str(e), user_id=user_id)
            await update.message.reply_text(
                "❌ Ошибка при создании проекта. Попробуйте позже.",
                reply_markup=self.get_main_keyboard()
            )
        
        # Очищаем данные из контекста
        context.user_data.pop('creating_project_type', None)
        return ConversationHandler.END
    
    async def handle_join_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработать присоединение к проекту"""
        user_id = update.effective_user.id
        invite_code = update.message.text.strip().upper()
        
        if len(invite_code) != 6:
            await update.message.reply_text(
                "❌ Код приглашения должен содержать 6 символов. Попробуйте еще раз:"
            )
            return JOINING_PROJECT
        
        try:
            result = self.db.join_project_by_code(user_id, invite_code)
            
            if result['success']:
                project_name = result['project_name']
                message = f"""{bold('✅ Успешно присоединились!')}

{bold('📂 Проект:')} {project_name}
{bold('👑 Владелец:')} {result['owner_name']}

{italic('Теперь вы можете участвовать в проекте и получать назначенные задачи!')}"""
                
                keyboard = [
                    [InlineKeyboardButton("📂 Открыть проект", callback_data=f"project_{result['project_id']}")],
                    [InlineKeyboardButton("📂 К проектам", callback_data="back_to_projects")]
                ]
                
                await update.message.reply_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                logger.info("Пользователь присоединился к проекту", user_id=user_id, project_name=project_name)
            else:
                error_message = result.get('error', 'Неизвестная ошибка')
                await update.message.reply_text(
                    f"❌ {error_message}",
                    reply_markup=self.get_main_keyboard()
                )
                
        except Exception as e:
            logger.error("Ошибка присоединения к проекту", error=str(e), user_id=user_id)
            await update.message.reply_text(
                "❌ Ошибка при присоединении к проекту. Попробуйте позже.",
                reply_markup=self.get_main_keyboard()
            )
        
        return ConversationHandler.END
    
    async def cancel_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отменить текущий разговор"""
        await update.message.reply_text(
            "❌ Операция отменена.",
            reply_markup=self.get_main_keyboard()
        )
        return ConversationHandler.END
    
    # === ДОПОЛНИТЕЛЬНЫЕ ОБРАБОТЧИКИ ===
    
    async def handle_settings_callback(self, query, context, setting_type):
        """Обработать настройки"""
        user_id = query.from_user.id
        
        if setting_type == "notifications":
            # Переключить уведомления
            current_settings = self.db.get_user_settings(user_id)
            new_value = not current_settings.get('notifications_enabled', True)
            
            self.db.update_user_setting(user_id, 'notifications_enabled', new_value)
            
            status = "включены" if new_value else "отключены"
            await query.edit_message_text(
                f"✅ Уведомления {status}.",
                parse_mode='HTML'
            )
        
        elif setting_type == "reminders":
            # Показать варианты времени напоминаний
            keyboard = [
                [InlineKeyboardButton("15 минут", callback_data="reminder_time_15")],
                [InlineKeyboardButton("30 минут", callback_data="reminder_time_30")],
                [InlineKeyboardButton("1 час", callback_data="reminder_time_60")],
                [InlineKeyboardButton("2 часа", callback_data="reminder_time_120")],
                [InlineKeyboardButton("1 день", callback_data="reminder_time_1440")]
            ]
            
            await query.edit_message_text(
                f"{bold('⏰ Выберите время напоминания:')}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif setting_type == "timezone":
            # Показать популярные часовые пояса
            keyboard = [
                [InlineKeyboardButton("UTC+3 (Москва)", callback_data="timezone_Europe/Moscow")],
                [InlineKeyboardButton("UTC+0 (Лондон)", callback_data="timezone_Europe/London")],
                [InlineKeyboardButton("UTC-5 (Нью-Йорк)", callback_data="timezone_America/New_York")],
                [InlineKeyboardButton("UTC+8 (Пекин)", callback_data="timezone_Asia/Shanghai")]
            ]
            
            await query.edit_message_text(
                f"{bold('🌍 Выберите часовой пояс:')}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif setting_type == "language":
            # Показать доступные языки
            keyboard = [
                [InlineKeyboardButton("🇷🇺 Русский", callback_data="language_ru")],
                [InlineKeyboardButton("🇺🇸 English", callback_data="language_en")]
            ]
            
            await query.edit_message_text(
                f"{bold('🌐 Выберите язык:')}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif setting_type == "theme":
            # Показать доступные темы
            keyboard = [
                [InlineKeyboardButton("🌟 По умолчанию", callback_data="theme_default")],
                [InlineKeyboardButton("🌙 Темная", callback_data="theme_dark")],
                [InlineKeyboardButton("☀️ Светлая", callback_data="theme_light")]
            ]
            
            await query.edit_message_text(
                f"{bold('🎨 Выберите тему:')}",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    async def show_detailed_analytics(self, query, context):
        """Показать подробную аналитику"""
        user_id = query.from_user.id
        
        try:
            # Получить расширенную статистику
            weekly_stats = self.db.get_productivity_stats(user_id, days=7)
            monthly_stats = self.db.get_productivity_stats(user_id, days=30)
            
            message = f"{bold('📊 Подробная аналитика')}\n\n"
            
            # Статистика за неделю
            week_completed = sum(stat['completed_tasks'] for stat in weekly_stats)
            week_time = sum(stat['total_time_spent'] or 0 for stat in weekly_stats)
            
            message += f"{bold('📅 За неделю:')}\n\n"
            message += f"• Выполнено задач: {week_completed}\n"
            if week_time:
                hours = week_time // 60
                minutes = week_time % 60
                message += f"• Потрачено времени: {hours}ч {minutes}м\n"
            
            # Статистика за месяц
            month_completed = sum(stat['completed_tasks'] for stat in monthly_stats)
            month_time = sum(stat['total_time_spent'] or 0 for stat in monthly_stats)
            
            message += f"\n\n{bold('📅 За месяц:')}\n\n"
            message += f"• Выполнено задач: {month_completed}\n"
            if month_time:
                hours = month_time // 60
                minutes = month_time % 60
                message += f"• Потрачено времени: {hours}ч {minutes}м\n"
            
            # Средние показатели
            if len(weekly_stats) > 0:
                avg_daily = week_completed / 7
                message += f"\n\n{bold('📈 Средние показатели:')}\n\n"
                message += f"• Задач в день: {avg_daily:.1f}\n"
            
            await query.edit_message_text(
                message,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error("Ошибка показа подробной аналитики", error=str(e), user_id=user_id)
            await query.edit_message_text(
                "❌ Ошибка при загрузке аналитики.",
                parse_mode='HTML'
            )
    
    async def show_team_analytics(self, query, context):
        """Показать командную аналитику"""
        user_id = query.from_user.id
        
        try:
            # Получить проекты где пользователь владелец
            owned_projects = self.db.get_user_owned_projects(user_id)
            
            if not owned_projects:
                await query.edit_message_text(
                    f"{bold('👥 Командная аналитика')}\n\nУ вас нет командных проектов.",
                    parse_mode='HTML'
                )
                return
            
            message = f"{bold('👥 Командная аналитика')}\n\n"
            
            for project in owned_projects:
                project_stats = self.db.get_project_team_stats(project['id'])
                
                message += f"{bold(f'📂 {project["name"]}:')}\n"
                message += f"• Участников: {project_stats['member_count']}\n"
                message += f"• Всего задач: {project_stats['total_tasks']}\n"
                message += f"• Выполнено: {project_stats['completed_tasks']}\n"
                
                if project_stats['total_tasks'] > 0:
                    progress = (project_stats['completed_tasks'] / project_stats['total_tasks']) * 100
                    message += f"• Прогресс: {progress:.0f}%\n"
                
                message += "\n"
            
            await query.edit_message_text(
                message,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error("Ошибка показа командной аналитики", error=str(e), user_id=user_id)
            await query.edit_message_text(
                "❌ Ошибка при загрузке командной аналитики.",
                parse_mode='HTML'
            )
    
    async def start_create_template(self, query, context):
        """Начать создание шаблона"""
        await query.edit_message_text(
            f"{bold('📋 Создание шаблона')}\n\n{italic('Введите название шаблона:')}",
            parse_mode='HTML'
        )
        
        return CREATING_TEMPLATE
    
    async def start_delete_template(self, query, context):
        """Начать удаление шаблона"""
        user_id = query.from_user.id
        templates = self.db.get_user_templates(user_id)
        
        if not templates:
            await query.edit_message_text(
                "❌ У вас нет шаблонов для удаления.",
                parse_mode='HTML'
            )
            return
        
        keyboard = []
        for template in templates:
            button_text = f"🗑 {template['name']}"
            callback_data = f"delete_template_{template['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_delete_template")])
        
        await query.edit_message_text(
            f"{bold('🗑 Удаление шаблона')}\n\n{italic('Выберите шаблон для удаления:')}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # === НАСТРОЙКА ОБРАБОТЧИКОВ ===
    
    async def show_order_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE, order_id=None):
        """Показать детали заказа"""
        user_id = update.effective_user.id
        
        try:
            if order_id is None:
                # Получить ID из callback_data если вызвано через callback
                if update.callback_query:
                    data = update.callback_query.data
                    if data.startswith("order_details_"):
                        order_id = int(data.split("_")[2])
                        await update.callback_query.answer()
                else:
                    return
            
            # Получить детали заказа
            order = self.db.get_project_details(order_id, user_id)
            if not order:
                await update.effective_message.reply_text("❌ Заказ не найден или доступ запрещен")
                return
            
            # Получить задачи заказа
            tasks = self.db.get_project_tasks(order_id, user_id)
            
            # Формировать сообщение
            status_emoji = {
                'active': '🔥',
                'completed': '✅',
                'paid': '💰',
                'pending': '⏳'
            }
            
            status_text = {
                'active': 'Активный',
                'completed': 'Завершён',
                'paid': 'Оплачен',
                'pending': 'Ожидает'
            }
            
            # Безопасное получение статуса с дефолтным значением
            order_status = order.get('status', 'active')
            
            message = f"""{bold('🎨 Детали заказа')}

{bold('Название:')} {order['name']}
{bold('Описание:')} {order['description'] or 'Нет описания'}
{bold('Статус:')} {status_emoji.get(order_status, '📋')} {status_text.get(order_status, order_status)}
{bold('Создан:')} {order['created_at'].strftime('%d.%m.%Y %H:%M')}
{bold('Дедлайн:')} {order.get('deadline').strftime('%d.%m.%Y %H:%M') if order.get('deadline') else 'Не установлен'}

{bold('Прогресс:')} {order['completed_count'] or 0}/{order['task_count'] or 0} задач
{bold('Участников:')} {order['member_count'] or 1}"""

            if tasks:
                message += f"\n\n{bold('Задачи:')}"
                for i, task in enumerate(tasks[:5], 1):
                    status = "✅" if task['completed_at'] else "⏳"
                    message += f"\n{i}. {status} {task['title']}"
                
                if len(tasks) > 5:
                    message += f"\n... и ещё {len(tasks) - 5} задач"
            
            # Клавиатура
            keyboard = []
            
            # Кнопки действий
            action_buttons = []
            if order_status == 'active':
                action_buttons.append(InlineKeyboardButton("✅ Завершить заказ", callback_data=f"complete_order_{order_id}"))
            elif order_status == 'pending':
                action_buttons.append(InlineKeyboardButton("🔥 Активировать", callback_data=f"activate_order_{order_id}"))
            
            if action_buttons:
                keyboard.append(action_buttons)
            
            # Навигационные кнопки
            keyboard.extend([
                [InlineKeyboardButton("📋 Все задачи", callback_data=f"order_tasks_{order_id}")],
                [InlineKeyboardButton("🎨 К заказам", callback_data="team_all_orders"),
                 InlineKeyboardButton("📊 Дашборд", callback_data="team_dashboard")]
            ])
            
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.effective_message.reply_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
        except Exception as e:
            logger.error("Ошибка показа деталей заказа", error=str(e), user_id=user_id)
            await update.effective_message.reply_text("❌ Ошибка при загрузке деталей заказа")

    async def show_order_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE, order_id=None):
        """Показать все задачи заказа"""
        user_id = update.effective_user.id
        
        try:
            if order_id is None:
                if update.callback_query and update.callback_query.data.startswith("order_tasks_"):
                    order_id = int(update.callback_query.data.split("_")[2])
                    await update.callback_query.answer()
                else:
                    return
            
            # Получить заказ и задачи
            order = self.db.get_project_by_id(order_id, user_id)
            if not order:
                await update.effective_message.reply_text("❌ Заказ не найден")
                return
            
            tasks = self.db.get_project_tasks(order_id, user_id)
            
            message = f"""{bold('📋 Задачи заказа')}: {order['name']}

Всего задач: {len(tasks)}"""
            
            if tasks:
                active_tasks = [t for t in tasks if not t['completed_at']]
                completed_tasks = [t for t in tasks if t['completed_at']]
                
                if active_tasks:
                    message += f"\n\n{bold('🔥 Активные задачи:')}"
                    for i, task in enumerate(active_tasks, 1):
                        deadline_str = f" (до {task.get('deadline').strftime('%d.%m')})" if task.get('deadline') else ""
                        message += f"\n{i}. {task['title']}{deadline_str}"
                
                if completed_tasks:
                    message += f"\n\n{bold('✅ Выполненные задачи:')}"
                    for i, task in enumerate(completed_tasks[:3], 1):
                        completed_str = task['completed_at'].strftime('%d.%m') if task['completed_at'] else ""
                        message += f"\n{i}. {task['title']} ({completed_str})"
                    
                    if len(completed_tasks) > 3:
                        message += f"\n... и ещё {len(completed_tasks) - 3}"
            else:
                message += "\n\nЗадач пока нет"
            
            # Клавиатура
            keyboard = [
                [InlineKeyboardButton("➕ Добавить задачу", callback_data=f"add_task_{order_id}")],
                [InlineKeyboardButton("🔍 Детали заказа", callback_data=f"order_details_{order_id}")],
                [InlineKeyboardButton("🎨 К заказам", callback_data="team_all_orders"),
                 InlineKeyboardButton("📊 Дашборд", callback_data="team_dashboard")]
            ]
            
            # Добавляем кнопки для активных задач
            if active_tasks:
                for task in active_tasks:
                    keyboard.insert(1, [InlineKeyboardButton(f"✅ {task['title']}", callback_data=f"complete_task_{task['id']}")])
            
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.effective_message.reply_text(
                    message,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
        except Exception as e:
            logger.error("Ошибка показа задач заказа", error=str(e), user_id=user_id)
            await update.effective_message.reply_text("❌ Ошибка при загрузке задач")

    async def complete_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE, order_id=None):
        """Завершить заказ"""
        user_id = update.effective_user.id
        
        try:
            if order_id is None and update.callback_query:
                if update.callback_query.data.startswith("complete_order_"):
                    order_id = int(update.callback_query.data.split("_")[2])
                    await update.callback_query.answer()
            
            if not order_id:
                return
            
            # Проверить, что пользователь может завершить заказ
            order = self.db.get_project_by_id(order_id, user_id)
            if not order:
                await update.effective_message.reply_text("❌ Заказ не найден")
                return
            
            # Проверить, что все задачи выполнены
            tasks = self.db.get_project_tasks(order_id, user_id, completed=False)
            if tasks:
                await update.effective_message.reply_text(
                    f"❌ Нельзя завершить заказ: есть невыполненные задачи ({len(tasks)} шт.)"
                )
                return
            
            # Обновить статус заказа
            success = self.db.update_project_status(order_id, 'completed')
            if success:
                await update.effective_message.reply_text(
                    f"✅ Заказ '{order['name']}' успешно завершён!",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🎨 К заказам", callback_data="team_all_orders")
                    ]])
                )
            else:
                await update.effective_message.reply_text("❌ Ошибка при завершении заказа")
                
        except Exception as e:
            logger.error("Ошибка завершения заказа", error=str(e), user_id=user_id)
            await update.effective_message.reply_text("❌ Ошибка при завершении заказа")

    async def activate_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE, order_id=None):
        """Активировать заказ"""
        user_id = update.effective_user.id
        
        try:
            if order_id is None and update.callback_query:
                if update.callback_query.data.startswith("activate_order_"):
                    order_id = int(update.callback_query.data.split("_")[2])
                    await update.callback_query.answer()
            
            if not order_id:
                return
            
            order = self.db.get_project_by_id(order_id, user_id)
            if not order:
                await update.effective_message.reply_text("❌ Заказ не найден")
                return
            
            success = self.db.update_project_status(order_id, 'active')
            if success:
                await update.effective_message.reply_text(
                    f"🔥 Заказ '{order['name']}' активирован!",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📋 Детали", callback_data=f"order_details_{order_id}"),
                        InlineKeyboardButton("🎨 К заказам", callback_data="team_all_orders")
                    ]])
                )
            else:
                await update.effective_message.reply_text("❌ Ошибка при активации заказа")
                
        except Exception as e:
            logger.error("Ошибка активации заказа", error=str(e), user_id=user_id)
            await update.effective_message.reply_text("❌ Ошибка при активации заказа")

    def setup_handlers(self):
        """Настроить обработчики команд и сообщений"""
        
        # Основные команды
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        # Conversation handlers
        create_project_handler = ConversationHandler(
            entry_points=[],
            states={
                CREATING_PROJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_project_creation)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)]
        )
        
        join_project_handler = ConversationHandler(
            entry_points=[],
            states={
                JOINING_PROJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_join_project)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)]
        )
        
        self.application.add_handler(create_project_handler)
        self.application.add_handler(join_project_handler)
        
        # Callback handlers для команды режима
        self.application.add_handler(CallbackQueryHandler(self.show_team_dashboard, pattern="^team_dashboard$"))
        self.application.add_handler(CallbackQueryHandler(self.show_team_orders, pattern="^team_all_orders$"))
        self.application.add_handler(CallbackQueryHandler(self.show_active_orders, pattern="^team_active_orders$"))
        self.application.add_handler(CallbackQueryHandler(self.show_paid_orders, pattern="^team_paid_orders$"))
        
        # Новые обработчики для деталей заказов
        self.application.add_handler(CallbackQueryHandler(self.show_order_details, pattern="^order_details_"))
        self.application.add_handler(CallbackQueryHandler(self.show_order_tasks, pattern="^order_tasks_"))
        self.application.add_handler(CallbackQueryHandler(self.complete_order, pattern="^complete_order_"))
        self.application.add_handler(CallbackQueryHandler(self.activate_order, pattern="^activate_order_"))
        
        # Общий обработчик callback
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        # Message handlers
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        self.application.add_handler(MessageHandler(filters.VOICE, self.handle_voice_message))
        
        logger.info("Обработчики настроены")
    
    def stop_scheduler(self):
        """Остановить планировщик"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Планировщик остановлен")

# === ТОЧКА ВХОДА ===

def main():
    """Главная функция"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не найден в переменных окружения")
        return
    
    bot = TaskFlowBot(token)
    
    # Запускаем планировщик синхронно
    if not bot.scheduler.running:
        bot.scheduler.start()
        logger.info("Планировщик запущен")
    
    # Запускаем бота
    logger.info("Запуск TaskFlow бота")
    bot.application.run_polling()

if __name__ == '__main__':
    main()
    

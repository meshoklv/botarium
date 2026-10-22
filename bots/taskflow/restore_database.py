#!/usr/bin/env python3
"""
Восстановление базы данных TaskFlow Bot из бэкапа
"""
import json
import logging
import sys
from datetime import datetime
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def restore_database(backup_filename):
    """Восстановить базу данных из бэкапа"""
    if not backup_filename:
        print("❌ Не указан файл бэкапа")
        return False
    
    try:
        # Загружаем бэкап
        print(f"📂 Загрузка бэкапа: {backup_filename}")
        with open(backup_filename, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        
        print(f"📅 Дата бэкапа: {backup_data['backup_date']}")
        print(f"📦 Версия: {backup_data['version']}")
        print(f"📋 Таблиц в бэкапе: {len(backup_data['tables'])}")
        
        # Подключаемся к новой базе данных
        db = Database()
        
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Восстанавливаем данные по таблицам в правильном порядке
                table_order = [
                    'users',
                    'user_settings', 
                    'projects',
                    'project_members',
                    'task_templates',
                    'tasks',
                    'task_comments',
                    'task_history',
                    'notifications',
                    'activity_log'
                ]
                
                for table_name in table_order:
                    if table_name not in backup_data['tables']:
                        print(f"⚠️  Таблица {table_name} не найдена в бэкапе")
                        continue
                    
                    table_data = backup_data['tables'][table_name]
                    records = table_data['data']
                    
                    print(f"📄 Восстановление таблицы: {table_name} ({len(records)} записей)")
                    
                    if not records:
                        print(f"   ℹ️  Таблица {table_name} пуста")
                        continue
                    
                    # Получаем названия колонок из первой записи
                    columns = list(records[0].keys())
                    
                    # Создаем SQL для вставки
                    placeholders = ', '.join(['%s'] * len(columns))
                    columns_str = ', '.join(columns)
                    
                    insert_sql = f"""
                        INSERT INTO {table_name} ({columns_str})
                        VALUES ({placeholders})
                        ON CONFLICT DO NOTHING
                    """
                    
                    # Вставляем данные пачками
                    batch_size = 100
                    inserted_count = 0
                    
                    for i in range(0, len(records), batch_size):
                        batch = records[i:i + batch_size]
                        
                        for record in batch:
                            try:
                                values = [record[col] for col in columns]
                                cur.execute(insert_sql, values)
                                inserted_count += 1
                            except Exception as e:
                                print(f"   ⚠️  Ошибка вставки в {table_name}: {e}")
                                # Продолжаем с остальными записями
                    
                    print(f"   ✅ Вставлено записей: {inserted_count}")
                
                # Коммитим все изменения
                conn.commit()
                print("\n✅ Все данные восстановлены и сохранены")
        
        return True
        
    except FileNotFoundError:
        print(f"❌ Файл бэкапа не найден: {backup_filename}")
        return False
    except json.JSONDecodeError:
        print(f"❌ Некорректный JSON в файле: {backup_filename}")
        return False
    except Exception as e:
        print(f"❌ Ошибка восстановления: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Использование: python3 restore_database.py <backup_file.json>")
        sys.exit(1)
    
    backup_file = sys.argv[1]
    success = restore_database(backup_file)
    
    if success:
        print("\n🎉 Восстановление завершено успешно!")
    else:
        print("\n💥 Восстановление не удалось")
        sys.exit(1)
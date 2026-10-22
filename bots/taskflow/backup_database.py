#!/usr/bin/env python3
"""
Создание полного бэкапа базы данных TaskFlow Bot
"""
import json
import logging
from datetime import datetime
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def backup_database():
    """Создать полный бэкап базы данных"""
    db = Database()
    backup_data = {
        'backup_date': datetime.now().isoformat(),
        'version': '1.0',
        'tables': {}
    }
    
    print("📦 Создание бэкапа базы данных...")
    
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                # Получаем список всех таблиц
                cur.execute("""
                    SELECT tablename 
                    FROM pg_tables 
                    WHERE schemaname = 'public'
                    ORDER BY tablename
                """)
                tables = [row[0] for row in cur.fetchall()]
                print(f"📋 Найдено таблиц: {len(tables)}")
                
                for table_name in tables:
                    print(f"   📄 Бэкап таблицы: {table_name}")
                    
                    # Получаем структуру таблицы
                    cur.execute(f"""
                        SELECT column_name, data_type, is_nullable, column_default
                        FROM information_schema.columns
                        WHERE table_name = %s AND table_schema = 'public'
                        ORDER BY ordinal_position
                    """, (table_name,))
                    
                    columns_info = cur.fetchall()
                    
                    # Получаем данные таблицы
                    cur.execute(f"SELECT * FROM {table_name}")
                    rows = cur.fetchall()
                    
                    backup_data['tables'][table_name] = {
                        'structure': [dict(row) for row in columns_info],
                        'data': [dict(row) for row in rows],
                        'count': len(rows)
                    }
                    
                    print(f"      ✅ {len(rows)} записей")
    
        # Сохраняем бэкап
        backup_filename = f"backup_taskflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Конвертируем datetime объекты в строки для JSON
        def json_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return str(obj)
        
        with open(backup_filename, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2, default=json_serializer)
        
        print(f"\n✅ Бэкап сохранен: {backup_filename}")
        print(f"📊 Статистика:")
        
        total_records = 0
        for table_name, table_data in backup_data['tables'].items():
            count = table_data['count']
            total_records += count
            print(f"   📄 {table_name}: {count} записей")
        
        print(f"\n🎯 Всего записей: {total_records}")
        return backup_filename
        
    except Exception as e:
        print(f"❌ Ошибка создания бэкапа: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    backup_file = backup_database()
    if backup_file:
        print(f"\n🎉 Бэкап создан успешно: {backup_file}")
    else:
        print("\n💥 Не удалось создать бэкап")
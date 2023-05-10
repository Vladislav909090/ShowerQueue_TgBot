import psycopg2

# Подключение к базе данных
conn = psycopg2.connect(
    host="localhost",
    database="postgres",
    user="postgres",
    password="karburator93"
)

# Создание курсора
cur = conn.cursor()

# Запрос списка таблиц
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public';
""")

# Печать списка таблиц
print("Список таблиц:\n")
for table in cur.fetchall():
    print(f">>{table[0]}")
    # Запрос списка колонок и типов данных для каждой таблицы
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = '{}';
    """.format(table[0]))
    # Печать списка колонок и типов данных
    for column in cur.fetchall():
        print(f"    -{column[0]} ({column[1]})")

# Закрытие курсора и соединения с базой данных
cur.close()
conn.close()

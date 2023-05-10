import datetime
import itertools
import json
import random

import psycopg2
import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from telebot import types

from words_book import texts_list, times_list
from token_tg_bot import TOKEN

token = TOKEN
bot = telebot.TeleBot(token)


def create_acc(message):
    cursor.execute("INSERT INTO Users (chat_id, date_of_create, user_role) VALUES (%s, %s, %s)",
                   (message.chat.id, str(datetime.datetime.now()), 0))
    conn.commit()
    bot.send_message(message.chat.id, "вы зарегистрированы")


def smile_message(k):
    a = ''
    for i in range(k):
        a += chr(random.randint(128512, 128568))
    return a


def create_ln_schedule(cur_mas):
    res = str(cur_mas[0][0].strftime('%H:%M')) + "    "
    for i in cur_mas:
        res += f"{i[1]}: {('🔴' if i[4] == 1 else ('🟠' if i[2] is not None else '🟢'))}  "
    return res


def date_check():
    cursor.execute("DELETE FROM Queue WHERE date_trunc('day', time_schedule) = %s;",
                   (str(datetime.date.today() - datetime.timedelta(days=1)),))
    for j in range(1, 11):
        for i in times_list:
            for k in range(1, 4):
                cursor.execute("INSERT INTO Queue (time_schedule, id_shower) VALUES (%s, %s);",
                               (str(datetime.date.today() + datetime.timedelta(days=1)) + " " + i, j * 10 + k))
    cursor.execute("""UPDATE Users SET message_id IS NULL;""")
    conn.commit()
    print(f"INFO: Deleted old data: {datetime.date.today() - datetime.timedelta(days=1)}")


def update_message(chat_id, update_time):
    cursor.execute("""SELECT chat_id, floor, message_id FROM Users
        WHERE floor = (SELECT floor FROM Users WHERE chat_id = %s)
        AND message_id IS NOT NULL;""", (chat_id,))
    mas_people = cursor.fetchall()
    cursor.execute("""SELECT chat_id, queue.id_shower, stat FROM queue
                        JOIN shower_room ON shower_room.id_shower = queue.id_shower
                        JOIN floor_showers ON floor_showers.id_shower = queue.id_shower
                        WHERE floor = %s
                        AND time_schedule = %s
                        ORDER BY queue.id_shower;""",
                   (mas_people[0][1], datetime.datetime.today().strftime('%Y-%m-%d') + " " + update_time))
    mas_for_change_stat = cursor.fetchall()
    res = update_time + "    "
    for i in mas_for_change_stat:
        res += f"{i[1]}: {('🔴' if i[2] == 1 else ('🟠' if i[0] is not None else '🟢'))}  "

    keyboard = types.InlineKeyboardMarkup()
    buttons = []
    for i in mas_for_change_stat:
        buttons.append(
            types.InlineKeyboardButton(text=str(i[1]),
                                       callback_data=("set_queue_" + update_time + "_" + str(i[1]))))
    keyboard.add(*buttons)

    for person, floor, messages in mas_people:
        bot.edit_message_text(chat_id=person, message_id=messages[update_time], text=res, reply_markup=keyboard)


@bot.message_handler(commands=["start"])
def start(message):
    cursor.execute("SELECT EXISTS(SELECT 1 FROM Users WHERE chat_id = %s);", (message.chat.id,))
    if cursor.fetchone()[0]:
        bot.send_message(message.chat.id, "вы уже есть в базе базы.")
    else:
        create_acc(message)
        keyboard = types.InlineKeyboardMarkup(row_width=5)
        buttons = []
        for i in range(1, 11):
            buttons.append(types.InlineKeyboardButton(text=str(i), callback_data="set_floor_" + str(i)))
        keyboard.add(*buttons)
        bot.send_message(message.chat.id, "на каком этаже вы живете?", reply_markup=keyboard)


@bot.message_handler(commands=["help"])
def help_func(message):
    bot.send_message(message.from_user.id, texts_list[1])


@bot.message_handler(commands=["change_floor"])
def change_floor(message):
    keyboard = types.InlineKeyboardMarkup(row_width=5)
    buttons = []
    for i in range(1, 11):
        buttons.append(types.InlineKeyboardButton(text=str(i), callback_data="set_floor_" + str(i)))
    keyboard.add(*buttons)
    bot.send_message(message.chat.id, "на каком этаже теперь вы живете?", reply_markup=keyboard)


@bot.message_handler(commands=["shower"])
def shower(message):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(text="посмотреть ближайшее время /near_future", callback_data="near_future"))
    keyboard.add(
        types.InlineKeyboardButton(text="посмотреть ближайшее свободное место /next_free", callback_data="next_free"))
    keyboard.add(types.InlineKeyboardButton(text="/morning (6:00-11:20)", callback_data="morning"),
                 types.InlineKeyboardButton(text="/daytime (12:00-16:00)", callback_data="daytime"))
    keyboard.add(types.InlineKeyboardButton(text="/afternoon (16:40-22:00)", callback_data="afternoon"),
                 types.InlineKeyboardButton(text="/night (22:40-00:00)", callback_data="night"))
    bot.send_message(message.chat.id, "выберите из списка: ", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data == "next_free")
def next_free(call):
    cursor.execute("""SELECT * FROM queue 
        JOIN shower_room ON shower_room.id_shower = queue.id_shower
        WHERE queue.id_shower IN(SELECT id_shower FROM floor_showers WHERE floor= (SELECT floor FROM Users WHERE chat_id = %s))
        AND queue.time_schedule = (
            SELECT MIN(time_schedule) 
            FROM Queue 
            WHERE id_shower IN(SELECT id_shower FROM shower_room WHERE stat=0)
            AND chat_id IS NULL
            AND date_part('day', time_schedule) = date_part('day', current_date)
            AND time_schedule >= CURRENT_TIMESTAMP::timestamp without time zone
          )
        ORDER BY queue.id_shower;""", (call.from_user.id,))
    tmp = cursor.fetchall()
    if not tmp:
        bot.send_message(call.from_user.id, "на сегодня свободного врмемени нет")
    else:
        cursor.execute("SELECT message_id FROM Users WHERE chat_id=%s", (call.from_user.id,))
        mas_for_delete = cursor.fetchone()[0]
        if mas_for_delete is not None:
            for i in mas_for_delete.values():
                bot.delete_message(call.from_user.id, i)

        keyboard = types.InlineKeyboardMarkup()
        buttons = []
        for i in tmp:
            buttons.append(
                types.InlineKeyboardButton(text=str(i[3]),
                                           callback_data=("set_queue_" + i[0].strftime('%H:%M')) + "_" + str(
                                               i[3])))
        keyboard.add(*buttons)
        message_id = bot.send_message(call.from_user.id, create_ln_schedule(tmp), reply_markup=keyboard)
        message_dict = {message_id.text[:5].rstrip(): message_id.message_id}
        cursor.execute("UPDATE Users SET message_id = %s WHERE chat_id=%s",
                       (json.dumps(message_dict), call.from_user.id))
        conn.commit()


@bot.callback_query_handler(func=lambda call: call.data == "near_future")
def near_future(call):
    cursor.execute("""SELECT * FROM queue 
        JOIN shower_room ON shower_room.id_shower = queue.id_shower
        WHERE shower_room.id_shower IN(SELECT id_shower FROM floor_showers 
                                            WHERE floor= (SELECT floor FROM Users WHERE chat_id = %s))
        AND time_schedule IN (SELECT DISTINCT time_schedule FROM Queue 
                                            WHERE time_schedule >= CURRENT_TIMESTAMP::timestamp without time zone
                                            LIMIT 3)
        ORDER BY time_schedule, shower_room.id_shower;""", (call.from_user.id,))
    tmp = cursor.fetchall()
    if not tmp:
        bot.send_message(call.from_user.id, "на сегодня свободного врмемени нет")
    else:
        cursor.execute("SELECT message_id FROM Users WHERE chat_id=%s", (call.from_user.id,))
        cur_mas = cursor.fetchone()[0]
        if cur_mas is not None:
            for i in cur_mas.values():
                bot.delete_message(call.from_user.id, i)

        message_dict = {}
        for _, group in itertools.groupby(tmp, key=lambda x: x[0]):
            group_copy = list(group)
            keyboard = types.InlineKeyboardMarkup()
            buttons = []
            for i in group_copy:
                buttons.append(
                    types.InlineKeyboardButton(text=str(i[1]),
                                               callback_data=("set_queue_" + i[0].strftime('%H:%M') + "_" + str(i[1]))))
            keyboard.add(*buttons)
            message_id = bot.send_message(call.from_user.id, create_ln_schedule(group_copy), reply_markup=keyboard)
            message_dict[message_id.text[:5].rstrip()] = message_id.message_id
        cursor.execute("UPDATE Users SET message_id = %s WHERE chat_id=%s",
                       (json.dumps(message_dict), call.from_user.id))
        conn.commit()


@bot.callback_query_handler(func=lambda call: call.data.startswith("set_floor_"))
def set_floor(call):
    cursor.execute("SELECT floor FROM Users WHERE chat_id = %s;", (call.from_user.id,))
    current_floor = cursor.fetchone()[0]
    new_floor = int(call.data.split("_")[-1])
    if current_floor is None:
        cursor.execute("UPDATE Users SET floor=%s WHERE chat_id=%s", (new_floor, call.from_user.id))
        conn.commit()
        bot.send_message(call.from_user.id, f"{new_floor} этаж установлен")
        bot.send_message(call.from_user.id, "для допонительной информации напишите /help")
    elif new_floor == current_floor:
        bot.send_message(call.from_user.id, f"{current_floor} этаж уже стоит")
    else:
        cursor.execute("SELECT message_id FROM Users WHERE chat_id=%s", (call.from_user.id,))
        cur_mas = cursor.fetchone()[0]
        if cur_mas is not None:
            for i in cur_mas.values():
                bot.delete_message(call.from_user.id, i)
        cursor.execute("UPDATE Users SET floor=%s, message_id = NULL WHERE chat_id=%s", (new_floor, call.from_user.id))
        conn.commit()
        bot.send_message(call.from_user.id, f"{current_floor} этаж изменен на {new_floor}")


@bot.callback_query_handler(func=lambda call: call.data.startswith("set_queue_"))
def set_queue(call):
    tm, id_sh = call.data[10:].split("_")
    id_sh = int(id_sh)
    print(tm, id_sh)
    cursor.execute("""SELECT chat_id FROM Queue 
        WHERE time_schedule = %s
        AND id_shower = %s;""", (str(datetime.date.today()) + " " + tm, id_sh))
    IsNone_chat_id = cursor.fetchone()[0]
    cursor.execute("""SELECT stat FROM shower_room 
        WHERE id_shower = %s;""", (id_sh,))
    IsWorking_shr = cursor.fetchone()[0]
    cursor.execute("""SELECT user_shower_stat FROM Users WHERE chat_id = %s;""", (call.from_user.id,))
    current_per_shr = cursor.fetchone()[0]

    cursor.execute("SELECT time_schedule FROM queue WHERE chat_id = %s;",
                   (call.from_user.id,))
    tm_sch = cursor.fetchone()
    tm_sch = tm_sch if tm_sch is None else tm_sch[0]


    if (current_per_shr is None):
        if (IsWorking_shr == 0):
            if (IsNone_chat_id is None):
                cursor.execute("SELECT message_id FROM Users WHERE chat_id = %s;",
                               (call.from_user.id,))
                tm_sch = None
                if len(cursor.fetchone()[0]) > 1:
                    cursor.execute("SELECT time_schedule FROM queue WHERE chat_id = %s;",
                                   (call.from_user.id,))
                    tm_sch = cursor.fetchone()
                    tm_sch = tm_sch if tm_sch is None else tm_sch[0]

                cursor.execute("UPDATE Queue SET chat_id=%s WHERE time_schedule = %s AND id_shower = %s;",
                               (call.from_user.id, str(datetime.date.today()) + " " + tm, id_sh))
                cursor.execute("UPDATE Users SET user_shower_stat=%s WHERE chat_id = %s;",
                               (id_sh, call.from_user.id))
                conn.commit()

                if (tm_sch is not None) and (tm != tm_sch.strftime('%H:%M')):
                    update_message(call.from_user.id, tm_sch.strftime('%H:%M'))

                update_message(call.from_user.id, tm)
                bot.send_message(call.from_user.id, "вы успешно записались")
            else:
                bot.send_message(call.from_user.id, "место уже занято")
        else:
            bot.send_message(call.from_user.id, "к сожалению, в настоящий момент этот душ не работает")
    elif current_per_shr == id_sh and tm == tm_sch.strftime('%H:%M'):
        cursor.execute("UPDATE Queue SET chat_id=%s WHERE time_schedule = %s AND id_shower = %s;",
                       (None, str(datetime.date.today()) + " " + tm, current_per_shr))
        cursor.execute("UPDATE Users SET user_shower_stat=%s WHERE chat_id = %s;",
                       (None, call.from_user.id))
        conn.commit()
        update_message(call.from_user.id, tm)
        bot.send_message(call.from_user.id, "вы отписались")
    else:
        if (IsNone_chat_id is None):
            cursor.execute("SELECT message_id FROM Users WHERE chat_id = %s;",
                           (call.from_user.id,))
            count_messages = len(cursor.fetchone()[0])
            # cursor.execute("SELECT time_schedule FROM queue WHERE chat_id = %s;",
            #                (call.from_user.id,))
            # tm_sch = cursor.fetchone()[0]
            # tm_sch = tm_sch if tm_sch is None else tm_sch[0]

            cursor.execute("UPDATE Queue SET chat_id=%s WHERE time_schedule = %s AND id_shower = %s;",
                           (None, tm_sch, current_per_shr))
            cursor.execute("UPDATE Queue SET chat_id=%s WHERE time_schedule = %s AND id_shower = %s;",
                           (call.from_user.id, str(datetime.date.today()) + " " + tm, id_sh))
            cursor.execute("UPDATE Users SET user_shower_stat=%s WHERE chat_id = %s;",
                           (id_sh, call.from_user.id))
            conn.commit()

            if (tm != tm_sch.strftime('%H:%M')) and (count_messages > 1):
                update_message(call.from_user.id, tm_sch.strftime('%H:%M'))

            update_message(call.from_user.id, tm)
            bot.send_message(call.from_user.id, "вы успешно переписались")
        else:
            bot.send_message(call.from_user.id, "место уже занято")


@bot.message_handler(content_types=["text"])
def any_msg(message):
    if message.text == 'kapibara':
        cursor.execute("UPDATE Users SET user_role=%s WHERE chat_id=%s", (3, message.chat.id))
        conn.commit()
        bot.send_message(message.chat.id, smile_message(10))
    if message.text == 'ITMO':
        cursor.execute("SELECT user_role FROM Users WHERE chat_id = %s;", (message.chat.id,))
        if cursor.fetchone()[0] == 3:
            bot.send_message(message.chat.id, "ваша роль уже выше. понижение статуса роли не предполагается")
        else:
            cursor.execute("UPDATE Users SET user_role=%s WHERE chat_id=%s", (2, message.chat.id))
            conn.commit()
            bot.send_message(message.chat.id, smile_message(5))

    if message.text.lower().startswith("prm "):
        cursor.execute(
            "SELECT COUNT(*) FROM Offers_table WHERE date_trunc('day', date_of_create) = date_trunc('day', now()) and chat_id = %s;",
            (message.chat.id,))
        if cursor.fetchone()[0] <= (2 - 1):
            if not message.text[3:].strip():
                bot.send_message(message.chat.id, "в сообщении должно что-то быть написано")
            else:
                cursor.execute("INSERT INTO offers_table (chat_id, offers, date_of_create) VALUES (%s, %s, %s)",
                               (message.chat.id, message.text[4:], str(datetime.datetime.now())))
                conn.commit()
                bot.send_message(message.chat.id, "запись успешно добавлена")
        else:
            bot.send_message(message.chat.id, "вы препвысили количество предложений в день")


if __name__ == '__main__':
    # Подключение к базе данных
    conn = psycopg2.connect(
        host="localhost",
        database="postgres",
        user="postgres",
        password="karburator93"
    )
    print("connected to DB")

    # Создание курсора
    cursor = conn.cursor()

    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
    tables = cursor.fetchall()
    for i in tables:
        if i[0] == 'users':
            cursor.execute("TRUNCATE TABLE Users RESTART IDENTITY CASCADE;")
        else:
            cursor.execute(f"TRUNCATE TABLE {i[0]} CASCADE;")
    conn.commit()
    print("cleared tables")

    for i in range(1, 11):
        for j in range(1, 4):
            cursor.execute("INSERT INTO Floor_showers (floor, id_shower) VALUES (%s, %s);", (i, i * 10 + j))
    conn.commit()

    for i in range(1, 11):
        for j in range(1, 4):
            cursor.execute("INSERT INTO Shower_room (id_shower, stat) VALUES (%s, %s);", (i * 10 + j, 0))
    conn.commit()

    for j in range(1, 11):
        for i in times_list:
            for k in range(1, 4):
                cursor.execute("INSERT INTO Queue (time_schedule, id_shower) VALUES (%s, %s);",
                               (str(datetime.date.today()) + " " + i, j * 10 + k))
    for j in range(1, 11):
        for i in times_list:
            for k in range(1, 4):
                cursor.execute("INSERT INTO Queue (time_schedule, id_shower) VALUES (%s, %s);",
                               (str(datetime.date.today() + datetime.timedelta(days=1)) + " " + i, j * 10 + k))
    conn.commit()
    print("inserted all needed information")

    scheduler = BackgroundScheduler()
    trigger = CronTrigger(hour=2, minute=0, timezone=timezone('Europe/Moscow'))
    scheduler.add_job(date_check, trigger)
    scheduler.start()

    print("starting bot polling")
    bot.infinity_polling()

    # закрытие соединения
    conn.close()
    print("closed connecting")

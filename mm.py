import os
import json
import logging
import pandas as pd
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
from datetime import datetime, time, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
DATA_FILE = "Data.json"
ORDERS = "Заказы.xlsx"
MENU = "https://docs.google.com/spreadsheets/d/1eEEHGwtSV2znQDGJcgGVEQ2PzNTLoDPOT-9vtyQCoQY/export?format=csv"
ADDRESSES_FILE = "Addresses.json" 
TOKEN = "8154269678:AAE-CLwwQi6ZHW_nQvgoDERzG6lsqt37htY"

CHOOSE_ADDRESS, ENTER_NAME, BROADCAST_MESSAGE, ADD_ADDRESS = range(4)

def load_data(file_path, default):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return default
    except Exception as e:
        logger.error(f"Error loading data from {file_path}: {e}")
        return default

def save_data(file_path, data):
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Error saving data to {file_path}: {e}")

def load_user_data():
    return load_data(DATA_FILE, {"users": []})

def save_user_data(data):
    save_data(DATA_FILE, data)

def load_addresses():
    return load_data(ADDRESSES_FILE, {"addresses": []})

def save_addresses(data):
    save_data(ADDRESSES_FILE, data)

def load_menu_data():
    try:
        df = pd.read_csv(MENU)
        return df
    except Exception as e:
        logger.error(f"Ошибка при загрузке меню: {e}")
        return None

def normalize_phone_number(phone_number):
    digits = ''.join(filter(str.isdigit, phone_number))
    if len(digits) == 11 and digits.startswith('8'):
        return '7' + digits[1:]
    elif len(digits) == 10 and digits.startswith('9'):
        return '7' + digits
    elif len(digits) == 11 and digits.startswith('7'):
        return digits
    elif len(digits) == 12 and digits.startswith('+7'):
        return digits
    return phone_number

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_data = load_user_data()
        chat_id = update.message.chat_id
        if context.user_data.get("phone_verified"):
            user = next((u for u in user_data["users"] if u.get("chat_id") == chat_id), None)
            if user:
                keyboard = get_role_keyboard(user.get("role", "Заказчик"))
                await update.message.reply_text(
                    f"Добро пожаловать, {user['name']}! Ваша роль: {user['role']}.",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                )
                return
            
        user = next((u for u in user_data["users"] if u.get("chat_id") == chat_id), None)
        if user:
            context.user_data["phone_verified"] = True
            context.user_data["phone_number"] = user["phone"]
            context.user_data["role"] = user.get("role", "Заказчик")

            logger.info(f"Пользователь уже зарегистрирован: {user['name']}, роль: {user['role']}")

            keyboard = get_role_keyboard(user.get("role", "Заказчик"))
            await update.message.reply_text(
                f"Добро пожаловать, {user['name']}! Ваша роль: {user['role']}.",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return

        contact = update.message.contact
        if contact:
            phone_number = normalize_phone_number(contact.phone_number)
            user = next((u for u in user_data["users"] if u["phone"] == phone_number), None)

            if user:
                context.user_data["phone_verified"] = True
                context.user_data["phone_number"] = phone_number
                context.user_data["role"] = user.get("role", "Заказчик")

                logger.info(f"Роль пользователя: {context.user_data.get('role')}")

                keyboard = get_role_keyboard(user.get("role", "Заказчик"))
                await update.message.reply_text(
                    f"Добро пожаловать, {user['name']}! Ваша роль: {user['role']}.",
                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                )
            else:
                addresses = load_addresses().get("addresses", [])
                if not addresses:
                    await update.message.reply_text(
                        "Список адресов доставки недоступен. Свяжитесь с администратором."
                    )
                    return

                context.user_data["phone_number"] = phone_number
                keyboard = [[InlineKeyboardButton(address, callback_data=address)] for address in addresses]
                await update.message.reply_text(
                    "Выберите адрес доставки:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return CHOOSE_ADDRESS
        else:
            await update.message.reply_text(
                "Пожалуйста, подтвердите ваш номер телефона.",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("Подтвердить номер телефона", request_contact=True)]],
                    resize_keyboard=True, one_time_keyboard=True
                )
            )
    except Exception as e:
        logger.error(f"Ошибка в команде start: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")
        
def get_role_keyboard(role):
    if role == "Администратор":
        return [["Список заказов", "Сообщить всем"], ["Добавить адрес доставки", "Импорт chat_id"]]
    elif role == "Заказчик":
        return [["Сделать заказ", "Корзина"]]  

async def choose_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()

        address = query.data
        phone_number = context.user_data.get("phone_number")
        if not phone_number:
            await query.edit_message_text("Ошибка регистрации. Попробуйте ещё раз.")
            return

        context.user_data["address"] = address
        await query.edit_message_text(f"Адрес доставки выбран: {address}. Введите ваше имя:")
        return ENTER_NAME
    except Exception as e:
        logger.error(f"Error in choose_address: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def enter_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        name = update.message.text
        phone_number = context.user_data.get("phone_number")
        address = context.user_data.get("address")

        if not phone_number or not address:
            await update.message.reply_text("Ошибка регистрации. Попробуйте снова.")
            return ConversationHandler.END

        user_data = load_user_data()
        user_data["users"].append({"phone": phone_number, "role": "Заказчик", "address": address, "name": name, "chat_id": update.message.chat_id})
        save_user_data(user_data)

        await update.message.reply_text(f"Регистрация завершена. Добро пожаловать, {name}!")
        role = context.user_data.get("role", "Заказчик")
        
        if role != "Администратор":
            keyboard = get_role_keyboard("Заказчик")
            await update.message.reply_text(
                f"Теперь вы можете заказывать, {name}!",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
        else:
            keyboard = get_role_keyboard("Администратор")
            await update.message.reply_text(
                f"Добро пожаловать, {name}!",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in enter_name: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")
        return ConversationHandler.END
    
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        today = datetime.now()
        days = [today + timedelta(days=i) for i in range(7)]
        cutoff_time = time(10, 0)  # Время, после которого нельзя заказывать на сегодня

        keyboard = []
        days_of_week = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        for day in days:
            if day.date() == today.date() and datetime.now().time() >= cutoff_time:
                continue
            day_name = days_of_week[day.weekday()]
            button_text = f"{day.strftime('%d.%m.%Y')} ({day_name})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=day.strftime('%d.%m.%Y'))])
        next_day = today + timedelta(days=1)
        next_day_name = days_of_week[next_day.weekday()]
        button_text = f"{next_day.strftime('%d.%m.%Y')} ({next_day_name})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=next_day.strftime('%d.%m.%Y'))])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выберите дату:", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка в функции show_menu: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def handle_menu_and_lunch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(update, Update) and update.callback_query:
        query = update.callback_query
        selected_date_str = query.data
        try:
            selected_date_full = datetime.strptime(selected_date_str, '%d.%m.%Y')
        except ValueError:
            try:
                selected_date_full = datetime.strptime(selected_date_str, '%d-%m-%Y')
            except ValueError as e:
                await query.message.reply_text(f"Некорректный формат даты: {selected_date_str}. Используйте формат ДД.ММ.ГГГГ или ДД-ММ-ГГГГ.")
                return

        days_of_week = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        day_index = selected_date_full.weekday()
        selected_day_name = days_of_week[day_index]

        await query.answer()
        await query.edit_message_text(f"Вы выбрали дату: {selected_date_str} ({selected_day_name})")
        context.user_data["selected_date"] = selected_date_str
        context.user_data["selected_day_name"] = selected_day_name

        try:
            menu_data = pd.read_csv(MENU)
            menu_data['Цена'] = menu_data['Цена'].astype(str) + ' рублей'

            week_number = selected_date_full.isocalendar()[1] % 2  

            daily_menu = menu_data[(menu_data['День недели'] == selected_day_name) & (menu_data['Неделя'] == week_number)]
            print(daily_menu)

            if daily_menu.empty:
                await query.message.reply_text("К сожалению, на эту дату нет меню.")
                return

            lunch_items = daily_menu.groupby('Название').agg({'Блюдо': list, 'Цена': 'first'}).reset_index()

            menu_text = f"Меню на {selected_date_str} ({days_of_week[day_index]})\n\n"

            for index, row in lunch_items.iterrows():
                menu_text += f"*{row['Название']}* ({row['Цена']}):\n"
                for i, dish in enumerate(row['Блюдо']):
                    menu_text += f"{i+1}. {dish}\n"
                menu_text += "\n"

            await query.message.reply_text(menu_text)
            keyboard = []
            complex_lunches = daily_menu[daily_menu['Название'] == 'Комплексный обед']['Название'].unique().tolist()
            drinks = daily_menu[daily_menu['Название'] == 'Напиток']['Блюдо'].unique().tolist()
            salads = daily_menu[daily_menu['Название'] == 'Салат']['Блюдо'].unique().tolist()

            if complex_lunches:
                row = [KeyboardButton(option) for option in complex_lunches]
                keyboard.append(row)

            if drinks:
                row = [KeyboardButton(option) for option in drinks]
                keyboard.append(row)

            if salads:
                row = [KeyboardButton(option) for option in salads]
                keyboard.append(row)

            keyboard.append([KeyboardButton("Корзина")])
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await query.message.reply_text("Выберите обед:", reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Ошибка при загрузке меню: {e}")
            await query.message.reply_text(f"Ошибка при загрузке меню: {e}")
            return

    elif isinstance(update, Update) and update.message and update.message.text:
        message = update.message.text
        phone = context.user_data.get("phone_number")
        if phone is None:
            await update.message.reply_text("Ваш номер телефона не зарегистрирован, перезапустите бота!")
            return
        
        selected_date = context.user_data.get("selected_date")
        selected_day_name = context.user_data.get("selected_day_name")

        if selected_date is None:
            await update.message.reply_text("Выберите дату, прежде чем заказывать обед.")
            return

        try:
            menu_data = pd.read_csv(MENU)
            daily_menu = menu_data[menu_data['День недели'] == selected_day_name] 

            if message in daily_menu['Название'].unique():
                complex_lunch_options = daily_menu[daily_menu['Название'] == message]
                if not complex_lunch_options.empty:
                    price = complex_lunch_options['Цена'].iloc[0]
                else:
                    await update.message.reply_text(f"Цена для {message} не найдена в меню.")
                    return

            else:
                price_row = daily_menu[daily_menu['Блюдо'] == message]
                if not price_row.empty:
                    price = price_row['Цена'].iloc[0]
                else:
                    await update.message.reply_text(f"Цена для {message} не найдена в меню.")
                    return

            try:
                orders_df = pd.read_excel(ORDERS)
            except FileNotFoundError:
                orders_df = pd.DataFrame(columns=['Номер телефона', 'Дата', 'День недели', 'Обед', 'Цена', 'Статус оплаты']) 

            selected_date_full = datetime.strptime(selected_date, '%d.%m.%Y')
            days_of_week = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
            day_name = days_of_week[selected_date_full.weekday()]

            new_order = pd.DataFrame({
                'Номер телефона': [phone],
                'Дата': [selected_date],
                'День недели': [selected_day_name],
                'Обед': [message],
                'Цена': [price],
                'Статус оплаты': ['Не оплачено']
            })
            orders_df = pd.concat([orders_df, new_order], ignore_index=True)
            orders_df.to_excel(ORDERS, index=False)

            await update.message.reply_text(f"Ваш выбор ({message}) записан! Цена: {price} рублей.")
            daily_menu = menu_data[menu_data['День недели'] == selected_day_name]
            complex_lunches = daily_menu[daily_menu['Название'] == 'Комплексный обед']['Название'].unique().tolist()
            drinks = daily_menu[daily_menu['Название'] == 'Напиток']['Блюдо'].unique().tolist()
            salads = daily_menu[daily_menu['Название'] == 'Салат']['Блюдо'].unique().tolist()

            keyboard = []
            if complex_lunches:
                row = [KeyboardButton(option) for option in complex_lunches]
                keyboard.append(row)

            if drinks:
                row = [KeyboardButton(option) for option in drinks]
                keyboard.append(row)

            if salads:
                row = [KeyboardButton(option) for option in salads]
                keyboard.append(row)
            next_day = selected_date_full + timedelta(days=1)
            next_day_str = next_day.strftime('%d.%m.%Y')
            keyboard = [
                [InlineKeyboardButton("Сделать следующий заказ", callback_data="next_order")],
                [InlineKeyboardButton("Перейти в корзину", callback_data="show_cart")],
                [InlineKeyboardButton("Вернуться в главное меню", callback_data="main_menu")]
                ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Заказ успешно добавлен! Что дальше?", reply_markup=reply_markup)
        except Exception as e:
                    logger.error(f"Ошибка при записи заказа: {e}")
                    await update.message.reply_text(f"Ошибка при записи заказа: {e}")
                    return

async def show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if context.user_data.get("role") == "Администратор":
            await update.message.reply_text("У вас нет доступа к этой функции.")
            return
        selected_date = context.user_data.get("selected_date")
        if not selected_date:
            await update.message.reply_text("Выберите дату, чтобы увидеть заказы.")
            return

        try:
            orders_df = pd.read_excel(ORDERS)
        except FileNotFoundError:
            await update.message.reply_text("Файл с заказами не найден.")
            return
        phone_number = context.user_data.get("phone_number")
        if not phone_number:
            await update.message.reply_text("Ваш номер телефона не зарегистрирован. Перезапустите бота.")
            return
        phone_number_clean = ''.join(filter(str.isdigit, phone_number))
        orders_df['Номер телефона'] = orders_df['Номер телефона'].astype(str).str.replace('[^0-9]', '', regex=True)
        user_orders = orders_df[
            (orders_df['Номер телефона'] == phone_number_clean) &
            (orders_df['Дата'] == selected_date)
        ]

        if user_orders.empty:
            await update.message.reply_text(f"На {selected_date} у вас нет заказов.")
            return
        orders_text = f"Ваши заказы на {selected_date}:\n\n"
        total_price = 0

        for index, row in user_orders.iterrows():
            orders_text += f"• {row['Обед']} - {row['Цена']} рублей\n"
            total_price += row['Цена']
        orders_text += f"\nИтого к оплате: {total_price} рублей."
        keyboard = [
            [KeyboardButton("Оплатить")],
            [KeyboardButton("Отмена")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(orders_text, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Ошибка при отображении заказов: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if context.user_data.get("role") == "Администратор":
            await update.message.reply_text("У вас нет доступа к этой функции.")
            return

        keyboard = [["Меню", "Мои заказы", "Корзина"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Главное меню:", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in menu: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = context.user_data.get("role")
    logger.info(f"Роль пользователя в broadcast_start: {role}")

    if role != "Администратор":
        await update.message.reply_text("У вас нет прав для использования этой функции.")
        return

    await update.message.reply_text("Введите сообщение, которое вы хотите отправить всем пользователям.")
    return BROADCAST_MESSAGE

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message.text
        user_data = load_user_data()

        for user in user_data["users"]:
            chat_id = user.get("chat_id")
            if chat_id:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=f"[Сообщение от администратора]\n{message}")
                except Exception as e:
                    logger.error(f"Error sending message to {chat_id}: {e}")

        await update.message.reply_text("Сообщение было отправлено всем пользователям.")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in broadcast_message: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def add_address_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = context.user_data.get("role")
    logger.info(f"Роль пользователя в add_address_start: {role}")

    if role != "Администратор":
        await update.message.reply_text("У вас нет прав для использования этой функции.")
        return

    await update.message.reply_text("Введите адрес, который вы хотите добавить в список доступных для доставки.")
    return ADD_ADDRESS

async def add_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = update.message.text
        addresses = load_addresses()
        addresses["addresses"].append(address)
        save_addresses(addresses)

        await update.message.reply_text(f"Адрес '{address}' был успешно добавлен.")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in add_address: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        logger.info(f"Нажата кнопка: {text}")  # Логируем нажатую кнопку

        if text == "Сделать заказ":
            await show_menu(update, context)
        elif text == "Корзина":
            await show_orders(update, context)
        elif text == "Список заказов":
            await show_all_orders(update, context)
        elif text == "Сообщить всем":
            await broadcast_start(update, context)
        elif text == "Добавить адрес доставки":
            await add_address_start(update, context)
        elif text == "Импорт chat_id":
            await import_chat_ids(update, context)
        elif text == "Комплексный обед":
            await handle_complex_lunch(update, context, "Комплексный обед")
        elif text == "Комплексный обед №2":
            await handle_complex_lunch(update, context, "Комплексный обед №2")
        elif text == "Комплексный обед №3":
            await handle_complex_lunch(update, context, "Комплексный обед №3")
        elif text == "Комплексный обед №4":
            await handle_complex_lunch(update, context, "Комплексный обед №4")
        elif text == "Чай":
            await handle_drink(update, context, "Чай")
        elif text == "Кофе":
            await handle_drink(update, context, "Кофе")
        elif text == "Цезарь":
            await handle_salad(update, context, "Цезарь")
        elif text == "Салат Греческий":
            await handle_salad(update, context, "Салат Греческий")
        elif text == "Компот":
            await handle_drink(update, context, "Компот")
        elif text == "Оплатить":
            if update.callback_query:
                    pass
            else:
                    await handle_payment(update, context)

        elif text == "Отмена":
            await handle_cancel(update, context)
        elif text == "Нет, спасибо":
            await update.message.reply_text("Спасибо за ваш заказ! Если хотите что-то ещё, выберите из меню.")
        elif text.startswith("Заказать на "):
            next_day_str = text.replace("Заказать на ", "")
            context.user_data["selected_date"] = next_day_str
            await show_menu(update, context)
        elif text == "Вернуться в главное меню":
            await show_main_menu(update, context)
        else:
            await update.message.reply_text("Неизвестная команда. Пожалуйста, выберите действие из меню.")
    except Exception as e:
        logger.error(f"Ошибка при обработке кнопки: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    logger.info(f"Получен callback_query с данными: {data}")

    if data == "main_menu":
        await show_main_menu(update, context)

    elif data == "next_order":
        await show_menu(update, context)

    elif data == "pay_now":
        await handle_payment(update, context)

    elif data.startswith("order_"):
        next_day_str = data.replace("order_", "")
        try:
            datetime.strptime(next_day_str, '%d.%m.%Y')
            context.user_data["selected_date"] = next_day_str
            await show_menu(update, context)
        except ValueError:
            await query.edit_message_text(f"Некорректный формат даты: {next_day_str}. Используйте формат ДД.ММ.ГГГГ.")

    elif re.match(r'\d{2}\.\d{2}\.\d{4}', data):
        await handle_payment(update, context)
    
    else:
        await query.edit_message_text("Неизвестная команда. Пожалуйста, выберите действие из меню.")

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        selected_date = context.user_data.get("selected_date")
        phone_number = context.user_data.get("phone_number")

        if not selected_date or not phone_number:
            await update.message.reply_text("Ошибка: не удалось найти данные о заказе.")
            return

        try:
            orders_df = pd.read_excel(ORDERS)
        except FileNotFoundError:
            await update.message.reply_text("Файл с заказами не найден.")
            return
        phone_number_clean = ''.join(filter(str.isdigit, phone_number))
        orders_df['Номер телефона'] = orders_df['Номер телефона'].astype(str).str.replace('[^0-9]', '', regex=True)

        user_orders = orders_df[
            (orders_df['Номер телефона'] == phone_number_clean) &
            (orders_df['Дата'] == selected_date)
        ]

        if user_orders.empty:
            await update.message.reply_text("Нет заказов для отмены.")
            return
        orders_df = orders_df[
            ~((orders_df['Номер телефона'] == phone_number_clean) &
              (orders_df['Дата'] == selected_date))
        ]
        orders_df.to_excel(ORDERS, index=False)

        await update.message.reply_text("Ваши заказы успешно отменены!")
        await show_main_menu(update, context)

    except Exception as e:
        logger.error(f"Ошибка при отмене заказов: {e}")
        await update.message.reply_text("Произошла ошибка при отмене заказов. Пожалуйста, попробуйте снова.")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        role = context.user_data.get("role", "Заказчик")
        if role == "Администратор":
            keyboard = [
                ["Список заказов", "Сообщить всем"],
                ["Добавить адрес доставки", "Импорт chat_id"]
            ]
        else:
            keyboard = [
                ["Сделать заказ", "Корзина"]
            ]

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Главное меню:", reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Ошибка при отображении главного меню: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def handle_drink(update: Update, context: ContextTypes.DEFAULT_TYPE, drink_name: str):
    try:
        phone = context.user_data.get("phone_number")
        if phone is None:
            await update.message.reply_text("Ваш номер телефона не зарегистрирован, перезапустите бота!")
            return

        selected_date = context.user_data.get("selected_date")
        if selected_date is None:
            await update.message.reply_text("Выберите дату, прежде чем заказывать напиток.")
            return

        try:
            menu_data = pd.read_csv(MENU)
            drink_prices = dict(zip(menu_data['Блюдо'], menu_data['Цена']))

            price = drink_prices.get(drink_name)
            if price is None:
                await update.message.reply_text(f"Цена для {drink_name} не найдена в меню.")
                return

            try:
                orders_df = pd.read_excel(ORDERS)
            except FileNotFoundError:
                orders_df = pd.DataFrame(columns=['Номер телефона', 'Дата', 'Обед', 'Цена', 'Статус оплаты'])

            new_order = pd.DataFrame({
                'Номер телефона': [phone],
                'Дата': [selected_date],
                'Обед': [drink_name],
                'Цена': [price],
                'Статус оплаты': ['Не оплачено']
            })
            orders_df = pd.concat([orders_df, new_order], ignore_index=True)
            orders_df.to_excel(ORDERS, index=False)
            logger.info(f"Заказ сохранён: {drink_name}, цена: {price}, дата: {selected_date}, телефон: {phone}")
            await update.message.reply_text(f"Ваш выбор ({drink_name}) записан! Цена: {price} рублей.")
        except Exception as e:
            logger.error(f"Ошибка записи в файл: {e}")
            await update.message.reply_text(f"Ошибка записи в файл: {e}")
    except Exception as e:
        logger.error(f"Ошибка при обработке напитка: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def handle_salad(update: Update, context: ContextTypes.DEFAULT_TYPE, salad_name: str):
    try:
        phone = context.user_data.get("phone_number")
        if phone is None:
            await update.message.reply_text("Ваш номер телефона не зарегистрирован, перезапустите бота!")
            return

        selected_date = context.user_data.get("selected_date")
        if selected_date is None:
            await update.message.reply_text("Выберите дату, прежде чем заказывать салат.")
            return

        try:
            menu_data = pd.read_csv(MENU)
            salad_prices = dict(zip(menu_data['Блюдо'], menu_data['Цена']))

            price = salad_prices.get(salad_name)
            if price is None:
                await update.message.reply_text(f"Цена для {salad_name} не найдена в меню.")
                return

            try:
                orders_df = pd.read_excel(ORDERS)
            except FileNotFoundError:
                orders_df = pd.DataFrame(columns=['Номер телефона', 'Дата', 'Обед', 'Цена', 'Статус оплаты'])

            new_order = pd.DataFrame({
                'Номер телефона': [phone],
                'Дата': [selected_date],
                'Обед': [salad_name],
                'Цена': [price],
                'Статус оплаты': ['Не оплачено']
            })
            orders_df = pd.concat([orders_df, new_order], ignore_index=True)
            orders_df.to_excel(ORDERS, index=False)
            logger.info(f"Заказ сохранён: {salad_name}, цена: {price}, дата: {selected_date}, телефон: {phone}")
            await update.message.reply_text(f"Ваш выбор ({salad_name}) записан! Цена: {price} рублей.")
        except Exception as e:
            logger.error(f"Ошибка записи в файл: {e}")
            await update.message.reply_text(f"Ошибка записи в файл: {e}")
    except Exception as e:
        logger.error(f"Ошибка при обработке: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        await handle_buttons(update, context)
    except Exception as e:
        logger.error(f"Ошибка при обработке текстового сообщения: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def handle_complex_lunch(update: Update, context: ContextTypes.DEFAULT_TYPE, lunch_name: str):
    try:
        phone = context.user_data.get("phone_number")
        if phone is None:
            await update.message.reply_text("Ваш номер телефона не зарегистрирован, перезапустите бота!")
            return

        selected_date = context.user_data.get("selected_date")
        if selected_date is None:
            await update.message.reply_text("Выберите дату, прежде чем заказывать обед.")
            return

        try:
            menu_data = pd.read_csv(MENU)
            lunch_prices = dict(zip(menu_data['Название'], menu_data['Цена']))

            price = lunch_prices.get(lunch_name)
            if price is None:
                await update.message.reply_text(f"Цена для {lunch_name} не найдена в меню.")
                return

            try:
                orders_df = pd.read_excel(ORDERS)
            except FileNotFoundError:
                orders_df = pd.DataFrame(columns=['Номер телефона', 'Дата', 'Обед', 'Цена', 'Статус оплаты'])

            new_order = pd.DataFrame({
                'Номер телефона': [phone],
                'Дата': [selected_date],
                'Обед': [lunch_name],
                'Цена': [price],
                'Статус оплаты': ['Не оплачено']
            })
            orders_df = pd.concat([orders_df, new_order], ignore_index=True)
            orders_df.to_excel(ORDERS, index=False)
            logger.info(f"Заказ сохранён: {lunch_name}, цена: {price}, дата: {selected_date}, телефон: {phone}")
            await update.message.reply_text(f"Ваш выбор ({lunch_name}) записан! Цена: {price} рублей.")
        except Exception as e:
            logger.error(f"Ошибка записи в файл: {e}")
            await update.message.reply_text(f"Ошибка записи в файл: {e}")
    except Exception as e:
        logger.error(f"Ошибка при обработке комплексного обеда: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def handle_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        selected_date = context.user_data.get("selected_date")
        phone_number = context.user_data.get("phone_number")

        if not selected_date or not phone_number:
            await update.message.reply_text("Ошибка: не удалось найти данные о заказе.")
            return

        try:
            orders_df = pd.read_excel(ORDERS)
        except FileNotFoundError:
            await update.message.reply_text("Файл с заказами не найден.")
            return

        phone_number_clean = ''.join(filter(str.isdigit, phone_number))
        orders_df['Номер телефона'] = orders_df['Номер телефона'].astype(str).str.replace('[^0-9]', '', regex=True)

        user_orders = orders_df[
            (orders_df['Номер телефона'] == phone_number_clean) &
            (orders_df['Дата'] == selected_date)
        ]

        if user_orders.empty:
            await update.message.reply_text("Нет заказов для оплаты.")
            return

        # Обновляем статус оплаты
        orders_df.loc[
            (orders_df['Номер телефона'] == phone_number_clean) & 
            (orders_df['Дата'] == selected_date),
            'Статус оплаты'
        ] = 'Оплачено'
        orders_df.to_excel(ORDERS, index=False)

        message_text = "Ваши заказы успешно оплачены!\n\n"

        # Кнопка "Следующий заказ"
        keyboard = [
            [InlineKeyboardButton("Сделать следующий заказ", callback_data=" ")],
            [InlineKeyboardButton("Вернуться в главное меню", callback_data=" ")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message_text, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Ошибка при обработке оплаты: {e}")
        await update.message.reply_text("Произошла ошибка при оплате. Пожалуйста, попробуйте снова.")

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        phone_number = context.user_data.get("phone_number")
        if not phone_number:
            await update.message.reply_text("Ваш номер телефона не зарегистрирован. Перезапустите бота.")
            return

        try:
            orders_df = pd.read_excel(ORDERS)
        except FileNotFoundError:
            await update.message.reply_text("Заказов пока нет.")
            return

        phone_number_clean = ''.join(filter(str.isdigit, phone_number))
        orders_df['Номер телефона'] = orders_df['Номер телефона'].astype(str).str.replace('[^0-9]', '', regex=True)

        user_orders = orders_df[
            (orders_df['Номер телефона'] == phone_number_clean)
        ]

        if user_orders.empty:
            await update.message.reply_text("У вас пока нет заказов.")
            return

        # Группируем заказы по дате
        orders_by_date = user_orders.groupby('Дата')

        cart_message = "Ваши заказы:\n\n"
        for date, orders in orders_by_date:
            cart_message += f"📅 *Заказы на {date}:*\n"
            total_price = 0
            for index, row in orders.iterrows():
                cart_message += f"• {row['Обед']} - {row['Цена']} рублей\n"
                total_price += row['Цена']
            cart_message += f"*Итого к оплате: {total_price} рублей.*\n\n"

        keyboard = [
            [InlineKeyboardButton("Оплатить", callback_data="pay_now")],
            [InlineKeyboardButton("Сделать следующий заказ", callback_data="next_order")],
            [InlineKeyboardButton("Вернуться в главное меню", callback_data="main_menu")]
        ]
        

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(cart_message, reply_markup=reply_markup, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка при отображении корзины: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def import_chat_ids(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        
        if context.user_data.get("role") != "Администратор":
            await update.message.reply_text("У вас нет прав для использования этой функции.")
            return
        user_data = load_user_data()
        chat_ids_message = "Список chat_id пользователей:\n\n"
        for user in user_data["users"]:
            chat_ids_message += f"Имя: {user['name']}, chat_id: {user.get('chat_id', 'не указан')}\n"

        await update.message.reply_text(chat_ids_message)
    except Exception as e:
        logger.error(f"Ошибка при импорте chat_id: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def show_all_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if context.user_data.get("role") != "Администратор":
            await update.message.reply_text("У вас нет прав для использования этой функции.")
            return
        try:
            orders_df = pd.read_excel(ORDERS)
        except FileNotFoundError:
            await update.message.reply_text("Файл с заказами не найден.")
            return

        if orders_df.empty:
            await update.message.reply_text("Заказов пока нет.")
            return

        orders_text = "Список всех заказов:\n\n"
        for index, row in orders_df.iterrows():
            orders_text += (
                f"Номер телефона: {row['Номер телефона']}\n"
                f"Дата: {row['Дата']}\n"
                f"Обед: {row['Обед']}\n"
                f"Цена: {row['Цена']} рублей\n"
                f"Статус оплаты: {row['Статус оплаты']}\n\n"
            )

        await update.message.reply_text(orders_text)
    except Exception as e:
        logger.error(f"Ошибка при отображении всех заказов: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

def main():
    try:
        application = Application.builder().token(TOKEN).build()

        registration_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.CONTACT, start)],
            states={
                CHOOSE_ADDRESS: [CallbackQueryHandler(choose_address)],
                ENTER_NAME: [MessageHandler(filters.TEXT, enter_name)],
            },
            fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        )

        broadcast_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^Сообщить всем$"), broadcast_start)],
            states={
                BROADCAST_MESSAGE: [MessageHandler(filters.TEXT, broadcast_message)],
            },
            fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        )

        address_handler = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex("^Добавить адрес доставки$"), add_address_start)],
            states={
                ADD_ADDRESS: [MessageHandler(filters.TEXT, add_address)],
            },
            fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        )

        application.add_handler(CommandHandler("start", start))
        application.add_handler(registration_handler)
        application.add_handler(broadcast_handler)
        application.add_handler(address_handler)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))  
        application.add_handler(CallbackQueryHandler(handle_menu_and_lunch))
        application.add_handler(CallbackQueryHandler(handle_callback_query))

        application.run_polling()
    except Exception as e:
        logger.error(f"Ошибка в main: {e}")

if __name__ == "__main__":
    main()

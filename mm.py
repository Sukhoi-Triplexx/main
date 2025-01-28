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
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
DATA_FILE = "Data.json"
ORDERS = "Заказы.xlsx"
MENU = "https://docs.google.com/spreadsheets/d/1VsiuMFOGDAz86qcXmBSc2mq5hXJXnqNPJIM09HooV2A/export?format=csv"
ADDRESSES_FILE = "Addresses.json" 
TOKEN = "7814928433:AAGERulnnNOIvqbKp6IcQ-0yytP0szoSp9A"

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
        logger.info("Функция show_menu вызвана")  
        today = datetime.now()
        days = [today + timedelta(days=i) for i in range(7)]
        days_of_week = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        keyboard = [
            [InlineKeyboardButton(f"{day.strftime('%d-%m-%Y')} ({days_of_week[day.weekday()]})", callback_data=day.strftime('%d-%m-%Y'))]
            for day in days
        ]

        logger.info(f"Клавиатура с датами: {keyboard}")  
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Выберите день недели:", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in show_menu: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def handle_menu_and_lunch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(update, Update) and update.callback_query:
        query = update.callback_query
        selected_date_str = query.data
        selected_date_full = datetime.strptime(selected_date_str, '%d-%m-%Y')
        days_of_week = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        day_index = selected_date_full.weekday()

        await query.answer()
        await query.edit_message_text(f"Вы выбрали дату: {selected_date_str} ({days_of_week[day_index]})")
        context.user_data["selected_date"] = selected_date_str

        try:
            menu_data = pd.read_csv(MENU)
            menu_data['Цена'] = menu_data['Цена'].astype(str) + ' рублей'
            daily_menu = menu_data.groupby('Название')['Блюдо'].apply(list).reset_index()
            daily_menu['Цена'] = menu_data.groupby('Название')['Цена'].first().values

            if daily_menu.empty:
                await query.message.reply_text("К сожалению, на эту дату нет меню.")
                return

            menu_text = f"Меню на {selected_date_str} ({days_of_week[day_index]})\n\n"
            for index, row in daily_menu.iterrows():
                menu_text += f"*{row['Название']}* - {row['Цена']}\n"
                for i, dish in enumerate(row['Блюдо']):
                    menu_text += f"{i+1}. {dish}\n"
                menu_text += "\n"

            await query.message.reply_text(menu_text)

            keyboard = [
                [KeyboardButton("Комплексный обед №1")],
                [KeyboardButton("Комплексный обед №2")],
                [KeyboardButton("Комплексный обед №3")],
                [KeyboardButton("Комплексный обед №4")]
            ]
            keyboard.append([KeyboardButton("Корзина")])
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await query.message.reply_text("Выберите обед:", reply_markup=reply_markup)

        except Exception as e:
            logging.exception(f"Error loading menu: {e}")
            await query.message.reply_text(f"Ошибка при загрузке меню: {e}")
            return

    elif isinstance(update, Update) and update.message and update.message.text:
        message = update.message.text
        phone = context.user_data.get("phone_number")
        if phone is None:
            await update.message.reply_text("Ваш номер телефона не зарегестрирован, перезапустите бота!")
            return

        selected_date = context.user_data.get("selected_date")

        if selected_date is None:
            await update.message.reply_text("Выберите дату, прежде чем заказывать обед.")
            return

        try:
            menu_data = pd.read_csv(MENU)
            lunch_prices = dict(zip(menu_data['Название'], menu_data['Цена']))

            price = lunch_prices.get(message)

            if price is None:
                await update.message.reply_text(f"Цена для {message} не найдена в меню.")
                return

            try:
                orders_df = pd.read_excel(ORDERS)
            except FileNotFoundError:
                orders_df = pd.DataFrame(columns=['Номер телефона', 'Дата', 'Обед', 'Цена', 'Статус оплаты'])

            phone = context.user_data.get("phone_number")
            new_order = pd.DataFrame({'Номер телефона': [phone], 'Дата': [selected_date], 'Обед': [message], 'Цена': [price], 'Статус оплаты': ['Не оплачено']})
            orders_df = pd.concat([orders_df, new_order], ignore_index=True)
            orders_df.to_excel(ORDERS, index=False)

            await update.message.reply_text(f"Ваш выбор ({message}) записан! Цена: {price} рублей.")
        except Exception as e:
            await update.message.reply_text(f"Ошибка записи в файл: {e}")

async def show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        orders_df = pd.read_excel(ORDERS)
        if orders_df.empty:
            await update.message.reply_text("Заказов пока нет.")
            return
        
        orders_text = "Список ваших заказов:\n\n"
        for index, row in orders_df.iterrows():
            orders_text += f"Дата заказа: {row['Дата']}, Обед: {row['Обед']}\n"
        await update.message.reply_text(orders_text)

    except FileNotFoundError:
        await update.message.reply_text("Файл с заказами не найден.")
    except Exception as e:
        logging.exception(f"Error reading orders file: {e}")
        await update.message.reply_text(f"Ошибка чтения файла заказов: {e}")
        
async def show_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if context.user_data.get("role") == "Администратор":
            await update.message.reply_text("У вас нет доступа к этой функции.")
            return

        orders_df = pd.read_excel(ORDERS)
        if orders_df.empty:
            await update.message.reply_text("Заказов пока нет.")
            return
        
        orders_text = "Список ваших заказов:\n\n"
        for index, row in orders_df.iterrows():
            orders_text += f"Дата заказа: {row['Дата']}, Обед: {row['Обед']}\n"
        await update.message.reply_text(orders_text)
    except FileNotFoundError:
        await update.message.reply_text("Файл с заказами не найден.")
    except Exception as e:
        logger.error(f"Error reading orders file: {e}")
        await update.message.reply_text(f"Ошибка чтения файла заказов: {e}")

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

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE, button_text: str):
    try:
        logger.info(f"Нажата кнопка: {button_text}")

        if button_text == "Сделать заказ":
            await show_menu(update, context)
        elif button_text == "Мои заказы":
            await show_orders(update, context)
        elif button_text == "Корзина":
            await show_cart(update, context)
        elif button_text == "Комплексный обед №1":
            await handle_complex_lunch(update, context, "Комплексный обед №1")
        elif button_text == "Комплексный обед №2":
            await handle_complex_lunch(update, context, "Комплексный обед №2")
        elif button_text == "Комплексный обед №3":
            await handle_complex_lunch(update, context, "Комплексный обед №3")
        elif button_text == "Комплексный обед №4":
            await handle_complex_lunch(update, context, "Комплексный обед №4")
        elif button_text == "Список заказов":  
            await show_all_orders(update, context)
        elif button_text == "Сообщить всем":  
            await broadcast_start(update, context)
        elif button_text == "Добавить адрес доставки": 
            await add_address_start(update, context)
        elif button_text == "Импорт chat_id":  
            await import_chat_ids(update, context)
        else:
            await update.message.reply_text("Неизвестная команда. Пожалуйста, выберите действие из меню.")
    except Exception as e:
        logger.error(f"Ошибка при обработке кнопки: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        await handle_button_click(update, context, text)
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

async def handle_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()

        selected_date = query.data.replace("pay_", "")
        phone_number = context.user_data.get("phone_number")

        try:
            orders_df = pd.read_excel(ORDERS)
        except FileNotFoundError:
            await query.edit_message_text("Заказов пока нет.")
            return

        user_orders = orders_df[
            (orders_df['Номер телефона'] == phone_number) & 
            (orders_df['Дата'] == selected_date)
        ]

        if user_orders.empty:
            await query.edit_message_text(f"На {selected_date} у вас нет заказов.")
            return

        orders_df.loc[
            (orders_df['Номер телефона'] == phone_number) & 
            (orders_df['Дата'] == selected_date),
            'Статус оплаты'
        ] = 'Оплачено'
        orders_df.to_excel(ORDERS, index=False)

        await query.edit_message_text(f"Заказы на {selected_date} успешно оплачены!")
    except Exception as e:
        logger.error(f"Ошибка при обработке оплаты: {e}")
        await query.edit_message_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Получаем номер телефона из context.user_data
        phone_number = context.user_data.get("phone_number")
        if not phone_number:
            await update.message.reply_text("Ваш номер телефона не зарегистрирован. Перезапустите бота.")
            return

        # Получаем выбранную дату из context.user_data
        selected_date = context.user_data.get("selected_date")
        if not selected_date:
            await update.message.reply_text("Выберите день, чтобы увидеть заказы.")
            return

        try:
            # Чтение файла с заказами
            orders_df = pd.read_excel(ORDERS)
        except FileNotFoundError:
            await update.message.reply_text("Заказов пока нет.")
            return

        # Преобразуем selected_date в datetime для корректного сравнения
        selected_date_dt = pd.to_datetime(selected_date, format='%d-%m-%Y')

        # Преобразуем столбец 'Дата' в формат datetime, если он еще не в этом формате
        if not pd.api.types.is_datetime64_any_dtype(orders_df['Дата']):
            orders_df['Дата'] = pd.to_datetime(orders_df['Дата'], format='%d-%m-%Y')

        # Приводим номер телефона в файле к строке и удаляем лишние символы (например, запятые)
        orders_df['Номер телефона'] = orders_df['Номер телефона'].astype(str).str.replace('[^0-9]', '', regex=True)

        # Приводим номер телефона из context.user_data к тому же формату
        phone_number_clean = ''.join(filter(str.isdigit, phone_number))

        # Фильтруем заказы по номеру телефона и дате
        user_orders = orders_df[
            (orders_df['Номер телефона'] == phone_number_clean) &
            (orders_df['Дата'] == selected_date_dt)
        ]

        if user_orders.empty:
            await update.message.reply_text(f"На {selected_date} у вас нет заказов.")
            return

        # Формируем сообщение с заказами
        cart_message = f"Ваши заказы на {selected_date}:\n\n"
        total_price = 0

        for index, row in user_orders.iterrows():
            cart_message += f"• {row['Обед']} - {row['Цена']} рублей\n"
            total_price += row['Цена']

        cart_message += f"\nИтого к оплате: {total_price} рублей."

        # Создаем кнопку для оплаты
        keyboard = [
            [InlineKeyboardButton("Оплатить", callback_data=f"pay_{selected_date}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправляем сообщение с заказами
        await update.message.reply_text(cart_message, reply_markup=reply_markup)
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

        # Обработчики для администратора
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
        application.add_handler(MessageHandler(filters.Regex("^Мои заказы$"), handle_text))
        application.add_handler(CallbackQueryHandler(handle_menu_and_lunch))
        application.add_handler(broadcast_handler)
        application.add_handler(address_handler)
        application.add_handler(CommandHandler("menu", menu))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        application.add_handler(MessageHandler(filters.Regex("^Сделать заказ$"), handle_text))

        application.run_polling()
    except Exception as e:
        logger.error(f"Ошибка в main: {e}")

if __name__ == "__main__":
    main()

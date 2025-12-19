import asyncio
import random
import aiosqlite
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# ================== НАСТРОЙКИ ==================
TOKEN = "8559287207:AAEtEgXw4YxhDZnHy4J9cf5QZE9-TelIAxQ"
DB_PATH = "deathnote.db"

MAX_DAILY_WRITES = 10
BASE_SUCCESS_CHANCE = 0.8

# ================== ИНИЦИАЛИЗАЦИЯ ==================
bot = Bot(TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================== ДАННЫЕ ==================
SHINIGAMI = {
    "Рюк 🍎": "🔹 Увеличивает шанс успешной записи +5%",
    "Рем 🕊️": "🔹 Защищает один раз от L",
    "Сидо 👁️": "🔹 Даёт +5 очков при успешной записи"
}

RULES = [
    ("🔒 Скрытая страница", "safe", "Сегодня все записи защищены, потери минимальны."),
    ("📜 Двойные очки", "double_points", "Все успешные записи приносят вдвое больше очков!"),
    ("👁️ Взгляд L", "danger", "L наблюдает, шанс провала выше."),
    ("💀 Чёрная страница", "double_loss", "Все неудачные записи отнимают вдвое больше очков!")
]

STREAK_REWARDS = {
    7: 50,
    14: 120,
    30: 300
}

# ================== FSM ==================
class WriteState(StatesGroup):
    waiting_name = State()

# ================== БАЗА ==================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            shinigami TEXT,
            points INTEGER,
            daily_writes INTEGER,
            last_day TEXT,
            streak INTEGER,
            protected INTEGER
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            date TEXT
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS daily_rule (
            date TEXT PRIMARY KEY,
            name TEXT,
            effect TEXT,
            description TEXT
        )""")
        await db.commit()

# ================== ПОЛЬЗОВАТЕЛЬ ==================
async def get_user(uid, username):
    today = datetime.utcnow().date()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (uid,))
        u = await cur.fetchone()

        if not u:
            sh = random.choice(list(SHINIGAMI.keys()))
            await db.execute(
                "INSERT INTO users VALUES (?, ?, ?, 0, 0, ?, 0, 1)",
                (uid, username, sh, today.isoformat())
            )
            await db.commit()
            return await get_user(uid, username)

        last = datetime.fromisoformat(u[5]).date()
        streak = u[6]

        if last < today - timedelta(days=1):
            streak = 0

        if last != today:
            await db.execute(
                "UPDATE users SET daily_writes=0, last_day=?, streak=? WHERE user_id=?",
                (today.isoformat(), streak, uid)
            )
            await db.commit()

        return {
            "id": u[0],
            "username": u[1],
            "shinigami": u[2],
            "points": u[3],
            "daily": u[4],
            "streak": streak,
            "protected": u[7]
        }

# ================== ПРАВИЛО ДНЯ ==================
async def get_rule():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT name, effect, description FROM daily_rule WHERE date=?", (today,))
        r = await cur.fetchone()
        if r:
            return r
        rule = random.choice(RULES)
        await db.execute(
            "INSERT INTO daily_rule VALUES (?, ?, ?, ?)",
            (today, rule[0], rule[1], rule[2])
        )
        await db.commit()
        return rule

# ================== КОМАНДЫ ==================
@dp.message(Command("start"))
async def start(m: types.Message):
    u = await get_user(m.from_user.id, m.from_user.username)
    await m.answer(
        "📓 *Тетрадь смерти*\n\n"
        "✍️ /write — записать имя\n"
        "📖 /note — тетрадь\n"
        "👤 /profile — профиль\n"
        "🔥 /streak — серия\n"
        "🏆 /top — топ по очкам\n"
        "📜 /rules — правило дня",
        parse_mode="Markdown"
    )

@dp.message(Command("profile"))
async def profile(m: types.Message):
    u = await get_user(m.from_user.id, m.from_user.username)
    await m.answer(
        f"👤 *Профиль*\n\n"
        f"✨ Шинигами: {u['shinigami']} — {SHINIGAMI[u['shinigami']]}\n"
        f"💎 Очки: {u['points']}\n"
        f"📝 Сегодня: {u['daily']}/{MAX_DAILY_WRITES}\n"
        f"🔥 Стрик: {u['streak']} дней",
        parse_mode="Markdown"
    )

@dp.message(Command("streak"))
async def streak(m: types.Message):
    u = await get_user(m.from_user.id, m.from_user.username)
    text = f"🔥 *Твой стрик*: {u['streak']} дней\n\n"
    for d, r in STREAK_REWARDS.items():
        text += f"{'✅' if u['streak'] >= d else '❌'} {d} дней — {r} 💎\n"
    await m.answer(text, parse_mode="Markdown")

@dp.message(Command("rules"))
async def rules(m: types.Message):
    name, effect, desc = await get_rule()
    await m.answer(f"📜 *Правило дня*\n\n{name}\n\n💡 {desc}", parse_mode="Markdown")

@dp.message(Command("top"))
async def top(m: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
        rows = await cur.fetchall()

    if not rows:
        await m.answer("🏆 Топ пуст.")
        return

    text = "🏆 *Топ по очкам*\n\n"
    for i, (u, p) in enumerate(rows, 1):
        text += f"{i}️⃣ @{u or 'без_ника'} — {p} 💎\n"
    await m.answer(text, parse_mode="Markdown")

# ================== WRITE ==================
@dp.message(Command("write"))
async def write(m: types.Message, state: FSMContext):
    u = await get_user(m.from_user.id, m.from_user.username)
    if u["daily"] >= MAX_DAILY_WRITES:
        await m.answer("⛔ Лимит на сегодня исчерпан.")
        return
    await m.answer("✍️ Введи имя:")
    await state.set_state(WriteState.waiting_name)

@dp.message(WriteState.waiting_name)
async def save(m: types.Message, state: FSMContext):
    name = m.text.strip()
    u = await get_user(m.from_user.id, m.from_user.username)
    rule_name, rule, _ = await get_rule()

    chance = BASE_SUCCESS_CHANCE
    if rule == "danger":
        chance -= 0.2
    if u["shinigami"] == "Рюк 🍎":
        chance += 0.05

    success = random.random() < chance
    today = datetime.utcnow().strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_PATH) as db:
        if success:
            gain = random.randint(8, 15)
            if rule == "double_points":
                gain *= 2
            if u["shinigami"] == "Сидо 👁️":
                gain += 5

            await db.execute(
                "UPDATE users SET points=points+?, daily_writes=daily_writes+1 WHERE user_id=?",
                (gain, u["id"])
            )
            msg = f"✅ Имя *{name}* записано\n💎 +{gain}"
        else:
            if u["protected"]:
                await db.execute(
                    "UPDATE users SET protected=0, daily_writes=daily_writes+1 WHERE user_id=?",
                    (u["id"],)
                )
                msg = "🕊️ Рем защитила тебя. L ничего не заметил."
            else:
                loss = random.randint(5, 15)
                if rule == "double_loss":
                    loss *= 2
                await db.execute(
                    "UPDATE users SET points=points-?, daily_writes=daily_writes+1, streak=0 WHERE user_id=?",
                    (loss, u["id"])
                )
                msg = f"👁️ L заметил тебя\n💀 -{loss}"

        await db.execute(
            "INSERT INTO notes(user_id, name, date) VALUES (?, ?, ?)",
            (u["id"], name, today)
        )
        await db.commit()

    await m.answer(msg, parse_mode="Markdown")
    await state.clear()

@dp.message(Command("note"))
async def note(m: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT name, date FROM notes WHERE user_id=?", (m.from_user.id,))
        rows = await cur.fetchall()

    if not rows:
        await m.answer("📖 Тетрадь пуста.")
        return

    text = "📖 *Твоя тетрадь*\n\n"
    for n, d in rows:
        text += f"{d} — {n}\n"

    await m.answer(text, parse_mode="Markdown")

# ================== ЗАПУСК ==================
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

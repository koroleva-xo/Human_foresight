# -*- coding: utf-8 -*-
import asyncio
import logging
import os
 
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
 
from dotenv import load_dotenv
 
import data
 
load_dotenv()
 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
 
TELEGRAM_MAX_LEN = 4096
DIVIDER = "──────────"
 
DIM_EMOJI = {"PDI": "🏛", "UAI": "🌀", "IDV": "👤"}
 
TEST_TITLES = {
    "tuckman_main": "Такман, базовый (6 сценариев)",
    "tuckman_ext": "Такман, расширенный (14 сценариев)",
    "hofstede_main": "Хофстеде, базовый (9 сценариев)",
    "hofstede_ext": "Хофстеде, расширенный (24 сценария)",
}
 
router = Router()
 
 
class TestStates(StatesGroup):
    answering = State()
 
 
def main_menu_kb() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=title, callback_data=f"start:{key}")]
        for key, title in TEST_TITLES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
 
 
def options_kb(letters) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text=letter, callback_data=f"ans:{letter}") for letter in letters]
    cancel_row = [InlineKeyboardButton(text="❌ Прервать тест", callback_data="cancel_test")]
    return InlineKeyboardMarkup(inline_keyboard=[row, cancel_row])
 
 
def get_flat_scenarios(test_key: str):
    """Такман -> список сценариев. Хофстеде -> список (измерение, сценарий)."""
    if test_key == "tuckman_main":
        return data.TUCKMAN_MAIN_SCENARIOS
    if test_key == "tuckman_ext":
        return data.TUCKMAN_EXTENDED_SCENARIOS
    if test_key == "hofstede_main":
        flat = []
        for dim in ("PDI", "UAI", "IDV"):
            for sc in data.HOFSTEDE_MAIN_SCENARIOS[dim]:
                flat.append((dim, sc))
        return flat
    if test_key == "hofstede_ext":
        flat = []
        for dim in ("PDI", "UAI", "IDV"):
            for sc in data.HOFSTEDE_EXTENDED_SCENARIOS[dim]:
                flat.append((dim, sc))
        return flat
    raise ValueError(f"Неизвестный тест: {test_key}")
 
 
def _scenario_fields(test_key: str, scenario):
    if test_key.startswith("tuckman"):
        return scenario["text"], scenario["options"]
    _, sc = scenario
    return sc["text"], sc["options"]
 
 
def format_scenario_text(idx: int, total: int, test_key: str, scenario) -> str:
    text, options = _scenario_fields(test_key, scenario)
    lines = [f"<b>Сценарий {idx + 1} из {total}</b>", "", text, ""]
    for letter, opt_text in options.items():
        lines.append(f"<b>{letter})</b> {opt_text}")
    return "\n".join(lines)
 
 
def option_letters(test_key: str, scenario) -> list:
    _, options = _scenario_fields(test_key, scenario)
    return list(options.keys())
 
 
async def send_long(message: Message, text: str):
    while text:
        if len(text) <= TELEGRAM_MAX_LEN:
            await message.answer(text)
            break
        cut = text.rfind("\n\n", 0, TELEGRAM_MAX_LEN)
        if cut <= 0:
            cut = TELEGRAM_MAX_LEN
        await message.answer(text[:cut])
        text = text[cut:].lstrip("\n")
 
 
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "<b>Диагностика Human Foresight</b>\n\n"
        "Четыре теста: два по стадиям развития команды (Такман), два по культурному "
        "профилю команды (Хофстеде: дистанция власти, избегание неопределённости, "
        "индивидуализм/коллективизм).\n\n⚠️ " + data.DISCLAIMER
    )
    await message.answer("Выбери тест:", reply_markup=main_menu_kb())
 
 
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Прервано. Выбери тест:", reply_markup=main_menu_kb())
 
 
@router.callback_query(F.data.startswith("start:"))
async def on_start_test(callback: CallbackQuery, state: FSMContext):
    test_key = callback.data.split(":", 1)[1]
    await state.set_state(TestStates.answering)
    await state.update_data(test=test_key, index=0, answers=[])
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await ask_scenario(callback.message, state)
    await callback.answer()
 
 
async def ask_scenario(message: Message, state: FSMContext):
    fsm_data = await state.get_data()
    test_key = fsm_data["test"]
    idx = fsm_data["index"]
    scenarios = get_flat_scenarios(test_key)
    scenario = scenarios[idx]
    text = format_scenario_text(idx, len(scenarios), test_key, scenario)
    letters = option_letters(test_key, scenario)
    await message.answer(text, reply_markup=options_kb(letters))
 
 
@router.callback_query(TestStates.answering, F.data == "cancel_test")
async def on_cancel_test(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("Тест прерван. Выбери другой:", reply_markup=main_menu_kb())
    await callback.answer()
 
 
@router.callback_query(TestStates.answering, F.data.startswith("ans:"))
async def on_answer(callback: CallbackQuery, state: FSMContext):
    letter = callback.data.split(":", 1)[1]
    fsm_data = await state.get_data()
    test_key = fsm_data["test"]
    idx = fsm_data["index"]
    answers = fsm_data["answers"]
    answers.append(letter)
 
    scenarios = get_flat_scenarios(test_key)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
 
    if idx + 1 >= len(scenarios):
        await state.update_data(answers=answers)
        await finish_test(callback.message, state)
        await state.clear()
    else:
        await state.update_data(index=idx + 1, answers=answers)
        await ask_scenario(callback.message, state)
    await callback.answer()
 
 
def score_tuckman(test_key: str, answers) -> dict:
    scenarios = get_flat_scenarios(test_key)
    counts = {"F": 0, "St": 0, "N": 0, "P": 0}
    for ans, scenario in zip(answers, scenarios):
        stage = scenario["key"][ans]
        counts[stage] += 1
    return counts
 
 
def score_hofstede(test_key: str, answers) -> dict:
    scenarios = get_flat_scenarios(test_key)
    sums = {"PDI": 0, "UAI": 0, "IDV": 0}
    n_per_dim = {"PDI": 0, "UAI": 0, "IDV": 0}
    for ans, (dim, sc) in zip(answers, scenarios):
        sums[dim] += sc["key"][ans]
        n_per_dim[dim] += 1
 
    results = {}
    for dim in ("PDI", "UAI", "IDV"):
        n = n_per_dim[dim]
        raw_sum = sums[dim]
        score = (raw_sum - n) / (2 * n) * 100
        if score <= 40:
            zone = "low"
        elif score <= 70:
            zone = "mid"
        else:
            zone = "high"
        results[dim] = {"score": round(score), "zone": zone}
    return results
 
 
def tuckman_report(counts: dict) -> str:
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    dominant, dom_n = ranked[0]
    secondary, sec_n = ranked[1]
 
    lines = ["<b>📊 Результат</b>", ""]
    for stage, n in ranked:
        lines.append(f"• {data.TUCKMAN_STAGE_NAMES[stage]}: {n}")
    lines.append("")
    lines.append(DIVIDER)
    lines.append("")
 
    if dom_n == sec_n:
        lines.append(
            "⚖️ <b>Две стадии набрали одинаковое количество.</b> Это переходное состояние "
            "системы, не ошибка измерения. Ниже интерпретация обеих."
        )
        lines.append("")
        for stage in (dominant, secondary):
            lines.append(f"<b>{data.TUCKMAN_STAGE_NAMES[stage]} доминирует</b>")
            lines.append(data.TUCKMAN_STAGE_TEXT[stage])
            lines.append("")
    else:
        lines.append(
            f"Команда преимущественно на <b>{data.TUCKMAN_STAGE_NAMES[dominant]}</b> "
            f"с признаками <b>{data.TUCKMAN_STAGE_NAMES[secondary]}</b>."
        )
        lines.append("")
        lines.append(f"<b>{data.TUCKMAN_STAGE_NAMES[dominant]} доминирует</b>")
        lines.append(data.TUCKMAN_STAGE_TEXT[dominant])
        combo = data.TUCKMAN_COMBO_TEXT.get((dominant, secondary))
        if combo:
            lines.append("")
            lines.append(
                f"<b>{data.TUCKMAN_STAGE_NAMES[dominant]} + {data.TUCKMAN_STAGE_NAMES[secondary]}</b>"
            )
            lines.append(combo)
 
    return "\n".join(lines)
 
 
def hofstede_report(results: dict) -> str:
    lines = ["<b>📊 Результат по трём измерениям</b>", ""]
    for dim in ("PDI", "UAI", "IDV"):
        r = results[dim]
        label = data.HOFSTEDE_ZONE_LABELS[dim][r["zone"]]
        lines.append(f"{DIM_EMOJI[dim]} <b>{data.HOFSTEDE_DIM_NAMES[dim]}</b>: {r['score']} ({label})")
    lines.append("")
    lines.append(
        "Эти три числа не складываются в единый балл. Читайте их как комбинацию, не как сумму."
    )
    lines.append("")
    lines.append(DIVIDER)
    lines.append("")
    for dim in ("PDI", "UAI", "IDV"):
        r = results[dim]
        lines.append(f"{DIM_EMOJI[dim]} <b>{data.HOFSTEDE_DIM_NAMES[dim]}</b>")
        lines.append(data.HOFSTEDE_ZONE_TEXT[dim][r["zone"]])
        lines.append("")
    return "\n".join(lines).rstrip()
 
 
async def finish_test(message: Message, state: FSMContext):
    fsm_data = await state.get_data()
    test_key = fsm_data["test"]
    answers = fsm_data["answers"]
 
    if test_key.startswith("tuckman"):
        counts = score_tuckman(test_key, answers)
        report = tuckman_report(counts)
    else:
        results = score_hofstede(test_key, answers)
        report = hofstede_report(results)
 
    await send_long(message, report)
    await message.answer("Пройти ещё тест?", reply_markup=main_menu_kb())
 
 
async def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("Не задан BOT_TOKEN (переменная окружения). См. .env")
 
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
 
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен, начинаю polling")
    await dp.start_polling(bot)
 
 
if __name__ == "__main__":
    asyncio.run(main())

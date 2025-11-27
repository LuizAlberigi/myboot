#!/usr/bin/env python3
"""
Cassino Virtual com MINES interativo (5x5) usando InlineKeyboard (callback_query).
Dependência: python-telegram-bot==20.7
"""

import json
import random
import math
from datetime import date
from typing import Dict, Any, List, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# -----------------------------
# CONFIG
# -----------------------------
BOT_TOKEN = "8535442521:AAFLX5mnmdCYAGxnS9RW6jhIX0dLzzVzac4"
DB_FILE = "casino_db.json"
BOARD_SIZE = 5  # 5x5
TOTAL_CELLS = BOARD_SIZE * BOARD_SIZE

# -----------------------------
# DB simples em JSON
# -----------------------------
def load_db() -> Dict[str, Any]:
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": {}, "games": {}}

def save_db(db: Dict[str, Any]):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

db = load_db()

def get_user_obj(user_id: int) -> Dict[str, Any]:
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {"coins": 1000, "last_bonus": ""}
        save_db(db)
    return db["users"][uid]

def get_balance(user_id: int) -> int:
    return int(get_user_obj(user_id)["coins"])

def set_balance(user_id: int, amount: int):
    obj = get_user_obj(user_id)
    obj["coins"] = int(amount)
    save_db(db)

def change_balance(user_id: int, delta: int):
    obj = get_user_obj(user_id)
    obj["coins"] = int(obj.get("coins", 0)) + int(delta)
    save_db(db)

# Game helpers
def save_game(user_id: int, game: Dict[str, Any]):
    db.setdefault("games", {})
    db["games"][str(user_id)] = game
    save_db(db)

def load_game(user_id: int) -> Optional[Dict[str, Any]]:
    return db.get("games", {}).get(str(user_id))

def remove_game(user_id: int):
    if "games" in db and str(user_id) in db["games"]:
        del db["games"][str(user_id)]
        save_db(db)

# -----------------------------
# Utils
# -----------------------------
def safe_int(x: str) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None

def compute_mines_multiplier(mines: int, safe_picks: int) -> float:
    """Multiplicador simples e crescente (não exato real-market)."""
    safe_total = TOTAL_CELLS - mines
    denom = safe_total - safe_picks
    if denom <= 0:
        return float("inf")
    multiplier = (safe_total) / denom
    return float(multiplier)

def build_board_buttons(opened: List[int], mines_revealed: Optional[List[int]] = None, owner_id: Optional[int] = None):
    """
    Retorna InlineKeyboardMarkup representando tabuleiro.
    opened: lista de posições abertas (1..TOTAL_CELLS)
    mines_revealed: lista de minas para mostrar (quando perdeu)
    owner_id: para incluir no callback data
    """
    kb = []
    for r in range(BOARD_SIZE):
        row = []
        for c in range(BOARD_SIZE):
            pos = r * BOARD_SIZE + c + 1
            label = f"{pos:02d}"
            if mines_revealed and pos in mines_revealed:
                label = "💣"
                # disable by setting callback to noop
                cb = f"noop"
            elif pos in opened:
                label = "✅"
                cb = "noop"
            else:
                label = f"{pos:02d}"
                cb = f"mines:{owner_id}:{pos}"
            row.append(InlineKeyboardButton(label, callback_data=cb))
        kb.append(row)
    # Add cashout button
    kb.append([InlineKeyboardButton("💸 SACAR", callback_data=f"cashout:{owner_id}")])
    return InlineKeyboardMarkup(kb)

# -----------------------------
# Commands
# -----------------------------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎰 *Cassino Virtual* — Comandos:\n\n"
        "/start - iniciar e receber 1000 moedas iniciais\n"
        "/saldo - ver seu saldo\n"
        "/bonus - bônus diário (+500)\n\n"
        "Jogos:\n"
        "/blackjack <aposta>\n"
        "/roleta <vermelho|preto|verde> <aposta>\n"
        "/crash <aposta>\n\n"
        "Mines (interativo 5x5):\n"
        "/mines <aposta> <minas>  - iniciar jogo (minas entre 1 e 10)\n"
        "Clique nas casas do tabuleiro para abrir. Use SACAR para pegar payout.\n\n"
        "Observação: todas as moedas são fictícias."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    obj = get_user_obj(user.id)
    await update.message.reply_text(
        f"👋 Olá, {user.first_name}! Bem-vindo ao Cassino Virtual.\n"
        f"Você tem *{obj['coins']}* moedas.\nUse /help para ver comandos.",
        parse_mode="Markdown"
    )

async def saldo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bal = get_balance(update.effective_user.id)
    await update.message.reply_text(f"💰 Seu saldo: *{bal}* moedas", parse_mode="Markdown")

async def bonus_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user = get_user_obj(update.effective_user.id)
    today = date.today().isoformat()
    if user.get("last_bonus") == today:
        await update.message.reply_text("⛔ Você já pegou o bônus diário hoje.")
        return
    user["last_bonus"] = today
    user["coins"] = int(user.get("coins", 0)) + 500
    save_db(db)
    await update.message.reply_text("🎁 Bônus diário concedido: +500 moedas!")

# Simple games (blackjack/roleta/crash) - concise implementations
async def blackjack_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Use: /blackjack <aposta>")
        return
    bet = safe_int(context.args[0])
    if bet is None or bet <= 0:
        await update.message.reply_text("Aposta inválida.")
        return
    if bet > get_balance(update.effective_user.id):
        await update.message.reply_text("Saldo insuficiente.")
        return
    player = random.randint(15, 22)
    dealer = random.randint(15, 22)
    text = f"🃏 *Blackjack*\nVocê: {player}\nDealer: {dealer}\n\n"
    if player > 21:
        text += f"❌ Você estourou e perdeu {bet} moedas."
        change_balance(update.effective_user.id, -bet)
    elif dealer > 21 or player > dealer:
        text += f"🏆 Você ganhou {bet} moedas!"
        change_balance(update.effective_user.id, bet)
    elif dealer > player:
        text += f"❌ Você perdeu {bet} moedas."
        change_balance(update.effective_user.id, -bet)
    else:
        text += "🤝 Empate — nada acontece."
    text += f"\n💰 Saldo: {get_balance(update.effective_user.id)}"
    await update.message.reply_text(text, parse_mode="Markdown")

async def roleta_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Use: /roleta <vermelho|preto|verde> <aposta>")
        return
    escolha = context.args[0].lower()
    bet = safe_int(context.args[1])
    if bet is None or bet <= 0:
        await update.message.reply_text("Aposta inválida.")
        return
    if escolha not in ("vermelho", "preto", "verde"):
        await update.message.reply_text("Escolha inválida: vermelho, preto ou verde.")
        return
    if bet > get_balance(update.effective_user.id):
        await update.message.reply_text("Saldo insuficiente.")
        return
    num = random.randint(0, 36)
    cor = "verde" if num == 0 else ("vermelho" if num % 2 == 1 else "preto")
    text = f"🎡 *Roleta*\nNúmero sorteado: {num} ({cor})\n\n"
    if escolha == cor:
        ganho = bet * (14 if cor == "verde" else 2)
        text += f"🏆 Você acertou! Ganhou {ganho} moedas."
        change_balance(update.effective_user.id, ganho)
    else:
        text += f"❌ Você errou e perdeu {bet} moedas."
        change_balance(update.effective_user.id, -bet)
    text += f"\n💰 Saldo: {get_balance(update.effective_user.id)}"
    await update.message.reply_text(text, parse_mode="Markdown")

async def crash_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Use: /crash <aposta>")
        return
    bet = safe_int(context.args[0])
    if bet is None or bet <= 0:
        await update.message.reply_text("Aposta inválida.")
        return
    if bet > get_balance(update.effective_user.id):
        await update.message.reply_text("Saldo insuficiente.")
        return
    mult = round(random.uniform(1.10, 10.0), 2)
    payout = int(math.floor(bet * mult))
    change_balance(update.effective_user.id, payout - bet)
    text = f"🚀 *Crash*\nMultiplicador: x{mult}\nVocê ganhou {payout} moedas!\n💰 Saldo: {get_balance(update.effective_user.id)}"
    await update.message.reply_text(text, parse_mode="Markdown")

# -----------------------------
# MINES interativo
# -----------------------------
async def mines_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /mines <aposta> <minas>
    inicia jogo com aposta e número de minas (1..10)
    """
    if len(context.args) < 2:
        await update.message.reply_text("Use: /mines <aposta> <minas> (minas entre 1 e 10)")
        return
    bet = safe_int(context.args[0])
    mines = safe_int(context.args[1])
    if bet is None or bet <= 0 or mines is None:
        await update.message.reply_text("Argumentos inválidos.")
        return
    if mines < 1 or mines > 10:
        await update.message.reply_text("Número de minas deve ser entre 1 e 10.")
        return
    if bet > get_balance(update.effective_user.id):
        await update.message.reply_text("Saldo insuficiente.")
        return

    # Deduz aposta
    change_balance(update.effective_user.id, -bet)

    # Create mines positions
    mine_positions = sorted(random.sample(range(1, TOTAL_CELLS + 1), mines))
    game = {
        "type": "mines",
        "bet": int(bet),
        "mines": int(mines),
        "mine_positions": mine_positions,
        "opened": [],
        "owner_id": update.effective_user.id,
    }
    save_game(update.effective_user.id, game)

    # Build keyboard and send message
    kb = build_board_buttons(opened=[], mines_revealed=None, owner_id=update.effective_user.id)
    text = (
        f"💣 *Mines* iniciado!\nAposta: {bet} moedas | Minas: {mines}\n\n"
        f"Clique nas casas para abrir. Se encontrar mina, perde. Aperte SACAR para sacar payout atual.\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

async def handle_mines_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    callback_data formats:
      - "mines:<owner_id>:<pos>"
      - "cashout:<owner_id>"
      - "noop"
    """
    query = update.callback_query
    await query.answer()  # acknowledge to remove 'loading'

    data = query.data or ""
    parts = data.split(":")
    if parts[0] == "noop":
        return

    if parts[0] == "mines":
        try:
            owner_id = int(parts[1])
            pos = int(parts[2])
        except Exception:
            await query.edit_message_text("Erro: callback inválido.")
            return

        # Only owner can interact
        if query.from_user.id != owner_id:
            await query.answer("Este jogo não é seu.", show_alert=True)
            return

        game = load_game(owner_id)
        if not game or game.get("type") != "mines":
            await query.edit_message_text("Jogo não encontrado ou já finalizado.")
            return

        # Already opened?
        if pos in game.get("opened", []):
            await query.answer("Posição já aberta.", show_alert=True)
            return

        if pos in game.get("mine_positions", []):
            # Lost: reveal all mines
            mines_revealed = game["mine_positions"]
            board = build_board_buttons(opened=game.get("opened", []), mines_revealed=mines_revealed, owner_id=owner_id)
            # edit message to show explosion and mines
            text = (
                f"💥 *BOOM!* Você abriu a posição {pos} e encontrou uma mina.\n\n"
                f"Minas: {', '.join(map(str, mines_revealed))}\n"
                "Você perdeu a aposta.\n"
            )
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=board)
            # remove game
            remove_game(owner_id)
            return
        else:
            # Safe pick
            opened = game.get("opened", [])
            opened.append(pos)
            game["opened"] = opened
            save_game(owner_id, game)

            safe_picks = len(opened)
            mult = compute_mines_multiplier(game["mines"], safe_picks)
            if math.isinf(mult):
                payout = game["bet"] * 2
            else:
                payout = int(math.floor(game["bet"] * mult))

            kb = build_board_buttons(opened=opened, mines_revealed=None, owner_id=owner_id)
            text = (
                f"✅ Posição {pos} segura!\n"
                f"Casas seguras: {safe_picks}\n"
                f"Multiplicador atual: x{round(mult,2)}\n"
                f"Se sacar agora, receberá: {payout} moedas.\n\n"
                "Abra outra casa ou pressione SACAR para sacar."
            )
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
            return

    elif parts[0] == "cashout":
        try:
            owner_id = int(parts[1])
        except Exception:
            await query.edit_message_text("Erro no cashout.")
            return

        # Only owner can cashout
        if query.from_user.id != owner_id:
            await query.answer("Este jogo não é seu.", show_alert=True)
            return

        game = load_game(owner_id)
        if not game or game.get("type") != "mines":
            await query.edit_message_text("Jogo não encontrado ou já finalizado.")
            return

        bet = int(game["bet"])
        opened = game.get("opened", [])
        safe_picks = len(opened)
        mult = compute_mines_multiplier(game["mines"], safe_picks)
        if math.isinf(mult):
            payout = bet * 2
        else:
            payout = int(math.floor(bet * mult))

        # Pay user
        change_balance(owner_id, payout)
        text = (
            f"💸 Você sacou {payout} moedas! (aposta {bet})\n"
            f"💰 Saldo atual: {get_balance(owner_id)}"
        )
        # Reveal opened board after cashout (do not reveal mines)
        kb = build_board_buttons(opened=opened, mines_revealed=None, owner_id=owner_id)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
        remove_game(owner_id)
        return

# -----------------------------
# Callback for noop or others
# -----------------------------
async def generic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Catch-all; already handled in handle_mines_callback
    await update.callback_query.answer()

# -----------------------------
# MAIN
# -----------------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # basic handlers
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("saldo", saldo_cmd))
    app.add_handler(CommandHandler("bonus", bonus_cmd))
    app.add_handler(CommandHandler("blackjack", blackjack_cmd))
    app.add_handler(CommandHandler("roleta", roleta_cmd))
    app.add_handler(CommandHandler("crash", crash_cmd))
    app.add_handler(CommandHandler("mines", mines_cmd))

    # callback handler for mines and cashout
    app.add_handler(CallbackQueryHandler(handle_mines_callback, pattern=r"^(mines|cashout):"))
    # noop & other callbacks
    app.add_handler(CallbackQueryHandler(generic_callback, pattern="^noop"))

    print("🤖 Cassino bot (com Mines interativo 5x5) rodando...")
    app.run_polling()

if __name__ == "__main__":
    main()

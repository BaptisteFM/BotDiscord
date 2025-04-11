import os
import json
import discord
import asyncio
import time
import datetime
import uuid
import aiofiles
import threading
import random
import logging
from discord.ext import commands, tasks
from discord import app_commands, TextStyle, PartialEmoji
from discord.ui import Modal, TextInput, View, Button
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo

# Configuration du logging
logging.basicConfig(level=logging.INFO)

# --------------------------------------------------
# CONFIGURATION ET PERSÉVÉRANCE
# --------------------------------------------------
os.environ["PORT"] = "10000"
DATA_FOLDER = "/data"
XP_FILE = os.path.join(DATA_FOLDER, "xp.json")
MSG_FILE = os.path.join(DATA_FOLDER, "messages_programmes.json")
DEFIS_FILE = os.path.join(DATA_FOLDER, "defis.json")
AUTO_DM_FILE = os.path.join(DATA_FOLDER, "auto_dm_configs.json")
POMODORO_FILE = os.path.join(DATA_FOLDER, "pomodoro.json")
GOALS_FILE = os.path.join(DATA_FOLDER, "goals.json")
WEEKLY_PLAN_FILE = os.path.join(DATA_FOLDER, "weekly_plan.json")
REMINDERS_FILE = os.path.join(DATA_FOLDER, "reminders.json")
QUIZ_FILE = os.path.join(DATA_FOLDER, "quiz.json")
CITATIONS_FILE = os.path.join(DATA_FOLDER, "citations.json")
LINKS_FILE = os.path.join(DATA_FOLDER, "links.json")

os.makedirs(DATA_FOLDER, exist_ok=True)
file_lock = asyncio.Lock()

async def charger_json_async(path):
    async with file_lock:
        if not os.path.exists(path):
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(json.dumps({}))
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {}

async def sauvegarder_json_async(path, data):
    async with file_lock:
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=4))

def get_emoji_key(emoji):
    try:
        pe = PartialEmoji.from_str(str(emoji))
        if pe.is_custom_emoji():
            return f"<:{pe.name}:{pe.id}>"
        return str(pe)
    except Exception:
        return str(emoji)

# --------------------------------------------------
# TÂCHE VIDE POUR LA VERIFICATION PROGRAMMÉE
# --------------------------------------------------
@tasks.loop(minutes=1)
async def check_programmed_messages():
    # Cette tâche est ici uniquement pour éviter une erreur de variable non définie.
    pass

# --------------------------------------------------
# DÉCORATEUR POUR PROTEGER LES COMMANDES
# --------------------------------------------------
def safe_command(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            import traceback
            traceback.print_exc()
            # Recherche d'un objet Interaction parmi les arguments
            for arg in args:
                if isinstance(arg, discord.Interaction):
                    try:
                        if not arg.response.is_done():
                            await arg.response.send_message("❌ Une erreur interne est survenue. Veuillez réessayer plus tard.", ephemeral=True)
                    except Exception:
                        pass
                    break
    return wrapper

# --------------------------------------------------
# VARIABLES PERSISTANTES
# --------------------------------------------------
xp_data = {}
messages_programmes = {}
defis_data = {}

# Données pour les modules existants
pomodoro_data = {}       # { user_id: { "total_focus": int, "session_count": int } }
goals_data = {}          # { user_id: [ { "id": str, "texte": str, "status": "en cours" ou "terminé" }, ... ] }
weekly_plan_data = {}    # { user_id: [ "Priorité 1", "Priorité 2", ... ] }
reminders_data = {}      # { reminder_id: { "user_id": str, "time": "HH:MM", "message": str, "daily": bool } }
quiz_data = {}           # { "questions": [ { "question": str, "choices": [str,...], "answer": int }, ... ] }
quiz_results_data = {}   # { user_id: [ { "score": int, "total": int, "date": float }, ... ] }
citations_data = {}      # { "citations": [ "Citation 1", "Citation 2", ... ] }
links_data = {}          # { "links": [ { "lien": str, "description": str, "public": bool }, ... ] }

# --------------------------------------------------
# CONFIGURATION RÉCAP HEBDOMADAIRE
# --------------------------------------------------
weekly_recap_config = {
    "channel_id": None,    # ID du canal de récap
    "time": "18:00",       # Heure (HH:MM)
    "day": "Sunday",       # Jour (ex: Sunday)
    "role_id": None        # ID du rôle à ping (optionnel)
}

# --------------------------------------------------
# BOT, INTENTS ET CONFIGURATION DES CANAUX
# --------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True
intents.voice_states = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.reaction_roles = {}  # Pour la gestion des reaction roles
        self.vocal_start_times = {}
        self.xp_config = {
            "xp_per_message": 10,
            "xp_per_minute_vocal": 5,
            "multipliers": {},
            "level_roles": {},
            "announcement_channel": None,
            "announcement_message": "🎉 {mention} a atteint {xp} XP !",
            "xp_command_channel": None,
            "xp_command_min_xp": 0,
            "badges": {},
            "titres": {}
        }
        # Configuration des canaux autorisés pour chaque module
        self.allowed_channels = {
            "pomodoro": None,
            "goals": None,
            "weekly_plan": None,
            "quiz": None,
            "reminders": None,
            "aide": None,
            "recherche_personnelle": None,
            "activity_drop": None,
            "bibliotheque": None,
            "reactions_smart": None,
            "quetes": None,
            "discipline_lock": None,
            "questions_puissantes": None,
            "combo": None,
            "routine": None,
            "observateur": None,
            "discipline_test": None
        }

    async def setup_hook(self):
        try:
            synced = await self.tree.sync()
            logging.info(f"🌐 {len(synced)} commandes slash synchronisées")
            if not check_programmed_messages.is_running():
                check_programmed_messages.start()
                logging.info("✅ Boucle de vérification programmée démarrée")
        except Exception as e:
            logging.error(f"❌ Erreur dans setup_hook : {e}")

bot = MyBot()
tree = bot.tree

def is_allowed(feature: str, interaction: discord.Interaction) -> bool:
    allowed = bot.allowed_channels.get(feature)
    if allowed is None:
        return True
    return interaction.channel.id == int(allowed)

# --------------------------------------------------
# HANDLER GLOBAL D'ERREURS POUR LES COMMANDES SLASH
# --------------------------------------------------
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    import traceback
    traceback.print_exc()
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Une erreur interne est survenue. Veuillez réessayer plus tard.", ephemeral=True)
    except Exception as e:
        logging.error(f"Erreur dans le handler global : {e}")

# --------------------------------------------------
# MODULE REACTION ROLE
# --------------------------------------------------
class ReactionRoleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Mapping de message_id -> { emoji: role_id }
        self.reaction_roles = {}

    @safe_command
    @app_commands.command(name="add_reaction_role", description="Ajoutez une réaction pour attribuer un rôle (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_reaction_role(self, interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
        mid = int(message_id)
        if mid not in self.reaction_roles:
            self.reaction_roles[mid] = {}
        self.reaction_roles[mid][emoji] = role.id
        await interaction.response.send_message("✅ Reaction role ajouté.", ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return
        if payload.message_id in self.reaction_roles:
            current = self.reaction_roles[payload.message_id]
            emoji = str(payload.emoji)
            if emoji in current:
                guild = self.bot.get_guild(payload.guild_id)
                if guild is None:
                    return
                member = guild.get_member(payload.user_id)
                if member is None:
                    return
                role = guild.get_role(current[emoji])
                if role:
                    try:
                        await member.add_roles(role)
                    except Exception as e:
                        logging.error(e)

async def setup_reaction_roles(bot: commands.Bot):
    await bot.add_cog(ReactionRoleCog(bot))

# --------------------------------------------------
# MODULE POMODORO
# --------------------------------------------------
pomodoro_config = {
    "focus": 25,
    "short_break": 5,
    "long_break": 15,
    "cycles_before_long_break": 4
}
active_pomodoro_sessions = {}

class PomodoroCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @safe_command
    async def pomodoro_cycle(self, user: discord.Member, cmd_channel: discord.TextChannel, focus_duration: int, short_break: int, long_break: int):
        session_count = 0
        try:
            dm = user.dm_channel or await user.create_dm()
            while True:
                await dm.send(f"🚀 **Focus**: Début d'une session de {focus_duration} minutes.")
                msg = await dm.send(f"⏱️ Focus : {focus_duration} minutes restantes.")
                for remaining in range(focus_duration, 0, -1):
                    await asyncio.sleep(60)
                    try:
                        await msg.edit(content=f"⏱️ Focus : {remaining-1} minutes restantes.")
                    except Exception:
                        pass
                session_count += 1
                uid = str(user.id)
                stats = pomodoro_data.get(uid, {"total_focus": 0, "session_count": 0})
                stats["total_focus"] += focus_duration
                stats["session_count"] += 1
                pomodoro_data[uid] = stats
                await sauvegarder_json_async(POMODORO_FILE, pomodoro_data)
                await dm.send("✅ **Focus terminé** ! Début de la pause courte.")
                if session_count % pomodoro_config["cycles_before_long_break"] == 0:
                    break_dur = long_break
                    phase = "Grosse pause"
                else:
                    break_dur = short_break
                    phase = "Pause courte"
                await dm.send(f"⏳ {phase} de {break_dur} minutes.")
                await asyncio.sleep(break_dur * 60)
                await dm.send("🔔 Fin de la pause, nouvelle session de focus démarre.")
        except asyncio.CancelledError:
            await dm.send("🛑 Session Pomodoro arrêtée.")
        except Exception as e:
            await dm.send(f"❌ Erreur Pomodoro : {e}")

    @safe_command
    @app_commands.command(name="focus_start", description="Démarrez une session Pomodoro")
    async def focus_start(self, interaction: discord.Interaction, focus: int, short_break: int, long_break: int):
        if not is_allowed("pomodoro", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Pomodoro autorisé.", ephemeral=True)
            return
        user = interaction.user
        if str(user.id) in active_pomodoro_sessions:
            await interaction.response.send_message("❌ Vous avez déjà une session active.", ephemeral=True)
            return
        task = self.bot.loop.create_task(self.pomodoro_cycle(user, interaction.channel, focus, short_break, long_break))
        active_pomodoro_sessions[str(user.id)] = task
        await interaction.response.send_message("✅ Session Pomodoro démarrée. Consultez vos DM.", ephemeral=True)

    @safe_command
    @app_commands.command(name="stop_focus", description="Arrêtez votre session Pomodoro")
    async def stop_focus(self, interaction: discord.Interaction):
        if not is_allowed("pomodoro", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Pomodoro autorisé.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        if uid in active_pomodoro_sessions:
            active_pomodoro_sessions[uid].cancel()
            del active_pomodoro_sessions[uid]
            await interaction.response.send_message("✅ Session arrêtée.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Aucune session active.", ephemeral=True)

    @safe_command
    @app_commands.command(name="focus_stats", description="Vos statistiques Pomodoro")
    async def focus_stats(self, interaction: discord.Interaction):
        if not is_allowed("pomodoro", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Pomodoro autorisé.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        stats = pomodoro_data.get(uid, {"total_focus": 0, "session_count": 0})
        await interaction.response.send_message(
            f"🔹 Sessions: {stats['session_count']}, Total Focus: {stats['total_focus']} minutes.",
            ephemeral=True)

    @safe_command
    @app_commands.command(name="set_pomodoro_config", description="Configurez les valeurs par défaut (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_pomodoro_config(self, interaction: discord.Interaction, focus: int, short_break: int, long_break: int, cycles: int):
        pomodoro_config["focus"] = focus
        pomodoro_config["short_break"] = short_break
        pomodoro_config["long_break"] = long_break
        pomodoro_config["cycles_before_long_break"] = cycles
        await interaction.response.send_message("✅ Config Pomodoro mise à jour.", ephemeral=True)

async def setup_pomodoro(bot: commands.Bot):
    await bot.add_cog(PomodoroCog(bot))

# --------------------------------------------------
# MODULE OBJECTIFS PERSONNELS
# --------------------------------------------------
class GoalsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @safe_command
    @app_commands.command(name="ajouter_objectif", description="Ajoutez un objectif personnel")
    async def ajouter_objectif(self, interaction: discord.Interaction, texte: str):
        if not is_allowed("goals", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Objectifs.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        obj = {"id": str(uuid.uuid4()), "texte": texte, "status": "en cours"}
        goals_data.setdefault(uid, []).append(obj)
        await sauvegarder_json_async(GOALS_FILE, goals_data)
        await interaction.response.send_message("✅ Objectif ajouté.", ephemeral=True)

    @safe_command
    @app_commands.command(name="mes_objectifs", description="Affichez vos objectifs")
    async def mes_objectifs(self, interaction: discord.Interaction):
        if not is_allowed("goals", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Objectifs.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        objs = goals_data.get(uid, [])
        if not objs:
            await interaction.response.send_message("Aucun objectif trouvé.", ephemeral=True)
            return
        lines = [f"`{o['id']}` - {o['texte']} ({o['status']})" for o in objs]
        await interaction.response.send_message("📝 **Vos objectifs :**\n" + "\n".join(lines), ephemeral=True)

    @safe_command
    @app_commands.command(name="objectif_fait", description="Marquez un objectif comme terminé")
    async def objectif_fait(self, interaction: discord.Interaction, id_objectif: str):
        if not is_allowed("goals", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Objectifs.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        objs = goals_data.get(uid, [])
        for o in objs:
            if o["id"] == id_objectif:
                o["status"] = "terminé"
                await sauvegarder_json_async(GOALS_FILE, goals_data)
                await interaction.response.send_message("✅ Objectif terminé.", ephemeral=True)
                return
        await interaction.response.send_message("❌ Objectif non trouvé.", ephemeral=True)

    @safe_command
    @app_commands.command(name="supprimer_objectif", description="Supprimez un objectif")
    async def supprimer_objectif(self, interaction: discord.Interaction, id_objectif: str):
        if not is_allowed("goals", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Objectifs.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        objs = goals_data.get(uid, [])
        new_objs = [o for o in objs if o["id"] != id_objectif]
        if len(new_objs) == len(objs):
            await interaction.response.send_message("❌ Objectif non trouvé.", ephemeral=True)
            return
        goals_data[uid] = new_objs
        await sauvegarder_json_async(GOALS_FILE, goals_data)
        await interaction.response.send_message("✅ Objectif supprimé.", ephemeral=True)

async def setup_goals(bot: commands.Bot):
    await bot.add_cog(GoalsCog(bot))

# --------------------------------------------------
# MODULE PLANNING HEBDOMADAIRE
# --------------------------------------------------
class WeeklyPlanModal(Modal, title="Planifiez votre semaine"):
    def __init__(self):
        super().__init__(timeout=None)
        self.priorites = TextInput(
            label="Entrez 3 à 5 priorités séparées par des virgules",
            style=TextStyle.paragraph,
            placeholder="Priorité 1, Priorité 2, ...",
            required=True,
            max_length=500
        )
        self.add_item(self.priorites)

    async def on_submit(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        plan = [p.strip() for p in self.priorites.value.split(",") if p.strip()]
        if not (3 <= len(plan) <= 5):
            await interaction.response.send_message("❌ Vous devez entrer entre 3 et 5 priorités.", ephemeral=True)
            return
        weekly_plan_data[uid] = plan
        await sauvegarder_json_async(WEEKLY_PLAN_FILE, weekly_plan_data)
        await interaction.response.send_message("✅ Planning sauvegardé.", ephemeral=True)

class WeeklyPlanCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @safe_command
    @app_commands.command(name="planifier_semaine", description="Planifiez vos priorités")
    async def planifier_semaine(self, interaction: discord.Interaction):
        if not is_allowed("weekly_plan", interaction):
            await interaction.response.send_message("❌ Commande réservée au canal Planning.", ephemeral=True)
            return
        await interaction.response.send_modal(WeeklyPlanModal())

    @safe_command
    @app_commands.command(name="ma_semaine", description="Affichez votre planning hebdomadaire")
    async def ma_semaine(self, interaction: discord.Interaction):
        if not is_allowed("weekly_plan", interaction):
            await interaction.response.send_message("❌ Commande réservée au canal Planning.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        plan = weekly_plan_data.get(uid, [])
        if not plan:
            await interaction.response.send_message("Aucun planning trouvé.", ephemeral=True)
        else:
            await interaction.response.send_message("📅 **Votre planning :**\n" + "\n".join(plan), ephemeral=True)

async def setup_weekly_plan(bot: commands.Bot):
    await bot.add_cog(WeeklyPlanCog(bot))

# --------------------------------------------------
# MODULE RAPPELS
# --------------------------------------------------
class RemindersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_task = self.bot.loop.create_task(self.check_reminders())

    async def check_reminders(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = datetime.datetime.now()
            to_remove = []
            for rid, rem in reminders_data.items():
                try:
                    rem_time = datetime.datetime.strptime(rem["time"], "%H:%M").time()
                    if now.time().hour == rem_time.hour and now.time().minute == rem_time.minute:
                        user = self.bot.get_user(int(rem["user_id"]))
                        if user:
                            await user.send(f"🔔 **Rappel**: {rem['message']}")
                        if not rem.get("daily", False):
                            to_remove.append(rid)
                except Exception as e:
                    logging.error(f"Erreur dans check_reminders: {e}")
            for rid in to_remove:
                reminders_data.pop(rid, None)
            if to_remove:
                await sauvegarder_json_async(REMINDERS_FILE, reminders_data)
            await asyncio.sleep(60)

    @safe_command
    @app_commands.command(name="ajouter_rappel", description="Ajoutez un rappel personnel")
    async def ajouter_rappel(self, interaction: discord.Interaction, time_str: str, message: str, daily: bool = False):
        if not is_allowed("reminders", interaction):
            await interaction.response.send_message("❌ Commande réservée au canal Rappels.", ephemeral=True)
            return
        try:
            datetime.datetime.strptime(time_str, "%H:%M")
        except ValueError:
            await interaction.response.send_message("❌ Format d'heure invalide (HH:MM).", ephemeral=True)
            return
        rid = str(uuid.uuid4())
        reminders_data[rid] = {"user_id": str(interaction.user.id), "time": time_str, "message": message, "daily": daily}
        await sauvegarder_json_async(REMINDERS_FILE, reminders_data)
        await interaction.response.send_message("✅ Rappel ajouté.", ephemeral=True)

    @safe_command
    @app_commands.command(name="mes_rappels", description="Affichez vos rappels")
    async def mes_rappels(self, interaction: discord.Interaction):
        if not is_allowed("reminders", interaction):
            await interaction.response.send_message("❌ Commande réservée au canal Rappels.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        lines = [f"`{rid}` - {rem['time']} : {rem['message']} ({'daily' if rem.get('daily') else 'one-time'})"
                 for rid, rem in reminders_data.items() if rem["user_id"] == uid]
        if lines:
            await interaction.response.send_message("🔔 **Vos rappels :**\n" + "\n".join(lines), ephemeral=True)
        else:
            await interaction.response.send_message("Aucun rappel trouvé.", ephemeral=True)

    @safe_command
    @app_commands.command(name="supprimer_rappel", description="Supprimez un rappel")
    async def supprimer_rappel(self, interaction: discord.Interaction, rid: str):
        if rid in reminders_data and reminders_data[rid]["user_id"] == str(interaction.user.id):
            reminders_data.pop(rid)
            await sauvegarder_json_async(REMINDERS_FILE, reminders_data)
            await interaction.response.send_message("✅ Rappel supprimé.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Rappel non trouvé.", ephemeral=True)

async def setup_reminders(bot: commands.Bot):
    await bot.add_cog(RemindersCog(bot))

# --------------------------------------------------
# MODULE QUIZZ
# --------------------------------------------------
class QuizCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @safe_command
    @app_commands.command(name="ajouter_quizz", description="Définissez un quiz (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def ajouter_quizz(self, interaction: discord.Interaction, quizz_json: str):
        try:
            data = json.loads(quizz_json)
            if not isinstance(data, list):
                raise ValueError("Le quiz doit être une liste de questions.")
            quiz_data["questions"] = data
            await sauvegarder_json_async(QUIZ_FILE, quiz_data)
            await interaction.response.send_message("✅ Quiz mis à jour.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur dans le quiz: {e}", ephemeral=True)

    @safe_command
    @app_commands.command(name="lancer_quizz", description="Lancez le quiz et affichez votre score")
    async def lancer_quizz(self, interaction: discord.Interaction):
        if not is_allowed("quiz", interaction):
            await interaction.response.send_message("❌ Commande réservée au canal Quiz.", ephemeral=True)
            return
        if "questions" not in quiz_data or not quiz_data["questions"]:
            await interaction.response.send_message("❌ Aucun quiz défini.", ephemeral=True)
            return
        user = interaction.user
        dm = user.dm_channel or await user.create_dm()
        score = 0
        total = len(quiz_data["questions"])
        for q in quiz_data["questions"]:
            choix_text = "\n".join([f"{i+1}. {c}" for i, c in enumerate(q.get("choices", []))])
            await dm.send(f"❓ {q['question']}\n{choix_text}\n\nRépondez par le numéro.")
            def check(m):
                return m.author.id == user.id and m.channel == dm
            try:
                rep = await self.bot.wait_for("message", check=check, timeout=30)
                try:
                    ans = int(rep.content) - 1
                    if ans == q["answer"]:
                        score += 1
                        await dm.send("✅ Bonne réponse!")
                    else:
                        await dm.send("❌ Mauvaise réponse.")
                except Exception:
                    await dm.send("❌ Réponse invalide.")
            except asyncio.TimeoutError:
                await dm.send("⏰ Temps écoulé pour cette question.")
        quiz_results_data.setdefault(str(user.id), []).append({"score": score, "total": total, "date": time.time()})
        await dm.send(f"Votre score: {score} / {total}")
        await interaction.response.send_message("✅ Quiz terminé. Consultez vos DM.", ephemeral=True)

async def setup_quiz(bot: commands.Bot):
    await bot.add_cog(QuizCog(bot))

# --------------------------------------------------
# MODULE FOCUS GROUP
# --------------------------------------------------
class FocusGroupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.focus_participants = set()

    @safe_command
    @app_commands.command(name="ping_focus", description="Proposez une session de focus groupe")
    async def ping_focus(self, interaction: discord.Interaction):
        view = View(timeout=60)
        btn = Button(label="Je participe", style=discord.ButtonStyle.success)
        async def btn_callback(inter: discord.Interaction):
            self.focus_participants.add(inter.user.id)
            await inter.response.send_message("✅ Vous êtes inscrit.", ephemeral=True)
        btn.callback = btn_callback
        view.add_item(btn)
        await interaction.response.send_message("🔔 Session focus groupe proposée ! Cliquez sur 'Je participe'.", view=view)

    @safe_command
    @app_commands.command(name="set_focus_channel", description="Configurez le canal focus groupe (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_focus_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.bot.focus_channel_id = str(channel.id)
        await interaction.response.send_message(f"✅ Canal focus groupe configuré : {channel.mention}", ephemeral=True)

async def setup_focus_group(bot: commands.Bot):
    await bot.add_cog(FocusGroupCog(bot))

# --------------------------------------------------
# MODULE RÉCAP HEBDOMADAIRE AUTOMATIQUE
# --------------------------------------------------
class WeeklySummaryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sent_this_week = False
        self.task = self.bot.loop.create_task(self.weekly_summary_task())

    async def weekly_summary_task(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                now = datetime.datetime.now(ZoneInfo("Europe/Paris"))
                recap_day = weekly_recap_config.get("day", "Sunday")
                recap_time = weekly_recap_config.get("time", "18:00")
                recap_hour, recap_minute = map(int, recap_time.split(":"))
                if now.strftime("%A") == recap_day and now.hour == recap_hour and now.minute == recap_minute and not self.sent_this_week:
                    total_xp = sum(xp_data.values())
                    total_focus = sum([d.get("total_focus", 0) for d in pomodoro_data.values()])
                    total_sessions = sum([d.get("session_count", 0) for d in pomodoro_data.values()])
                    total_objectifs = sum([len([o for o in lst if o["status"]=="terminé"]) for lst in goals_data.values()])
                    defis_valides = 0
                    citation = ""
                    if "citations" in citations_data and citations_data.get("citations"):
                        citation = random.choice(citations_data["citations"])
                    recap = f"""**Récapitulatif Hebdomadaire**
Total XP : {total_xp}
Sessions Pomodoro : {total_sessions} (pour {total_focus} minutes)
Objectifs terminés : {total_objectifs}
Défis validés : {defis_valides}
Citation de la semaine : {citation if citation else 'Aucune'} """
                    channel_id = weekly_recap_config.get("channel_id")
                    if channel_id:
                        chan = self.bot.get_channel(int(channel_id))
                        if chan:
                            ping = ""
                            role_id = weekly_recap_config.get("role_id")
                            if role_id:
                                r = chan.guild.get_role(int(role_id))
                                if r:
                                    ping = r.mention
                            await chan.send(f"{ping}\n{recap}")
                    self.sent_this_week = True
                if now.strftime("%A") == "Monday":
                    self.sent_this_week = False
            except Exception as e:
                logging.error(f"Erreur dans weekly_summary_task: {e}")
            await asyncio.sleep(60)

    @safe_command
    @app_commands.command(name="set_recap_config", description="Configurez le récap hebdomadaire (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_recap_config(self, interaction: discord.Interaction, channel: discord.TextChannel, time: str, day: str, role: discord.Role = None):
        weekly_recap_config["channel_id"] = str(channel.id)
        weekly_recap_config["time"] = time
        weekly_recap_config["day"] = day
        if role:
            weekly_recap_config["role_id"] = str(role.id)
        await interaction.response.send_message("✅ Récap configuré.", ephemeral=True)

async def setup_weekly_summary(bot: commands.Bot):
    await bot.add_cog(WeeklySummaryCog(bot))

# --------------------------------------------------
# MODULE AIDE
# --------------------------------------------------
class AideModal(Modal, title="J'ai besoin d'aide"):
    def __init__(self):
        super().__init__(timeout=None)
        self.domaine = TextInput(label="Domaine", style=TextStyle.short, placeholder="Ex: Informatique", required=True, max_length=100)
        self.description = TextInput(label="Description", style=TextStyle.paragraph, placeholder="Décrivez votre besoin", required=True, max_length=500)
        self.add_item(self.domaine)
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True)
        }
        category = await interaction.guild.create_category(name=f"Aide_{interaction.user.name}", overwrites=overwrites)
        text_ch = await interaction.guild.create_text_channel(name="aide-text", category=category, overwrites=overwrites)
        voice_ch = await interaction.guild.create_voice_channel(name="aide-voice", category=category, overwrites=overwrites)
        await interaction.response.send_message(f"✅ Demande d'aide enregistrée. Canaux créés: {text_ch.mention} et {voice_ch.mention}", ephemeral=True)

class AideCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @safe_command
    @app_commands.command(name="qui_a_besoin", description="Déclarez que vous avez besoin d'aide")
    async def qui_a_besoin(self, interaction: discord.Interaction):
        if not is_allowed("aide", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Aide configuré.", ephemeral=True)
            return
        view = View(timeout=60)
        btn_besoin = Button(label="J’ai besoin d’aide", style=discord.ButtonStyle.danger)
        btn_aider = Button(label="Je peux aider", style=discord.ButtonStyle.success)
        async def besoin_callback(inter: discord.Interaction):
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True)
            }
            category = await interaction.guild.create_category(name=f"Aide_{interaction.user.name}", overwrites=overwrites)
            text_ch = await interaction.guild.create_text_channel(name="aide-text", category=category, overwrites=overwrites)
            voice_ch = await interaction.guild.create_voice_channel(name="aide-voice", category=category, overwrites=overwrites)
            await inter.response.send_message(f"✅ Canal d'aide créé: {text_ch.mention}", ephemeral=True)
        async def aider_callback(inter: discord.Interaction):
            await inter.response.send_message("✅ Vous serez notifié en cas de besoin d'aide.", ephemeral=True)
        btn_besoin.callback = besoin_callback
        btn_aider.callback = aider_callback
        view.add_item(btn_besoin)
        view.add_item(btn_aider)
        await interaction.response.send_message("🔔 Demande d'aide : choisissez une option.", view=view, ephemeral=True)

    @safe_command
    @app_commands.command(name="j_ai_besoin_d_aide", description="Exprimez précisément votre besoin d'aide")
    async def j_ai_besoin_d_aide(self, interaction: discord.Interaction):
        if not is_allowed("aide", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Aide configuré.", ephemeral=True)
            return
        await interaction.response.send_modal(AideModal())

async def setup_aide(bot: commands.Bot):
    await bot.add_cog(AideCog(bot))

# --------------------------------------------------
# MODULE CITATIONS
# --------------------------------------------------
class CitationsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.citations = citations_data.get("citations", [])

    @safe_command
    @app_commands.command(name="ajouter_citation", description="Ajoutez une citation marquante")
    async def ajouter_citation(self, interaction: discord.Interaction, citation: str):
        self.citations.append(citation)
        citations_data["citations"] = self.citations
        await sauvegarder_json_async(CITATIONS_FILE, citations_data)
        await interaction.response.send_message("✅ Citation ajoutée.", ephemeral=True)

    @safe_command
    @app_commands.command(name="mes_citations", description="Affichez vos citations")
    async def mes_citations(self, interaction: discord.Interaction):
        if not self.citations:
            await interaction.response.send_message("Aucune citation enregistrée.", ephemeral=True)
            return
        await interaction.response.send_message("💬 **Citations :**\n" + "\n".join(self.citations), ephemeral=True)

async def setup_citations(bot: commands.Bot):
    global citations_data
    citations_data = await charger_json_async(CITATIONS_FILE)
    await bot.add_cog(CitationsCog(bot))

# --------------------------------------------------
# MODULE ALERTE URGENCE
# --------------------------------------------------
class EmergencyAlertCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @safe_command
    @app_commands.command(name="besoin_d_aide", description="Envoyez une alerte aux mentors")
    async def besoin_d_aide(self, interaction: discord.Interaction, message: str):
        alert = f"⚠️ Urgence de {interaction.user.mention}: {message}"
        mentor_role_id = "MENTOR_ROLE_ID"  # À configurer par admin
        role = interaction.guild.get_role(int(mentor_role_id)) if mentor_role_id.isdigit() else None
        ping = role.mention if role else ""
        for member in interaction.guild.members:
            if member.guild_permissions.administrator:
                try:
                    await member.send(f"{ping}\n{alert}")
                except Exception as e:
                    logging.error(f"Erreur DM pour {member}: {e}")
        await interaction.response.send_message("✅ Alerte envoyée aux mentors.", ephemeral=True)

async def setup_emergency(bot: commands.Bot):
    await bot.add_cog(EmergencyAlertCog(bot))

# --------------------------------------------------
# MODULE TRACKER DE LIENS
# --------------------------------------------------
links_data = {}
class LinksTrackerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @safe_command
    @app_commands.command(name="ajouter_lien", description="Ajoutez un lien utile (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def ajouter_lien(self, interaction: discord.Interaction, lien: str, description: str, public: bool = False):
        entry = {"lien": lien, "description": description, "public": public}
        links_data.setdefault("links", []).append(entry)
        await sauvegarder_json_async(LINKS_FILE, links_data)
        await interaction.response.send_message("✅ Lien ajouté.", ephemeral=True)

    @safe_command
    @app_commands.command(name="mes_liens", description="Affichez vos liens (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def mes_liens(self, interaction: discord.Interaction):
        if "links" not in links_data or not links_data["links"]:
            await interaction.response.send_message("Aucun lien trouvé.", ephemeral=True)
            return
        lines = [f"- {e['description']}: {e['lien']} ({'public' if e['public'] else 'privé'})" for e in links_data["links"]]
        await interaction.response.send_message("🔗 **Liens enregistrés :**\n" + "\n".join(lines), ephemeral=True)

    @safe_command
    @app_commands.command(name="partager_lien", description="Marquez un lien comme public (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def partager_lien(self, interaction: discord.Interaction, index: int):
        try:
            links_data["links"][index]["public"] = True
            await sauvegarder_json_async(LINKS_FILE, links_data)
            await interaction.response.send_message("✅ Lien marqué public.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

async def setup_links(bot: commands.Bot):
    global links_data
    links_data = await charger_json_async(LINKS_FILE)
    await bot.add_cog(LinksTrackerCog(bot))

# --------------------------------------------------
# MODULE CHRONO SECRET & SYSTÈME XP
# --------------------------------------------------
async def add_xp(user_id, amount):
    uid = str(user_id)
    xp_data[uid] = xp_data.get(uid, 0) + amount
    await sauvegarder_json_async(XP_FILE, xp_data)
    logging.info(f"XP ajouté à {uid}: {amount}")

class SecretChronoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @safe_command
    @app_commands.command(name="lancer_chrono_secret", description="Lancez un chrono secret (20-40 min)")
    async def lancer_chrono_secret(self, interaction: discord.Interaction):
        duration = random.randint(20, 40)
        await interaction.response.send_message(f"⏰ Chrono secret lancé pour {duration} minutes. Restez actif pour un bonus XP !", ephemeral=True)
        await asyncio.sleep(duration * 60)
        bonus = duration // 2
        await add_xp(interaction.user.id, bonus)
        await interaction.followup.send(f"🎉 Chrono terminé ! Bonus XP : {bonus}.", ephemeral=True)

async def setup_chrono(bot: commands.Bot):
    await bot.add_cog(SecretChronoCog(bot))

# --------------------------------------------------
# MODULE LIMITE DE TEMPS
# --------------------------------------------------
time_limits = {}  # { channel_id: { user_id: { "limit": int, "used": int, "reset": timestamp } } }
class TimeLimiterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.loop.create_task(self.reset_limits())

    async def reset_limits(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = time.time()
            for chan, users in time_limits.items():
                for uid, data in users.items():
                    if now > data["reset"]:
                        data["used"] = 0
                        data["reset"] = now + 24*3600
            await asyncio.sleep(600)

    @safe_command
    @app_commands.command(name="limiter_temps", description="Définissez une limite de temps par salon (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def limiter_temps(self, interaction: discord.Interaction, channel: discord.TextChannel, temps: int):
        time_limits.setdefault(str(channel.id), {})[str(interaction.user.id)] = {"limit": temps, "used": 0, "reset": time.time() + 24*3600}
        await interaction.response.send_message(f"✅ Limite de {temps} minutes pour {channel.mention} définie.", ephemeral=True)

async def setup_time_limiter(bot: commands.Bot):
    await bot.add_cog(TimeLimiterCog(bot))

# --------------------------------------------------
# MODULE FOCUS EXTREME & MODE FOCUS
# --------------------------------------------------
class FocusExtremeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.social_roles = []  # IDs de rôles à retirer
        self.extreme_channels = []  # IDs de salons à restreindre

    @safe_command
    @app_commands.command(name="set_focus_extreme_config", description="Configurez Focus Extreme (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_focus_extreme_config(self, interaction: discord.Interaction, roles: str, channels: str):
        self.social_roles = [r.strip() for r in roles.split(",") if r.strip()]
        self.extreme_channels = [c.strip() for c in channels.split(",") if c.strip()]
        await interaction.response.send_message("✅ Configuration Focus Extreme enregistrée.", ephemeral=True)

    @safe_command
    @app_commands.command(name="activer_focus_extreme", description="Activez Focus Extreme (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def activer_focus_extreme(self, interaction: discord.Interaction):
        for member in interaction.guild.members:
            roles_to_remove = [role for role in member.roles if str(role.id) in self.social_roles]
            if roles_to_remove:
                try:
                    await member.remove_roles(*roles_to_remove, reason="Focus Extreme activé")
                except Exception as e:
                    logging.error(f"Erreur retrait rôles pour {member}: {e}")
        for cid in self.extreme_channels:
            channel = interaction.guild.get_channel(int(cid))
            if channel:
                try:
                    await channel.set_permissions(interaction.guild.default_role, view_channel=False)
                except Exception as e:
                    logging.error(f"Erreur sur {channel.name}: {e}")
        await interaction.response.send_message("✅ Focus Extreme activé.", ephemeral=True)

    @safe_command
    @app_commands.command(name="desactiver_focus_extreme", description="Désactivez Focus Extreme (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def desactiver_focus_extreme(self, interaction: discord.Interaction):
        for cid in self.extreme_channels:
            channel = interaction.guild.get_channel(int(cid))
            if channel:
                try:
                    await channel.set_permissions(interaction.guild.default_role, overwrite=None)
                except Exception as e:
                    logging.error(f"Erreur réinitialisation {channel.name}: {e}")
        await interaction.response.send_message("✅ Focus Extreme désactivé.", ephemeral=True)

class FocusModeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.focus_mode_channels = []  # IDs des salons à masquer

    @safe_command
    @app_commands.command(name="set_focus_mode_channels", description="Définissez les salons pour le mode Focus (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_focus_mode_channels(self, interaction: discord.Interaction, channels: str):
        self.focus_mode_channels = [c.strip() for c in channels.split(",") if c.strip()]
        await interaction.response.send_message("✅ Salons configurés pour Focus.", ephemeral=True)

    @safe_command
    @app_commands.command(name="mode_focus", description="Activez le mode Focus")
    async def mode_focus(self, interaction: discord.Interaction):
        for cid in self.focus_mode_channels:
            channel = interaction.guild.get_channel(int(cid))
            if channel:
                try:
                    await channel.set_permissions(interaction.user, view_channel=False)
                except Exception as e:
                    logging.error(f"Erreur sur {channel.name}: {e}")
        await interaction.response.send_message("✅ Mode Focus activé pour vous.", ephemeral=True)

    @safe_command
    @app_commands.command(name="mode_normal", description="Désactivez le mode Focus")
    async def mode_normal(self, interaction: discord.Interaction):
        for cid in self.focus_mode_channels:
            channel = interaction.guild.get_channel(int(cid))
            if channel:
                try:
                    await channel.set_permissions(interaction.user, overwrite=None)
                except Exception as e:
                    logging.error(f"Erreur sur {channel.name}: {e}")
        await interaction.response.send_message("✅ Mode Normal rétabli.", ephemeral=True)

async def setup_focus_mode(bot: commands.Bot):
    await bot.add_cog(FocusModeCog(bot))

async def setup_focus_extreme(bot: commands.Bot):
    await bot.add_cog(FocusExtremeCog(bot))

# --------------------------------------------------
# MODULE /lock et /unlock
# --------------------------------------------------
class ChannelLockCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @safe_command
    @app_commands.command(name="lock", description="Verrouillez un salon (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def lock(self, interaction: discord.Interaction, channel: discord.TextChannel):
        try:
            await channel.set_permissions(interaction.guild.default_role, view_channel=False)
            await interaction.response.send_message(f"✅ {channel.mention} verrouillé.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

    @safe_command
    @app_commands.command(name="unlock", description="Déverrouillez un salon (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def unlock(self, interaction: discord.Interaction, channel: discord.TextChannel):
        try:
            await channel.set_permissions(interaction.guild.default_role, overwrite=None)
            await interaction.response.send_message(f"✅ {channel.mention} déverrouillé.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

async def setup_channel_lock(bot: commands.Bot):
    await bot.add_cog(ChannelLockCog(bot))

# --------------------------------------------------
# MODULE "PROTECT FOCUS" (anti-mentions, blocage MP)
# --------------------------------------------------
focus_protect = {}
class FocusProtectCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.loop.create_task(self.check_protect_expiry())

    async def check_protect_expiry(self):
        while not self.bot.is_closed():
            now = time.time()
            for uid, expiry in list(focus_protect.items()):
                if expiry <= now:
                    del focus_protect[uid]
            await asyncio.sleep(30)

    @safe_command
    @app_commands.command(name="focus_protect", description="Activez Protect Focus pour X minutes")
    async def focus_protect_cmd(self, interaction: discord.Interaction, durée: int):
        if not is_allowed("pomodoro", interaction):
            await interaction.response.send_message("❌ Cette commande est réservée au canal Protect Focus.", ephemeral=True)
            return
        focus_protect[str(interaction.user.id)] = time.time() + durée * 60
        await interaction.response.send_message(f"✅ Protect Focus activé pour {durée} minutes.", ephemeral=True)

async def setup_focus_protect(bot: commands.Bot):
    await bot.add_cog(FocusProtectCog(bot))

# --------------------------------------------------
# MODULE VEILLE (inactivité)
# --------------------------------------------------
last_activity = {}
exempt_veille = set()

@bot.event
async def on_message(message):
    try:
        if not message.author.bot:
            last_activity[str(message.author.id)] = time.time()
        await bot.process_commands(message)
    except Exception as e:
        logging.error(f"Erreur dans on_message: {e}")

class SleepModeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_task = self.bot.loop.create_task(self.check_inactivity())

    async def check_inactivity(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = time.time()
            for member in self.bot.guilds[0].members:
                uid = str(member.id)
                if uid in exempt_veille:
                    continue
                last = last_activity.get(uid, now)
                if now - last > 7 * 24 * 3600:
                    try:
                        await member.send("💤 Besoin d’un coup de main ?")
                    except Exception as e:
                        logging.error(f"Erreur veille pour {member}: {e}")
            await asyncio.sleep(3600)

    @safe_command
    @app_commands.command(name="desactiver_veille", description="Désactivez la veille pour vous")
    async def desactiver_veille(self, interaction: discord.Interaction):
        exempt_veille.add(str(interaction.user.id))
        await interaction.response.send_message("✅ Veille désactivée.", ephemeral=True)

async def setup_sleep_mode(bot: commands.Bot):
    await bot.add_cog(SleepModeCog(bot))

# --------------------------------------------------
# MODULE RECHERCHES PERSONNELLES
# --------------------------------------------------
class RecherchesPersoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_recherches = {}  # { user_id: { "topic": str, "next_dm_time": float } }
        self.dm_task = self.bot.loop.create_task(self.dm_recherches_loop())

    async def dm_recherches_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = time.time()
            for uid, recherche in list(self.active_recherches.items()):
                if now >= recherche.get("next_dm_time", 0):
                    user = self.bot.get_user(int(uid))
                    if user:
                        try:
                            await user.send(f"🔍 Suivi de ta recherche sur '{recherche['topic']}'. N'oublie pas de noter tes avancées!")
                        except Exception as e:
                            logging.error(f"Erreur DM pour recherche: {e}")
                    recherche["next_dm_time"] = now + 3600  # suivi toutes les heures
            await asyncio.sleep(60)

    @safe_command
    @app_commands.command(name="nouvelle_recherche", description="Débute une nouvelle recherche perso")
    async def nouvelle_recherche(self, interaction: discord.Interaction, sujet: str):
        if not is_allowed("recherche_personnelle", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Recherches Perso autorisé.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        self.active_recherches[uid] = {"topic": sujet, "next_dm_time": time.time() + 3600}
        await interaction.response.send_message(f"✅ Recherche sur '{sujet}' démarrée. Tu recevras des suivis en DM.", ephemeral=True)

    @safe_command
    @app_commands.command(name="publier_recherche", description="Publiez vos résultats de recherche dans le canal configuré")
    async def publier_recherche(self, interaction: discord.Interaction, contenu: str):
        if not is_allowed("recherche_personnelle", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Recherches Perso autorisé.", ephemeral=True)
            return
        channel_id = bot.allowed_channels.get("recherche_personnelle")
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                topic = self.active_recherches.get(str(interaction.user.id), {}).get("topic", "Inconnu")
                await channel.send(f"🔍 {interaction.user.mention} partage ses résultats de recherche sur '{topic}':\n{contenu}")
                await interaction.response.send_message("✅ Recherche publiée.", ephemeral=True)
                return
        await interaction.response.send_message("❌ Canal de publication non configuré par un admin.", ephemeral=True)

async def setup_recherches(bot: commands.Bot):
    await bot.add_cog(RecherchesPersoCog(bot))

# --------------------------------------------------
# MODULE STATISTIQUES DE CHUTE D’ACTIVITÉ
# --------------------------------------------------
class ActivityDropCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.activity_counts = {}
        self.chute_disabled = set()
        self.bot.loop.create_task(self.activity_monitor_loop())

    @safe_command
    @app_commands.command(name="desactiver_chute", description="Désactivez les alertes de chute d'activité")
    async def desactiver_chute(self, interaction: discord.Interaction):
        if not is_allowed("activity_drop", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Chute d'activité autorisé.", ephemeral=True)
            return
        self.chute_disabled.add(str(interaction.user.id))
        await interaction.response.send_message("✅ Alertes de chute d'activité désactivées.", ephemeral=True)

    async def activity_monitor_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(3600)  # vérification toutes les heures
            for uid, count in list(self.activity_counts.items()):
                if uid in self.chute_disabled:
                    continue
                if count < 5:  # seuil arbitraire
                    user = self.bot.get_user(int(uid))
                    if user:
                        try:
                            await user.send("💡 On dirait que tu es moins actif ces derniers temps. Tu es capable de rebondir!")
                        except Exception as e:
                            logging.error(f"Erreur DM pour activité drop: {e}")
            self.activity_counts = {}

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.author.bot:
            uid = str(message.author.id)
            self.activity_counts[uid] = self.activity_counts.get(uid, 0) + 1

async def setup_activity_drop(bot: commands.Bot):
    await bot.add_cog(ActivityDropCog(bot))

# --------------------------------------------------
# MODULE BIBLIOTHÈQUE COMMUNAUTAIRE ÉVOLUTIVE
# --------------------------------------------------
class BibliothequeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.biblio = []  # En mémoire (pour persistance, étendre avec un fichier JSON)

    @safe_command
    @app_commands.command(name="proposer_ressource", description="Proposez une ressource utile")
    async def proposer_ressource(self, interaction: discord.Interaction, lien: str, description: str):
        if not is_allowed("bibliotheque", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Bibliothèque autorisé.", ephemeral=True)
            return
        self.biblio.append({"lien": lien, "description": description})
        unlock_message = ""
        if len(self.biblio) % 5 == 0:
            unlock_message = "🎉 Nouvelle section de la bibliothèque débloquée!"
        await interaction.response.send_message(f"✅ Ressource proposée. {unlock_message}", ephemeral=True)

    @safe_command
    @app_commands.command(name="voir_bibliotheque", description="Afficher la bibliothèque communautaire")
    async def voir_bibliotheque(self, interaction: discord.Interaction):
        if not is_allowed("bibliotheque", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Bibliothèque autorisé.", ephemeral=True)
            return
        if not self.biblio:
            await interaction.response.send_message("Aucune ressource proposée pour l'instant.", ephemeral=True)
            return
        lines = [f"- {entry['description']}: {entry['lien']}" for entry in self.biblio]
        await interaction.response.send_message("📚 **Bibliothèque communautaire:**\n" + "\n".join(lines), ephemeral=True)

async def setup_bibliotheque(bot: commands.Bot):
    await bot.add_cog(BibliothequeCog(bot))

# --------------------------------------------------
# MODULE RÉACTIONS CONTEXTUELLES INTELLIGENTES (SMART REACTIONS)
# --------------------------------------------------
class SmartReactionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @safe_command
    @app_commands.command(name="activer_reactions_smart", description="Activez les réactions contextuelles intelligentes (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def activer_reactions_smart(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.bot.allowed_channels["reactions_smart"] = str(channel.id)
        await interaction.response.send_message(f"✅ Réactions intelligentes activées dans {channel.mention}", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        channel_id = str(message.channel.id)
        allowed = self.bot.allowed_channels.get("reactions_smart")
        if allowed and allowed == channel_id:
            content = message.content.lower()
            if any(word in content for word in ["victoire", "gagné", "réussi"]):
                try:
                    await message.add_reaction("🎉")
                except Exception as e:
                    logging.error(e)
            elif any(word in content for word in ["plaint", "problème", "découragé"]):
                try:
                    await message.channel.send(f"{message.author.mention} Courage, tu peux y arriver!")
                except Exception as e:
                    logging.error(e)

async def setup_smart_reactions(bot: commands.Bot):
    await bot.add_cog(SmartReactionsCog(bot))

# --------------------------------------------------
# MODULE SCÉNARIO / QUÊTES
# --------------------------------------------------
class QuetesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.quests = {}  # { user_id: quest }

    @safe_command
    @app_commands.command(name="commencer_quete", description="Commencez une quête")
    async def commencer_quete(self, interaction: discord.Interaction):
        if not is_allowed("quetes", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Quêtes autorisé.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        if uid in self.quests:
            await interaction.response.send_message("❌ Vous avez déjà une quête en cours.", ephemeral=True)
            return
        quest = {
            "titre": "Mission : Reprendre le contrôle",
            "etapes": ["Fixer 3 objectifs", "Faire 2 pomodoros", "Écrire un log de fin de journée"],
            "current": 0
        }
        self.quests[uid] = quest
        await interaction.response.send_message("✅ Quête commencée ! Utilisez /voir_quete pour voir vos étapes.", ephemeral=True)

    @safe_command
    @app_commands.command(name="voir_quete", description="Voir votre quête actuelle")
    async def voir_quete(self, interaction: discord.Interaction):
        if not is_allowed("quetes", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Quêtes autorisé.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        quest = self.quests.get(uid)
        if not quest:
            await interaction.response.send_message("❌ Aucune quête en cours.", ephemeral=True)
            return
        etapes = quest["etapes"]
        current = quest["current"]
        text = f"**{quest['titre']}**\nÉtape actuelle: {etapes[current]}\n"
        if current > 0:
            text += "Étapes terminées: " + ", ".join(etapes[:current])
        await interaction.response.send_message(text, ephemeral=True)

    @safe_command
    @app_commands.command(name="valider_etape", description="Validez l'étape actuelle de votre quête")
    async def valider_etape(self, interaction: discord.Interaction):
        if not is_allowed("quetes", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Quêtes autorisé.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        quest = self.quests.get(uid)
        if not quest:
            await interaction.response.send_message("❌ Aucune quête en cours.", ephemeral=True)
            return
        quest["current"] += 1
        if quest["current"] >= len(quest["etapes"]):
            del self.quests[uid]
            await interaction.response.send_message("🎉 Quête terminée ! Bravo pour votre discipline !", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Étape validée ! Utilisez /voir_quete pour voir la suite.", ephemeral=True)

async def setup_quetes(bot: commands.Bot):
    await bot.add_cog(QuetesCog(bot))

# --------------------------------------------------
# MODULE VERROUILLÉ JUSQU'À RÉUSSITE (DISCIPLINE LOCK)
# --------------------------------------------------
class DisciplineLockCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.locked_users = {}  # { user_id: [channel_id, ...] }

    @safe_command
    @app_commands.command(name="activer_verrou", description="Activez le verrou de discipline sur vous")
    async def activer_verrou(self, interaction: discord.Interaction, channels: str):
        if not is_allowed("discipline_lock", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Discipline Lock autorisé.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        channel_ids = [c.strip() for c in channels.split(",") if c.strip()]
        self.locked_users[uid] = channel_ids
        await interaction.response.send_message("✅ Verrou activé. Vous ne pourrez pas parler dans les salons verrouillés jusqu'à réussite.", ephemeral=True)

    @safe_command
    @app_commands.command(name="valider_verrou", description="Déverrouillez vos salons verrouillés (après réussite)")
    async def valider_verrou(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        if uid in self.locked_users:
            del self.locked_users[uid]
            await interaction.response.send_message("✅ Verrou levé. Vous pouvez maintenant accéder aux salons.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Vous n'avez pas de verrou actif.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        uid = str(message.author.id)
        if uid in self.locked_users:
            if str(message.channel.id) in self.locked_users[uid]:
                try:
                    await message.delete()
                except Exception as e:
                    logging.error(e)

async def setup_discipline_lock(bot: commands.Bot):
    await bot.add_cog(DisciplineLockCog(bot))

# --------------------------------------------------
# MODULE SYSTÈME DE QUESTIONS PUISSANTES
# --------------------------------------------------
class QuestionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.questions = [
            "Qu’est-ce que tu fuis en ce moment ?",
            "Quel comportement as-tu envie de briser aujourd’hui ?"
        ]
        self.answers = {}  # { user_id: [ {date, reponse}, ... ] }
        self.bot.loop.create_task(self.daily_question_task())

    async def daily_question_task(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            now = datetime.datetime.now()
            # Envoi à 9h00 chaque jour
            if now.hour == 9 and now.minute == 0:
                for member in self.bot.guilds[0].members:
                    if not member.bot:
                        try:
                            q = random.choice(self.questions)
                            await member.send(f"❓ Question du jour: {q}\nRépondez avec /repondre_question <votre réponse>")
                        except Exception as e:
                            logging.error(f"Erreur envoi question à {member}: {e}")
                await asyncio.sleep(60)
            await asyncio.sleep(30)

    @safe_command
    @app_commands.command(name="repondre_question", description="Répondez à la question du jour")
    async def repondre_question(self, interaction: discord.Interaction, reponse: str):
        uid = str(interaction.user.id)
        self.answers.setdefault(uid, []).append({"date": time.time(), "reponse": reponse})
        await interaction.response.send_message("✅ Réponse enregistrée.", ephemeral=True)

async def setup_questions(bot: commands.Bot):
    await bot.add_cog(QuestionsCog(bot))

# --------------------------------------------------
# MODULE SYSTÈME DE COMBO
# --------------------------------------------------
class ComboCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.combo_data = {}  # { user_id: { "count": int, "last_time": float } }

    @safe_command
    @app_commands.command(name="combo_increment", description="Incrémentez votre combo (à appeler après une action)")
    async def combo_increment(self, interaction: discord.Interaction):
        if not is_allowed("combo", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Combo autorisé.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        now = time.time()
        combo = self.combo_data.get(uid, {"count": 0, "last_time": now})
        if now - combo["last_time"] > 300:
            combo["count"] = 0
        combo["count"] += 1
        combo["last_time"] = now
        self.combo_data[uid] = combo
        await interaction.response.send_message(f"✅ Combo incrémenté. Actuellement: {combo['count']}.", ephemeral=True)
        if combo["count"] >= 5:
            bonus = 20  # bonus XP
            await add_xp(interaction.user.id, bonus)
            try:
                role = discord.utils.get(interaction.guild.roles, name="ENRAGE ⚡")
                if role:
                    await interaction.user.add_roles(role)
                    await asyncio.sleep(60)
                    await interaction.user.remove_roles(role)
            except Exception as e:
                logging.error(e)
            self.combo_data[uid] = {"count": 0, "last_time": now}
            await interaction.followup.send(f"🎉 Combo complet ! Bonus XP: {bonus} et rôle ENRAGE attribué temporairement.", ephemeral=True)

    @safe_command
    @app_commands.command(name="combo_en_cours", description="Vérifiez votre combo actuel")
    async def combo_en_cours(self, interaction: discord.Interaction):
        if not is_allowed("combo", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Combo autorisé.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        combo = self.combo_data.get(uid, {"count": 0})
        await interaction.response.send_message(f"🔔 Votre combo actuel est: {combo['count']}.", ephemeral=True)

async def setup_combo(bot: commands.Bot):
    await bot.add_cog(ComboCog(bot))

# --------------------------------------------------
# MODULE GÉNÉRATEUR DE ROUTINES
# --------------------------------------------------
class RoutineGeneratorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @safe_command
    @app_commands.command(name="generer_routine", description="Génère une routine pour la journée")
    async def generer_routine(self, interaction: discord.Interaction):
        if not is_allowed("routine", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Routine autorisé.", ephemeral=True)
            return
        wake = f"{random.randint(5,9)}:00"
        pause = f"{random.randint(12,14)}:00"
        deep_work = f"{random.randint(9,11)}:00"
        sport = f"{random.randint(17,19)}:00"
        routine = f"Routine du jour:\n- Réveil: {wake}\n- Deep Work: {deep_work}\n- Pause déjeuner: {pause}\n- Sport: {sport}\n- Coupure écran: 21:00"
        await interaction.response.send_message(routine, ephemeral=True)

async def setup_routine(bot: commands.Bot):
    await bot.add_cog(RoutineGeneratorCog(bot))

# --------------------------------------------------
# MODULE OBSERVATEUR SILENCIEUX
# --------------------------------------------------
class ObservateurCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.observateurs = set()  # IDs des utilisateurs activant ce mode
        self.message_counts = {}
        self.bot.loop.create_task(self.observateur_loop())

    @safe_command
    @app_commands.command(name="activer_observateur", description="Activez le mode Observateur Silencieux")
    async def activer_observateur(self, interaction: discord.Interaction):
        if not is_allowed("observateur", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Observateur autorisé.", ephemeral=True)
            return
        self.observateurs.add(str(interaction.user.id))
        await interaction.response.send_message("✅ Mode Observateur activé.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        uid = str(message.author.id)
        if uid in self.observateurs:
            self.message_counts[uid] = self.message_counts.get(uid, 0) + 1

    async def observateur_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(3600)  # toutes les heures
            for uid in list(self.observateurs):
                count = self.message_counts.get(uid, 0)
                user = self.bot.get_user(int(uid))
                if user:
                    if count == 0:
                        try:
                            await user.send("⚡ Tu as été silencieux pendant 1 heure. Un petit rappel motivant!")
                        except Exception as e:
                            logging.error(e)
                    elif count > 20:
                        try:
                            await user.send("👏 Bravo pour ton activité, continue comme ça!")
                        except Exception as e:
                            logging.error(e)
                self.message_counts[uid] = 0

async def setup_observateur(bot: commands.Bot):
    await bot.add_cog(ObservateurCog(bot))

# --------------------------------------------------
# MODULE TEST DE DISCIPLINE
# --------------------------------------------------
class DisciplineTestCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @safe_command
    @app_commands.command(name="test_discipline", description="Testez votre discipline")
    async def test_discipline(self, interaction: discord.Interaction):
        if not is_allowed("discipline_test", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Test de Discipline autorisé.", ephemeral=True)
            return
        await interaction.response.send_message("❓ Veux-tu aller sur Insta ? (réponds par oui/non)", ephemeral=True)
        def check(m):
            return m.author.id == interaction.user.id and m.channel == interaction.channel
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=30)
            if msg.content.lower() in ["non", "n"]:
                await interaction.followup.send("✅ Discipline +. Bien joué !", ephemeral=True)
            else:
                await add_xp(interaction.user.id, -10)
                await interaction.followup.send("😅 Tu viens de perdre 10 XP mais c'est honnête.", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Temps écoulé.", ephemeral=True)

async def setup_discipline_test(bot: commands.Bot):
    await bot.add_cog(DisciplineTestCog(bot))

# --------------------------------------------------
# MODULE REACTION ROLE (déjà défini ci-dessus)
# --------------------------------------------------
# Nous avons déjà ajouté le module ReactionRoleCog plus haut.

# --------------------------------------------------
# MODULES ADMIN DIVERS (création de salons, rôles, etc.)
# --------------------------------------------------
@tree.command(name="creer_salon", description="Créez un ou plusieurs salons (admin)")
@safe_command
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(noms="Noms séparés par des virgules", categorie="Catégorie cible", type="text ou voice")
async def creer_salon(interaction: discord.Interaction, noms: str, categorie: discord.CategoryChannel, type: str):
    try:
        noms_list = [n.strip() for n in noms.split(",") if n.strip()]
        if not noms_list:
            await interaction.response.send_message("❌ Aucun nom fourni.", ephemeral=True)
            return
        created = []
        for nom in noms_list:
            if type.lower() == "text":
                ch = await interaction.guild.create_text_channel(name=nom, category=categorie)
            elif type.lower() == "voice":
                ch = await interaction.guild.create_voice_channel(name=nom, category=categorie)
            else:
                await interaction.response.send_message("❌ Type invalide.", ephemeral=True)
                return
            created.append(ch.mention)
        await interaction.response.send_message("✅ Salon(s) créé(s) : " + ", ".join(created), ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

@tree.command(name="creer_role", description="Créez un ou plusieurs rôles (admin)")
@safe_command
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(noms="Noms séparés par des virgules")
async def creer_role(interaction: discord.Interaction, noms: str):
    try:
        noms_list = [n.strip() for n in noms.split(",") if n.strip()]
        if not noms_list:
            await interaction.response.send_message("❌ Aucun nom fourni.", ephemeral=True)
            return
        created = []
        for nom in noms_list:
            role = await interaction.guild.create_role(name=nom)
            created.append(role.name)
        await interaction.response.send_message("✅ Rôle(s) créé(s) : " + ", ".join(created), ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

@tree.command(name="creer_categorie_privee", description="Créez une catégorie privée (admin)")
@safe_command
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(nom="Nom de la catégorie", role="Rôle ayant accès")
async def creer_categorie_privee(interaction: discord.Interaction, nom: str, role: discord.Role):
    try:
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            role: discord.PermissionOverwrite(view_channel=True)
        }
        cat = await interaction.guild.create_category(name=nom, overwrites=overwrites)
        await interaction.response.send_message(f"✅ Catégorie {cat.name} créée.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

# --------------------------------------------------
# SERVEUR KEEP-ALIVE
# --------------------------------------------------
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot actif et en ligne.')
    def log_message(self, format, *args):
        return

def keep_alive(port=10000):
    try:
        server = HTTPServer(('0.0.0.0', port), KeepAliveHandler)
        thread = threading.Thread(target=server.serve_forever, name="KeepAliveThread")
        thread.daemon = True
        thread.start()
        logging.info(f"✅ Serveur keep-alive lancé sur le port {port}")
    except Exception as e:
        logging.error(f"❌ Erreur lancement keep-alive : {e}")

keep_alive()

@bot.event
async def on_ready():
    try:
        logging.info(f"✅ Connecté en tant que {bot.user} (ID: {bot.user.id})")
    except Exception as e:
        logging.error(f"❌ Erreur on_ready: {e}")

# --------------------------------------------------
# MAIN – Chargement des données et lancement du bot
# --------------------------------------------------
async def main():
    global xp_data, messages_programmes, defis_data, pomodoro_data, goals_data, weekly_plan_data, reminders_data, quiz_data
    try:
        xp_data = await charger_json_async(XP_FILE)
        messages_programmes = await charger_json_async(MSG_FILE)
        defis_data = await charger_json_async(DEFIS_FILE)
        pomodoro_data = await charger_json_async(POMODORO_FILE)
        goals_data = await charger_json_async(GOALS_FILE)
        weekly_plan_data = await charger_json_async(WEEKLY_PLAN_FILE)
        reminders_data = await charger_json_async(REMINDERS_FILE)
        quiz_data = await charger_json_async(QUIZ_FILE)
    except Exception as e:
        logging.error(f"❌ Erreur chargement données: {e}")

    # Chargement de tous les modules
    await setup_reaction_roles(bot)
    await setup_pomodoro(bot)
    await setup_goals(bot)
    await setup_weekly_plan(bot)
    await setup_reminders(bot)
    await setup_quiz(bot)
    await setup_focus_group(bot)
    await setup_weekly_summary(bot)
    await setup_focus_mode(bot)
    await setup_focus_extreme(bot)
    await setup_channel_lock(bot)
    await setup_focus_protect(bot)
    await setup_sleep_mode(bot)
    await setup_aide(bot)
    await setup_citations(bot)
    await setup_emergency(bot)
    await setup_links(bot)
    await setup_chrono(bot)
    await setup_time_limiter(bot)
    await setup_recherches(bot)
    await setup_activity_drop(bot)
    await setup_bibliotheque(bot)
    await setup_smart_reactions(bot)
    await setup_quetes(bot)
    await setup_discipline_lock(bot)
    await setup_questions(bot)
    await setup_combo(bot)
    await setup_routine(bot)
    await setup_observateur(bot)
    await setup_discipline_test(bot)

    try:
        await bot.start(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        logging.error(f"❌ Erreur lancement bot: {e}")

asyncio.run(main())

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
import re
from discord.ext import commands, tasks
from discord import app_commands, TextStyle, PartialEmoji
from discord.ui import Modal, TextInput, View, Button
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo

# -------------------- Configuration du logging --------------------
logging.basicConfig(level=logging.INFO)

# -------------------- Configuration et persistance --------------------
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

# -------------------- Tâche vide pour la vérification programmée --------------------
@tasks.loop(minutes=1)
async def check_programmed_messages():
    pass

# -------------------- Décorateur de protection des commandes --------------------
def safe_command(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            import traceback
            traceback.print_exc()
            for arg in args:
                if isinstance(arg, discord.Interaction):
                    try:
                        if not arg.response.is_done():
                            await arg.response.send_message("❌ Une erreur interne est survenue. Veuillez réessayer plus tard.", ephemeral=True)
                    except Exception:
                        pass
                    break
    return wrapper

# -------------------- Variables persistantes --------------------
xp_data = {}
messages_programmes = {}
defis_data = {}

pomodoro_data = {}       # { user_id: { "total_focus": int, "session_count": int } }
goals_data = {}          # { user_id: [ { "id": str, "texte": str, "status": str }, ... ] }
weekly_plan_data = {}    # { user_id: [ "Priorité 1", "Priorité 2", ... ] }
reminders_data = {}      # { reminder_id: { "user_id": str, "time": str, "message": str, "daily": bool } }
quiz_data = {}           # { "questions": [ { "question": str, "choices": [str,...], "answer": int } ] }
quiz_results_data = {}   # { user_id: [ { "score": int, "total": int, "date": float } ] }
citations_data = {}      # { "citations": [ "Citation 1", "Citation 2", ... ] }
links_data = {}          # { "links": [ { "lien": str, "description": str, "public": bool } ] }

# Données pour les nouvelles fonctionnalités
discipline_personnelle_rules = {}  # { user_id: [rule, ...] }
season_data = {}                   # Détails de la saison actuelle
double_profile = {}                # { user_id: {"current": 1 or 2, "profile1": {...}, "profile2": {...}} }
isolation_status = {}              # { user_id: {"active": bool, "end_time": timestamp, "lost_roles": [role_ids]} }
journal_de_guerre = []             # Liste de logs publics
tribunal_confessions = []           # Liste de confessions
quêtes_identite = {}               # { user_id: response }
univers_paralleles = {"active": False, "theme": None}
hall_of_mastery = []               # Liste d'utilisateurs (simulée)
livres_savoir = []                 # Liste de livres partagés
protocoles = {}                    # { nom: description }
promesses = []                     # Liste des promesses publiques
rpg_profiles = {}                  # { user_id: {"volonte": int, "tentation": int, "niveau": int} }
eclipse_mentale = {"active": False, "end_time": None}
legacy_messages = []               # Liste des messages d’héritage

# -------------------- Configuration récap hebdomadaire --------------------
weekly_recap_config = {
    "channel_id": None,
    "time": "18:00",
    "day": "Sunday",
    "role_id": None
}

# -------------------- Bot, Intents et configuration des canaux --------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True
intents.voice_states = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.reaction_roles = {}
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
        # Définir les canaux autorisés pour chaque module (clés utilisées par chaque cog)
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
            "discipline_test": None,
            "discipline_personnelle": None,
            "saison": None,
            "commandant": None,
            "double_compte": None,
            "isolation": None,
            "tempete": None,
            "version_parallele": None,
            "journal_guerre": None,
            "tribunal": None,
            "quetes_identite": None,
            "univers_paralleles": None,
            "hall_of_mastery": None,
            "chrono_discipline": None,
            "livres_savoir": None,
            "jour_zero": None,
            "forge_protocoles": None,
            "mur_promesses": None,
            "rpg_discipline": None,
            "eclipse_mentale": None,
            "miroir_futur": None,
            "monnaie_mentale": None,
            "rituel_vocal": None,
            "chasseur_distraction": None,
            "influence_mentale": None,
            "base_secrete": None,
            "eveil_progressif": None,
            "rituel_silence": None,
            "commandements": None,
            "archives_mentales": None,
            "pacte_sang": None,
            "duel_mental": None,
            "codex": None,
            "roles_totem": None,
            "visionnaire": None,
            "legacy": None
        }
        # Nouvelle configuration pour les mentors – une liste qui pourra contenir des dictionnaires de type {'type': 'role'/'member'/'channel', 'id': <id>}
        self.mentor_targets = []
        
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

# -------------------- Handler global des erreurs --------------------
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    import traceback
    traceback.print_exc()
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Une erreur interne est survenue. Veuillez réessayer plus tard.", ephemeral=True)
    except Exception as e:
        logging.error(f"Erreur dans le handler global : {e}")

# -------------------- COMMANDES ADMIN POUR DÉFINIR LES SALONS --------------------
@tree.command(name="set_channel", description="Définit le canal autorisé pour un module (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(module="Nom du module", channel="Salon où la commande est accessible")
async def set_channel(interaction: discord.Interaction, module: str, channel: discord.TextChannel):
    module = module.lower()
    if module in bot.allowed_channels:
        bot.allowed_channels[module] = str(channel.id)
        await interaction.response.send_message(f"✅ Canal pour {module} configuré : {channel.mention}", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Module inconnu: {module}", ephemeral=True)

# -------------------- NOUVELLE COG DE CONFIGURATION --------------------
class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @safe_command
    @app_commands.command(name="set_mentors", description="Définir les mentors pour les alertes (admin). Vous pouvez spécifier une liste de mentions (rôles, membres ou salons) séparées par un espace.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_mentors(self, interaction: discord.Interaction, mentors: str):
        """
        Exemple d'entrée : "@MentorRole @Membre1 <#123456789012345678>"
        """
        mentor_list = []
        # Recherche des mentions de rôles (<@&ID>), membres (<@!ID> ou <@ID>) et salons (<#ID>)
        role_mentions = re.findall(r"<@&(\d+)>", mentors)
        member_mentions = re.findall(r"<@!?(\d+)>", mentors)
        channel_mentions = re.findall(r"<#(\d+)>", mentors)
        for role_id in role_mentions:
            mentor_list.append({"type": "role", "id": int(role_id)})
        for member_id in member_mentions:
            # Pour éviter de repasser sur les mentions de rôle (qui peuvent aussi apparaître comme <@ID>)
            if member_id not in role_mentions:
                mentor_list.append({"type": "member", "id": int(member_id)})
        for channel_id in channel_mentions:
            mentor_list.append({"type": "channel", "id": int(channel_id)})
        self.bot.mentor_targets = mentor_list
        await interaction.response.send_message("✅ Mentors mis à jour.", ephemeral=True)
    
    @safe_command
    @app_commands.command(name="set_xp_config", description="Configurer le système XP (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_xp_config(self, interaction: discord.Interaction, config: str):
        """
        Mettez à jour la configuration XP au format JSON.
        Exemples : 
        {"xp_per_message": 15, "announcement_channel": "123456789012345678"}
        """
        try:
            new_config = json.loads(config)
            bot.xp_config.update(new_config)
            await interaction.response.send_message("✅ XP configuration mise à jour.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

async def setup_config(bot: commands.Bot):
    await bot.add_cog(ConfigCog(bot))

# -------------------- MODULES EXISTANTS (déjà fournis dans la version antérieure) --------------------
# (Les modules Pomodoro, Goals, Weekly Plan, Reminders, Quiz, Focus Group, Weekly Summary, Aide, Citations,
# EmergencyAlert, ReactionRole, Channels Lock, Focus Protect, Sleep Mode, Recherches Perso, Activity Drop,
# Bibliothèque, Smart Reactions, Quêtes, Discipline Lock, Questions, Combo, Routine)
# Ils sont identiques à ceux de la version précédente et sont inclus ci-dessous :

# --- Pomodoro Cog ---
pomodoro_config = {"focus": 25, "short_break": 5, "long_break": 15, "cycles_before_long_break": 4}
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
                await dm.send(f"🚀 **Focus** : Début d'une session de {focus_duration} minutes.")
                msg = await dm.send(f"⏱️ {focus_duration} minutes restantes.")
                for remaining in range(focus_duration, 0, -1):
                    await asyncio.sleep(60)
                    try:
                        await msg.edit(content=f"⏱️ {remaining-1} minutes restantes.")
                    except Exception:
                        pass
                session_count += 1
                uid = str(user.id)
                stats = pomodoro_data.get(uid, {"total_focus": 0, "session_count": 0})
                stats["total_focus"] += focus_duration
                stats["session_count"] += 1
                pomodoro_data[uid] = stats
                await sauvegarder_json_async(POMODORO_FILE, pomodoro_data)
                await dm.send("✅ Focus terminé ! Début de la pause courte.")
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
    @app_commands.command(name="focus_start", description="Démarrer une session Pomodoro")
    async def focus_start(self, interaction: discord.Interaction, focus: int, short_break: int, long_break: int):
        if not is_allowed("pomodoro", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Pomodoro.", ephemeral=True)
            return
        user = interaction.user
        if str(user.id) in active_pomodoro_sessions:
            await interaction.response.send_message("❌ Une session est déjà active.", ephemeral=True)
            return
        task = self.bot.loop.create_task(self.pomodoro_cycle(user, interaction.channel, focus, short_break, long_break))
        active_pomodoro_sessions[str(user.id)] = task
        await interaction.response.send_message("✅ Session démarrée. Vérifiez vos DM.", ephemeral=True)
    @safe_command
    @app_commands.command(name="stop_focus", description="Arrêter sa session Pomodoro")
    async def stop_focus(self, interaction: discord.Interaction):
        if not is_allowed("pomodoro", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Pomodoro.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        if uid in active_pomodoro_sessions:
            active_pomodoro_sessions[uid].cancel()
            del active_pomodoro_sessions[uid]
            await interaction.response.send_message("✅ Session stoppée.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Aucune session active.", ephemeral=True)
    @safe_command
    @app_commands.command(name="focus_stats", description="Afficher ses statistiques Pomodoro")
    async def focus_stats(self, interaction: discord.Interaction):
        if not is_allowed("pomodoro", interaction):
            await interaction.response.send_message("❌ Utilisez cette commande dans le canal Pomodoro.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        stats = pomodoro_data.get(uid, {"total_focus": 0, "session_count": 0})
        await interaction.response.send_message(f"🔹 Sessions : {stats['session_count']}, Total focus : {stats['total_focus']} minutes.", ephemeral=True)
    @safe_command
    @app_commands.command(name="set_pomodoro_config", description="Configurer Pomodoro (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_pomodoro_config(self, interaction: discord.Interaction, focus: int, short_break: int, long_break: int, cycles: int):
        pomodoro_config["focus"] = focus
        pomodoro_config["short_break"] = short_break
        pomodoro_config["long_break"] = long_break
        pomodoro_config["cycles_before_long_break"] = cycles
        await interaction.response.send_message("✅ Configuration mise à jour.", ephemeral=True)
async def setup_pomodoro(bot: commands.Bot):
    await bot.add_cog(PomodoroCog(bot))

# --- Goals Cog (Objectifs personnels) ---
class GoalsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="ajouter_objectif", description="Ajouter un objectif personnel")
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
    @app_commands.command(name="mes_objectifs", description="Afficher ses objectifs")
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
        await interaction.response.send_message("📝 Objectifs :\n" + "\n".join(lines), ephemeral=True)
    @safe_command
    @app_commands.command(name="objectif_fait", description="Marquer un objectif comme terminé")
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
        await interaction.response.send_message("❌ Objectif introuvable.", ephemeral=True)
    @safe_command
    @app_commands.command(name="supprimer_objectif", description="Supprimer un objectif")
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

# --- Weekly Plan Cog ---
class WeeklyPlanModal(Modal, title="Planifiez votre semaine"):
    def __init__(self):
        super().__init__(timeout=None)
        self.priorites = TextInput(label="Priorités", style=TextStyle.paragraph, placeholder="Priorité 1, Priorité 2, ...", required=True, max_length=500)
        self.add_item(self.priorites)
    async def on_submit(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        plan = [p.strip() for p in self.priorites.value.split(",") if p.strip()]
        if not (3 <= len(plan) <= 5):
            await interaction.response.send_message("❌ Entrez entre 3 et 5 priorités.", ephemeral=True)
            return
        weekly_plan_data[uid] = plan
        await sauvegarder_json_async(WEEKLY_PLAN_FILE, weekly_plan_data)
        await interaction.response.send_message("✅ Planning enregistré.", ephemeral=True)
class WeeklyPlanCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="planifier_semaine", description="Planifier sa semaine")
    async def planifier_semaine(self, interaction: discord.Interaction):
        if not is_allowed("weekly_plan", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Planning.", ephemeral=True)
            return
        await interaction.response.send_modal(WeeklyPlanModal())
    @safe_command
    @app_commands.command(name="ma_semaine", description="Afficher son planning")
    async def ma_semaine(self, interaction: discord.Interaction):
        if not is_allowed("weekly_plan", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Planning.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        plan = weekly_plan_data.get(uid, [])
        if not plan:
            await interaction.response.send_message("Aucun planning défini.", ephemeral=True)
        else:
            await interaction.response.send_message("📅 Votre planning :\n" + "\n".join(plan), ephemeral=True)
async def setup_weekly_plan(bot: commands.Bot):
    await bot.add_cog(WeeklyPlanCog(bot))

# --- Reminders Cog ---
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
                            await user.send(f"🔔 Rappel : {rem['message']}")
                        if not rem.get("daily", False):
                            to_remove.append(rid)
                except Exception as e:
                    logging.error(f"Erreur check_reminders: {e}")
            for rid in to_remove:
                reminders_data.pop(rid, None)
            if to_remove:
                await sauvegarder_json_async(REMINDERS_FILE, reminders_data)
            await asyncio.sleep(60)
    @safe_command
    @app_commands.command(name="ajouter_rappel", description="Ajouter un rappel personnel")
    async def ajouter_rappel(self, interaction: discord.Interaction, time_str: str, message: str, daily: bool = False):
        if not is_allowed("reminders", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Rappels.", ephemeral=True)
            return
        try:
            datetime.datetime.strptime(time_str, "%H:%M")
        except ValueError:
            await interaction.response.send_message("❌ Heure invalide (HH:MM).", ephemeral=True)
            return
        rid = str(uuid.uuid4())
        reminders_data[rid] = {"user_id": str(interaction.user.id), "time": time_str, "message": message, "daily": daily}
        await sauvegarder_json_async(REMINDERS_FILE, reminders_data)
        await interaction.response.send_message("✅ Rappel ajouté.", ephemeral=True)
    @safe_command
    @app_commands.command(name="mes_rappels", description="Afficher ses rappels")
    async def mes_rappels(self, interaction: discord.Interaction):
        if not is_allowed("reminders", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Rappels.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        lines = [f"`{rid}` - {rem['time']}: {rem['message']} ({'daily' if rem.get('daily') else 'one-time'})"
                 for rid, rem in reminders_data.items() if rem["user_id"] == uid]
        if lines:
            await interaction.response.send_message("🔔 Vos rappels :\n" + "\n".join(lines), ephemeral=True)
        else:
            await interaction.response.send_message("Aucun rappel.", ephemeral=True)
    @safe_command
    @app_commands.command(name="supprimer_rappel", description="Supprimer un rappel")
    async def supprimer_rappel(self, interaction: discord.Interaction, rid: str):
        if rid in reminders_data and reminders_data[rid]["user_id"] == str(interaction.user.id):
            reminders_data.pop(rid)
            await sauvegarder_json_async(REMINDERS_FILE, reminders_data)
            await interaction.response.send_message("✅ Rappel supprimé.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Rappel introuvable.", ephemeral=True)
async def setup_reminders(bot: commands.Bot):
    await bot.add_cog(RemindersCog(bot))

# --- Quiz Cog ---
class QuizCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="ajouter_quizz", description="Définir un quiz (admin)")
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
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
    @safe_command
    @app_commands.command(name="lancer_quizz", description="Lancer le quiz")
    async def lancer_quizz(self, interaction: discord.Interaction):
        if not is_allowed("quiz", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Quiz.", ephemeral=True)
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

# --- Focus Group Cog ---
class FocusGroupCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.focus_participants = set()
    @safe_command
    @app_commands.command(name="ping_focus", description="Proposer une session de focus groupe")
    async def ping_focus(self, interaction: discord.Interaction):
        view = View(timeout=60)
        btn = Button(label="Je participe", style=discord.ButtonStyle.success)
        async def btn_callback(inter: discord.Interaction):
            self.focus_participants.add(inter.user.id)
            await inter.response.send_message("✅ Vous êtes inscrit.", ephemeral=True)
        btn.callback = btn_callback
        view.add_item(btn)
        await interaction.response.send_message("🔔 Session focus groupe proposée !", view=view)
    @safe_command
    @app_commands.command(name="set_focus_channel", description="Définir le canal de focus groupe (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_focus_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.bot.allowed_channels["focus_group"] = str(channel.id)
        await interaction.response.send_message(f"✅ Canal focus groupe configuré : {channel.mention}", ephemeral=True)
async def setup_focus_group(bot: commands.Bot):
    await bot.add_cog(FocusGroupCog(bot))

# --- Weekly Summary Cog ---
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
Citation de la semaine : {citation if citation else 'Aucune'}"""
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
                logging.error(f"Erreur weekly_summary_task: {e}")
            await asyncio.sleep(60)
    @safe_command
    @app_commands.command(name="set_recap_config", description="Configurer le récap (admin)")
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

# --- Aide Cog ---
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
        await interaction.response.send_message(f"✅ Demande d'aide enregistrée. Canaux: {text_ch.mention} & {voice_ch.mention}", ephemeral=True)
class AideCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="qui_a_besoin", description="Déclarez un besoin d'aide")
    async def qui_a_besoin(self, interaction: discord.Interaction):
        if not is_allowed("aide", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Aide.", ephemeral=True)
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
            await inter.response.send_message(f"✅ Canal créé: {text_ch.mention}", ephemeral=True)
        async def aider_callback(inter: discord.Interaction):
            await inter.response.send_message("✅ Vous serez notifié en cas de besoin.", ephemeral=True)
        btn_besoin.callback = besoin_callback
        btn_aider.callback = aider_callback
        view.add_item(btn_besoin)
        view.add_item(btn_aider)
        await interaction.response.send_message("🔔 Choisissez une option :", view=view, ephemeral=True)
    @safe_command
    @app_commands.command(name="j_ai_besoin_d_aide", description="Exprimez précisément votre besoin d'aide")
    async def j_ai_besoin_d_aide(self, interaction: discord.Interaction):
        if not is_allowed("aide", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Aide.", ephemeral=True)
            return
        await interaction.response.send_modal(AideModal())
async def setup_aide(bot: commands.Bot):
    await bot.add_cog(AideCog(bot))

# --- Citations Cog ---
class CitationsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.citations = citations_data.get("citations", [])
    @safe_command
    @app_commands.command(name="ajouter_citation", description="Ajoutez une citation")
    async def ajouter_citation(self, interaction: discord.Interaction, citation: str):
        self.citations.append(citation)
        citations_data["citations"] = self.citations
        await sauvegarder_json_async(CITATIONS_FILE, citations_data)
        await interaction.response.send_message("✅ Citation ajoutée.", ephemeral=True)
    @safe_command
    @app_commands.command(name="mes_citations", description="Afficher vos citations")
    async def mes_citations(self, interaction: discord.Interaction):
        if not self.citations:
            await interaction.response.send_message("Aucune citation.", ephemeral=True)
            return
        await interaction.response.send_message("💬 Citations :\n" + "\n".join(self.citations), ephemeral=True)
async def setup_citations(bot: commands.Bot):
    global citations_data
    citations_data = await charger_json_async(CITATIONS_FILE)
    await bot.add_cog(CitationsCog(bot))

# --- Emergency Alert Cog ---
class EmergencyAlertCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="besoin_d_aide", description="Envoyer une alerte aux mentors")
    async def besoin_d_aide(self, interaction: discord.Interaction, message: str):
        alert = f"⚠️ Urgence de {interaction.user.mention}: {message}"
        # Utiliser la configuration dynamique des mentors
        if not self.bot.mentor_targets:
            await interaction.response.send_message("❌ Aucun mentor défini. Veuillez configurer via /set_mentors.", ephemeral=True)
            return
        sent = False
        for target in self.bot.mentor_targets:
            if target["type"] == "role":
                role = interaction.guild.get_role(target["id"])
                if role:
                    alert_message = f"{role.mention}\n{alert}"
                    # On envoie dans tous les salons autorisés pour les alertes (ou directement dans le canal courant)
                    try:
                        await interaction.channel.send(alert_message)
                        sent = True
                    except Exception as e:
                        logging.error(f"Erreur envoi alerte role: {e}")
            elif target["type"] == "member":
                member = interaction.guild.get_member(target["id"])
                if member:
                    try:
                        await member.send(alert)
                        sent = True
                    except Exception as e:
                        logging.error(f"Erreur DM mentor membre: {e}")
            elif target["type"] == "channel":
                channel = self.bot.get_channel(target["id"])
                if channel:
                    try:
                        await channel.send(alert)
                        sent = True
                    except Exception as e:
                        logging.error(f"Erreur envoi alerte canal: {e}")
        if sent:
            await interaction.response.send_message("✅ Alerte envoyée.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Aucun mentor joignable.", ephemeral=True)
async def setup_emergency(bot: commands.Bot):
    await bot.add_cog(EmergencyAlertCog(bot))

# --- Reaction Role Cog ---
class ReactionRoleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reaction_roles = {}
    @safe_command
    @app_commands.command(name="add_reaction_role", description="Ajouter une réaction role (admin)")
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

# --- Channel Lock Cog ---
class ChannelLockCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="lock", description="Verrouiller un salon (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def lock(self, interaction: discord.Interaction, channel: discord.TextChannel):
        try:
            await channel.set_permissions(interaction.guild.default_role, view_channel=False)
            await interaction.response.send_message(f"✅ {channel.mention} verrouillé.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
    @safe_command
    @app_commands.command(name="unlock", description="Déverrouiller un salon (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def unlock(self, interaction: discord.Interaction, channel: discord.TextChannel):
        try:
            await channel.set_permissions(interaction.guild.default_role, overwrite=None)
            await interaction.response.send_message(f"✅ {channel.mention} déverrouillé.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
async def setup_channel_lock(bot: commands.Bot):
    await bot.add_cog(ChannelLockCog(bot))

# --- Focus Protect Cog ---
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
    @app_commands.command(name="focus_protect", description="Activer Protect Focus pour X minutes")
    async def focus_protect_cmd(self, interaction: discord.Interaction, durée: int):
        if not is_allowed("pomodoro", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Protect Focus.", ephemeral=True)
            return
        focus_protect[str(interaction.user.id)] = time.time() + durée * 60
        await interaction.response.send_message(f"✅ Protect Focus activé pour {durée} minutes.", ephemeral=True)
async def setup_focus_protect(bot: commands.Bot):
    await bot.add_cog(FocusProtectCog(bot))

# --- Sleep Mode Cog ---
last_activity = {}
exempt_veille = set()
@bot.event
async def on_message(message):
    try:
        if not message.author.bot:
            last_activity[str(message.author.id)] = time.time()
        await bot.process_commands(message)
    except Exception as e:
        logging.error(f"Erreur on_message: {e}")
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
    @app_commands.command(name="desactiver_veille", description="Désactiver la veille pour soi")
    async def desactiver_veille(self, interaction: discord.Interaction):
        exempt_veille.add(str(interaction.user.id))
        await interaction.response.send_message("✅ Veille désactivée.", ephemeral=True)
async def setup_sleep_mode(bot: commands.Bot):
    await bot.add_cog(SleepModeCog(bot))

# --- Recherches Perso Cog ---
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
                            await user.send(f"🔍 Suivi de ta recherche sur '{recherche['topic']}'. Pense à noter tes avancées!")
                        except Exception as e:
                            logging.error(f"Erreur DM recherche: {e}")
                    recherche["next_dm_time"] = now + 3600
            await asyncio.sleep(60)
    @safe_command
    @app_commands.command(name="nouvelle_recherche", description="Démarrer une nouvelle recherche perso")
    async def nouvelle_recherche(self, interaction: discord.Interaction, sujet: str):
        if not is_allowed("recherche_personnelle", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Recherches Perso.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        self.active_recherches[uid] = {"topic": sujet, "next_dm_time": time.time() + 3600}
        await interaction.response.send_message(f"✅ Recherche '{sujet}' démarrée. Suivi en DM.", ephemeral=True)
    @safe_command
    @app_commands.command(name="publier_recherche", description="Publier ses résultats de recherche")
    async def publier_recherche(self, interaction: discord.Interaction, contenu: str):
        if not is_allowed("recherche_personnelle", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Recherches Perso.", ephemeral=True)
            return
        channel_id = bot.allowed_channels.get("recherche_personnelle")
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                topic = self.active_recherches.get(str(interaction.user.id), {}).get("topic", "Inconnu")
                await channel.send(f"🔍 {interaction.user.mention} partage ses résultats sur '{topic}':\n{contenu}")
                await interaction.response.send_message("✅ Recherche publiée.", ephemeral=True)
                return
        await interaction.response.send_message("❌ Canal non configuré par admin.", ephemeral=True)
async def setup_recherches(bot: commands.Bot):
    await bot.add_cog(RecherchesPersoCog(bot))

# --- Activity Drop Cog ---
class ActivityDropCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.activity_counts = {}
        self.chute_disabled = set()
        self.bot.loop.create_task(self.activity_monitor_loop())
    @safe_command
    @app_commands.command(name="desactiver_chute", description="Désactiver les alertes de chute d'activité")
    async def desactiver_chute(self, interaction: discord.Interaction):
        if not is_allowed("activity_drop", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Chute d'activité.", ephemeral=True)
            return
        self.chute_disabled.add(str(interaction.user.id))
        await interaction.response.send_message("✅ Alertes désactivées.", ephemeral=True)
    async def activity_monitor_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(3600)
            for uid, count in list(self.activity_counts.items()):
                if uid in self.chute_disabled:
                    continue
                if count < 5:
                    user = self.bot.get_user(int(uid))
                    if user:
                        try:
                            await user.send("💡 Tu es moins actif ces derniers temps. Tu peux rebondir!")
                        except Exception as e:
                            logging.error(f"Erreur DM activité drop: {e}")
            self.activity_counts = {}
    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.author.bot:
            uid = str(message.author.id)
            self.activity_counts[uid] = self.activity_counts.get(uid, 0) + 1
async def setup_activity_drop(bot: commands.Bot):
    await bot.add_cog(ActivityDropCog(bot))

# --- Bibliothèque Cog ---
class BibliothequeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.biblio = []
    @safe_command
    @app_commands.command(name="proposer_ressource", description="Proposer une ressource utile")
    async def proposer_ressource(self, interaction: discord.Interaction, lien: str, description: str):
        if not is_allowed("bibliotheque", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Bibliothèque.", ephemeral=True)
            return
        self.biblio.append({"lien": lien, "description": description})
        unlock = ""
        if len(self.biblio) % 5 == 0:
            unlock = "🎉 Nouvelle section débloquée!"
        await interaction.response.send_message(f"✅ Ressource proposée. {unlock}", ephemeral=True)
    @safe_command
    @app_commands.command(name="voir_bibliotheque", description="Voir la bibliothèque communautaire")
    async def voir_bibliotheque(self, interaction: discord.Interaction):
        if not is_allowed("bibliotheque", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Bibliothèque.", ephemeral=True)
            return
        if not self.biblio:
            await interaction.response.send_message("Aucune ressource.", ephemeral=True)
            return
        lines = [f"- {entry['description']}: {entry['lien']}" for entry in self.biblio]
        await interaction.response.send_message("📚 Bibliothèque :\n" + "\n".join(lines), ephemeral=True)
async def setup_bibliotheque(bot: commands.Bot):
    await bot.add_cog(BibliothequeCog(bot))

# --- Smart Reactions Cog ---
class SmartReactionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="activer_reactions_smart", description="Activer les réactions smart (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def activer_reactions_smart(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.bot.allowed_channels["reactions_smart"] = str(channel.id)
        await interaction.response.send_message(f"✅ Réactions smart activées dans {channel.mention}", ephemeral=True)
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if self.bot.allowed_channels.get("reactions_smart") == str(message.channel.id):
            content = message.content.lower()
            if any(w in content for w in ["victoire", "gagné", "réussi"]):
                try:
                    await message.add_reaction("🎉")
                except Exception as e:
                    logging.error(e)
            elif any(w in content for w in ["plaint", "problème", "découragé"]):
                try:
                    await message.channel.send(f"{message.author.mention} Courage, tu peux y arriver!")
                except Exception as e:
                    logging.error(e)
async def setup_smart_reactions(bot: commands.Bot):
    await bot.add_cog(SmartReactionsCog(bot))

# --- Quêtes Cog ---
class QuetesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.quests = {}
    @safe_command
    @app_commands.command(name="commencer_quete", description="Commencer une quête")
    async def commencer_quete(self, interaction: discord.Interaction):
        if not is_allowed("quetes", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Quêtes.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        if uid in self.quests:
            await interaction.response.send_message("❌ Quête déjà en cours.", ephemeral=True)
            return
        quest = {
            "titre": "Mission : Reprendre le contrôle",
            "etapes": ["Fixer 3 objectifs", "Faire 2 pomodoros", "Écrire un log de fin de journée"],
            "current": 0
        }
        self.quests[uid] = quest
        await interaction.response.send_message("✅ Quête commencée !", ephemeral=True)
    @safe_command
    @app_commands.command(name="voir_quete", description="Voir sa quête actuelle")
    async def voir_quete(self, interaction: discord.Interaction):
        if not is_allowed("quetes", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Quêtes.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        quest = self.quests.get(uid)
        if not quest:
            await interaction.response.send_message("❌ Aucune quête en cours.", ephemeral=True)
            return
        text = f"**{quest['titre']}**\nÉtape actuelle: {quest['etapes'][quest['current']]}"
        await interaction.response.send_message(text, ephemeral=True)
    @safe_command
    @app_commands.command(name="valider_etape", description="Valider l'étape actuelle")
    async def valider_etape(self, interaction: discord.Interaction):
        if not is_allowed("quetes", interaction):
            await interaction.response.send_message("❌ Utilisez le canal Quêtes.", ephemeral=True)
            return
        uid = str(interaction.user.id)
        quest = self.quests.get(uid)
        if not quest:
            await interaction.response.send_message("❌ Aucune quête en cours.", ephemeral=True)
            return
        quest["current"] += 1
        if quest["current"] >= len(quest["etapes"]):
            del self.quests[uid]
            await interaction.response.send_message("🎉 Quête terminée !", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Étape validée.", ephemeral=True)
async def setup_quetes(bot: commands.Bot):
    await bot.add_cog(QuetesCog(bot))

# --- Discipline Personnelle Cog ---
class DisciplinePersonnelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rules = {}  # { user_id: [règle, ...] }
    @safe_command
    @app_commands.command(name="ajouter_regle", description="Ajouter une règle personnelle")
    async def ajouter_regle(self, interaction: discord.Interaction, regle: str):
        uid = str(interaction.user.id)
        self.rules.setdefault(uid, []).append(regle)
        await interaction.response.send_message("✅ Règle ajoutée.", ephemeral=True)
    @safe_command
    @app_commands.command(name="liste_regles", description="Afficher vos règles")
    async def liste_regles(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        regles = self.rules.get(uid, [])
        if not regles:
            await interaction.response.send_message("Aucune règle définie.", ephemeral=True)
        else:
            await interaction.response.send_message("📜 Vos règles:\n" + "\n".join(regles), ephemeral=True)
async def setup_discipline_personnelle(bot: commands.Bot):
    await bot.add_cog(DisciplinePersonnelCog(bot))

# --- Saison Cog ---
class SaisonCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="definir_saison", description="Définir la saison actuelle (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def definir_saison(self, interaction: discord.Interaction, theme: str, duree_jours: int):
        season_data.clear()
        season_data.update({"theme": theme, "duration": duree_jours, "start": time.time()})
        await interaction.response.send_message(f"✅ Saison définie : {theme} pour {duree_jours} jours.", ephemeral=True)
    @safe_command
    @app_commands.command(name="saison_info", description="Afficher la saison actuelle")
    async def saison_info(self, interaction: discord.Interaction):
        if season_data:
            await interaction.response.send_message(f"🌟 Thème : {season_data.get('theme')}, Durée : {season_data.get('duration')} jours.", ephemeral=True)
        else:
            await interaction.response.send_message("Aucune saison définie.", ephemeral=True)
async def setup_saison(bot: commands.Bot):
    await bot.add_cog(SaisonCog(bot))

# --- Commandant Cog ---
class CommandantCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.commandant_mode = False
    @safe_command
    @app_commands.command(name="activer_commandant", description="Activer le mode Commandant (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def activer_commandant(self, interaction: discord.Interaction):
        self.commandant_mode = True
        await interaction.response.send_message("✅ Mode Commandant activé pour cette semaine.", ephemeral=True)
    @safe_command
    @app_commands.command(name="verifier_commandant", description="Vérifier le mode Commandant")
    async def verifier_commandant(self, interaction: discord.Interaction):
        msg = "activé" if self.commandant_mode else "désactivé"
        await interaction.response.send_message(f"Le mode Commandant est {msg}.", ephemeral=True)
async def setup_commandant(bot: commands.Bot):
    await bot.add_cog(CommandantCog(bot))

# --- Double Compte Cog ---
class DoubleCompteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="switch_ego", description="Basculer vers votre autre profil (alter ego)")
    async def switch_ego(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        profile = double_profile.get(uid, {"current": 1, "profile1": {}, "profile2": {}})
        profile["current"] = 2 if profile["current"] == 1 else 1
        double_profile[uid] = profile
        await interaction.response.send_message(f"✅ Vous êtes maintenant sur le profil alter ego #{profile['current']}.", ephemeral=True)
async def setup_double_compte(bot: commands.Bot):
    await bot.add_cog(DoubleCompteCog(bot))

# --- Isolation Cog ---
class IsolationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="activer_isolation", description="Activer l'isolation volontaire pour X jours")
    async def activer_isolation(self, interaction: discord.Interaction, jours: int):
        uid = str(interaction.user.id)
        end_time = time.time() + jours * 24 * 3600
        # Simuler la suppression temporaire des rôles sociaux
        isolation_status[uid] = {"active": True, "end_time": end_time, "lost_roles": []}
        await interaction.response.send_message(f"✅ Isolation activée pour {jours} jours.", ephemeral=True)
async def setup_isolation(bot: commands.Bot):
    await bot.add_cog(IsolationCog(bot))

# --- Tempête Cog ---
class TempeteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.loop.create_task(self.random_tempete())
    async def random_tempete(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            await asyncio.sleep(3600)
            if random.random() < 0.2:  # 20% de chance par heure
                # Envoyer un message de tempête dans le canal défini
                channel_id = bot.allowed_channels.get("tempete")
                if channel_id:
                    channel = self.bot.get_channel(int(channel_id))
                    if channel:
                        await channel.send("🌀 Tempête mentale : Une vague de fatigue traverse la base... Envoyez /resister pour prouver votre force!")
            await asyncio.sleep(10)
    @safe_command
    @app_commands.command(name="resister", description="Répondre à une tempête mentale")
    async def resister(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ Résistance validée! Tu as surmonté la tempête.", ephemeral=True)
async def setup_tempete(bot: commands.Bot):
    await bot.add_cog(TempeteCog(bot))

# --- Version Parallèle Cog ---
class VersionParalleleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="simuler_autre_toi", description="Générer une version parallèle de vous-même")
    async def simuler_autre_toi(self, interaction: discord.Interaction):
        await interaction.response.send_message("😈 Voici votre version parallèle : Plus audacieux, plus performant... Un peu plus agressif. Motivation renforcée!", ephemeral=True)
async def setup_version_parallele(bot: commands.Bot):
    await bot.add_cog(VersionParalleleCog(bot))

# --- Journal de Guerre Cog ---
class JournalGuerreCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="publier_journal", description="Publier son log de bataille")
    async def publier_journal(self, interaction: discord.Interaction, log: str):
        journal_de_guerre.append({"user": interaction.user.name, "log": log, "time": time.time()})
        await interaction.response.send_message("✅ Journal de Guerre publié.", ephemeral=True)
async def setup_journal_guerre(bot: commands.Bot):
    await bot.add_cog(JournalGuerreCog(bot))

# --- Tribunal du Mental Cog ---
class TribunalCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="confesser", description="Confesser une erreur")
    async def confesser(self, interaction: discord.Interaction, confession: str):
        tribunal_confessions.append({"user": interaction.user.name, "confession": confession, "time": time.time()})
        await interaction.response.send_message("✅ Confession enregistrée. Le tribunal statuera.", ephemeral=True)
async def setup_tribunal(bot: commands.Bot):
    await bot.add_cog(TribunalCog(bot))

# --- Quêtes d’Identité Cog ---
class QuetesIdentiteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="queteridentite", description="Répondre à la grande question identitaire")
    async def queteridentite(self, interaction: discord.Interaction, reponse: str):
        quêtes_identite[str(interaction.user.id)] = reponse
        await interaction.response.send_message("✅ Réponse enregistrée dans votre grimoire intérieur.", ephemeral=True)
async def setup_quetes_identite(bot: commands.Bot):
    await bot.add_cog(QuetesIdentiteCog(bot))

# --- Univers Parallèles Cog ---
class UniversParallelesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="changer_univers", description="Changer le thème du serveur")
    @app_commands.checks.has_permissions(administrator=True)
    async def changer_univers(self, interaction: discord.Interaction, theme: str, duree_jours: int):
        univers_paralleles["active"] = True
        univers_paralleles["theme"] = theme
        univers_paralleles["end"] = time.time() + duree_jours * 24 * 3600
        await interaction.response.send_message(f"✅ Univers parallèle activé: {theme} pendant {duree_jours} jours.", ephemeral=True)
async def setup_univers_paralleles(bot: commands.Bot):
    await bot.add_cog(UniversParallelesCog(bot))

# --- Hall of Mastery Cog ---
class HallOfMasteryCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="hall_of_fame", description="Afficher le Hall of Mastery")
    async def hall_of_fame(self, interaction: discord.Interaction):
        if hall_of_mastery:
            await interaction.response.send_message("🏆 Hall of Mastery:\n" + "\n".join(hall_of_mastery), ephemeral=True)
        else:
            await interaction.response.send_message("Aucun membre qualifié pour l'instant.", ephemeral=True)
async def setup_hall_of_mastery(bot: commands.Bot):
    await bot.add_cog(HallOfMasteryCog(bot))

# --- Chronomètre de Discipline Cog ---
class ChronoDisciplineCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_chronos = {}
    @safe_command
    @app_commands.command(name="chrono_discipline", description="Activer un chrono de discipline pure")
    async def chrono_discipline(self, interaction: discord.Interaction, duree_minutes: int):
        uid = str(interaction.user.id)
        end = time.time() + duree_minutes * 60
        self.active_chronos[uid] = end
        await interaction.response.send_message(f"✅ Chrono activé pour {duree_minutes} minutes. Ne touchez à rien!", ephemeral=True)
        while time.time() < end:
            await asyncio.sleep(10)
        await interaction.followup.send("🎉 Chrono terminé ! Badge de discipline attribué.", ephemeral=True)
async def setup_chrono_discipline(bot: commands.Bot):
    await bot.add_cog(ChronoDisciplineCog(bot))

# --- Livres de Savoir Cog ---
class LivresSavoirCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="creer_livre", description="Créer un livre de savoir partagé")
    async def creer_livre(self, interaction: discord.Interaction, titre: str, contenu: str):
        livres_savoir.append({"user": interaction.user.name, "titre": titre, "contenu": contenu, "votes": 0})
        await interaction.response.send_message("✅ Livre créé.", ephemeral=True)
    @safe_command
    @app_commands.command(name="bibliotheque_des_savoirs", description="Afficher les livres de savoir")
    async def bibliotheque_des_savoirs(self, interaction: discord.Interaction):
        if livres_savoir:
            lines = [f"{livre['titre']} par {livre['user']} - Votes: {livre['votes']}" for livre in livres_savoir]
            await interaction.response.send_message("📚 Livres de savoir:\n" + "\n".join(lines), ephemeral=True)
        else:
            await interaction.response.send_message("Aucun livre.", ephemeral=True)
async def setup_livres_savoir(bot: commands.Bot):
    await bot.add_cog(LivresSavoirCog(bot))

# --- Jour Zéro Cog ---
class JourZeroCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.jour_zero_active = False
        self.end_time = None
    @safe_command
    @app_commands.command(name="activer_jour_zero", description="Activer le mode Jour Zéro (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def activer_jour_zero(self, interaction: discord.Interaction, duree_heures: int):
        self.jour_zero_active = True
        self.end_time = time.time() + duree_heures * 3600
        await interaction.response.send_message(f"✅ Jour Zéro activé pour {duree_heures} heures.", ephemeral=True)
async def setup_jour_zero(bot: commands.Bot):
    await bot.add_cog(JourZeroCog(bot))

# --- Forge des Protocoles Cog ---
class ForgeProtocolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="protocole", description="Proposer un protocole personnel")
    async def protocole(self, interaction: discord.Interaction, nom: str, description: str):
        protocoles[nom] = description
        await interaction.response.send_message("✅ Protocole proposé et en attente de validation admin.", ephemeral=True)
async def setup_forge_protocoles(bot: commands.Bot):
    await bot.add_cog(ForgeProtocolesCog(bot))

# --- Mur des Promesses Cog ---
class MurPromessesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="je_m_engage", description="Faire une promesse publique")
    async def je_m_engage(self, interaction: discord.Interaction, promesse: str):
        mur = f"{interaction.user.mention} s’engage: {promesse}"
        promesses.append(mur)
        channel_id = bot.allowed_channels.get("mur_promesses")
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                await channel.send(mur)
        await interaction.response.send_message("✅ Promesse enregistrée.", ephemeral=True)
async def setup_mur_promesses(bot: commands.Bot):
    await bot.add_cog(MurPromessesCog(bot))

# --- Mode RPG Discipline Cog ---
class RPGDisciplineCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="voir_stats", description="Voir votre fiche de discipline")
    async def voir_stats(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        profil = rpg_profiles.get(uid, {"volonte": 10, "tentation": 0, "niveau": 1})
        await interaction.response.send_message(f"Votre fiche : Volonté: {profil['volonte']}, Tentation: {profil['tentation']}, Niveau: {profil['niveau']}", ephemeral=True)
    @safe_command
    @app_commands.command(name="level_up", description="Level up de discipline")
    async def level_up(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        profil = rpg_profiles.setdefault(uid, {"volonte": 10, "tentation": 0, "niveau": 1})
        profil["niveau"] += 1
        profil["volonte"] += 5
        await interaction.response.send_message(f"🎉 Vous êtes passé au niveau {profil['niveau']}!", ephemeral=True)
async def setup_rpg_discipline(bot: commands.Bot):
    await bot.add_cog(RPGDisciplineCog(bot))

# --- Éclipse Mentale Cog ---
class EclipseMentaleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active = False
        self.end_time = None
    @safe_command
    @app_commands.command(name="activer_eclipse", description="Activer l'éclipse mentale (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def activer_eclipse(self, interaction: discord.Interaction, duree_heures: int):
        self.active = True
        self.end_time = time.time() + duree_heures * 3600
        await interaction.response.send_message(f"✅ Éclipse activée pour {duree_heures} heures.", ephemeral=True)
async def setup_eclipse_mentale(bot: commands.Bot):
    await bot.add_cog(EclipseMentaleCog(bot))

# --- Miroir Futur Cog ---
class MiroirFuturCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="miroir_futur", description="Afficher un reflet du futur")
    async def miroir_futur(self, interaction: discord.Interaction):
        await interaction.response.send_message("✨ Si tu augmentais tes efforts de 10%, imagine le futur! Concentre-toi et excelle!", ephemeral=True)
async def setup_miroir_futur(bot: commands.Bot):
    await bot.add_cog(MiroirFuturCog(bot))

# --- Monnaie Mentale Cog ---
class MonnaieMentaleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.monnaie = {}  # { user_id: balance }
    @safe_command
    @app_commands.command(name="solde_fragments", description="Afficher votre solde de Fragments de Volonté")
    async def solde_fragments(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        balance = self.monnaie.get(uid, 0)
        await interaction.response.send_message(f"💰 Votre solde: {balance} Fragments de Volonté", ephemeral=True)
    @safe_command
    @app_commands.command(name="gagner_fragments", description="Gagner des Fragments de Volonté (simulation)")
    async def gagner_fragments(self, interaction: discord.Interaction, montant: int):
        uid = str(interaction.user.id)
        self.monnaie[uid] = self.monnaie.get(uid, 0) + montant
        await interaction.response.send_message(f"✅ Vous avez gagné {montant} fragments.", ephemeral=True)
    @safe_command
    @app_commands.command(name="depense_fragments", description="Dépenser des Fragments de Volonté")
    async def depense_fragments(self, interaction: discord.Interaction, montant: int):
        uid = str(interaction.user.id)
        balance = self.monnaie.get(uid, 0)
        if balance < montant:
            await interaction.response.send_message("❌ Solde insuffisant.", ephemeral=True)
        else:
            self.monnaie[uid] = balance - montant
            await interaction.response.send_message(f"✅ Dépensé {montant} fragments. Nouveau solde: {self.monnaie[uid]}", ephemeral=True)
async def setup_monnaie_mentale(bot: commands.Bot):
    await bot.add_cog(MonnaieMentaleCog(bot))

# --- Rituel Vocal Cog ---
class RituelVocalCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="lancer_rituel", description="Démarrer le rituel vocal collectif")
    async def lancer_rituel(self, interaction: discord.Interaction):
        await interaction.response.send_message("🎤 Rituel de discipline lancé. Rendez-vous dans le salon vocal 'RITUEL DE LA DISCIPLINE' pour 15 minutes de focus.", ephemeral=True)
async def setup_rituel_vocal(bot: commands.Bot):
    await bot.add_cog(RituelVocalCog(bot))

# --- Chasseur de Distraction Cog ---
class ChasseurDistractionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="traquer_tentation", description="Traquer ta tentation de distraction")
    async def traquer_tentation(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ Ton comportement a été noté. Continue de te concentrer!", ephemeral=True)
async def setup_chasseur_distraction(bot: commands.Bot):
    await bot.add_cog(ChasseurDistractionCog(bot))

# --- Influence Mentale Cog ---
class InfluenceMentaleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="influence", description="Afficher votre influence mentale")
    async def influence(self, interaction: discord.Interaction):
        await interaction.response.send_message("✨ Vous rayonnez! Votre influence est de 75 points.", ephemeral=True)
async def setup_influence_mentale(bot: commands.Bot):
    await bot.add_cog(InfluenceMentaleCog(bot))

# --- Base Secrète Évolutive Cog ---
class BaseSecreteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.progression = 0
    @safe_command
    @app_commands.command(name="maj_base", description="Mettre à jour la base secrète (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def maj_base(self, interaction: discord.Interaction, progression: int):
        self.progression = progression
        await interaction.response.send_message(f"✅ Base mise à jour : Progression {progression}%.", ephemeral=True)
async def setup_base_secrete(bot: commands.Bot):
    await bot.add_cog(BaseSecreteCog(bot))

# --- Eveil Progressif Cog ---
class EveilProgressifCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="grimoire", description="Afficher votre révélation personnelle")
    async def grimoire(self, interaction: discord.Interaction):
        await interaction.response.send_message("💡 Révélation : Tu n'es plus passif, tu es l'architecte de ton destin.", ephemeral=True)
async def setup_eveil_progressif(bot: commands.Bot):
    await bot.add_cog(EveilProgressifCog(bot))

# --- Rituel du Silence Cog ---
class RituelSilenceCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="rituel_silence", description="Participer au rituel du silence")
    async def rituel_silence(self, interaction: discord.Interaction):
        await interaction.response.send_message("🤫 Rituel du Silence activé. Profitez de 1 heure d'introspection.", ephemeral=True)
async def setup_rituel_silence(bot: commands.Bot):
    await bot.add_cog(RituelSilenceCog(bot))

# --- Commandements Personnels Cog ---
class CommandementsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.commandements = {}  # { user_id: [commandement, ...] }
    @safe_command
    @app_commands.command(name="nouveau_commandement", description="Définir un commandement personnel")
    async def nouveau_commandement(self, interaction: discord.Interaction, texte: str):
        uid = str(interaction.user.id)
        self.commandements.setdefault(uid, []).append(texte)
        await interaction.response.send_message("✅ Commandement enregistré.", ephemeral=True)
    @safe_command
    @app_commands.command(name="rappeler_commandements", description="Rappeler vos commandements personnels")
    async def rappeler_commandements(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        cmds = self.commandements.get(uid, [])
        if cmds:
            await interaction.response.send_message("📜 Vos commandements:\n" + "\n".join(cmds), ephemeral=True)
        else:
            await interaction.response.send_message("Aucun commandement enregistré.", ephemeral=True)
async def setup_commandements(bot: commands.Bot):
    await bot.add_cog(CommandementsCog(bot))

# --- Archives Mentales Cog ---
class ArchivesMentalesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.archives = {}  # { user_id: [log, ...] }
    @safe_command
    @app_commands.command(name="mes_archives", description="Afficher vos archives mentales")
    async def mes_archives(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        logs = self.archives.get(uid, [])
        if logs:
            await interaction.response.send_message("🗄️ Vos archives:\n" + "\n".join(logs), ephemeral=True)
        else:
            await interaction.response.send_message("Aucune archive.", ephemeral=True)
    @safe_command
    @app_commands.command(name="archiver", description="Archiver un moment fort")
    async def archiver(self, interaction: discord.Interaction, log: str):
        uid = str(interaction.user.id)
        self.archives.setdefault(uid, []).append(log)
        await interaction.response.send_message("✅ Moment archivé.", ephemeral=True)
async def setup_archives_mentales(bot: commands.Bot):
    await bot.add_cog(ArchivesMentalesCog(bot))

# --- Pacte de Sang Mental Cog ---
class PacteSangCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pactes = {}  # { user_id: {"active": bool, "end": timestamp} }
    @safe_command
    @app_commands.command(name="pacte_sang", description="Activer le Pacte de Sang Mental pour 7 jours")
    async def pacte_sang(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        self.pactes[uid] = {"active": True, "end": time.time() + 7 * 24 * 3600}
        await interaction.response.send_message("✅ Pacte activé pour 7 jours.", ephemeral=True)
async def setup_pacte_sang(bot: commands.Bot):
    await bot.add_cog(PacteSangCog(bot))

# --- Duel Mental Cog ---
class DuelMentalCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="duel_mental", description="Défier un autre membre au duel mental")
    async def duel_mental(self, interaction: discord.Interaction, adversaire: discord.Member):
        await interaction.response.send_message(f"⚔️ {interaction.user.mention} défie {adversaire.mention} au duel mental !", ephemeral=True)
async def setup_duel_mental(bot: commands.Bot):
    await bot.add_cog(DuelMentalCog(bot))

# --- Codex Vivant Cog ---
class CodexCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.codex = []  # Liste des meilleures citations et pensées
    @safe_command
    @app_commands.command(name="codex", description="Afficher le Codex du serveur")
    async def codex(self, interaction: discord.Interaction):
        if self.codex:
            await interaction.response.send_message("📖 Codex du Serveur:\n" + "\n".join(self.codex), ephemeral=True)
        else:
            await interaction.response.send_message("Codex vide.", ephemeral=True)
async def setup_codex(bot: commands.Bot):
    await bot.add_cog(CodexCog(bot))

# --- Rôles Totémiques Cog ---
class RolesTotemCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="choisir_totem", description="Choisir un animal totem")
    async def choisir_totem(self, interaction: discord.Interaction, totem: str):
        await interaction.response.send_message(f"✅ Totem activé : {totem}. Vos messages seront adaptés.", ephemeral=True)
async def setup_roles_totem(bot: commands.Bot):
    await bot.add_cog(RolesTotemCog(bot))

# --- Visionnaire de Long Terme Cog ---
class VisionnaireCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.responses = {}  # { user_id: response }
    @safe_command
    @app_commands.command(name="visionnaire", description="Répondre à la question du futur")
    async def visionnaire(self, interaction: discord.Interaction, reponse: str):
        uid = str(interaction.user.id)
        self.responses[uid] = reponse
        await interaction.response.send_message("✅ Réponse enregistrée. Elle vous sera rappelée dans 30 jours.", ephemeral=True)
async def setup_visionnaire(bot: commands.Bot):
    await bot.add_cog(VisionnaireCog(bot))

# --- Système de Legacy Cog ---
class LegacyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @safe_command
    @app_commands.command(name="legacy", description="Déposer un message d'héritage")
    async def legacy(self, interaction: discord.Interaction, message: str):
        legacy_messages.append({"user": interaction.user.name, "message": message, "time": time.time()})
        await interaction.response.send_message("✅ Héritage enregistré dans le Mur des Anciens.", ephemeral=True)
async def setup_legacy(bot: commands.Bot):
    await bot.add_cog(LegacyCog(bot))

# -------------------- Nouveaux Modules Terminés --------------------

# -------------------- Serveur Keep-Alive --------------------
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
        logging.error(f"❌ Erreur lancement keep-alive: {e}")
keep_alive()

@bot.event
async def on_ready():
    try:
        logging.info(f"✅ Connecté en tant que {bot.user} (ID: {bot.user.id})")
    except Exception as e:
        logging.error(f"❌ Erreur on_ready: {e}")

# -------------------- MAIN --------------------
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
    # Chargement des modules existants
    await setup_reaction_roles(bot)
    await setup_pomodoro(bot)
    await setup_goals(bot)
    await setup_weekly_plan(bot)
    await setup_reminders(bot)
    await setup_quiz(bot)
    await setup_focus_group(bot)
    await setup_weekly_summary(bot)
    await setup_aide(bot)
    await setup_citations(bot)
    await setup_emergency(bot)
    await setup_channel_lock(bot)
    await setup_focus_protect(bot)
    await setup_sleep_mode(bot)
    await setup_recherches(bot)
    await setup_activity_drop(bot)
    await setup_bibliotheque(bot)
    await setup_smart_reactions(bot)
    await setup_quetes(bot)
    # Nouveaux modules
    await setup_discipline_personnelle(bot)
    await setup_saison(bot)
    await setup_commandant(bot)
    await setup_double_compte(bot)
    await setup_isolation(bot)
    await setup_tempete(bot)
    await setup_version_parallele(bot)
    await setup_journal_guerre(bot)
    await setup_tribunal(bot)
    await setup_quetes_identite(bot)
    await setup_univers_paralleles(bot)
    await setup_hall_of_mastery(bot)
    await setup_chrono_discipline(bot)
    await setup_livres_savoir(bot)
    await setup_jour_zero(bot)
    await setup_forge_protocoles(bot)
    await setup_mur_promesses(bot)
    await setup_rpg_discipline(bot)
    await setup_eclipse_mentale(bot)
    await setup_miroir_futur(bot)
    await setup_monnaie_mentale(bot)
    await setup_rituel_vocal(bot)
    await setup_chasseur_distraction(bot)
    await setup_influence_mentale(bot)
    await setup_base_secrete(bot)
    await setup_eveil_progressif(bot)
    await setup_rituel_silence(bot)
    await setup_commandements(bot)
    await setup_archives_mentales(bot)
    await setup_pacte_sang(bot)
    await setup_duel_mental(bot)
    await setup_codex(bot)
    await setup_roles_totem(bot)
    await setup_visionnaire(bot)
    await setup_legacy(bot)
    await setup_config(bot)  # Charge la cog de configuration
    try:
        await bot.start(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        logging.error(f"❌ Erreur lancement bot: {e}")

asyncio.run(main())

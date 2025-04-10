import os
import json
import discord
from discord.ext import commands, tasks
from discord import app_commands, TextStyle, PartialEmoji
from discord.ui import Modal, TextInput, View, Button
import asyncio
import textwrap
import time
import datetime
from zoneinfo import ZoneInfo  # Gestion des fuseaux horaires
import uuid
import aiofiles
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, List

# Configuration du port pour Render (ou autre hébergeur)
os.environ["PORT"] = "10000"

# ========================================
# 📁 Chemins des fichiers persistants
# ========================================
DATA_FOLDER = "/data"
XP_FILE = os.path.join(DATA_FOLDER, "xp.json")
MSG_FILE = os.path.join(DATA_FOLDER, "messages_programmes.json")
DEFIS_FILE = os.path.join(DATA_FOLDER, "defis.json")
AUTO_DM_FILE = os.path.join(DATA_FOLDER, "auto_dm_configs.json")
os.makedirs(DATA_FOLDER, exist_ok=True)
POMODORO_CONFIG_FILE = os.path.join(DATA_FOLDER, "config_pomodoro.json")
GOALS_FILE = os.path.join(DATA_FOLDER, "objectifs.json")
SOS_CONFIG_FILE = os.path.join(DATA_FOLDER, "sos_config.json")
EVENEMENT_CONFIG_FILE = os.path.join(DATA_FOLDER, "evenement.json")
THEME_CONFIG_FILE = os.path.join(DATA_FOLDER, "themes.json")
MISSIONS_FILE = os.path.join(DATA_FOLDER, "missions_secretes.json")
CALENDRIER_FILE = os.path.join(DATA_FOLDER, "evenements_calendrier.json")
HELP_REQUEST_FILE = os.path.join(DATA_FOLDER, "help_requests.json")
REACTION_ROLE_FILE = os.path.join(DATA_FOLDER, "reaction_roles.json")

# ========================================
# Verrou global pour accès asynchrone aux fichiers
# ========================================
file_lock = asyncio.Lock()

# ========================================
# Fonctions asynchrones de persistance
# ========================================
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

# ========================================
# Utilitaire pour standardiser un emoji
# ========================================
def get_emoji_key(emoji):
    try:
        pe = PartialEmoji.from_str(str(emoji))
        if pe.is_custom_emoji():
            return f"<:{pe.name}:{pe.id}>"
        return str(pe)
    except Exception:
        return str(emoji)

# ========================================
# Variables globales de données persistantes
# ========================================
xp_data = {}
messages_programmes = {}
defis_data = {}
config_pomodoro = {}
objectifs_data = {}
categories_crees = {}

# ========================================
# Configuration des intents
# ========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True
intents.voice_states = True

# ========================================
# 🧠 Classe principale du bot (MyBot)
# ========================================
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        # Rôles par réaction (message_id: {emoji_key: role_id})
        self.reaction_roles = {}
        # Temps d’entrée en vocal (user_id: timestamp)
        self.vocal_start_times = {}
        # Configuration du système d’XP
        self.xp_config = {
            "xp_per_message": 10,
            "xp_per_minute_vocal": 5,
            "multipliers": {},  # channel_id: multiplicateur
            "level_roles": {},  # xp_seuil: role_id
            "announcement_channel": None,
            "announcement_message": "🎉 {mention} a atteint {xp} XP !",
            "xp_command_channel": None,
            "xp_command_min_xp": 0,
            "badges": {},  # xp: badge
            "titres": {},  # xp: titre
            "goals_channel": None  # Salon autorisé pour la commande /objectif
        }
        # Configuration pour le récapitulatif hebdomadaire automatique
        self.recap_config = {
            "channel_id": None,
            "role_id": None
        }
        # Données d’objectifs persos
        self.objectifs_data = {}
        # Salon pour journal de focus
        self.journal_focus_channel = None
        # Salon pour stats hebdo
        self.weekly_stats_channel = None
        # Mémoire temporaire des stats hebdomadaires
        self.weekly_stats = {}
        # Destinataires des messages de détresse (roles ou IDs)
        self.sos_receivers = []
        self.missions_secretes = {}
        self.categories_crees = {}
        self.evenement_config = {}
        self.theme_config = {}
        self.evenements_calendrier = {}

    def get_emoji_key(self, emoji):
        try:
            pe = PartialEmoji.from_str(str(emoji))
            if pe.is_custom_emoji():
                return f"<:{pe.name}:{pe.id}>"
            return str(pe)
        except Exception as e:
            print(f"❌ Erreur lors de la récupération de l'emoji : {e}")
            return str(emoji)

    async def setup_hook(self):
        try:
            # Synchronisation des commandes slash
            synced = await self.tree.sync()
            print(f"🌐 {len(synced)} commandes slash synchronisées")
            # Démarrage des tâches planifiées
            if not check_programmed_messages.is_running():
                check_programmed_messages.start()
                print("✅ Boucle des messages programmés démarrée")
            if not recap_hebdo_task.is_running():
                recap_hebdo_task.start()
                print("🕒 Tâche recap_hebdo_task démarrée")
            if not weekly_stats_task.is_running():
                weekly_stats_task.start()
                print("📊 Tâche weekly_stats_task démarrée")
        except Exception as e:
            print(f"❌ Erreur dans setup_hook : {e}")

bot = MyBot()
tree = bot.tree

# ========================================
# Tâche de vérification des messages programmés et défis récurrents
# ========================================
@tasks.loop(seconds=30)
async def check_programmed_messages():
    try:
        if not bot.is_ready():
            print("⏳ Bot pas encore prêt, attente...")
            return
        now = datetime.datetime.now(ZoneInfo("Europe/Paris"))
        print(f"🔁 Vérification des messages programmés à {now.strftime('%H:%M:%S')} (Europe/Paris)")
        messages_modifies = False
        for msg_id, msg in list(messages_programmes.items()):
            try:
                try:
                    msg_time_naive = datetime.datetime.strptime(msg["next"], "%d/%m/%Y %H:%M")
                    msg_time = msg_time_naive.replace(tzinfo=ZoneInfo("Europe/Paris"))
                except ValueError as ve:
                    print(f"❌ Format invalide pour {msg_id} : {ve}")
                    continue
                if now >= msg_time:
                    channel = bot.get_channel(int(msg["channel_id"]))
                    if channel:
                        if msg["type"] in ["once", "daily", "weekly"]:
                            await channel.send(textwrap.dedent(msg["message"]))
                            print(f"✅ Message {msg_id} envoyé dans #{channel.name}")
                        elif msg["type"] == "weekly_challenge":
                            sent_msg = await channel.send(textwrap.dedent(msg["message"]))
                            await sent_msg.add_reaction("✅")
                            end_timestamp = time.time() + float(msg["duration_hours"]) * 3600
                            defis_data[str(sent_msg.id)] = {
                                "channel_id": channel.id,
                                "role_id": msg["role_id"],
                                "end_timestamp": end_timestamp
                            }
                            await sauvegarder_json_async(DEFIS_FILE, defis_data)
                            asyncio.create_task(retirer_role_apres_defi(channel.guild, sent_msg.id,
                                                                         channel.guild.get_role(int(msg["role_id"]))))
                            print(f"✅ Défi lancé dans #{channel.name} pour {msg['duration_hours']}h")
                        if msg["type"] == "once":
                            del messages_programmes[msg_id]
                            messages_modifies = True
                        elif msg["type"] == "daily":
                            while now >= msg_time:
                                msg_time += datetime.timedelta(days=1)
                            messages_programmes[msg_id]["next"] = msg_time.strftime("%d/%m/%Y %H:%M")
                            messages_modifies = True
                        elif msg["type"] in ["weekly", "weekly_challenge"]:
                            while now >= msg_time:
                                msg_time += datetime.timedelta(weeks=1)
                            messages_programmes[msg_id]["next"] = msg_time.strftime("%d/%m/%Y %H:%M")
                            messages_modifies = True
                    else:
                        print(f"⚠️ Salon introuvable pour {msg_id}")
            except Exception as e:
                print(f"❌ Erreur lors du traitement de {msg_id} : {e}")
        if messages_modifies:
            await sauvegarder_json_async(MSG_FILE, messages_programmes)
    except Exception as e:
        print(f"❌ Erreur globale dans check_programmed_messages : {e}")

# ========================================
# Fonctions XP
# ========================================
async def add_xp(user_id, amount):
    uid = str(user_id)
    current = xp_data.get(uid, 0)
    new_total = current + amount
    xp_data[uid] = new_total
    await sauvegarder_json_async(XP_FILE, xp_data)
    return new_total

def get_xp(user_id):
    return xp_data.get(str(user_id), 0)

# ========================================
# Gestion de l'XP sur messages et en vocal
# ========================================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    uid = str(message.author.id)
    if uid not in bot.weekly_stats:
        bot.weekly_stats[uid] = {"messages": 0, "vocal": 0}
    bot.weekly_stats[uid]["messages"] += 1

    xp_val = bot.xp_config["xp_per_message"]
    mult = bot.xp_config["multipliers"].get(str(message.channel.id), 1.0)
    total_xp = int(xp_val * mult)
    current_xp = await add_xp(message.author.id, total_xp)

    for seuil, role_id in bot.xp_config["level_roles"].items():
        if current_xp >= int(seuil):
            role = message.guild.get_role(int(role_id))
            if role and role not in message.author.roles:
                try:
                    await message.author.add_roles(role, reason="Palier XP atteint")
                    if bot.xp_config["announcement_channel"]:
                        chan = bot.get_channel(int(bot.xp_config["announcement_channel"]))
                        if chan:
                            text_annonce = bot.xp_config["announcement_message"].replace("{mention}", message.author.mention).replace("{xp}", str(current_xp))
                            await chan.send(text_annonce)
                except Exception as e:
                    print(f"❌ Erreur attribution rôle XP: {e}")

    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    if not before.channel and after.channel:
        bot.vocal_start_times[member.id] = time.time()
    elif before.channel and not after.channel:
        start = bot.vocal_start_times.pop(member.id, None)
        if start:
            duree = int((time.time() - start) / 60)
            mult = bot.xp_config["multipliers"].get(str(before.channel.id), 1.0)
            gained = int(duree * bot.xp_config["xp_per_minute_vocal"] * mult)
            current_xp = await add_xp(member.id, gained)

            uid = str(member.id)
            if uid not in bot.weekly_stats:
                bot.weekly_stats[uid] = {"messages": 0, "vocal": 0}
            bot.weekly_stats[uid]["vocal"] += duree * 60

            for seuil, role_id in bot.xp_config["level_roles"].items():
                if current_xp >= int(seuil):
                    role = member.guild.get_role(int(role_id))
                    if role and role not in member.roles:
                        try:
                            await member.add_roles(role, reason="XP vocal atteint")
                            if bot.xp_config["announcement_channel"]:
                                chan = bot.get_channel(int(bot.xp_config["announcement_channel"]))
                                if chan:
                                    text_annonce = bot.xp_config["announcement_message"].replace("{mention}", member.mention).replace("{xp}", str(current_xp))
                                    await chan.send(text_annonce)
                        except Exception as e:
                            print(f"❌ Erreur attribution rôle vocal: {e}")

# ========================================
# Commandes XP et Leaderboard
# ========================================
@tree.command(name="xp", description="Affiche ton XP")
async def xp(interaction: discord.Interaction):
    config = bot.xp_config
    if config["xp_command_channel"] and interaction.channel.id != int(config["xp_command_channel"]):
        await interaction.response.send_message("❌ Commande non autorisée ici.", ephemeral=True)
        return
    user_xp = get_xp(interaction.user.id)
    if user_xp < config["xp_command_min_xp"]:
        await interaction.response.send_message("❌ XP insuffisant.", ephemeral=True)
        return
    badge = ""
    for seuil, b in sorted(config["badges"].items(), key=lambda x: int(x[0]), reverse=True):
        if user_xp >= int(seuil):
            badge = b
            break
    titre = ""
    for seuil, t in sorted(config["titres"].items(), key=lambda x: int(x[0]), reverse=True):
        if user_xp >= int(seuil):
            titre = t
            break
    texte = textwrap.dedent(f"""
        🔹 {interaction.user.mention}, tu as **{user_xp} XP**.
        {"🏅 Badge : **" + badge + "**" if badge else ""}
        {"📛 Titre : **" + titre + "**" if titre else ""}
    """)
    await interaction.response.send_message(texte.strip(), ephemeral=True)

@tree.command(name="leaderboard", description="Affiche le top 10 des membres par XP")
async def leaderboard(interaction: discord.Interaction):
    config = bot.xp_config
    if config["xp_command_channel"] and interaction.channel.id != int(config["xp_command_channel"]):
        await interaction.response.send_message("❌ Commande non autorisée ici.", ephemeral=True)
        return
    classement = sorted(xp_data.items(), key=lambda x: x[1], reverse=True)[:10]
    lignes = []
    for i, (uid, xp_val) in enumerate(classement):
        membre = interaction.guild.get_member(int(uid))
        nom = membre.display_name if membre else f"Utilisateur {uid}"
        lignes.append(f"{i+1}. {nom} — {xp_val} XP")
    texte = "🏆 **Top 10 XP :**\n" + "\n".join(lignes) if lignes else "Aucun XP enregistré."
    await interaction.response.send_message(texte, ephemeral=True)

# ========================================
# Commandes XP ADMIN
# ========================================
@tree.command(name="add_xp", description="Ajoute de l'XP à un membre (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(member="Membre ciblé", amount="Quantité d'XP à ajouter")
async def add_xp_cmd(interaction: discord.Interaction, member: discord.Member, amount: int):
    new_total = await add_xp(member.id, amount)
    texte = f"✅ {amount} XP ajoutés à {member.mention}\n🔹 Total : **{new_total} XP**"
    await interaction.response.send_message(texte, ephemeral=True)

@tree.command(name="set_xp_config", description="Modifie l'XP par message et en vocal (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp_per_message="XP par message", xp_per_minute_vocal="XP par minute vocale")
async def set_xp_config(interaction: discord.Interaction, xp_per_message: int, xp_per_minute_vocal: int):
    bot.xp_config["xp_per_message"] = xp_per_message
    bot.xp_config["xp_per_minute_vocal"] = xp_per_minute_vocal
    await interaction.response.send_message(f"✅ XP mis à jour : {xp_per_message}/msg, {xp_per_minute_vocal}/min", ephemeral=True)

@tree.command(name="set_xp_role", description="Définit un rôle à débloquer par XP (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", role="Rôle à attribuer")
async def set_xp_role(interaction: discord.Interaction, xp: int, role: discord.Role):
    bot.xp_config["level_roles"][str(xp)] = role.id
    await interaction.response.send_message(f"✅ Le rôle **{role.name}** sera attribué dès {xp} XP.", ephemeral=True)

@tree.command(name="set_xp_boost", description="Ajoute un multiplicateur d'XP à un salon (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon concerné", multiplier="Ex: 2.0 pour XP x2")
async def set_xp_boost(interaction: discord.Interaction, channel: discord.TextChannel, multiplier: float):
    bot.xp_config["multipliers"][str(channel.id)] = multiplier
    await interaction.response.send_message(f"✅ Multiplicateur x{multiplier} appliqué à {channel.mention}.", ephemeral=True)

@tree.command(name="set_salon_annonce", description="Définit le salon des annonces de niveau (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon cible")
async def set_salon_annonce(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["announcement_channel"] = str(channel.id)
    await interaction.response.send_message(f"✅ Annonces de niveau dans {channel.mention}.", ephemeral=True)

@tree.command(name="set_message_annonce", description="Modifie le message d’annonce de niveau (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message="Utilise {mention} et {xp}")
async def set_message_annonce(interaction: discord.Interaction, message: str):
    bot.xp_config["announcement_message"] = message
    preview = message.replace("{mention}", interaction.user.mention).replace("{xp}", "1234")
    await interaction.response.send_message(f"✅ Message mis à jour !\n\n💬 Aperçu:\n{preview}", ephemeral=True)

@tree.command(name="set_channel_xp", description="Définit le salon où /xp et /leaderboard sont utilisables (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon autorisé")
async def set_channel_xp(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["xp_command_channel"] = str(channel.id)
    await interaction.response.send_message(f"✅ Commandes XP limitées à {channel.mention}.", ephemeral=True)

@tree.command(name="set_minimum_xp", description="Définit le XP minimum pour /xp (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(min_xp="XP minimum requis")
async def set_minimum_xp(interaction: discord.Interaction, min_xp: int):
    bot.xp_config["xp_command_min_xp"] = min_xp
    await interaction.response.send_message(f"✅ Minimum requis: {min_xp} XP.", ephemeral=True)

@tree.command(name="ajouter_badge", description="Ajoute un badge débloqué par XP (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", badge="Nom ou emoji du badge")
async def ajouter_badge(interaction: discord.Interaction, xp: int, badge: str):
    bot.xp_config["badges"][str(xp)] = badge
    await interaction.response.send_message(f"✅ Badge '{badge}' ajouté dès {xp} XP.", ephemeral=True)

@tree.command(name="ajouter_titre", description="Ajoute un titre débloqué par XP (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", titre="Titre à débloquer")
async def ajouter_titre(interaction: discord.Interaction, xp: int, titre: str):
    bot.xp_config["titres"][str(xp)] = titre
    await interaction.response.send_message(f"✅ Titre '{titre}' ajouté dès {xp} XP.", ephemeral=True)

@tree.command(name="set_channel_pomodoro", description="Définit le salon autorisé pour la commande /pomodoro (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon autorisé pour les sessions Pomodoro")
async def set_channel_pomodoro(interaction: discord.Interaction, channel: discord.TextChannel):
    config_pomodoro["allowed_channel_id"] = str(channel.id)
    await sauvegarder_json_async(POMODORO_CONFIG_FILE, config_pomodoro)
    await interaction.response.send_message(f"✅ Salon Pomodoro défini : {channel.mention}", ephemeral=True)

@tree.command(name="set_channel_objectifs", description="Définit le salon autorisé pour gérer les objectifs (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon autorisé")
async def set_channel_objectifs(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["goals_channel"] = str(channel.id)
    await interaction.response.send_message(f"✅ Commandes d’objectifs limitées à {channel.mention}", ephemeral=True)

# ========================================
# Commandes de création rapide de salons, catégories privées et rôles
# ========================================
@tree.command(name="creer_salon", description="Crée un ou plusieurs salons dans une catégorie (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    noms="Nom(s) du salon (séparés par une virgule pour en créer plusieurs)",
    categorie="Catégorie dans laquelle créer les salons",
    type="Type de salon : text ou voice"
)
async def creer_salon(interaction: discord.Interaction, noms: str, categorie: discord.CategoryChannel, type: str):
    try:
        noms_list = [n.strip() for n in noms.split(",") if n.strip()]
        if not noms_list:
            await interaction.response.send_message("❌ Aucun nom fourni.", ephemeral=True)
            return

        created_channels = []
        for nom in noms_list:
            if type.lower() == "text":
                channel = await interaction.guild.create_text_channel(name=nom, category=categorie)
            elif type.lower() == "voice":
                channel = await interaction.guild.create_voice_channel(name=nom, category=categorie)
            else:
                await interaction.response.send_message("❌ Type de salon invalide (text ou voice uniquement).", ephemeral=True)
                return
            created_channels.append(channel.mention)
        msg = "✅ Salon" + ("s" if len(created_channels) > 1 else "") + " créé" + ("s" if len(created_channels) > 1 else "") + " : " + ", ".join(created_channels)
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur lors de la création du salon : {e}", ephemeral=True)

@tree.command(name="creer_role", description="Crée un ou plusieurs rôles (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    noms="Nom(s) du rôle (séparés par une virgule pour en créer plusieurs)"
)
async def creer_role(interaction: discord.Interaction, noms: str):
    try:
        noms_list = [n.strip() for n in noms.split(",") if n.strip()]
        if not noms_list:
            await interaction.response.send_message("❌ Aucun nom fourni.", ephemeral=True)
            return
        created_roles = []
        for nom in noms_list:
            role = await interaction.guild.create_role(name=nom)
            created_roles.append(role.name)
        msg = "✅ Rôle" + ("s" if len(created_roles) > 1 else "") + " créé" + ("s" if len(created_roles) > 1 else "") + " : " + ", ".join(created_roles)
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur lors de la création du rôle : {e}", ephemeral=True)

@tree.command(name="creer_categorie_privee", description="Crée une catégorie privée accessible uniquement à un rôle spécifique (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(nom="Nom de la catégorie", role="Rôle qui aura accès à la catégorie")
async def creer_categorie_privee(interaction: discord.Interaction, nom: str, role: discord.Role):
    try:
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            role: discord.PermissionOverwrite(view_channel=True)
        }
        new_category = await interaction.guild.create_category(name=nom, overwrites=overwrites)
        await interaction.response.send_message(f"✅ Catégorie privée **{new_category.name}** créée (accessible uniquement au rôle **{role.name}**).", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur lors de la création de la catégorie : {e}", ephemeral=True)

# ========================================
# Système de messages programmés (via modal)
# ========================================
class ProgrammerMessageModal(Modal, title="🗓️ Programmer un message"):
    def __init__(self, salon: discord.TextChannel, type_message: str, date_heure: str):
        super().__init__(timeout=None)
        self.salon = salon
        self.type = type_message  # "once", "daily", "weekly" ou "weekly_challenge"
        self.date_heure = date_heure  # Format "JJ/MM/AAAA HH:MM"
        self.contenu = TextInput(
            label="Contenu du message",
            style=TextStyle.paragraph,
            placeholder="Tape ici ton message complet",
            required=True,
            max_length=2000
        )
        self.add_item(self.contenu)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            texte_final = textwrap.dedent(self.contenu.value)
            if len(texte_final) > 2000:
                await interaction.followup.send("❌ Le message est trop long.", ephemeral=True)
                return
            msg_id = str(uuid.uuid4())
            messages_programmes[msg_id] = {
                "channel_id": str(self.salon.id),
                "message": texte_final,
                "type": self.type,
                "next": self.date_heure
            }
            await sauvegarder_json_async(MSG_FILE, messages_programmes)
            await interaction.followup.send(f"✅ Message programmé dans {self.salon.mention} ({self.type}) pour {self.date_heure}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

@tree.command(name="programmer_message", description="Planifie un message automatique (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(salon="Salon de destination", type="once, daily, weekly ou weekly_challenge", date_heure="Format: JJ/MM/AAAA HH:MM")
async def programmer_message(interaction: discord.Interaction, salon: discord.TextChannel, type: str, date_heure: str):
    valid_types = ["once", "daily", "weekly", "weekly_challenge"]
    if type.lower() not in valid_types:
        await interaction.response.send_message("❌ Type invalide.", ephemeral=True)
        return
    try:
        datetime.datetime.strptime(date_heure, "%d/%m/%Y %H:%M")
    except ValueError:
        await interaction.response.send_message("❌ Format de date invalide.", ephemeral=True)
        return
    try:
        await interaction.response.send_modal(ProgrammerMessageModal(salon, type.lower(), date_heure))
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur lors de l'ouverture du modal: {e}", ephemeral=True)

@tree.command(name="supprimer_message_programmé", description="Supprime un message programmé (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message_id="ID du message à supprimer")
async def supprimer_message_programme(interaction: discord.Interaction, message_id: str):
    if message_id in messages_programmes:
        del messages_programmes[message_id]
        await sauvegarder_json_async(MSG_FILE, messages_programmes)
        await interaction.response.send_message("✅ Message programmé supprimé.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ ID non trouvé.", ephemeral=True)

@tree.command(name="messages_programmés", description="Liste les messages programmés (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def messages_programmés_cmd(interaction: discord.Interaction):
    if not messages_programmes:
        await interaction.response.send_message("Aucun message programmé.", ephemeral=True)
        return
    txt = "**🗓️ Messages programmés :**\n"
    for msg_id, msg in messages_programmes.items():
        txt += f"🆔 `{msg_id}` — <#{msg['channel_id']}> — {msg['next']} — {msg['type']}\n"
    await interaction.response.send_message(txt.strip(), ephemeral=True)

class ModifierMessageModal(Modal, title="✏️ Modifier un message programmé"):
    def __init__(self, message_id: str):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.nouveau_contenu = TextInput(
            label="Nouveau message",
            style=TextStyle.paragraph,
            placeholder="Tape ici le nouveau message",
            required=True,
            max_length=2000
        )
        self.add_item(self.nouveau_contenu)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.message_id in messages_programmes:
            messages_programmes[self.message_id]["message"] = textwrap.dedent(self.nouveau_contenu.value)
            await sauvegarder_json_async(MSG_FILE, messages_programmes)
            await interaction.followup.send("✅ Message modifié.", ephemeral=True)
        else:
            await interaction.followup.send("❌ ID introuvable.", ephemeral=True)

@tree.command(name="modifier_message_programmé", description="Modifie un message programmé (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message_id="ID du message à modifier")
async def modifier_message_programme(interaction: discord.Interaction, message_id: str):
    if message_id in messages_programmes:
        await interaction.response.send_modal(ModifierMessageModal(message_id))
    else:
        await interaction.response.send_message("❌ ID non trouvé.", ephemeral=True)

# ========================================
# Système de réaction pour attribution de rôles via message
# ========================================
class RoleReactionModal(Modal, title="✍️ Message avec réaction"):
    def __init__(self, emoji: str, role: discord.Role, salon: discord.TextChannel):
        super().__init__(timeout=None)
        try:
            # Transformation de l'emoji fourni en une clé normalisée
            self.emoji = PartialEmoji.from_str(emoji)
            self.emoji_key = get_emoji_key(self.emoji)
        except Exception as e:
            raise ValueError(f"Emoji invalide: {emoji}") from e
        self.role = role
        self.salon = salon
        self.contenu = TextInput(
            label="Texte du message",
            style=TextStyle.paragraph,
            placeholder="Tape ton message (avec saut de ligne autorisé)",
            required=True,
            max_length=2000
        )
        self.add_item(self.contenu)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            message_envoye = await self.salon.send(textwrap.dedent(self.contenu.value))
            await message_envoye.add_reaction(self.emoji)
            # Enregistrer avec la clé normalisée
            bot.reaction_roles[str(message_envoye.id)] = {self.emoji_key: self.role.id}
            await sauvegarder_json_async(REACTION_ROLE_FILE, bot.reaction_roles)
            await interaction.followup.send(f"✅ Message envoyé dans {self.salon.mention}\n- Emoji: {self.emoji}\n- Rôle: **{self.role.name}**", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de l'envoi du message: {e}", ephemeral=True)

@tree.command(name="ajout_reaction_id", description="Ajoute une réaction à un message existant (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(role="Rôle à attribuer", emoji="Emoji à utiliser", message_id="ID du message")
async def ajout_reaction_id(interaction: discord.Interaction, role: discord.Role, emoji: str, message_id: str):
    try:
        msg_id = int(message_id)
        msg = await interaction.channel.fetch_message(msg_id)
        await msg.add_reaction(emoji)
        # Convertir l'emoji via la fonction pour obtenir la clé
        emoji_key = get_emoji_key(emoji)
        msg_id_str = str(msg_id)
        bot.reaction_roles.setdefault(msg_id_str, {})[emoji_key] = role.id
        await sauvegarder_json_async(REACTION_ROLE_FILE, bot.reaction_roles)
        await interaction.response.send_message(f"✅ Réaction {emoji} ajoutée pour le rôle {role.name} au message {message_id}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    try:
        guild = bot.get_guild(payload.guild_id)
        if not guild:
            print(f"❌ Guild introuvable pour {payload.guild_id}")
            return
        member = guild.get_member(payload.user_id)
        if not member:
            print(f"❌ Membre introuvable pour {payload.user_id}")
            return
        emoji_key = get_emoji_key(payload.emoji)
        data = bot.reaction_roles.get(str(payload.message_id))
        if not data:
            print(f"❌ Aucune donnée trouvée pour le message {payload.message_id}")
            return
        role_id = data.get(emoji_key)
        if not role_id:
            print(f"❌ Pas de rôle trouvé pour l'emoji {emoji_key} sur le message {payload.message_id}")
            return
        role = guild.get_role(int(role_id))
        if not role:
            print(f"❌ Rôle introuvable pour l'ID {role_id}")
            return
        if role not in member.roles:
            try:
                await member.add_roles(role, reason="Réaction ajoutée")
                print(f"✅ Rôle {role.name} ajouté à {member.name}")
            except discord.Forbidden:
                print(f"❌ Le bot n'a pas la permission d'ajouter le rôle {role.name} à {member.name}")
            except Exception as e:
                print(f"❌ Erreur lors de l'ajout du rôle {role.name} à {member.name} : {e}")
        else:
            print(f"⚠️ {member.name} a déjà le rôle {role.name}")
    except Exception as e:
        print(f"❌ Erreur dans on_raw_reaction_add : {e}")

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == bot.user.id:
        return
    try:
        guild = bot.get_guild(payload.guild_id)
        if not guild:
            print(f"❌ Guild introuvable pour {payload.guild_id}")
            return
        member = guild.get_member(payload.user_id)
        if not member:
            print(f"❌ Membre introuvable pour {payload.user_id}")
            return
        emoji_key = get_emoji_key(payload.emoji)
        data = bot.reaction_roles.get(str(payload.message_id))
        if not data:
            print(f"❌ Aucune donnée trouvée pour le message {payload.message_id}")
            return
        role_id = data.get(emoji_key)
        if not role_id:
            print(f"❌ Pas de rôle trouvé pour l'emoji {emoji_key} sur le message {payload.message_id}")
            return
        role = guild.get_role(int(role_id))
        if not role:
            print(f"❌ Rôle introuvable pour l'ID {role_id}")
            return
        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Réaction retirée")
                print(f"✅ Rôle {role.name} retiré de {member.name}")
            except discord.Forbidden:
                print(f"❌ Le bot n'a pas la permission de retirer le rôle {role.name} à {member.name}")
            except Exception as e:
                print(f"❌ Erreur lors du retrait du rôle {role.name} à {member.name} : {e}")
        else:
            print(f"⚠️ {member.name} ne possède pas le rôle {role.name}")
    except Exception as e:
        print(f"❌ Erreur dans on_raw_reaction_remove : {e}")

# ========================================
# Défi hebdomadaire et récurrent
# ========================================
class DefiModal(Modal, title="🔥 Défi de la semaine"):
    def __init__(self, salon: discord.TextChannel, role: discord.Role, duree_heures: int):
        super().__init__(timeout=None)
        self.salon = salon
        self.role = role
        self.duree_heures = duree_heures
        self.message = TextInput(
            label="Message du défi",
            style=TextStyle.paragraph,
            placeholder="Décris ton défi ici",
            required=True,
            max_length=2000
        )
        self.add_item(self.message)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            msg = await self.salon.send(textwrap.dedent(self.message.value))
            await msg.add_reaction("✅")
            end_timestamp = time.time() + self.duree_heures * 3600
            defis_data[str(msg.id)] = {
                "channel_id": self.salon.id,
                "role_id": self.role.id,
                "end_timestamp": end_timestamp
            }
            await sauvegarder_json_async(DEFIS_FILE, defis_data)
            asyncio.create_task(retirer_role_apres_defi(interaction.guild, msg.id, self.role))
            await interaction.followup.send(f"✅ Défi lancé dans {self.salon.mention} avec le rôle **{self.role.name}** pour {self.duree_heures}h", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors du lancement du défi: {e}", ephemeral=True)

async def retirer_role_apres_defi(guild: discord.Guild, message_id: int, role: discord.Role):
    try:
        data = defis_data.get(str(message_id))
        if not data:
            print(f"⚠️ Données introuvables pour le défi {message_id}")
            return
        temps_restant = data["end_timestamp"] - time.time()
        await asyncio.sleep(max(0, temps_restant))
        for member in role.members:
            try:
                await member.remove_roles(role, reason="Fin du défi hebdomadaire")
            except Exception as e:
                print(f"❌ Erreur en retirant le rôle pour {member.display_name}: {e}")
        del defis_data[str(message_id)]
        await sauvegarder_json_async(DEFIS_FILE, defis_data)
        print(f"✅ Rôle {role.name} retiré et défi supprimé pour {message_id}")
    except Exception as e:
        print(f"❌ Erreur dans retirer_role_apres_defi: {e}")

@tree.command(name="defi_semaine", description="Lance un défi hebdomadaire avec rôle temporaire (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    salon="Salon pour le défi",
    role="Rôle temporaire",
    duree_heures="Durée en heures (ex: 168 pour 7 jours)",
    recurrence="Booléen pour défi récurrent",
    start_date="Date de début (JJ/MM/AAAA HH:MM) si récurrent",
    challenge_message="Message du défi si récurrent"
)
async def defi_semaine(interaction: discord.Interaction, salon: discord.TextChannel, role: discord.Role,
                       duree_heures: int, recurrence: bool, start_date: str = None, challenge_message: str = None):
    if duree_heures <= 0 or duree_heures > 10000:
        await interaction.response.send_message("❌ Durée invalide.", ephemeral=True)
        return
    if recurrence:
        if not start_date or not challenge_message:
            await interaction.response.send_message("❌ Fournis start_date et challenge_message pour le défi récurrent.", ephemeral=True)
            return
        try:
            datetime.datetime.strptime(start_date, "%d/%m/%Y %H:%M")
        except ValueError:
            await interaction.response.send_message("❌ Format de start_date invalide.", ephemeral=True)
            return
        msg_id = str(uuid.uuid4())
        messages_programmes[msg_id] = {
            "channel_id": str(salon.id),
            "message": challenge_message,
            "type": "weekly_challenge",
            "next": start_date,
            "role_id": str(role.id),
            "duration_hours": str(duree_heures)
        }
        await sauvegarder_json_async(MSG_FILE, messages_programmes)
        await interaction.response.send_message(f"✅ Défi récurrent programmé dans {salon.mention} à partir du {start_date}.", ephemeral=True)
    else:
        try:
            await interaction.response.send_modal(DefiModal(salon, role, duree_heures))
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

# ========================================
# Envoi de message via modal (admin)
# ========================================
class ModalEnvoyerMessage(Modal, title="📩 Envoyer un message"):
    def __init__(self, salon: discord.TextChannel):
        super().__init__(timeout=None)
        self.salon = salon
        self.contenu = TextInput(
            label="Contenu du message",
            style=TextStyle.paragraph,
            placeholder="Colle ici ton message complet",
            required=True,
            max_length=2000
        )
        self.add_item(self.contenu)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.salon.send(textwrap.dedent(self.contenu.value))
            await interaction.followup.send(f"✅ Message envoyé dans {self.salon.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Permission insuffisante.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

@tree.command(name="envoyer_message", description="Envoie un message par le bot (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(salon="Salon de destination")
async def envoyer_message(interaction: discord.Interaction, salon: discord.TextChannel):
    try:
        await interaction.response.send_modal(ModalEnvoyerMessage(salon))
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

# ========================================
# Commande /clear pour supprimer des messages (admin)
# ========================================
@tree.command(name="clear", description="Supprime jusqu'à 100 messages dans le salon (admin)")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(nombre="Nombre de messages (entre 1 et 100)")
async def clear(interaction: discord.Interaction, nombre: int):
    if not (1 <= nombre <= 100):
        await interaction.response.send_message("❌ Choisis un nombre entre 1 et 100.", ephemeral=True)
        return
    try:
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=nombre)
        await interaction.followup.send(f"🧽 {len(deleted)} messages supprimés.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Permission insuffisante.", ephemeral=True)
    except Exception as e:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

# ========================================
# Vues de confirmation simples (boutons) avec mise à jour du message
# ========================================
class ConfirmDeleteRolesView(View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=60)
        self.interaction = interaction
    @discord.ui.button(label="Oui", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message("❌ Seul l'admin qui a exécuté la commande peut confirmer.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Suppression en cours...", view=None)
        errors = []
        guild = interaction.guild
        roles_to_delete = [role for role in guild.roles if not role.permissions.administrator and (role < guild.me.top_role)]
        for role in roles_to_delete:
            try:
                await role.delete(reason="Suppression demandée par un admin")
                await asyncio.sleep(0.5)
            except Exception as e:
                errors.append(f"{role.name}: {e}")
        if errors:
            await interaction.followup.send("Certains rôles n'ont pas pu être supprimés :\n" + "\n".join(errors), ephemeral=True)
        else:
            await interaction.followup.send("✅ Tous les rôles (sauf admins) ont été supprimés.", ephemeral=True)
        self.stop()
    @discord.ui.button(label="Non", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message("❌ Seul l'admin qui a exécuté la commande peut annuler.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Opération annulée.", view=None)
        self.stop()

class ConfirmDeleteChannelsView(View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=60)
        self.interaction = interaction
    @discord.ui.button(label="Oui", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message("❌ Seul l'admin qui a exécuté la commande peut confirmer.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Suppression en cours...", view=None)
        errors = []
        guild = interaction.guild
        for channel in guild.channels:
            try:
                await channel.delete(reason="Suppression demandée par un admin")
                await asyncio.sleep(0.5)
            except Exception as e:
                errors.append(f"{channel.name}: {e}")
        if errors:
            await interaction.followup.send("Certains canaux n'ont pas pu être supprimés :\n" + "\n".join(errors), ephemeral=True)
        else:
            await interaction.followup.send("✅ Tous les salons et catégories ont été supprimés.", ephemeral=True)
        self.stop()
    @discord.ui.button(label="Non", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message("❌ Seul l'admin qui a exécuté la commande peut annuler.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Opération annulée.", view=None)
        self.stop()

# ========================================
# Outils d'administration avancés (AdminUtilsCog)
# ========================================
class AdminUtilsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    @app_commands.command(name="supprimer_categorie", description="Supprime une catégorie (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def supprimer_categorie(self, interaction: discord.Interaction, categorie: discord.CategoryChannel):
        try:
            await categorie.delete()
            await interaction.response.send_message(f"✅ Catégorie **{categorie.name}** supprimée.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
    @app_commands.command(name="supprimer_salon", description="Supprime un salon (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def supprimer_salon(self, interaction: discord.Interaction, salon: discord.abc.GuildChannel):
        try:
            await salon.delete()
            await interaction.response.send_message(f"✅ Salon **{salon.name}** supprimé.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
    @app_commands.command(name="reset_roles", description="Retire tous les rôles (sauf admins) de tous les membres (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_roles(self, interaction: discord.Interaction):
        try:
            for member in interaction.guild.members:
                roles_to_remove = [role for role in member.roles if not role.permissions.administrator]
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason="Réinitialisation")
            await interaction.response.send_message("✅ Tous les rôles (sauf admins) retirés.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
    @app_commands.command(name="supprimer_tous_roles", description="Supprime tous les rôles (sauf admins) du serveur (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def supprimer_tous_roles(self, interaction: discord.Interaction):
        view = ConfirmDeleteRolesView(interaction)
        await interaction.response.send_message("Êtes-vous sûr de vouloir tout **supprimer** ?", view=view, ephemeral=True)
    @app_commands.command(name="supprimer_tous_salons_categories", description="Supprime tous les salons et catégories du serveur (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def supprimer_tous_salons_categories(self, interaction: discord.Interaction):
        view = ConfirmDeleteChannelsView(interaction)
        await interaction.response.send_message("Êtes-vous sûr de vouloir tout **supprimer** (salons + catégories) ?", view=view, ephemeral=True)

async def setup_admin_utils(bot: commands.Bot):
    await bot.add_cog(AdminUtilsCog(bot))

# ========================================
# Module AutoDM (admin protégé)
# ========================================
class AutoDMCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_dm_configs = {}
    async def load_configs(self):
        try:
            configs = await charger_json_async(AUTO_DM_FILE)
            if not isinstance(configs, dict):
                configs = {}
            self.auto_dm_configs = configs
            print("⚙️ Configurations AutoDM chargées.")
        except Exception as e:
            print(f"❌ Erreur chargement AutoDM: {e}")
            self.auto_dm_configs = {}
    async def save_configs(self):
        try:
            await sauvegarder_json_async(AUTO_DM_FILE, self.auto_dm_configs)
            print("⚙️ Config AutoDM sauvegardée.")
        except Exception as e:
            print(f"❌ Erreur sauvegarde AutoDM: {e}")
    async def cog_load(self):
        await self.load_configs()
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        try:
            added_roles = set(after.roles) - set(before.roles)
            if not added_roles:
                return
            for role in added_roles:
                for config in self.auto_dm_configs.values():
                    if not isinstance(config, dict):
                        continue
                    if str(role.id) == config.get("role_id", ""):
                        dm_message = config.get("dm_message", "")
                        if not dm_message:
                            print(f"⚠️ Aucun message DM pour le rôle {role.id}")
                            continue
                        try:
                            await after.send(dm_message)
                            print(f"✅ DM envoyé à {after} pour le rôle {role.name}")
                        except Exception as e:
                            print(f"❌ Échec DM pour {after}: {e}")
        except Exception as e:
            print(f"❌ Erreur dans on_member_update AutoDM: {e}")
    @app_commands.command(name="autodm_add", description="Ajoute une config AutoDM (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(role="Rôle concerné", dm_message="Message à envoyer en DM")
    async def autodm_add(self, interaction: discord.Interaction, role: discord.Role, dm_message: str):
        if not dm_message.strip():
            await interaction.response.send_message("❌ Le message DM ne peut être vide.", ephemeral=True)
            return
        config_id = str(uuid.uuid4())
        self.auto_dm_configs[config_id] = {"role_id": str(role.id), "dm_message": dm_message.strip()}
        await self.save_configs()
        await interaction.response.send_message(f"✅ Config ajoutée avec l'ID `{config_id}` pour {role.mention}.", ephemeral=True)
    @app_commands.command(name="autodm_list", description="Liste les configs AutoDM (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def autodm_list(self, interaction: discord.Interaction):
        if not self.auto_dm_configs:
            await interaction.response.send_message("Aucune config définie.", ephemeral=True)
            return
        lines = []
        for cid, config in self.auto_dm_configs.items():
            role_obj = interaction.guild.get_role(int(config.get("role_id", 0)))
            role_name = role_obj.name if role_obj else f"ID {config.get('role_id')}"
            dm_msg = config.get("dm_message", "Aucun message")
            lines.append(f"**ID:** `{cid}`\n**Rôle:** {role_name}\n**Message:** {dm_msg}\n")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)
    @app_commands.command(name="autodm_remove", description="Supprime une config AutoDM (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(config_id="ID de la config")
    async def autodm_remove(self, interaction: discord.Interaction, config_id: str):
        if config_id in self.auto_dm_configs:
            del self.auto_dm_configs[config_id]
            await self.save_configs()
            await interaction.response.send_message(f"✅ Config `{config_id}` supprimée.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ID non trouvé.", ephemeral=True)
    @app_commands.command(name="autodm_modify", description="Modifie une config AutoDM (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(config_id="ID de la config", new_role="Nouveau rôle (optionnel)", new_dm_message="Nouveau message DM (optionnel)")
    async def autodm_modify(self, interaction: discord.Interaction, config_id: str, new_role: discord.Role = None, new_dm_message: str = None):
        if config_id not in self.auto_dm_configs:
            await interaction.response.send_message("❌ ID non trouvé.", ephemeral=True)
            return
        config = self.auto_dm_configs[config_id]
        if new_role is not None:
            config["role_id"] = str(new_role.id)
        if new_dm_message is not None:
            if not new_dm_message.strip():
                await interaction.response.send_message("❌ Le nouveau message ne peut être vide.", ephemeral=True)
                return
            config["dm_message"] = new_dm_message.strip()
        self.auto_dm_configs[config_id] = config
        await self.save_configs()
        await interaction.response.send_message(f"✅ Config `{config_id}` modifiée.", ephemeral=True)

async def setup_autodm(bot: commands.Bot):
    await bot.add_cog(AutoDMCog(bot))

# ========================================
# Module de modération (admin uniquement)
# ========================================
class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.banned_words = {"merde", "putain", "con", "connard", "salop", "enculé", "nique ta mère"}
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.author.guild_permissions.administrator:
            return
        content_lower = message.content.lower()
        for banned in self.banned_words:
            if banned in content_lower:
                try:
                    await message.delete()
                    try:
                        await message.author.send("Ton message a été supprimé pour propos interdits.")
                    except Exception as e:
                        print(f"Erreur DM à {message.author}: {e}")
                except Exception as e:
                    print(f"Erreur de suppression: {e}")
                break
    @app_commands.command(name="list_banned_words", description="Liste les mots bannis (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_banned_words(self, interaction: discord.Interaction):
        words = ", ".join(sorted(self.banned_words))
        await interaction.response.send_message(f"Mots bannis : {words}", ephemeral=True)
    @app_commands.command(name="add_banned_word", description="Ajoute un mot à la liste (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(word="Mot à bannir")
    async def add_banned_word(self, interaction: discord.Interaction, word: str):
        word_lower = word.lower()
        if word_lower in self.banned_words:
            await interaction.response.send_message("Ce mot est déjà banni.", ephemeral=True)
        else:
            self.banned_words.add(word_lower)
            await interaction.response.send_message(f"Le mot '{word}' a été ajouté.", ephemeral=True)
    @app_commands.command(name="remove_banned_word", description="Retire un mot de la liste (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(word="Mot à retirer")
    async def remove_banned_word(self, interaction: discord.Interaction, word: str):
        word_lower = word.lower()
        if word_lower in self.banned_words:
            self.banned_words.remove(word_lower)
            await interaction.response.send_message(f"Le mot '{word}' n'est plus banni.", ephemeral=True)
        else:
            await interaction.response.send_message("Ce mot n'était pas banni.", ephemeral=True)
    @app_commands.command(name="mute", description="Mute un utilisateur (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="Membre à mute", duration="Durée en minutes")
    async def mute(self, interaction: discord.Interaction, member: discord.Member, duration: int):
        muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
        if not muted_role:
            try:
                muted_role = await interaction.guild.create_role(name="Muted", reason="Création pour modération.")
                for channel in interaction.guild.channels:
                    try:
                        await channel.set_permissions(muted_role, send_messages=False, speak=False)
                    except Exception as e:
                        print(f"Erreur permissions sur {channel.name}: {e}")
            except Exception as e:
                await interaction.response.send_message(f"Erreur création rôle Muted: {e}", ephemeral=True)
                return
        try:
            await member.add_roles(muted_role, reason="Mute admin")
            await interaction.response.send_message(f"{member.mention} muté pendant {duration} minutes.", ephemeral=True)
            await asyncio.sleep(duration * 60)
            await member.remove_roles(muted_role, reason="Fin du mute")
            await interaction.followup.send(f"{member.mention} n'est plus mute.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erreur lors du mute: {e}", ephemeral=True)
    @app_commands.command(name="ban", description="Bannit un utilisateur (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="Membre à bannir", reason="Raison (optionnel)")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison"):
        try:
            await member.ban(reason=reason)
            await interaction.response.send_message(f"{member.mention} banni. Raison: {reason}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erreur en bannissant {member.mention}: {e}", ephemeral=True)
    @app_commands.command(name="kick", description="Expulse un utilisateur (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="Membre à expulser", reason="Raison (optionnel)")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison"):
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(f"{member.mention} expulsé. Raison: {reason}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erreur en expulsant {member.mention}: {e}", ephemeral=True)

async def setup_moderation(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))

# ========================================
# Serveur HTTP keep-alive
# ========================================
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
        print(f"✅ Serveur keep-alive lancé sur le port {port}")
    except Exception as e:
        print(f"❌ Erreur lors du lancement du serveur keep-alive : {e}")

keep_alive()

# ========================================
# Fusion unique de on_ready pour éviter les redéfinitions
# ========================================
@bot.event
async def on_ready():
    try:
        print(f"✅ Connecté en tant que {bot.user} (ID : {bot.user.id})")
        if not check_programmed_messages.is_running():
            check_programmed_messages.start()
            print("✅ Boucle des messages programmés démarrée")
        if not recap_hebdo_task.is_running():
            recap_hebdo_task.start()
            print("🕒 Tâche recap_hebdo_task démarrée")
        if not weekly_stats_task.is_running():
            weekly_stats_task.start()
            print("📊 Tâche weekly_stats_task démarrée")
    except Exception as e:
        print(f"❌ Erreur dans on_ready : {e}")

# ========================================
# Pomodoro
# ========================================
@tree.command(name="pomodoro", description="Lance une session Pomodoro personnalisée")
@app_commands.describe(
    focus="Temps de concentration en minutes (par défaut 25)",
    pause="Petite pause en minutes (par défaut 5)",
    longue_pause="Pause longue toutes les 4 sessions (par défaut 10)"
)
async def pomodoro(interaction: discord.Interaction, focus: int = 25, pause: int = 5, longue_pause: int = 10):
    await interaction.response.defer(ephemeral=True)
    allowed_id = config_pomodoro.get("allowed_channel_id")
    if allowed_id and str(interaction.channel.id) != allowed_id:
        await interaction.followup.send("❌ Cette commande n'est pas autorisée ici.", ephemeral=True)
        return

    await interaction.followup.send(
        f"🕒 Début de ta session Pomodoro : **{focus} min de focus** / **{pause} min de pause** / **{longue_pause} min de longue pause** toutes les 4 sessions.",
        ephemeral=True
    )

    user = interaction.user
    for session in range(1, 5):
        await user.send(f"🔴 Session {session} — Focus pendant {focus} minutes !")
        await asyncio.sleep(focus * 60)
        if session < 4:
            await user.send(f"🟡 Pause courte — {pause} minutes de pause.")
            await asyncio.sleep(pause * 60)
        else:
            await user.send(f"🟢 Pause longue — {longue_pause} minutes de pause.")
            await asyncio.sleep(longue_pause * 60)
    await user.send("✅ Pomodoro terminé ! Bravo pour ton focus 💪")

# ========================================
# Objectifs semaine
# ========================================
@tree.command(name="ajouter_objectif", description="Ajoute un objectif personnel à suivre")
async def ajouter_objectif(interaction: discord.Interaction, objectif: str):
    if bot.xp_config.get("goals_channel") and str(interaction.channel.id) != str(bot.xp_config["goals_channel"]):
        await interaction.response.send_message("❌ Cette commande n’est pas autorisée ici.", ephemeral=True)
        return
    uid = str(interaction.user.id)
    objectifs_data.setdefault(uid, []).append(objectif)
    await sauvegarder_json_async(GOALS_FILE, objectifs_data)
    await interaction.response.send_message(f"✅ Objectif ajouté : **{objectif}**", ephemeral=True)

@tree.command(name="voir_objectifs", description="Affiche tes objectifs enregistrés")
async def voir_objectifs(interaction: discord.Interaction):
    if bot.xp_config.get("goals_channel") and str(interaction.channel.id) != str(bot.xp_config["goals_channel"]):
        await interaction.response.send_message("❌ Cette commande n’est pas autorisée ici.", ephemeral=True)
        return
    uid = str(interaction.user.id)
    objectifs = objectifs_data.get(uid, [])
    if not objectifs:
        await interaction.response.send_message("📭 Tu n’as aucun objectif enregistré.", ephemeral=True)
        return
    lignes = "\n".join(f"🔹 {o}" for o in objectifs)
    await interaction.response.send_message(f"🎯 Tes objectifs :\n{lignes}", ephemeral=True)

@tree.command(name="supprimer_objectif", description="Supprime un de tes objectifs")
@app_commands.describe(position="Numéro de l’objectif à supprimer (1 = premier)")
async def supprimer_objectif(interaction: discord.Interaction, position: int):
    if bot.xp_config.get("goals_channel") and str(interaction.channel.id) != str(bot.xp_config["goals_channel"]):
        await interaction.response.send_message("❌ Cette commande n’est pas autorisée ici.", ephemeral=True)
        return
    uid = str(interaction.user.id)
    objectifs = objectifs_data.get(uid, [])
    if not (1 <= position <= len(objectifs)):
        await interaction.response.send_message("❌ Numéro invalide.", ephemeral=True)
        return
    supprime = objectifs.pop(position - 1)
    if not objectifs:
        objectifs_data.pop(uid, None)
    await sauvegarder_json_async(GOALS_FILE, objectifs_data)
    await interaction.response.send_message(f"🗑️ Objectif supprimé : **{supprime}**", ephemeral=True)

# ========================================
# 📆 Récapitulatif hebdomadaire automatique
# ========================================
@tree.command(name="set_channel_recap", description="Définit le salon pour les récapitulatifs hebdomadaires (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon où sera posté le récap")
async def set_channel_recap(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.recap_config["channel_id"] = str(channel.id)
    await interaction.response.send_message(f"✅ Salon défini pour les récapitulatifs : {channel.mention}", ephemeral=True)

@tree.command(name="set_role_recap", description="Définit le rôle à mentionner pour le récapitulatif (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(role="Rôle à ping à chaque récap")
async def set_role_recap(interaction: discord.Interaction, role: discord.Role):
    bot.recap_config["role_id"] = str(role.id)
    await interaction.response.send_message(f"✅ Rôle défini pour le récap : {role.mention}", ephemeral=True)

@tasks.loop(minutes=1)
async def recap_hebdo_task():
    try:
        now = datetime.datetime.now(ZoneInfo("Europe/Paris"))
        if now.weekday() == 6 and now.hour == 20 and now.minute == 0:
            channel_id = bot.recap_config.get("channel_id")
            role_id = bot.recap_config.get("role_id")
            if channel_id and role_id:
                channel = bot.get_channel(int(channel_id))
                if channel:
                    message = (
                        f"📆 **Récapitulatif hebdomadaire !**\n"
                        f"<@&{role_id}> partagez vos avancées, réussites, et ce que vous voulez améliorer pour la semaine prochaine 💪"
                    )
                    await channel.send(message)
                    print("✅ Message de récap envoyé.")
                else:
                    print("❌ Salon introuvable pour le récap.")
    except Exception as e:
        print(f"❌ Erreur dans recap_hebdo_task : {e}")

@tasks.loop(minutes=1)
async def weekly_stats_task():
    try:
        now = datetime.datetime.now(ZoneInfo("Europe/Paris"))
        if now.weekday() == 6 and now.hour == 21 and now.minute == 0:
            if not hasattr(bot, "stats_channel_id") or not bot.stats_channel_id:
                print("⚠️ Aucun salon défini pour les stats hebdomadaires.")
                return
            channel = bot.get_channel(int(bot.stats_channel_id))
            if not channel:
                print("❌ Salon introuvable pour les stats hebdo.")
                return
            stats = bot.weekly_stats
            if not stats:
                await channel.send("📊 Aucune activité enregistrée cette semaine.")
                return
            message = "**📈 Statistiques hebdomadaires :**\n"
            for uid, data in stats.items():
                member = channel.guild.get_member(int(uid))
                if not member:
                    continue
                msg_count = data.get("messages", 0)
                vocal_minutes = round(data.get("vocal", 0) / 60)
                message += f"• {member.mention} — 📨 {msg_count} msg / 🔊 {vocal_minutes} min vocal\n"
            await channel.send(message.strip())
            bot.weekly_stats = {}
            print("✅ Statistiques hebdomadaires envoyées.")
    except Exception as e:
        print(f"❌ Erreur dans weekly_stats_task : {e}")

@tree.command(name="stats_hebdo", description="Affiche tes statistiques de la semaine")
async def stats_hebdo(interaction: discord.Interaction):
    try:
        uid = str(interaction.user.id)
        stats = bot.weekly_stats.get(uid, {"messages": 0, "vocal_minutes": 0})
        nb_messages = stats.get("messages", 0)
        minutes_vocal = stats.get("vocal_minutes", 0)
        texte = textwrap.dedent(f"""
        📊 **Stats de la semaine — {interaction.user.mention}**
        ✉️ Messages envoyés : **{nb_messages}**
        🎙️ Minutes en vocal : **{minutes_vocal}**
        """)
        await interaction.response.send_message(texte.strip(), ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)

# ---------------------------------------------------------------
# Commande admin : /set_destinataires_sos
# ---------------------------------------------------------------
@tree.command(name="set_destinataires_sos", description="Définit les destinataires des messages de détresse (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    mentions_roles="Mentionne les rôles (ex: @Aide @Soigneur)",
    mentions_utilisateurs="Mentionne les utilisateurs (ex: @Marie @Lucas)"
)
async def set_destinataires_sos(interaction: discord.Interaction, mentions_roles: str, mentions_utilisateurs: str):
    bot.sos_receivers = []
    for role in interaction.guild.roles:
        if role.mention in mentions_roles:
            bot.sos_receivers.append(role.id)
    for member in interaction.guild.members:
        if member.mention in mentions_utilisateurs:
            bot.sos_receivers.append(member.id)
    await sauvegarder_json_async(SOS_CONFIG_FILE, {"receivers": bot.sos_receivers})
    await interaction.response.send_message("✅ Destinataires mis à jour pour les messages SOS.", ephemeral=True)

@tree.command(name="sos", description="Lance une alerte en cas de burn-out ou besoin d’aide")
async def sos(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        if not bot.sos_receivers:
            await interaction.followup.send("⚠️ Aucun destinataire configuré pour les alertes. Contacte un admin.", ephemeral=True)
            return
        sent_to = []
        for receiver_id in bot.sos_receivers:
            try:
                member = interaction.guild.get_member(receiver_id)
                if member:
                    await member.send(f"🚨 Alerte SOS : {interaction.user.mention} a besoin d’aide.\n> *\"Je ne vais pas bien en ce moment. J’aurais besoin de parler ou d’un coup de main.\"*")
                    sent_to.append(member.display_name)
                else:
                    role = interaction.guild.get_role(receiver_id)
                    if role:
                        for m in role.members:
                            try:
                                await m.send(f"🚨 Alerte SOS : {interaction.user.mention} a besoin d’aide.\n> *\"Je ne vais pas bien en ce moment. J’aurais besoin de parler ou d’un coup de main.\"*")
                                sent_to.append(m.display_name)
                            except:
                                pass
            except Exception as e:
                print(f"❌ Erreur en envoyant SOS à {receiver_id} : {e}")
        if sent_to:
            await interaction.followup.send("✅ Alerte envoyée. Tu n’es pas seul.", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Aucun destinataire valide n’a pu être joint.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

@tree.command(name="mode_evenement", description="Active ou désactive un mode événement spécial (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(nom="Nom de l'événement", message="Message affiché pendant l'événement", actif="Activer ou désactiver")
async def mode_evenement(interaction: discord.Interaction, nom: str, message: str, actif: bool):
    try:
        evenement_config.update({
            "actif": actif,
            "nom": nom,
            "message": message
        })
        await sauvegarder_json_async(EVENEMENT_CONFIG_FILE, evenement_config)
        if actif:
            await interaction.response.send_message(f"🎉 Mode événement **{nom}** activé : {message}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Mode événement désactivé.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)

@tree.command(name="set_theme", description="Modifie le thème visuel du serveur (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(nom="Nom du thème (ex: Été, Noël...)", emoji="Emoji principal", message="Message d'ambiance")
async def set_theme(interaction: discord.Interaction, nom: str, emoji: str, message: str):
    try:
        theme_config.update({
            "nom": nom,
            "emoji": emoji,
            "message": message
        })
        await sauvegarder_json_async(THEME_CONFIG_FILE, theme_config)
        await interaction.response.send_message(f"🎨 Thème **{nom}** défini avec l'emoji {emoji} : {message}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)

@tree.command(name="mission_secrete", description="Assigne une mission secrète hebdomadaire à un utilisateur (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(utilisateur="Utilisateur ciblé", mission="Mission à accomplir")
async def mission_secrete(interaction: discord.Interaction, utilisateur: discord.Member, mission: str):
    try:
        missions_secretes[str(utilisateur.id)] = {
            "mission": mission,
            "assignée_par": interaction.user.id,
            "timestamp": datetime.datetime.now().isoformat()
        }
        await sauvegarder_json_async(MISSIONS_FILE, missions_secretes)
        try:
            await utilisateur.send(f"🕵️ Nouvelle mission secrète de la semaine :\n**{mission}**")
        except:
            pass
        await interaction.response.send_message(f"✅ Mission attribuée à {utilisateur.mention}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)

@tree.command(name="ma_mission", description="Affiche ta mission secrète de la semaine")
async def ma_mission(interaction: discord.Interaction):
    data = missions_secretes.get(str(interaction.user.id))
    if not data:
        await interaction.response.send_message("❌ Aucune mission secrète en cours.", ephemeral=True)
    else:
        await interaction.response.send_message(f"🕵️ Mission secrète : **{data['mission']}**", ephemeral=True)

@tree.command(name="ajouter_evenement", description="Ajoute un événement au calendrier collaboratif")
@app_commands.describe(titre="Titre de l'événement", date="Date (format JJ/MM/AAAA)", heure="Heure (HH:MM)", description="Détails")
async def ajouter_evenement(interaction: discord.Interaction, titre: str, date: str, heure: str, description: str):
    try:
        try:
            dt = datetime.datetime.strptime(f"{date} {heure}", "%d/%m/%Y %H:%M")
        except ValueError:
            await interaction.response.send_message("❌ Format de date ou heure invalide.", ephemeral=True)
            return
        eid = str(uuid.uuid4())
        evenements_calendrier[eid] = {
            "auteur": interaction.user.id,
            "titre": titre,
            "datetime": dt.isoformat(),
            "description": description
        }
        await sauvegarder_json_async(CALENDRIER_FILE, evenements_calendrier)
        await interaction.response.send_message(f"✅ Événement **{titre}** ajouté au calendrier !", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)

@tree.command(name="voir_evenements", description="Affiche les événements à venir")
async def voir_evenements(interaction: discord.Interaction):
    try:
        if not evenements_calendrier:
            await interaction.response.send_message("📭 Aucun événement prévu.", ephemeral=True)
            return
        lignes = []
        now = datetime.datetime.now()
        for eid, evt in sorted(evenements_calendrier.items(), key=lambda x: x[1]["datetime"]):
            dt = datetime.datetime.fromisoformat(evt["datetime"])
            if dt > now:
                date_str = dt.strftime("%d/%m/%Y à %H:%M")
                lignes.append(f"📅 **{evt['titre']}** — {date_str}\n📝 {evt['description']}")
        texte = "\n\n".join(lignes) if lignes else "📭 Aucun événement à venir."
        await interaction.response.send_message(texte.strip(), ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)

@tree.command(name="besoin_aide", description="Demander de l'aide et créer une catégorie privée pour l'aide.")
async def besoin_aide(interaction: discord.Interaction):
    modal = HelpRequestModal()
    await interaction.response.send_modal(modal)

class HelpRequestModal(Modal, title="📩 Demande d'aide"):
    def __init__(self):
        super().__init__(timeout=None)
        self.probleme = TextInput(
            label="Décris ton problème ou ta demande d'aide :",
            style=discord.TextStyle.paragraph,
            placeholder="Décris ton problème ici.",
            required=True,
            max_length=2000
        )
        self.add_item(self.probleme)
    async def on_submit(self, interaction: discord.Interaction):
        problem_description = self.probleme.value
        guild = interaction.guild
        categorie = await guild.create_category("Demande d'aide")
        text_channel = await guild.create_text_channel("problème", category=categorie)
        voice_channel = await guild.create_voice_channel("aide vocal", category=categorie)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True),
        }
        await text_channel.set_permissions(interaction.user, read_messages=True)
        await voice_channel.set_permissions(interaction.user, connect=True)
        help_request_data = {
            "user_id": str(interaction.user.id),
            "problem_description": problem_description,
            "category_id": str(categorie.id),
            "text_channel_id": str(text_channel.id),
            "voice_channel_id": str(voice_channel.id),
            "created_at": datetime.datetime.now().isoformat()
        }
        categories_crees[str(interaction.user.id)] = help_request_data
        await sauvegarder_json_async(HELP_REQUEST_FILE, categories_crees)
        await text_channel.send(
            f"{interaction.user.mention} a besoin d'aide. Problème : {problem_description}",
            view=HelpButtons(interaction.user.id)
        )
        await interaction.followup.send("✅ Demande d'aide envoyée ! Une catégorie privée a été créée.", ephemeral=True)

class HelpButtons(View):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    @discord.ui.button(label="J'ai besoin d'aide", style=discord.ButtonStyle.primary)
    async def button_need_help(self, interaction: discord.Interaction, button: Button):
        role = discord.utils.get(interaction.guild.roles, name="Besoin d'aide")
        if not role:
            role = await interaction.guild.create_role(name="Besoin d'aide")
        await interaction.user.add_roles(role)
        category_data = categories_crees.get(str(self.user_id), {})
        category = interaction.guild.get_category(int(category_data.get("category_id")))
        if category:
            await category.set_permissions(role, view_channel=True)
        await interaction.response.send_message(f"🔔 Vous avez été ajouté au rôle **{role.name}** pour aider.", ephemeral=True)
    @discord.ui.button(label="Je peux aider", style=discord.ButtonStyle.secondary)
    async def button_can_help(self, interaction: discord.Interaction, button: Button):
        role = discord.utils.get(interaction.guild.roles, name="Aider")
        if not role:
            role = await interaction.guild.create_role(name="Aider")
        await interaction.user.add_roles(role)
        category_data = categories_crees.get(str(self.user_id), {})
        category = interaction.guild.get_category(int(category_data.get("category_id")))
        if category:
            await category.set_permissions(role, view_channel=True)
        await interaction.response.send_message(f"🔔 Vous avez été ajouté au rôle **{role.name}** pour aider.", ephemeral=True)
    @discord.ui.button(label="Problème Résolu", style=discord.ButtonStyle.danger)
    async def button_problem_solved(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Seul l'utilisateur ayant créé la demande peut marquer le problème comme résolu.", ephemeral=True)
            return
        category_data = categories_crees.get(str(self.user_id), {})
        if category_data:
            category = interaction.guild.get_category(int(category_data.get("category_id")))
            if category:
                await category.delete()
            del categories_crees[str(self.user_id)]
            await sauvegarder_json_async(HELP_REQUEST_FILE, categories_crees)
        await interaction.response.send_message("✅ Le problème a été marqué comme résolu. La catégorie a été supprimée.", ephemeral=True)


@tree.command(name="set_channel_journal", description="Définit le salon autorisé pour écrire dans le journal de focus (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon autorisé")
async def set_channel_journal(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.journal_focus_channel = str(channel.id)
    await interaction.response.send_message(f"✅ Salon de journal défini : {channel.mention}", ephemeral=True)



@tree.command(name="journal_focus", description="Écris dans ton journal de focus (réflexions, engagement, etc.)")
async def journal_focus(interaction: discord.Interaction, texte: str):
    if bot.journal_focus_channel and str(interaction.channel.id) != str(bot.journal_focus_channel):
        await interaction.response.send_message("❌ Cette commande n’est pas autorisée ici.", ephemeral=True)
        return
    try:
        await interaction.response.send_message("✅ Merci ! Ton message a été enregistré.", ephemeral=True)
        await interaction.channel.send(f"📝 Journal de {interaction.user.mention} :\n```{texte}```")
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)




# ========================================
# 🧩 Commande : /reaction_role — message avec plusieurs rôles par réaction
# ========================================
@tree.command(name="reaction_role_avec_message", description="Créer un message avec des réactions pour attribuer des rôles")
@app_commands.checks.has_permissions(administrator=True)
async def reaction_role_avec_message(interaction: discord.Interaction, salon: discord.TextChannel, emojis: str, roles: str):
    try:
        if not interaction.guild:
            await interaction.response.send_message("Cette commande ne peut être utilisée que dans un serveur.", ephemeral=True)
            return
        emojis_liste = [e.strip() for e in emojis.split(",")]
        roles_liste = [r.strip() for r in roles.split(",")]
        if len(emojis_liste) != len(roles_liste):
            await interaction.response.send_message("❌ Le nombre d'emojis et de rôles doit être le même.", ephemeral=True)
            return
        interaction.client.temp_reaction_data = {
            "channel": salon,
            "emojis": emojis_liste,
            "roles": roles_liste,
            "user_id": interaction.user.id
        }
        class ModalReactionRole(discord.ui.Modal, title="Texte du message à envoyer"):
            message = discord.ui.TextInput(
                label="Contenu du message",
                style=discord.TextStyle.paragraph,
                required=True,
                max_length=4000
            )
            async def on_submit(self, interaction_modal: discord.Interaction):
                try:
                    await interaction_modal.response.defer(thinking=False)
                    data = interaction.client.temp_reaction_data
                    if interaction_modal.user.id != data["user_id"]:
                        await interaction_modal.followup.send("Tu n'es pas autorisé à envoyer ce message.", ephemeral=True)
                        return
                    channel = data["channel"]
                    emojis = data["emojis"]
                    roles = data["roles"]
                    message_texte = self.message.value
                    message_envoye = await channel.send(message_texte)
                    for emoji in emojis:
                        await message_envoye.add_reaction(emoji)
                    bot: commands.Bot = interaction.client
                    if not hasattr(bot, "reaction_roles"):
                        bot.reaction_roles = {}
                    role_ids = []
                    for role_str in roles:
                        role_str = role_str.strip()
                        if role_str.startswith("<@&"):
                            role_id = int(role_str.replace("<@&", "").replace(">", ""))
                            role_ids.append(role_id)
                        else:
                            role_obj = discord.utils.get(interaction.guild.roles, name=role_str.replace("@", ""))
                            if role_obj:
                                role_ids.append(role_obj.id)
                            else:
                                await interaction_modal.followup.send(f"❌ Rôle introuvable : `{role_str}`", ephemeral=True)
                                return
                    # Transformer chaque emoji avec get_emoji_key pour normaliser la clé.
                    mapping = { get_emoji_key(e): r_id for e, r_id in zip(emojis, role_ids) }
                    bot.reaction_roles[str(message_envoye.id)] = mapping
                    await sauvegarder_json_async(REACTION_ROLE_FILE, bot.reaction_roles)
                    await interaction_modal.followup.send("✅ Message envoyé avec succès et réactions enregistrées !", ephemeral=True)
                except Exception as e:
                    await interaction_modal.followup.send(f"❌ Erreur dans le modal : {e}", ephemeral=True)
        await interaction.response.send_modal(ModalReactionRole())
    except Exception as e:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)

# ========================================
# Fonction main – Chargement des données et lancement du bot
# ========================================
async def main():
    global xp_data, messages_programmes, defis_data, config_pomodoro, objectifs_data
    global sos_config, evenement_config, theme_config, missions_secretes, evenements_calendrier
    try:
        xp_data = await charger_json_async(XP_FILE)
        messages_programmes = await charger_json_async(MSG_FILE)
        defis_data = await charger_json_async(DEFIS_FILE)
        config_pomodoro = await charger_json_async(POMODORO_CONFIG_FILE)
        objectifs_data = await charger_json_async(GOALS_FILE)
        sos_config = await charger_json_async(SOS_CONFIG_FILE)
        evenement_config = await charger_json_async(EVENEMENT_CONFIG_FILE)
        theme_config = await charger_json_async(THEME_CONFIG_FILE)
        missions_secretes = await charger_json_async(MISSIONS_FILE)
        evenements_calendrier = await charger_json_async(CALENDRIER_FILE)
        categories_crees = await charger_json_async(HELP_REQUEST_FILE)
        bot.reaction_roles = await charger_json_async(REACTION_ROLE_FILE)
        bot.sos_receivers = sos_config.get("receivers", [])
        bot.evenement_config = evenement_config
        bot.theme_config = theme_config
        bot.missions_secretes = missions_secretes
        bot.evenements_calendrier = evenements_calendrier
        bot.categories_aide = categories_crees
    except Exception as e:
        print(f"❌ Erreur lors du chargement des données : {e}")
    await setup_admin_utils(bot)
    await setup_autodm(bot)
    await setup_moderation(bot)
    try:
        await bot.start(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        print(f"❌ Erreur critique au lancement du bot : {e}")

asyncio.run(main())

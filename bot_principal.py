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
from zoneinfo import ZoneInfo
import uuid
import aiofiles
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

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
POMODORO_CONFIG_FILE = os.path.join(DATA_FOLDER, "config_pomodoro.json")
GOALS_FILE = os.path.join(DATA_FOLDER, "objectifs.json")
SOS_CONFIG_FILE = os.path.join(DATA_FOLDER, "sos_config.json")
EVENEMENT_CONFIG_FILE = os.path.join(DATA_FOLDER, "evenement.json")
THEME_CONFIG_FILE = os.path.join(DATA_FOLDER, "themes.json")
MISSIONS_FILE = os.path.join(DATA_FOLDER, "missions_secretes.json")
CALENDRIER_FILE = os.path.join(DATA_FOLDER, "evenements_calendrier.json")
HELP_REQUEST_FILE = os.path.join(DATA_FOLDER, "help_requests.json")
REACTION_ROLE_FILE = os.path.join(DATA_FOLDER, "reaction_roles.json")
os.makedirs(DATA_FOLDER, exist_ok=True)

# ========================================
# Verrou global d'accès asynchrone aux fichiers
# ========================================
file_lock = asyncio.Lock()

# ========================================
# Fonctions asynchrones de persistance
# ========================================
async def charger_json_async(path: str):
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

async def sauvegarder_json_async(path: str, data):
    async with file_lock:
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=4))

# ========================================
# Utilitaire pour standardiser un emoji
# ========================================
def get_emoji_key(emoji_input) -> str:
    try:
        if isinstance(emoji_input, PartialEmoji):
            pe = emoji_input
        else:
            pe = PartialEmoji.from_str(str(emoji_input))
        if pe.is_custom_emoji():
            return f"<:{pe.name}:{pe.id}>"
        return str(pe)
    except Exception:
        return str(emoji_input)

# ========================================
# Variables globales
# ========================================
xp_data = {}
messages_programmes = {}
defis_data = {}
config_pomodoro = {}
objectifs_data = {}
# Pour gérer les demandes d'aide
categories_aide = {}

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
# Classe principale du bot
# ========================================
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.reaction_roles = {}  # Mapping message_id -> {emoji_key: role_id}
        self.vocal_start_times = {}  # {user_id: timestamp}
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
            "titres": {},
            "goals_channel": None
        }
        self.recap_config = {
            "channel_id": None,
            "role_id": None
        }
        self.weekly_stats = {}  # {user_id: {"messages": int, "vocal": int (secondes)}}
        self.sos_receivers = []
        self.missions_secretes = {}
        self.evenement_config = {}
        self.theme_config = {}
        self.evenements_calendrier = {}
        self.temp_data = {}  # Pour stocker temporairement des données (ex: reaction_role)

    async def setup_hook(self):
        try:
            synced = await self.tree.sync()
            print(f"🌐 {len(synced)} commandes slash synchronisées")
            if not check_programmed_messages.is_running():
                check_programmed_messages.start()
                print("✅ Boucle des messages programmés démarrée")
            if not recap_hebdo_task.is_running():
                recap_hebdo_task.start()
                print("🕒 Tâche récap hebdomadaire démarrée")
            if not weekly_stats_task.is_running():
                weekly_stats_task.start()
                print("📊 Tâche statistiques hebdomadaires démarrée")
        except Exception as e:
            print(f"❌ Erreur dans setup_hook: {e}")

bot = MyBot()
tree = bot.tree

# ========================================
# Gestion des messages (XP & modération)
# ========================================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    # Filtrage des mots interdits
    if not message.author.guild_permissions.administrator:
        banned_words = {"merde", "putain", "con", "connard", "salop", "enculé", "nique ta mère"}
        contenu_lower = message.content.lower()
        for banned in banned_words:
            if banned in contenu_lower:
                try:
                    await message.delete()
                    try:
                        await message.author.send("Ton message a été supprimé pour propos interdits.")
                    except Exception as dm_err:
                        print(f"Erreur en DM à {message.author}: {dm_err}")
                except Exception as del_err:
                    print(f"Erreur lors de la suppression du message: {del_err}")
                return
    # Attribution XP
    uid = str(message.author.id)
    bot.weekly_stats.setdefault(uid, {"messages": 0, "vocal": 0})
    bot.weekly_stats[uid]["messages"] += 1
    xp_val = bot.xp_config["xp_per_message"]
    multiplier = bot.xp_config["multipliers"].get(str(message.channel.id), 1.0)
    total_xp = int(xp_val * multiplier)
    current_xp = await add_xp(message.author.id, total_xp)
    for seuil, role_id in bot.xp_config["level_roles"].items():
        if current_xp >= int(seuil):
            role = message.guild.get_role(int(role_id))
            if role and role not in message.author.roles:
                try:
                    await message.author.add_roles(role, reason="Palier XP atteint")
                    if bot.xp_config["announcement_channel"]:
                        ann_chan = bot.get_channel(int(bot.xp_config["announcement_channel"]))
                        if ann_chan:
                            txt = bot.xp_config["announcement_message"].replace("{mention}", message.author.mention).replace("{xp}", str(current_xp))
                            await ann_chan.send(txt)
                except Exception as e:
                    print(f"❌ Erreur attribution rôle XP: {e}")
    await bot.process_commands(message)

# ========================================
# Gestion du temps vocal
# ========================================
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if not before.channel and after.channel:
        bot.vocal_start_times[member.id] = time.time()
    elif before.channel and not after.channel:
        start = bot.vocal_start_times.pop(member.id, None)
        if start:
            duration = int((time.time() - start) / 60)
            multiplier = bot.xp_config["multipliers"].get(str(before.channel.id), 1.0)
            gained = int(duration * bot.xp_config["xp_per_minute_vocal"] * multiplier)
            current_xp = await add_xp(member.id, gained)
            uid = str(member.id)
            bot.weekly_stats.setdefault(uid, {"messages": 0, "vocal": 0})
            bot.weekly_stats[uid]["vocal"] += duration * 60
            for seuil, role_id in bot.xp_config["level_roles"].items():
                if current_xp >= int(seuil):
                    role = member.guild.get_role(int(role_id))
                    if role and role not in member.roles:
                        try:
                            await member.add_roles(role, reason="XP vocal atteint")
                            if bot.xp_config["announcement_channel"]:
                                ann_chan = bot.get_channel(int(bot.xp_config["announcement_channel"]))
                                if ann_chan:
                                    txt = bot.xp_config["announcement_message"].replace("{mention}", member.mention).replace("{xp}", str(current_xp))
                                    await ann_chan.send(txt)
                        except Exception as e:
                            print(f"❌ Erreur attribution rôle vocal: {e}")

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
# Tâche de messages programmés & défis
# ========================================
@tasks.loop(seconds=30)
async def check_programmed_messages():
    try:
        if not bot.is_ready():
            print("⏳ Bot pas encore prêt...")
            return
        now = datetime.datetime.now(ZoneInfo("Europe/Paris"))
        messages_modifies = False
        for msg_id, msg in list(messages_programmes.items()):
            try:
                msg_time = datetime.datetime.strptime(msg["next"], "%d/%m/%Y %H:%M")
                msg_time = msg_time.replace(tzinfo=ZoneInfo("Europe/Paris"))
            except ValueError as ve:
                print(f"❌ Format invalide pour {msg_id}: {ve}")
                continue
            if now >= msg_time:
                channel = bot.get_channel(int(msg["channel_id"]))
                if channel:
                    if msg["type"] in ["once", "daily", "weekly"]:
                        await channel.send(textwrap.dedent(msg["message"]))
                    elif msg["type"] == "weekly_challenge":
                        sent_msg = await channel.send(textwrap.dedent(msg["message"]))
                        await sent_msg.add_reaction("✅")
                        end_ts = time.time() + float(msg["duration_hours"]) * 3600
                        defis_data[str(sent_msg.id)] = {
                            "channel_id": channel.id,
                            "role_id": msg["role_id"],
                            "end_timestamp": end_ts
                        }
                        await sauvegarder_json_async(DEFIS_FILE, defis_data)
                        asyncio.create_task(retirer_role_apres_defi(channel.guild, sent_msg.id, channel.guild.get_role(int(msg["role_id"]))))
                    # Mise à jour du prochain envoi selon le type
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
        if messages_modifies:
            await sauvegarder_json_async(MSG_FILE, messages_programmes)
    except Exception as e:
        print(f"❌ Erreur dans check_programmed_messages: {e}")

# ========================================
# Commandes XP & Leaderboard (slash)
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
        member = interaction.guild.get_member(int(uid))
        nom = member.display_name if member else f"Utilisateur {uid}"
        lignes.append(f"{i+1}. {nom} — {xp_val} XP")
    txt = "🏆 **Top 10 XP :**\n" + "\n".join(lignes) if lignes else "Aucun XP enregistré."
    await interaction.response.send_message(txt, ephemeral=True)

# ------------------------------------------
# Commandes XP ADMIN
# ------------------------------------------
@tree.command(name="add_xp", description="Ajoute de l'XP à un membre (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def add_xp_cmd(interaction: discord.Interaction, member: discord.Member, amount: int):
    new_total = await add_xp(member.id, amount)
    await interaction.response.send_message(f"✅ {amount} XP ajoutés à {member.mention}\n🔹 Total : **{new_total} XP**", ephemeral=True)

@tree.command(name="set_xp_config", description="Modifie l'XP par message et en vocal (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def set_xp_config(interaction: discord.Interaction, xp_per_message: int, xp_per_minute_vocal: int):
    bot.xp_config["xp_per_message"] = xp_per_message
    bot.xp_config["xp_per_minute_vocal"] = xp_per_minute_vocal
    await interaction.response.send_message(f"✅ XP mis à jour : {xp_per_message} xp/msg, {xp_per_minute_vocal} xp/min vocal", ephemeral=True)

@tree.command(name="set_xp_role", description="Définit un rôle à débloquer par XP (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def set_xp_role(interaction: discord.Interaction, xp: int, role: discord.Role):
    bot.xp_config["level_roles"][str(xp)] = role.id
    await interaction.response.send_message(f"✅ Le rôle **{role.name}** sera attribué dès {xp} XP.", ephemeral=True)

@tree.command(name="set_xp_boost", description="Ajoute un multiplicateur d'XP à un salon (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def set_xp_boost(interaction: discord.Interaction, channel: discord.TextChannel, multiplier: float):
    bot.xp_config["multipliers"][str(channel.id)] = multiplier
    await interaction.response.send_message(f"✅ Multiplicateur x{multiplier} appliqué à {channel.mention}.", ephemeral=True)

@tree.command(name="set_salon_annonce", description="Définit le salon des annonces de niveau (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def set_salon_annonce(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["announcement_channel"] = str(channel.id)
    await interaction.response.send_message(f"✅ Annonces de niveau envoyées dans {channel.mention}.", ephemeral=True)

@tree.command(name="set_message_annonce", description="Modifie le message d’annonce (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def set_message_annonce(interaction: discord.Interaction, message: str):
    bot.xp_config["announcement_message"] = message
    preview = message.replace("{mention}", interaction.user.mention).replace("{xp}", "1234")
    await interaction.response.send_message(f"✅ Message mis à jour !\n\n💬 Aperçu:\n{preview}", ephemeral=True)

@tree.command(name="set_channel_xp", description="Définit le salon où /xp et /leaderboard sont utilisables (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def set_channel_xp(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["xp_command_channel"] = str(channel.id)
    await interaction.response.send_message(f"✅ Commandes XP limitées à {channel.mention}.", ephemeral=True)

@tree.command(name="set_minimum_xp", description="Définit le XP minimum pour /xp (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def set_minimum_xp(interaction: discord.Interaction, min_xp: int):
    bot.xp_config["xp_command_min_xp"] = min_xp
    await interaction.response.send_message(f"✅ Minimum requis: {min_xp} XP.", ephemeral=True)

@tree.command(name="ajouter_badge", description="Ajoute un badge débloqué par XP (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def ajouter_badge(interaction: discord.Interaction, xp: int, badge: str):
    bot.xp_config["badges"][str(xp)] = badge
    await interaction.response.send_message(f"✅ Badge '{badge}' ajouté dès {xp} XP.", ephemeral=True)

@tree.command(name="ajouter_titre", description="Ajoute un titre débloqué par XP (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def ajouter_titre(interaction: discord.Interaction, xp: int, titre: str):
    bot.xp_config["titres"][str(xp)] = titre
    await interaction.response.send_message(f"✅ Titre '{titre}' ajouté dès {xp} XP.", ephemeral=True)

# ------------------------------------------
# Création rapide de salons, rôles et catégories
# ------------------------------------------
@tree.command(name="creer_salon", description="Crée un ou plusieurs salons dans une catégorie (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def creer_salon(interaction: discord.Interaction, noms: str, categorie: discord.CategoryChannel, type: str):
    noms_list = [n.strip() for n in noms.split(",") if n.strip()]
    if not noms_list:
        await interaction.response.send_message("❌ Aucun nom fourni.", ephemeral=True)
        return
    created_channels = []
    for nom in noms_list:
        try:
            if type.lower() == "text":
                channel = await interaction.guild.create_text_channel(name=nom, category=categorie)
            elif type.lower() == "voice":
                channel = await interaction.guild.create_voice_channel(name=nom, category=categorie)
            else:
                await interaction.response.send_message("❌ Type invalide (text ou voice).", ephemeral=True)
                return
            created_channels.append(channel.mention)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur création salon {nom}: {e}", ephemeral=True)
            return
    msg = f"✅ Salon{'s' if len(created_channels) > 1 else ''} créé{'s' if len(created_channels) > 1 else ''} : " + ", ".join(created_channels)
    await interaction.response.send_message(msg, ephemeral=True)

@tree.command(name="creer_role", description="Crée un ou plusieurs rôles (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def creer_role(interaction: discord.Interaction, noms: str):
    noms_list = [n.strip() for n in noms.split(",") if n.strip()]
    if not noms_list:
        await interaction.response.send_message("❌ Aucun nom fourni.", ephemeral=True)
        return
    created_roles = []
    for nom in noms_list:
        try:
            role = await interaction.guild.create_role(name=nom)
            created_roles.append(role.name)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur création rôle {nom}: {e}", ephemeral=True)
            return
    msg = f"✅ Rôle{'s' if len(created_roles) > 1 else ''} créé{'s' if len(created_roles) > 1 else ''} : " + ", ".join(created_roles)
    await interaction.response.send_message(msg, ephemeral=True)

@tree.command(name="creer_categorie_privee", description="Crée une catégorie privée accessible à un rôle (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def creer_categorie_privee(interaction: discord.Interaction, nom: str, role: discord.Role):
    try:
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            role: discord.PermissionOverwrite(view_channel=True)
        }
        new_cat = await interaction.guild.create_category(name=nom, overwrites=overwrites)
        await interaction.response.send_message(f"✅ Catégorie privée **{new_cat.name}** créée pour {role.name}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur création catégorie: {e}", ephemeral=True)

# ------------------------------------------
# Messages programmés & Défis
# ------------------------------------------
class ProgrammerMessageModal(Modal, title="🗓️ Programmer un message"):
    def __init__(self, salon: discord.TextChannel, type_message: str, date_heure: str):
        super().__init__(timeout=None)
        self.salon = salon
        self.msg_type = type_message  # "once", "daily", "weekly", "weekly_challenge"
        self.date_heure = date_heure
        self.contenu = TextInput(
            label="Contenu du message",
            style=TextStyle.paragraph,
            placeholder="Tapez le message complet",
            required=True,
            max_length=2000
        )
        self.add_item(self.contenu)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        texte = textwrap.dedent(self.contenu.value)
        if len(texte) > 2000:
            await interaction.followup.send("❌ Message trop long.", ephemeral=True)
            return
        msg_id = str(uuid.uuid4())
        messages_programmes[msg_id] = {
            "channel_id": str(self.salon.id),
            "message": texte,
            "type": self.msg_type,
            "next": self.date_heure
        }
        await sauvegarder_json_async(MSG_FILE, messages_programmes)
        await interaction.followup.send(f"✅ Message programmé dans {self.salon.mention} ({self.msg_type}) pour {self.date_heure}.", ephemeral=True)

@tree.command(name="programmer_message", description="Planifie un message automatique (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def programmer_message(interaction: discord.Interaction, salon: discord.TextChannel, type: str, date_heure: str):
    valid_types = ["once", "daily", "weekly", "weekly_challenge"]
    if type.lower() not in valid_types:
        await interaction.response.send_message("❌ Type invalide.", ephemeral=True)
        return
    try:
        datetime.datetime.strptime(date_heure, "%d/%m/%Y %H:%M")
    except ValueError:
        await interaction.response.send_message("❌ Format date invalide.", ephemeral=True)
        return
    try:
        await interaction.response.send_modal(ProgrammerMessageModal(salon, type.lower(), date_heure))
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur modal: {e}", ephemeral=True)

@tree.command(name="supprimer_message_programmé", description="Supprime un message programmé (admin)")
@app_commands.checks.has_permissions(administrator=True)
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
    for mid, msg in messages_programmes.items():
        txt += f"🆔 `{mid}` — <#{msg['channel_id']}> — {msg['next']} — {msg['type']}\n"
    await interaction.response.send_message(txt.strip(), ephemeral=True)

class ModifierMessageModal(Modal, title="✏️ Modifier un message"):
    def __init__(self, message_id: str):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.nouveau_msg = TextInput(
            label="Nouveau message",
            style=TextStyle.paragraph,
            placeholder="Tapez le nouveau message",
            required=True,
            max_length=2000
        )
        self.add_item(self.nouveau_msg)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.message_id in messages_programmes:
            messages_programmes[self.message_id]["message"] = textwrap.dedent(self.nouveau_msg.value)
            await sauvegarder_json_async(MSG_FILE, messages_programmes)
            await interaction.followup.send("✅ Message modifié.", ephemeral=True)
        else:
            await interaction.followup.send("❌ ID introuvable.", ephemeral=True)

@tree.command(name="modifier_message_programmé", description="Modifie un message programmé (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def modifier_message_programme(interaction: discord.Interaction, message_id: str):
    if message_id in messages_programmes:
        await interaction.response.send_modal(ModifierMessageModal(message_id))
    else:
        await interaction.response.send_message("❌ ID non trouvé.", ephemeral=True)

# ------------------------------------------
# Attribution de rôles via réactions
# ------------------------------------------
class RoleReactionModal(Modal, title="✍️ Message avec réaction"):
    def __init__(self, emoji: str, role: discord.Role, salon: discord.TextChannel):
        super().__init__(timeout=None)
        try:
            self.emoji = PartialEmoji.from_str(emoji)
            self.emoji_key = get_emoji_key(self.emoji)
        except Exception as e:
            raise ValueError(f"Emoji invalide: {emoji}") from e
        self.role = role
        self.salon = salon
        self.contenu = TextInput(
            label="Texte du message",
            style=TextStyle.paragraph,
            placeholder="Tapez le message",
            required=True,
            max_length=2000
        )
        self.add_item(self.contenu)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            msg_envoye = await self.salon.send(textwrap.dedent(self.contenu.value))
            await msg_envoye.add_reaction(self.emoji)
            bot.reaction_roles[str(msg_envoye.id)] = {self.emoji_key: self.role.id}
            await sauvegarder_json_async(REACTION_ROLE_FILE, bot.reaction_roles)
            await interaction.followup.send(f"✅ Message envoyé dans {self.salon.mention}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

@tree.command(name="ajout_reaction_id", description="Ajoute une réaction à un message existant (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def ajout_reaction_id(interaction: discord.Interaction, role: discord.Role, emoji: str, message_id: str):
    try:
        mid = int(message_id)
        msg = await interaction.channel.fetch_message(mid)
        await msg.add_reaction(emoji)
        key = get_emoji_key(emoji)
        bot.reaction_roles.setdefault(str(mid), {})[key] = role.id
        await sauvegarder_json_async(REACTION_ROLE_FILE, bot.reaction_roles)
        await interaction.response.send_message(f"✅ Réaction {emoji} ajoutée au message {message_id} pour le rôle {role.name}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
    try:
        guild = bot.get_guild(payload.guild_id)
        if not guild: return
        member = guild.get_member(payload.user_id)
        if not member: return
        key = get_emoji_key(payload.emoji)
        data = bot.reaction_roles.get(str(payload.message_id))
        if not data: return
        role_id = data.get(key)
        if not role_id: return
        role = guild.get_role(int(role_id))
        if role and role not in member.roles:
            try:
                await member.add_roles(role, reason="Réaction ajoutée")
            except Exception as e:
                print(f"❌ Erreur ajout rôle {role.name} pour {member.display_name}: {e}")
    except Exception as e:
        print(f"❌ Erreur dans on_raw_reaction_add: {e}")

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
    try:
        guild = bot.get_guild(payload.guild_id)
        if not guild: return
        member = guild.get_member(payload.user_id)
        if not member: return
        key = get_emoji_key(payload.emoji)
        data = bot.reaction_roles.get(str(payload.message_id))
        if not data: return
        role_id = data.get(key)
        if not role_id: return
        role = guild.get_role(int(role_id))
        if role and role in member.roles:
            try:
                await member.remove_roles(role, reason="Réaction retirée")
            except Exception as e:
                print(f"❌ Erreur retrait rôle {role.name} pour {member.display_name}: {e}")
    except Exception as e:
        print(f"❌ Erreur dans on_raw_reaction_remove: {e}")

# ------------------------------------------
# Défi hebdomadaire et récurrent
# ------------------------------------------
class DefiModal(Modal, title="🔥 Défi de la semaine"):
    def __init__(self, salon: discord.TextChannel, role: discord.Role, duree_heures: int):
        super().__init__(timeout=None)
        self.salon = salon
        self.role = role
        self.duree = duree_heures
        self.message = TextInput(
            label="Message du défi",
            style=TextStyle.paragraph,
            placeholder="Décrivez votre défi ici",
            required=True,
            max_length=2000
        )
        self.add_item(self.message)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            msg = await self.salon.send(textwrap.dedent(self.message.value))
            await msg.add_reaction("✅")
            end_ts = time.time() + self.duree * 3600
            defis_data[str(msg.id)] = {"channel_id": self.salon.id, "role_id": self.role.id, "end_timestamp": end_ts}
            await sauvegarder_json_async(DEFIS_FILE, defis_data)
            asyncio.create_task(retirer_role_apres_defi(interaction.guild, msg.id, self.role))
            await interaction.followup.send(f"✅ Défi lancé dans {self.salon.mention} pour {self.duree}h.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lancement défi: {e}", ephemeral=True)

async def retirer_role_apres_defi(guild: discord.Guild, message_id: int, role: discord.Role):
    try:
        data = defis_data.get(str(message_id))
        if not data:
            print(f"⚠️ Pas de données pour le défi {message_id}")
            return
        await asyncio.sleep(max(0, data["end_timestamp"] - time.time()))
        for member in role.members:
            try:
                await member.remove_roles(role, reason="Fin défi hebdomadaire")
            except Exception as e:
                print(f"❌ Erreur retrait rôle pour {member.display_name}: {e}")
        del defis_data[str(message_id)]
        await sauvegarder_json_async(DEFIS_FILE, defis_data)
        print(f"✅ Fin défi {message_id}")
    except Exception as e:
        print(f"❌ Erreur dans retirer_role_apres_defi: {e}")

@tree.command(name="defi_semaine", description="Lance un défi hebdomadaire (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def defi_semaine(interaction: discord.Interaction, salon: discord.TextChannel, role: discord.Role, duree_heures: int, recurrence: bool, start_date: Optional[str] = None, challenge_message: Optional[str] = None):
    if duree_heures <= 0 or duree_heures > 10000:
        await interaction.response.send_message("❌ Durée invalide.", ephemeral=True)
        return
    if recurrence:
        if not start_date or not challenge_message:
            await interaction.response.send_message("❌ Fournissez start_date et challenge_message.", ephemeral=True)
            return
        try:
            datetime.datetime.strptime(start_date, "%d/%m/%Y %H:%M")
        except ValueError:
            await interaction.response.send_message("❌ Format start_date invalide.", ephemeral=True)
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

# ------------------------------------------
# Envoi de message via modal (admin)
# ------------------------------------------
class ModalEnvoyerMessage(Modal, title="📩 Envoyer un message"):
    def __init__(self, salon: discord.TextChannel):
        super().__init__(timeout=None)
        self.salon = salon
        self.contenu = TextInput(
            label="Message",
            style=TextStyle.paragraph,
            placeholder="Tapez votre message",
            required=True,
            max_length=2000
        )
        self.add_item(self.contenu)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.salon.send(textwrap.dedent(self.contenu.value))
            await interaction.followup.send(f"✅ Message envoyé dans {self.salon.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

@tree.command(name="envoyer_message", description="Envoie un message via le bot (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def envoyer_message(interaction: discord.Interaction, salon: discord.TextChannel):
    try:
        await interaction.response.send_modal(ModalEnvoyerMessage(salon))
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

# ------------------------------------------
# Commande /clear (admin)
# ------------------------------------------
@tree.command(name="clear", description="Supprime jusqu'à 100 messages (admin)")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, nombre: int):
    if not (1 <= nombre <= 100):
        await interaction.response.send_message("❌ Choisissez entre 1 et 100.", ephemeral=True)
        return
    try:
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=nombre)
        await interaction.followup.send(f"🧽 {len(deleted)} messages supprimés.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

# ------------------------------------------
# Vues de confirmation pour suppression
# ------------------------------------------
class ConfirmDeleteRolesView(View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=60)
        self.interaction = interaction
    @discord.ui.button(label="Oui", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message("❌ Autorisé uniquement pour l'admin init.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Suppression en cours...", view=None)
        errors = []
        guild = interaction.guild
        for role in guild.roles:
            if not role.permissions.administrator and (role < guild.me.top_role):
                try:
                    await role.delete(reason="Demandé par admin")
                    await asyncio.sleep(0.5)
                except Exception as e:
                    errors.append(f"{role.name}: {e}")
        if errors:
            await interaction.followup.send("Certains rôles n'ont pas pu être supprimés:\n" + "\n".join(errors), ephemeral=True)
        else:
            await interaction.followup.send("✅ Rôles supprimés.", ephemeral=True)
        self.stop()
    @discord.ui.button(label="Non", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Opération annulée.", view=None)
        self.stop()

class ConfirmDeleteChannelsView(View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=60)
        self.interaction = interaction
    @discord.ui.button(label="Oui", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message("❌ Autorisé uniquement pour l'admin init.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Suppression en cours...", view=None)
        errors = []
        for channel in interaction.guild.channels:
            try:
                await channel.delete(reason="Demandé par admin")
                await asyncio.sleep(0.5)
            except Exception as e:
                errors.append(f"{channel.name}: {e}")
        if errors:
            await interaction.followup.send("Certains salons/catégories n'ont pas pu être supprimés:\n" + "\n".join(errors), ephemeral=True)
        else:
            await interaction.followup.send("✅ Salons et catégories supprimés.", ephemeral=True)
        self.stop()
    @discord.ui.button(label="Non", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Opération annulée.", view=None)
        self.stop()

# ------------------------------------------
# Cog d'administration avancée
# ------------------------------------------
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
    @app_commands.command(name="reset_roles", description="Retire tous les rôles (sauf admin) de tous les membres (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_roles(self, interaction: discord.Interaction):
        try:
            for member in interaction.guild.members:
                roles_to_remove = [r for r in member.roles if not r.permissions.administrator]
                if roles_to_remove:
                    await member.remove_roles(*roles_to_remove, reason="Réinitialisation")
            await interaction.response.send_message("✅ Rôles réinitialisés.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)
    @app_commands.command(name="supprimer_tous_roles", description="Supprime tous les rôles non-admin (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def supprimer_tous_roles(self, interaction: discord.Interaction):
        view = ConfirmDeleteRolesView(interaction)
        await interaction.response.send_message("Confirmez la suppression de tous les rôles non-admin.", view=view, ephemeral=True)
    @app_commands.command(name="supprimer_tous_salons_categories", description="Supprime tous les salons et catégories (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def supprimer_tous_salons_categories(self, interaction: discord.Interaction):
        view = ConfirmDeleteChannelsView(interaction)
        await interaction.response.send_message("Confirmez la suppression de tous les salons et catégories.", view=view, ephemeral=True)

async def setup_admin_utils(bot: commands.Bot):
    await bot.add_cog(AdminUtilsCog(bot))

# ------------------------------------------
# Module AutoDM (admin)
# ------------------------------------------
class AutoDMCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_dm_configs = {}
    async def load_configs(self):
        configs = await charger_json_async(AUTO_DM_FILE)
        if not isinstance(configs, dict):
            configs = {}
        self.auto_dm_configs = configs
        print("⚙️ Configurations AutoDM chargées.")
    async def save_configs(self):
        await sauvegarder_json_async(AUTO_DM_FILE, self.auto_dm_configs)
        print("⚙️ Config AutoDM sauvegardée.")
    async def cog_load(self):
        await self.load_configs()
    @app_commands.command(name="autodm_add", description="Ajoute une config AutoDM (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def autodm_add(self, interaction: discord.Interaction, role: discord.Role, dm_message: str):
        if not dm_message.strip():
            await interaction.response.send_message("❌ Message DM vide.", ephemeral=True)
            return
        config_id = str(uuid.uuid4())
        self.auto_dm_configs[config_id] = {"role_id": str(role.id), "dm_message": dm_message.strip()}
        await self.save_configs()
        await interaction.response.send_message(f"✅ Config ajoutée avec l'ID `{config_id}`.", ephemeral=True)
    @app_commands.command(name="autodm_list", description="Liste les configs AutoDM (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def autodm_list(self, interaction: discord.Interaction):
        if not self.auto_dm_configs:
            await interaction.response.send_message("Aucune config AutoDM.", ephemeral=True)
            return
        lines = []
        for cid, config in self.auto_dm_configs.items():
            role_obj = interaction.guild.get_role(int(config.get("role_id", 0)))
            role_name = role_obj.name if role_obj else f"ID {config.get('role_id')}"
            lines.append(f"ID: `{cid}`\nRôle: {role_name}\nMessage: {config.get('dm_message')}\n")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)
    @app_commands.command(name="autodm_remove", description="Supprime une config AutoDM (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def autodm_remove(self, interaction: discord.Interaction, config_id: str):
        if config_id in self.auto_dm_configs:
            del self.auto_dm_configs[config_id]
            await self.save_configs()
            await interaction.response.send_message(f"✅ Config `{config_id}` supprimée.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ID non trouvé.", ephemeral=True)
    @app_commands.command(name="autodm_modify", description="Modifie une config AutoDM (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def autodm_modify(self, interaction: discord.Interaction, config_id: str, new_role: Optional[discord.Role] = None, new_dm_message: Optional[str] = None):
        if config_id not in self.auto_dm_configs:
            await interaction.response.send_message("❌ ID non trouvé.", ephemeral=True)
            return
        config = self.auto_dm_configs[config_id]
        if new_role is not None:
            config["role_id"] = str(new_role.id)
        if new_dm_message is not None:
            if not new_dm_message.strip():
                await interaction.response.send_message("❌ Nouveau message vide.", ephemeral=True)
                return
            config["dm_message"] = new_dm_message.strip()
        self.auto_dm_configs[config_id] = config
        await self.save_configs()
        await interaction.response.send_message(f"✅ Config `{config_id}` modifiée.", ephemeral=True)

async def setup_autodm(bot: commands.Bot):
    await bot.add_cog(AutoDMCog(bot))

# ------------------------------------------
# Module de modération (admin)
# ------------------------------------------
class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.banned_words = {"merde", "putain", "con", "connard", "salop", "enculé", "nique ta mère"}
    @app_commands.command(name="list_banned_words", description="Liste des mots bannis (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_banned_words(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Mots bannis: {', '.join(sorted(self.banned_words))}", ephemeral=True)
    @app_commands.command(name="add_banned_word", description="Ajoute un mot à bannir (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_banned_word(self, interaction: discord.Interaction, word: str):
        word_low = word.lower()
        if word_low in self.banned_words:
            await interaction.response.send_message("Ce mot est déjà banni.", ephemeral=True)
        else:
            self.banned_words.add(word_low)
            await interaction.response.send_message(f"Le mot '{word}' a été ajouté.", ephemeral=True)
    @app_commands.command(name="remove_banned_word", description="Retire un mot de la liste (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_banned_word(self, interaction: discord.Interaction, word: str):
        word_low = word.lower()
        if word_low in self.banned_words:
            self.banned_words.remove(word_low)
            await interaction.response.send_message(f"Le mot '{word}' n'est plus banni.", ephemeral=True)
        else:
            await interaction.response.send_message("Ce mot n'était pas banni.", ephemeral=True)
    @app_commands.command(name="mute", description="Mute un utilisateur (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def mute(self, interaction: discord.Interaction, member: discord.Member, duration: int):
        muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
        if not muted_role:
            try:
                muted_role = await interaction.guild.create_role(name="Muted", reason="Création pour mute")
                for channel in interaction.guild.channels:
                    await channel.set_permissions(muted_role, send_messages=False, speak=False)
            except Exception as e:
                await interaction.response.send_message(f"❌ Erreur création rôle: {e}", ephemeral=True)
                return
        try:
            await member.add_roles(muted_role, reason="Mute admin")
            await interaction.response.send_message(f"{member.mention} muté pendant {duration} minutes.", ephemeral=True)
            await asyncio.sleep(duration * 60)
            await member.remove_roles(muted_role, reason="Fin du mute")
            await interaction.followup.send(f"{member.mention} n'est plus mute.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors du mute: {e}", ephemeral=True)
    @app_commands.command(name="ban", description="Bannit un utilisateur (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison"):
        try:
            await member.ban(reason=reason)
            await interaction.response.send_message(f"{member.mention} banni. Raison: {reason}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur banning: {e}", ephemeral=True)
    @app_commands.command(name="kick", description="Expulse un utilisateur (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison"):
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(f"{member.mention} expulsé. Raison: {reason}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur kick: {e}", ephemeral=True)

async def setup_moderation(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))

# ------------------------------------------
# Serveur HTTP keep-alive
# ------------------------------------------
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot actif.')
    def log_message(self, format, *args):
        return

def keep_alive(port=10000):
    try:
        server = HTTPServer(('0.0.0.0', port), KeepAliveHandler)
        thread = threading.Thread(target=server.serve_forever, name="KeepAliveThread")
        thread.daemon = True
        thread.start()
        print(f"✅ Serveur keep-alive sur le port {port}")
    except Exception as e:
        print(f"❌ Erreur keep-alive: {e}")

keep_alive()

@bot.event
async def on_ready():
    try:
        print(f"✅ Connecté en tant que {bot.user} (ID: {bot.user.id})")
    except Exception as e:
        print(f"❌ Erreur on_ready: {e}")

# ------------------------------------------
# Commande Pomodoro
# ------------------------------------------
@tree.command(name="pomodoro", description="Lance une session Pomodoro personnalisée")
@app_commands.describe(focus="Temps focus (min)", pause="Pause courte (min)", longue_pause="Pause longue (min)")
async def pomodoro(interaction: discord.Interaction, focus: int = 25, pause: int = 5, longue_pause: int = 10):
    await interaction.response.defer(ephemeral=True)
    allowed_id = config_pomodoro.get("allowed_channel_id")
    if allowed_id and str(interaction.channel.id) != allowed_id:
        await interaction.followup.send("❌ Cette commande n'est pas autorisée ici.", ephemeral=True)
        return
    await interaction.followup.send(f"🕒 Début de session Pomodoro : {focus} min focus, {pause} min pause, {longue_pause} min pause longue.", ephemeral=True)
    user = interaction.user
    try:
        # On envoie les instructions par DM pour ne pas bloquer le canal
        for session in range(1, 5):
            await user.send(f"🔴 Session {session} — Focus pendant {focus} minutes.")
            await asyncio.sleep(focus * 60)
            if session < 4:
                await user.send(f"🟡 Pause courte de {pause} minutes.")
                await asyncio.sleep(pause * 60)
            else:
                await user.send(f"🟢 Pause longue de {longue_pause} minutes.")
                await asyncio.sleep(longue_pause * 60)
        await user.send("✅ Pomodoro terminé !")
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur en DM: {e}", ephemeral=True)

# ------------------------------------------
# Module d'objectifs personnels
# ------------------------------------------
@tree.command(name="ajouter_objectif", description="Ajoute un objectif personnel")
async def ajouter_objectif(interaction: discord.Interaction, objectif: str):
    if bot.xp_config.get("goals_channel") and str(interaction.channel.id) != str(bot.xp_config["goals_channel"]):
        await interaction.response.send_message("❌ Commande non autorisée ici.", ephemeral=True)
        return
    uid = str(interaction.user.id)
    objectifs_data.setdefault(uid, []).append(objectif)
    await sauvegarder_json_async(GOALS_FILE, objectifs_data)
    await interaction.response.send_message(f"✅ Objectif ajouté : **{objectif}**", ephemeral=True)

@tree.command(name="voir_objectifs", description="Affiche tes objectifs")
async def voir_objectifs(interaction: discord.Interaction):
    if bot.xp_config.get("goals_channel") and str(interaction.channel.id) != str(bot.xp_config["goals_channel"]):
        await interaction.response.send_message("❌ Commande non autorisée ici.", ephemeral=True)
        return
    uid = str(interaction.user.id)
    objectifs = objectifs_data.get(uid, [])
    if not objectifs:
        await interaction.response.send_message("📭 Aucun objectif.", ephemeral=True)
        return
    txt = "\n".join(f"🔹 {o}" for o in objectifs)
    await interaction.response.send_message(f"🎯 Objectifs:\n{txt}", ephemeral=True)

@tree.command(name="supprimer_objectif", description="Supprime un de tes objectifs")
@app_commands.describe(position="Numéro de l'objectif (1 pour le premier)")
async def supprimer_objectif(interaction: discord.Interaction, position: int):
    if bot.xp_config.get("goals_channel") and str(interaction.channel.id) != str(bot.xp_config["goals_channel"]):
        await interaction.response.send_message("❌ Commande non autorisée ici.", ephemeral=True)
        return
    uid = str(interaction.user.id)
    objectifs = objectifs_data.get(uid, [])
    if not (1 <= position <= len(objectifs)):
        await interaction.response.send_message("❌ Numéro invalide.", ephemeral=True)
        return
    suppr = objectifs.pop(position - 1)
    if not objectifs:
        objectifs_data.pop(uid, None)
    await sauvegarder_json_async(GOALS_FILE, objectifs_data)
    await interaction.response.send_message(f"🗑️ Objectif supprimé: **{suppr}**", ephemeral=True)

# ------------------------------------------
# Récapitulatif et statistiques hebdomadaires
# ------------------------------------------
@tree.command(name="set_channel_recap", description="Définit le salon pour les récap hebdo (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def set_channel_recap(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.recap_config["channel_id"] = str(channel.id)
    await interaction.response.send_message(f"✅ Salon récap défini: {channel.mention}", ephemeral=True)

@tree.command(name="set_role_recap", description="Définit le rôle à mentionner pour le récap (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def set_role_recap(interaction: discord.Interaction, role: discord.Role):
    bot.recap_config["role_id"] = str(role.id)
    await interaction.response.send_message(f"✅ Rôle récap défini: {role.mention}", ephemeral=True)

@tasks.loop(minutes=1)
async def recap_hebdo_task():
    try:
        now = datetime.datetime.now(ZoneInfo("Europe/Paris"))
        if now.weekday() == 6 and now.hour == 20 and now.minute == 0:
            chan_id = bot.recap_config.get("channel_id")
            role_id = bot.recap_config.get("role_id")
            if chan_id and role_id:
                channel = bot.get_channel(int(chan_id))
                if channel:
                    msg = f"📆 **Récapitulatif hebdomadaire !**\n<@&{role_id}> partagez vos avancées pour la semaine à venir."
                    await channel.send(msg)
                    print("✅ Récap envoyé.")
                else:
                    print("❌ Salon récap introuvable.")
    except Exception as e:
        print(f"❌ Erreur dans recap_hebdo_task: {e}")

@tasks.loop(minutes=1)
async def weekly_stats_task():
    try:
        now = datetime.datetime.now(ZoneInfo("Europe/Paris"))
        if now.weekday() == 6 and now.hour == 21 and now.minute == 0:
            if not hasattr(bot, "stats_channel_id") or not bot.stats_channel_id:
                print("⚠️ Pas de salon stats défini.")
                return
            channel = bot.get_channel(int(bot.stats_channel_id))
            if not channel:
                print("❌ Salon stats introuvable.")
                return
            if not bot.weekly_stats:
                await channel.send("📊 Aucune activité cette semaine.")
                return
            stats_msg = "**📈 Stat hebdomadaire :**\n"
            for uid, data in bot.weekly_stats.items():
                member = channel.guild.get_member(int(uid))
                if not member: continue
                msg_count = data.get("messages", 0)
                minutes_vocal = round(data.get("vocal", 0) / 60)
                stats_msg += f"• {member.mention} — {msg_count} msg / {minutes_vocal} min vocal\n"
            await channel.send(stats_msg)
            bot.weekly_stats = {}
            print("✅ Stats hebdomadaires envoyées.")
    except Exception as e:
        print(f"❌ Erreur dans weekly_stats_task: {e}")

@tree.command(name="stats_hebdo", description="Affiche tes stats hebdomadaires")
async def stats_hebdo(interaction: discord.Interaction):
    try:
        uid = str(interaction.user.id)
        stats = bot.weekly_stats.get(uid, {"messages": 0, "vocal": 0})
        msg = stats.get("messages", 0)
        min_vocal = round(stats.get("vocal", 0) / 60)
        texte = f"📊 **Stats de la semaine — {interaction.user.mention}**\n✉️ Messages: {msg}\n🎙️ Vocal: {min_vocal} min"
        await interaction.response.send_message(texte, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

# ------------------------------------------
# Alertes SOS
# ------------------------------------------
@tree.command(name="set_destinataires_sos", description="Configure alertes SOS (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def set_destinataires_sos(interaction: discord.Interaction, mentions_roles: str, mentions_utilisateurs: str):
    bot.sos_receivers = []
    for role in interaction.guild.roles:
        if role.mention in mentions_roles:
            bot.sos_receivers.append(role.id)
    for member in interaction.guild.members:
        if member.mention in mentions_utilisateurs:
            bot.sos_receivers.append(member.id)
    await sauvegarder_json_async(SOS_CONFIG_FILE, {"receivers": bot.sos_receivers})
    await interaction.response.send_message("✅ Destinataires SOS configurés.", ephemeral=True)

@tree.command(name="sos", description="Lance une alerte SOS")
async def sos(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        if not bot.sos_receivers:
            await interaction.followup.send("⚠️ Aucun destinataire SOS configuré.", ephemeral=True)
            return
        for rec in bot.sos_receivers:
            member = interaction.guild.get_member(rec)
            if member:
                try:
                    await member.send(f"🚨 SOS: {interaction.user.mention} a besoin d'aide.")
                except Exception:
                    pass
        await interaction.followup.send("✅ Alerte SOS envoyée.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

# ------------------------------------------
# Modes événementiels et thèmes
# ------------------------------------------
@tree.command(name="mode_evenement", description="Active/désactive un mode événement (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def mode_evenement(interaction: discord.Interaction, nom: str, message: str, actif: bool):
    try:
        bot.evenement_config.update({"actif": actif, "nom": nom, "message": message})
        await sauvegarder_json_async(EVENEMENT_CONFIG_FILE, bot.evenement_config)
        if actif:
            await interaction.response.send_message(f"🎉 Mode événement '{nom}' activé: {message}", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Mode événement désactivé.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

@tree.command(name="set_theme", description="Définit un thème visuel (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def set_theme(interaction: discord.Interaction, nom: str, emoji: str, message: str):
    try:
        bot.theme_config.update({"nom": nom, "emoji": emoji, "message": message})
        await sauvegarder_json_async(THEME_CONFIG_FILE, bot.theme_config)
        await interaction.response.send_message(f"🎨 Thème '{nom}' défini avec {emoji}: {message}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

# ------------------------------------------
# Missions secrètes
# ------------------------------------------
@tree.command(name="mission_secrete", description="Assigne une mission secrète (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def mission_secrete(interaction: discord.Interaction, utilisateur: discord.Member, mission: str):
    try:
        bot.missions_secretes[str(utilisateur.id)] = {
            "mission": mission,
            "assignée_par": interaction.user.id,
            "timestamp": datetime.datetime.now().isoformat()
        }
        await sauvegarder_json_async(MISSIONS_FILE, bot.missions_secretes)
        try:
            await utilisateur.send(f"🕵️ Mission secrète: {mission}")
        except Exception:
            pass
        await interaction.response.send_message(f"✅ Mission attribuée à {utilisateur.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

@tree.command(name="ma_mission", description="Affiche ta mission secrète")
async def ma_mission(interaction: discord.Interaction):
    data = bot.missions_secretes.get(str(interaction.user.id))
    if data:
        await interaction.response.send_message(f"🕵️ Mission: {data['mission']}", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Aucune mission assignée.", ephemeral=True)

# ------------------------------------------
# Événements sur calendrier collaboratif
# ------------------------------------------
@tree.command(name="ajouter_evenement", description="Ajoute un événement au calendrier")
@app_commands.describe(titre="Titre", date="JJ/MM/AAAA", heure="HH:MM", description="Description")
async def ajouter_evenement(interaction: discord.Interaction, titre: str, date: str, heure: str, description: str):
    try:
        dt = datetime.datetime.strptime(f"{date} {heure}", "%d/%m/%Y %H:%M")
        eid = str(uuid.uuid4())
        bot.evenements_calendrier[eid] = {
            "auteur": interaction.user.id,
            "titre": titre,
            "datetime": dt.isoformat(),
            "description": description
        }
        await sauvegarder_json_async(CALENDRIER_FILE, bot.evenements_calendrier)
        await interaction.response.send_message(f"✅ Événement '{titre}' ajouté.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

@tree.command(name="voir_evenements", description="Affiche les événements à venir")
async def voir_evenements(interaction: discord.Interaction):
    try:
        if not bot.evenements_calendrier:
            await interaction.response.send_message("📭 Aucun événement prévu.", ephemeral=True)
            return
        now = datetime.datetime.now()
        events = []
        for eid, evt in sorted(bot.evenements_calendrier.items(), key=lambda x: x[1]["datetime"]):
            dt = datetime.datetime.fromisoformat(evt["datetime"])
            if dt > now:
                events.append(f"📅 **{evt['titre']}** le {dt.strftime('%d/%m/%Y à %H:%M')}\n📝 {evt['description']}")
        msg = "\n\n".join(events) if events else "📭 Aucun événement à venir."
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

# ------------------------------------------
# Système de demande d'aide – Version améliorée
# ------------------------------------------
class HelpRequestModal(Modal, title="📩 Demande d'aide"):
    def __init__(self):
        super().__init__(timeout=None)
        self.probleme = TextInput(
            label="Décris ton problème :",
            style=TextStyle.paragraph,
            placeholder="Exemple: Je bloque sur ...",
            required=True,
            max_length=2000
        )
        self.add_item(self.probleme)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            desc = self.probleme.value
            guild = interaction.guild
            # Création en arrière-plan du salon privé (accessible uniquement au demandeur)
            category = await guild.create_category(f"Aide - {interaction.user.display_name}")
            text_chan = await guild.create_text_channel("aide-privée", category=category)
            voice_chan = await guild.create_voice_channel("aide-privée", category=category)
            await category.set_permissions(guild.default_role, view_channel=False)
            await category.set_permissions(interaction.user, view_channel=True)
            # Sauvegarde de la demande
            data = {
                "user_id": str(interaction.user.id),
                "description": desc,
                "category_id": str(category.id),
                "text_channel_id": str(text_chan.id),
                "voice_channel_id": str(voice_chan.id),
                "created_at": datetime.datetime.now().isoformat()
            }
            categories_aide[str(interaction.user.id)] = data
            await sauvegarder_json_async(HELP_REQUEST_FILE, categories_aide)
            # Publication d'un message public dans le salon de commande
            public_msg = (f"🚨 **Demande d'aide** 🚨\n"
                          f"{interaction.user.mention} a besoin d'aide :\n>>> {desc}\n"
                          f"Cliquez sur le bouton ci-dessous pour accéder au salon privé d'aide.")
            await interaction.channel.send(public_msg, view=HelpButtons(interaction.user.id))
            await interaction.followup.send("✅ Demande d'aide créée. Consultez le message public pour accéder au salon.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de la demande d'aide: {e}", ephemeral=True)

class HelpButtons(View):
    def __init__(self, requester_id: int):
        super().__init__()
        self.requester_id = requester_id
    @discord.ui.button(label="Je peux aider", style=discord.ButtonStyle.primary)
    async def aider(self, interaction: discord.Interaction, button: Button):
        req = categories_aide.get(str(self.requester_id))
        if not req:
            await interaction.response.send_message("Cette demande d'aide n'existe plus.", ephemeral=True)
            return
        category = interaction.guild.get_category(int(req["category_id"]))
        if not category:
            await interaction.response.send_message("Salon d'aide introuvable.", ephemeral=True)
            return
        role = discord.utils.get(interaction.guild.roles, name="Aider")
        if not role:
            role = await interaction.guild.create_role(name="Aider")
        await interaction.user.add_roles(role)
        await category.set_permissions(role, view_channel=True)
        await interaction.response.send_message("🔔 Vous avez accès au salon privé d'aide.", ephemeral=True)
    @discord.ui.button(label="Problème Résolu", style=discord.ButtonStyle.danger)
    async def resoudre(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("❌ Seul le demandeur peut clore la demande.", ephemeral=True)
            return
        req = categories_aide.get(str(self.requester_id))
        if req:
            category = interaction.guild.get_category(int(req["category_id"]))
            if category:
                await category.delete()
            del categories_aide[str(self.requester_id)]
            await sauvegarder_json_async(HELP_REQUEST_FILE, categories_aide)
        await interaction.response.send_message("✅ Demande d'aide fermée.", ephemeral=True)

@tree.command(name="besoin_aide", description="Crée une demande d'aide")
async def besoin_aide(interaction: discord.Interaction):
    try:
        await interaction.response.send_modal(HelpRequestModal())
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

# ------------------------------------------
# Journal de focus – Modifications pour éviter le blocage et utiliser followup
# ------------------------------------------
@tree.command(name="journal_focus", description="Enregistre ton journal de focus")
async def journal_focus(interaction: discord.Interaction, texte: str):
    # Si un salon spécifique est défini, la commande doit être utilisée dans celui-ci
    if bot.journal_focus_channel and str(interaction.channel.id) != bot.journal_focus_channel:
        await interaction.response.send_message("❌ Cette commande n'est pas autorisée ici.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        # Utilisation de followup pour s'assurer que la réponse est envoyée sans délai
        await interaction.followup.send("✅ Journal enregistré.", ephemeral=True)
        # Envoi public du journal dans le même salon
        await interaction.followup.send(f"📝 Journal de {interaction.user.mention} :\n```{texte}```")
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

# ------------------------------------------
# Système de réactions multi rôle avec message
# ------------------------------------------
@tree.command(name="reaction_role_avec_message", description="Crée un message avec réactions pour attribuer des rôles")
@app_commands.checks.has_permissions(administrator=True)
async def reaction_role_avec_message(interaction: discord.Interaction, salon: discord.TextChannel, emojis: str, roles: str):
    try:
        emojis_list = [e.strip() for e in emojis.split(",")]
        roles_list = [r.strip() for r in roles.split(",")]
        if len(emojis_list) != len(roles_list):
            await interaction.response.send_message("❌ Le nombre d'emojis et de rôles doit correspondre.", ephemeral=True)
            return
        bot.temp_data["reaction_role"] = {
            "channel": salon,
            "emojis": emojis_list,
            "roles": roles_list,
            "user_id": interaction.user.id
        }
        class ModalReactionRole(Modal, title="Message avec réactions"):
            message = TextInput(
                label="Texte du message",
                style=TextStyle.paragraph,
                required=True,
                max_length=4000
            )
            async def on_submit(self, interaction_modal: discord.Interaction):
                await interaction_modal.response.defer(ephemeral=True)
                data = bot.temp_data.get("reaction_role", {})
                if interaction_modal.user.id != data.get("user_id"):
                    await interaction_modal.followup.send("❌ Vous n'êtes pas autorisé.", ephemeral=True)
                    return
                channel = data.get("channel")
                emojis = data.get("emojis")
                roles_str = data.get("roles")
                txt = self.message.value
                sent_msg = await channel.send(txt)
                for emo in emojis:
                    await sent_msg.add_reaction(emo)
                mapping = {}
                for emo, role_str in zip(emojis, roles_str):
                    key = get_emoji_key(emo)
                    # Recherche du rôle
                    if role_str.startswith("<@&"):
                        role_id = int(role_str.replace("<@&", "").replace(">", ""))
                    else:
                        r_obj = discord.utils.get(interaction.guild.roles, name=role_str.replace("@", ""))
                        if r_obj:
                            role_id = r_obj.id
                        else:
                            await interaction_modal.followup.send(f"❌ Rôle non trouvé: {role_str}", ephemeral=True)
                            return
                    mapping[key] = role_id
                bot.reaction_roles[str(sent_msg.id)] = mapping
                await sauvegarder_json_async(REACTION_ROLE_FILE, bot.reaction_roles)
                await interaction_modal.followup.send("✅ Message envoyé et réactions enregistrées!", ephemeral=True)
        await interaction.response.send_modal(ModalReactionRole())
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur: {e}", ephemeral=True)

# ------------------------------------------
# Fonction main – Chargement des données et lancement
# ------------------------------------------
async def main():
    global xp_data, messages_programmes, defis_data, config_pomodoro, objectifs_data, categories_aide
    try:
        xp_data = await charger_json_async(XP_FILE)
        messages_programmes = await charger_json_async(MSG_FILE)
        defis_data = await charger_json_async(DEFIS_FILE)
        config_pomodoro = await charger_json_async(POMODORO_CONFIG_FILE)
        objectifs_data = await charger_json_async(GOALS_FILE)
        bot.evenement_config = await charger_json_async(EVENEMENT_CONFIG_FILE)
        bot.theme_config = await charger_json_async(THEME_CONFIG_FILE)
        bot.missions_secretes = await charger_json_async(MISSIONS_FILE)
        bot.evenements_calendrier = await charger_json_async(CALENDRIER_FILE)
        categories_aide = await charger_json_async(HELP_REQUEST_FILE)
        bot.reaction_roles = await charger_json_async(REACTION_ROLE_FILE)
        sos_conf = await charger_json_async(SOS_CONFIG_FILE)
        bot.sos_receivers = sos_conf.get("receivers", [])
        print("⚙️ Données chargées.")
    except Exception as e:
        print(f"❌ Erreur chargement données: {e}")
    await setup_admin_utils(bot)
    await setup_autodm(bot)
    await setup_moderation(bot)
    try:
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            print("❌ DISCORD_TOKEN non défini")
            return
        await bot.start(token)
    except Exception as e:
        print(f"❌ Erreur critique lancement bot: {e}")

if __name__ == "__main__":
    asyncio.run(main())

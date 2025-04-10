import os
import json
import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import Modal, TextInput
from discord import TextStyle
import asyncio
import textwrap
import time
import datetime
from zoneinfo import ZoneInfo  # Gestion explicite du fuseau horaire
import uuid
import aiofiles  # Pour l'accès asynchrone aux fichiers

# Pour le serveur HTTP de keep-alive
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket

# Configuration du port pour Render
os.environ["PORT"] = "10000"

# ========================================
# 📁 Chemins des fichiers persistants
# ========================================
DATA_FOLDER = "/data"
XP_FILE = os.path.join(DATA_FOLDER, "xp.json")
MSG_FILE = os.path.join(DATA_FOLDER, "messages_programmes.json")
DEFIS_FILE = os.path.join(DATA_FOLDER, "defis.json")

# Création du dossier s'il n'existe pas
os.makedirs(DATA_FOLDER, exist_ok=True)

# ========================================
# Verrou global pour accéder aux fichiers de façon asynchrone
# ========================================
file_lock = asyncio.Lock()

# ========================================
# 🔧 Fonctions asynchrones pour la persistance des données
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
                # En cas de corruption, on renvoie un dictionnaire vide
                return {}

async def sauvegarder_json_async(path, data):
    async with file_lock:
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=4))

# ========================================
# Utilitaire pour standardiser la clé d'un emoji
# ========================================
def get_emoji_key(emoji):
    try:
        pe = discord.PartialEmoji.from_str(str(emoji))
        if pe.is_custom_emoji():
            return f"<:{pe.name}:{pe.id}>"
        else:
            return str(pe)
    except Exception:
        return str(emoji)

# ========================================
# Variables globales pour les données persistantes
# (Elles seront chargées dans main() de façon asynchrone)
# ========================================
xp_data = {}
messages_programmes = {}
defis_data = {}

# ========================================
# ⚙️ Configuration des intents
# ========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True
intents.voice_states = True

# ========================================
# 🤖 Classe principale du bot
# ========================================
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.reaction_roles = {}
        self.vocal_start_times = {}
        self.xp_config = {
            "xp_per_message": 10,
            "xp_per_minute_vocal": 5,
            "multipliers": {},           # {channel_id: multiplier (float)}
            "level_roles": {},           # {xp: role_id}
            "announcement_channel": None,
            "announcement_message": "🎉 {mention} a atteint {xp} XP !",
            "xp_command_channel": None,
            "xp_command_min_xp": 0,
            "badges": {},                # {xp: badge}
            "titres": {}                 # {xp: titre}
        }

    async def setup_hook(self):
        try:
            synced = await self.tree.sync()
            print(f"🌐 {len(synced)} commandes slash synchronisées")
            if not check_programmed_messages.is_running():
                check_programmed_messages.start()
                print("✅ Boucle check_programmed_messages démarrée via setup_hook()")
        except Exception as e:
            print(f"❌ Erreur dans setup_hook : {e}")

# ========================================
# Instanciation du bot
# ========================================
bot = MyBot()
tree = bot.tree

# ========================================
# ⏰ Boucle des messages programmés (version améliorée)
# ========================================
@tasks.loop(seconds=30)
async def check_programmed_messages():
    try:
        if not bot.is_ready():
            print("⏳ Bot pas encore prêt, attente...")
            return

        # Récupère l'heure actuelle en Europe/Paris
        now = datetime.datetime.now(ZoneInfo("Europe/Paris"))
        print(f"🔁 [check_programmed_messages] Vérification à {now.strftime('%H:%M:%S')} (Europe/Paris)")

        messages_modifies = False

        for msg_id, msg in list(messages_programmes.items()):
            try:
                # Parse la date programmée et la rend timezone-aware
                try:
                    msg_time_naive = datetime.datetime.strptime(msg["next"], "%d/%m/%Y %H:%M")
                    msg_time = msg_time_naive.replace(tzinfo=ZoneInfo("Europe/Paris"))
                except ValueError as ve:
                    print(f"❌ Format de date invalide pour le message {msg_id} : {ve}")
                    continue

                # Si l'heure actuelle est égale ou a dépassé l'heure programmée
                if now >= msg_time:
                    channel = bot.get_channel(int(msg["channel_id"]))
                    if channel:
                        await channel.send(textwrap.dedent(msg["message"]))
                        print(f"✅ Message {msg_id} envoyé dans #{channel.name}")

                    if msg["type"] == "once":
                        del messages_programmes[msg_id]
                        messages_modifies = True
                        print(f"🗑️ Message {msg_id} supprimé (type: once)")
                    else:
                        # Pour les messages récurrents, on reprogramme en tenant compte d'éventuels retards
                        if msg["type"] == "daily":
                            while now >= msg_time:
                                msg_time += datetime.timedelta(days=1)
                        elif msg["type"] == "weekly":
                            while now >= msg_time:
                                msg_time += datetime.timedelta(weeks=1)
                        messages_programmes[msg_id]["next"] = msg_time.strftime("%d/%m/%Y %H:%M")
                        messages_modifies = True
                        print(f"🔄 Message {msg_id} reprogrammé pour {messages_programmes[msg_id]['next']}")

            except Exception as e:
                print(f"❌ Erreur traitement message {msg_id} : {e}")

        if messages_modifies:
            await sauvegarder_json_async(MSG_FILE, messages_programmes)

    except Exception as e:
        print(f"❌ Erreur globale dans check_programmed_messages : {e}")

# ========================================
# 💾 Fonctions utilitaires pour l'XP (version asynchrone)
# ========================================
async def add_xp(user_id, amount):
    user_id = str(user_id)
    current = xp_data.get(user_id, 0)
    new_total = current + amount
    xp_data[user_id] = new_total
    await sauvegarder_json_async(XP_FILE, xp_data)
    return new_total

def get_xp(user_id):
    return xp_data.get(str(user_id), 0)

# ========================================
# 💬 Ajout d'XP à chaque message
# ========================================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    xp = bot.xp_config["xp_per_message"]
    multiplier = bot.xp_config["multipliers"].get(str(message.channel.id), 1.0)
    total_xp = int(xp * multiplier)
    current_xp = await add_xp(message.author.id, total_xp)

    # Attribution automatique des rôles selon XP
    for seuil, role_id in bot.xp_config["level_roles"].items():
        if current_xp >= int(seuil):
            role = message.guild.get_role(int(role_id))
            if role and role not in message.author.roles:
                try:
                    await message.author.add_roles(role, reason="Palier XP atteint")
                    if bot.xp_config["announcement_channel"]:
                        salon = bot.get_channel(int(bot.xp_config["announcement_channel"]))
                        if salon:
                            texte = bot.xp_config["announcement_message"].replace("{mention}", message.author.mention).replace("{xp}", str(current_xp))
                            await salon.send(texte)
                except Exception as e:
                    print(f"❌ Erreur rôle XP : {e}")

    await bot.process_commands(message)

# ========================================
# 🎙️ Ajout d'XP en vocal
# ========================================
@bot.event
async def on_voice_state_update(member, before, after):
    if not before.channel and after.channel:
        bot.vocal_start_times[member.id] = time.time()
    elif before.channel and not after.channel:
        start = bot.vocal_start_times.pop(member.id, None)
        if start:
            durée = int((time.time() - start) / 60)
            mult = bot.xp_config["multipliers"].get(str(before.channel.id), 1.0)
            gained = int(durée * bot.xp_config["xp_per_minute_vocal"] * mult)
            current_xp = await add_xp(member.id, gained)

            for seuil, role_id in bot.xp_config["level_roles"].items():
                if current_xp >= int(seuil):
                    role = member.guild.get_role(int(role_id))
                    if role and role not in member.roles:
                        try:
                            await member.add_roles(role, reason="XP vocal atteint")
                            if bot.xp_config["announcement_channel"]:
                                salon = bot.get_channel(int(bot.xp_config["announcement_channel"]))
                                if salon:
                                    texte = bot.xp_config["announcement_message"].replace("{mention}", member.mention).replace("{xp}", str(current_xp))
                                    await salon.send(texte)
                        except Exception as e:
                            print(f"❌ Erreur rôle vocal : {e}")

# ========================================
# 🧠 /xp — Voir son XP actuel
# ========================================
@tree.command(name="xp", description="Affiche ton XP (réservé à un salon / niveau minimum)")
async def xp(interaction: discord.Interaction):
    config = bot.xp_config
    user_xp = get_xp(interaction.user.id)

    if config["xp_command_channel"] and interaction.channel.id != int(config["xp_command_channel"]):
        await interaction.response.send_message("❌ Cette commande n'est pas autorisée dans ce salon.", ephemeral=True)
        return

    if user_xp < config["xp_command_min_xp"]:
        await interaction.response.send_message("❌ Tu n'as pas encore assez d'XP pour voir ton profil.", ephemeral=True)
        return

    badge = ""
    for seuil, b in sorted(bot.xp_config["badges"].items(), key=lambda x: int(x[0]), reverse=True):
        if user_xp >= int(seuil):
            badge = b
            break

    titre = ""
    for seuil, t in sorted(bot.xp_config["titres"].items(), key=lambda x: int(x[0]), reverse=True):
        if user_xp >= int(seuil):
            titre = t
            break

    texte = textwrap.dedent(f"""
        🔹 {interaction.user.mention}, tu as **{user_xp} XP**.
        {"🏅 Badge : **" + badge + "**" if badge else ""}
        {"📛 Titre : **" + titre + "**" if titre else ""}
    """)
    await interaction.response.send_message(texte.strip(), ephemeral=True)

# ========================================
# 🏆 /leaderboard — Top 10 XP
# ========================================
@tree.command(name="leaderboard", description="Classement des membres avec le plus d'XP")
async def leaderboard(interaction: discord.Interaction):
    classement = sorted(xp_data.items(), key=lambda x: x[1], reverse=True)[:10]
    lignes = []

    for i, (user_id, xp_val) in enumerate(classement):
        membre = interaction.guild.get_member(int(user_id))
        nom = membre.display_name if membre else f"Utilisateur {user_id}"
        lignes.append(f"{i+1}. {nom} — {xp_val} XP")

    texte = "🏆 **Top 10 XP :**\n" + "\n".join(lignes) if lignes else "Aucun membre avec de l'XP."
    await interaction.response.send_message(texte, ephemeral=True)

# ========================================
# 🛠️ /add_xp — Ajoute manuellement de l'XP à un membre
# ========================================
@tree.command(name="add_xp", description="Ajoute de l'XP à un membre (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(member="Membre ciblé", amount="Quantité d'XP à ajouter")
async def add_xp_cmd(interaction: discord.Interaction, member: discord.Member, amount: int):
    new_total = await add_xp(member.id, amount)
    texte = f"✅ {amount} XP ajoutés à {member.mention}\n🔹 Total : **{new_total} XP**"
    await interaction.response.send_message(texte, ephemeral=True)

# ========================================
# ⚙️ Commandes de configuration du système XP
# ========================================
@tree.command(name="set_xp_config", description="Modifie l'XP gagné par message et en vocal")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp_per_message="XP/message", xp_per_minute_vocal="XP/minute vocal")
async def set_xp_config(interaction: discord.Interaction, xp_per_message: int, xp_per_minute_vocal: int):
    bot.xp_config["xp_per_message"] = xp_per_message
    bot.xp_config["xp_per_minute_vocal"] = xp_per_minute_vocal
    await interaction.response.send_message(
        f"✅ XP mis à jour : {xp_per_message}/msg, {xp_per_minute_vocal}/min vocal", ephemeral=True)

@tree.command(name="set_xp_role", description="Définit un rôle à débloquer à partir d'un certain XP")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", role="Rôle à attribuer")
async def set_xp_role(interaction: discord.Interaction, xp: int, role: discord.Role):
    bot.xp_config["level_roles"][str(xp)] = role.id
    await interaction.response.send_message(
        f"✅ Le rôle **{role.name}** sera attribué à partir de **{xp} XP**", ephemeral=True)

@tree.command(name="set_xp_boost", description="Ajoute un multiplicateur d'XP à un salon")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon concerné", multiplier="Ex : 2.0 = XP x2")
async def set_xp_boost(interaction: discord.Interaction, channel: discord.TextChannel, multiplier: float):
    bot.xp_config["multipliers"][str(channel.id)] = multiplier
    await interaction.response.send_message(
        f"✅ Multiplicateur **x{multiplier}** appliqué à {channel.mention}", ephemeral=True)

@tree.command(name="set_salon_annonce", description="Salon des annonces de niveau")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon cible")
async def set_salon_annonce(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["announcement_channel"] = str(channel.id)
    await interaction.response.send_message(
        f"✅ Les annonces de niveau seront postées dans {channel.mention}", ephemeral=True)

@tree.command(name="set_message_annonce", description="Modifie le message d’annonce de niveau")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message="Utilise {mention} et {xp} comme variables")
async def set_message_annonce(interaction: discord.Interaction, message: str):
    bot.xp_config["announcement_message"] = message
    preview = message.replace("{mention}", interaction.user.mention).replace("{xp}", "1234")
    await interaction.response.send_message(
        f"✅ Message mis à jour !\n\n💬 **Aperçu :**\n{preview}", ephemeral=True)

@tree.command(name="set_channel_xp_commands", description="Salon autorisé pour /xp et /leaderboard")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon autorisé")
async def set_channel_xp(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["xp_command_channel"] = str(channel.id)
    await interaction.response.send_message(
        f"✅ Les commandes XP sont maintenant limitées à {channel.mention}", ephemeral=True)

@tree.command(name="set_minimum_xp", description="XP minimum requis pour voir /xp et /leaderboard")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(min_xp="XP requis")
async def set_minimum_xp(interaction: discord.Interaction, min_xp: int):
    bot.xp_config["xp_command_min_xp"] = min_xp
    await interaction.response.send_message(
        f"✅ Il faut maintenant **{min_xp} XP** pour accéder aux commandes XP", ephemeral=True)

@tree.command(name="ajouter_badge", description="Ajoute un badge débloqué à un certain XP")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", badge="Nom ou emoji du badge")
async def ajouter_badge(interaction: discord.Interaction, xp: int, badge: str):
    bot.xp_config["badges"][str(xp)] = badge
    await interaction.response.send_message(
        f"✅ Badge **{badge}** ajouté à partir de **{xp} XP**", ephemeral=True)

@tree.command(name="ajouter_titre", description="Ajoute un titre débloqué à un certain XP")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", titre="Titre à débloquer")
async def ajouter_titre(interaction: discord.Interaction, xp: int, titre: str):
    bot.xp_config["titres"][str(xp)] = titre
    await interaction.response.send_message(
        f"✅ Titre **{titre}** ajouté à partir de **{xp} XP**", ephemeral=True)

# ========================================
# ⏰ Messages programmés (avec modaux)
# ========================================
class ProgrammerMessageModal(Modal, title="🗓️ Programmer un message"):
    def __init__(self, salon, type, date_heure):
        super().__init__(timeout=None)
        self.salon = salon
        self.type = type
        self.date_heure = date_heure  # Format attendu : "JJ/MM/AAAA HH:MM" en Europe/Paris

        self.contenu = TextInput(
            label="Contenu du message",
            style=TextStyle.paragraph,
            placeholder="Tape ici ton message complet avec mise en forme",
            required=True,
            max_length=2000
        )
        self.add_item(self.contenu)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            texte_final = textwrap.dedent(self.contenu.value)
            if len(texte_final) > 2000:
                await interaction.followup.send("❌ Le message est trop long après formatage (max 2000 caractères).", ephemeral=True)
                return

            # Utilisation de uuid4 pour générer un identifiant unique
            msg_id = str(uuid.uuid4())
            messages_programmes[msg_id] = {
                "channel_id": str(self.salon.id),
                "message": texte_final,
                "type": self.type,
                "next": self.date_heure
            }
            await sauvegarder_json_async(MSG_FILE, messages_programmes)
            await interaction.followup.send(
                f"✅ Message programmé dans {self.salon.mention} ({self.type}) pour le **{self.date_heure}**",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)

@tree.command(name="programmer_message", description="Planifie un message automatique (via modal)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    salon="Salon de destination",
    type="Type : once, daily ou weekly",
    date_heure="Date/heure (JJ/MM/AAAA HH:MM)"
)
async def programmer_message(interaction: discord.Interaction, salon: discord.TextChannel, type: str, date_heure: str):
    valid_types = ["once", "daily", "weekly"]
    if type.lower() not in valid_types:
        await interaction.response.send_message("❌ Type invalide. Choisissez entre: once, daily ou weekly.", ephemeral=True)
        return

    try:
        datetime.datetime.strptime(date_heure, "%d/%m/%Y %H:%M")
    except ValueError:
        await interaction.response.send_message("❌ Format invalide. Utilise : JJ/MM/AAAA HH:MM", ephemeral=True)
        return

    try:
        modal = ProgrammerMessageModal(salon, type.lower(), date_heure)
        await interaction.response.send_modal(modal)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur lors de l'ouverture du modal : {e}", ephemeral=True)

@tree.command(name="supprimer_message_programmé", description="Supprime un message programmé")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message_id="ID du message à supprimer (affiché dans /messages_programmés)")
async def supprimer_message_programmé(interaction: discord.Interaction, message_id: str):
    if message_id in messages_programmes:
        del messages_programmes[message_id]
        await sauvegarder_json_async(MSG_FILE, messages_programmes)
        await interaction.response.send_message("✅ Message programmé supprimé.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ ID non trouvé.", ephemeral=True)

@tree.command(name="messages_programmés", description="Affiche les messages programmés")
@app_commands.checks.has_permissions(administrator=True)
async def messages_programmés(interaction: discord.Interaction):
    if not messages_programmes:
        await interaction.response.send_message("Aucun message programmé.", ephemeral=True)
        return

    texte = "**🗓️ Messages programmés :**\n"
    for msg_id, msg in messages_programmes.items():
        texte += f"🆔 `{msg_id}` — <#{msg['channel_id']}> — ⏰ {msg['next']} — 🔁 {msg['type']}\n"

    await interaction.response.send_message(texte.strip(), ephemeral=True)

class ModifierMessageModal(Modal, title="✏️ Modifier un message programmé"):
    def __init__(self, message_id):
        super().__init__(timeout=None)
        self.message_id = message_id

        self.nouveau_contenu = TextInput(
            label="Nouveau message",
            style=TextStyle.paragraph,
            placeholder="Tape ici le nouveau message...",
            required=True,
            max_length=2000
        )
        self.add_item(self.nouveau_contenu)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.message_id in messages_programmes:
            messages_programmes[self.message_id]["message"] = textwrap.dedent(self.nouveau_contenu.value)
            await sauvegarder_json_async(MSG_FILE, messages_programmes)
            await interaction.followup.send("✅ Message modifié avec succès.", ephemeral=True)
        else:
            await interaction.followup.send("❌ ID introuvable.", ephemeral=True)

@tree.command(name="modifier_message_programmé", description="Modifie un message programmé")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message_id="ID du message à modifier")
async def modifier_message_programmé(interaction: discord.Interaction, message_id: str):
    if message_id in messages_programmes:
        modal = ModifierMessageModal(message_id)
        await interaction.response.send_modal(modal)
    else:
        await interaction.response.send_message("❌ ID introuvable.", ephemeral=True)

# ========================================
# 🎭 /roledereaction — Crée un message avec réaction et rôle (via modal)
# ========================================
class RoleReactionModal(Modal, title="✍️ Créer un message avec formatage"):
    def __init__(self, emoji: str, role: discord.Role, salon: discord.TextChannel):
        super().__init__(timeout=None)
        try:
            self.emoji = discord.PartialEmoji.from_str(emoji)
            self.emoji_key = get_emoji_key(self.emoji)
        except Exception as e:
            raise ValueError(f"Emoji invalide : {emoji}") from e

        self.role = role
        self.salon = salon

        self.contenu = TextInput(
            label="Texte du message",
            style=TextStyle.paragraph,
            placeholder="Entre ton message ici (sauts de ligne autorisés)",
            required=True,
            max_length=2000,
            custom_id="roledereaction_contenu"
        )
        self.add_item(self.contenu)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            message_envoye = await self.salon.send(textwrap.dedent(self.contenu.value))
            await message_envoye.add_reaction(self.emoji)
            bot.reaction_roles[message_envoye.id] = {self.emoji_key: self.role.id}
            await interaction.followup.send(
                f"✅ Nouveau message envoyé dans {self.salon.mention}\n- Emoji utilisé : {self.emoji}\n- Rôle associé : **{self.role.name}**",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de l'envoi du message : {e}", ephemeral=True)

# ========================================
# 🎭 /ajout_reaction_id — Ajoute un rôle à une réaction sur un message existant
# ========================================
@tree.command(name="ajout_reaction_id", description="Ajoute une réaction à un message déjà publié")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    role="Rôle à attribuer",
    emoji="Emoji à utiliser",
    message_id="ID du message existant"
)
async def ajout_reaction_id(interaction: discord.Interaction, role: discord.Role, emoji: str, message_id: str):
    try:
        msg_id = int(message_id)
        msg = await interaction.channel.fetch_message(msg_id)
        await msg.add_reaction(emoji)

        emoji_key = get_emoji_key(emoji)
        if msg_id in bot.reaction_roles:
            bot.reaction_roles[msg_id][emoji_key] = role.id
        else:
            bot.reaction_roles[msg_id] = {emoji_key: role.id}

        await interaction.response.send_message(
            f"✅ Réaction {emoji} ajoutée au message `{message_id}` pour le rôle **{role.name}**",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {str(e)}", ephemeral=True)

# ========================================
# 🔁 Événements : gestion automatique des rôles via réactions
# ========================================
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    member = guild.get_member(payload.user_id)
    if not member or member.bot:
        return

    # Gestion spécifique pour l'emoji "✅" (défi)
    if str(payload.emoji) == "✅":
        data = defis_data.get(str(payload.message_id))
        if data:
            role = guild.get_role(data["role_id"])
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Participation au défi hebdomadaire")
                except Exception as e:
                    print(f"❌ Erreur lors de l'ajout du rôle défi : {e}")
        return

    emoji_key = get_emoji_key(payload.emoji)
    data = bot.reaction_roles.get(payload.message_id)
    if isinstance(data, dict):
        role_id = data.get(emoji_key)
        if role_id:
            role = guild.get_role(int(role_id))
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Réaction ajoutée")
                except Exception as e:
                    print(f"❌ Erreur ajout rôle : {e}")

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return

    member = guild.get_member(payload.user_id)
    if not member or member.bot:
        return

    if str(payload.emoji) == "✅":
        data = defis_data.get(str(payload.message_id))
        if data:
            role = guild.get_role(data["role_id"])
            if role and role in member.roles:
                try:
                    await member.remove_roles(role, reason="Abandon du défi hebdomadaire")
                except Exception as e:
                    print(f"❌ Erreur lors du retrait du rôle défi : {e}")
        return

    emoji_key = get_emoji_key(payload.emoji)
    data = bot.reaction_roles.get(payload.message_id)
    if isinstance(data, dict):
        role_id = data.get(emoji_key)
        if role_id:
            role = guild.get_role(int(role_id))
            if role and role in member.roles:
                try:
                    await member.remove_roles(role, reason="Réaction retirée")
                except Exception as e:
                    print(f"❌ Erreur retrait rôle : {e}")

# ========================================
# 🔥 Modal de défi hebdomadaire (amélioré)
# ========================================
class DefiModal(Modal, title="🔥 Défi de la semaine"):
    def __init__(self, salon, role, durée_heures):
        super().__init__(timeout=None)
        self.salon = salon
        self.role = role
        self.durée_heures = durée_heures

        self.message = TextInput(
            label="Message du défi",
            style=TextStyle.paragraph,
            placeholder="Décris ton défi ici (sauts de ligne acceptés)",
            required=True,
            max_length=2000
        )
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            msg = await self.salon.send(textwrap.dedent(self.message.value))
            await msg.add_reaction("✅")

            end_timestamp = time.time() + self.durée_heures * 3600

            defis_data[str(msg.id)] = {
                "channel_id": self.salon.id,
                "role_id": self.role.id,
                "end_timestamp": end_timestamp
            }
            await sauvegarder_json_async(DEFIS_FILE, defis_data)

            # Lancement de la tâche en arrière-plan
            asyncio.create_task(retirer_role_après_defi(interaction.guild, msg.id, self.role))

            await interaction.followup.send(
                f"✅ Défi lancé dans {self.salon.mention} avec le rôle **{self.role.name}** pour **{self.durée_heures}h**",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de la création du défi : {e}", ephemeral=True)

# ========================================
# ⏳ Retrait du rôle à la fin du défi (optimisé via role.members)
# ========================================
async def retirer_role_après_defi(guild, message_id, role):
    try:
        data = defis_data.get(str(message_id))
        if not data:
            print(f"⚠️ Données du défi introuvables pour le message {message_id}")
            return

        temps_restant = data["end_timestamp"] - time.time()
        await asyncio.sleep(max(0, temps_restant))

        for member in role.members:
            try:
                await member.remove_roles(role, reason="Fin du défi hebdomadaire")
            except Exception as e:
                print(f"❌ Impossible de retirer le rôle à {member.display_name} : {e}")

        del defis_data[str(message_id)]
        await sauvegarder_json_async(DEFIS_FILE, defis_data)
        print(f"✅ Rôle {role.name} retiré à tous et défi supprimé (message : {message_id})")
    except Exception as e:
        print(f"❌ Erreur dans retirer_role_après_defi : {e}")

@tree.command(name="defi_semaine", description="Lance un défi hebdomadaire avec un rôle temporaire")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    salon="Salon où poster le défi",
    role="Rôle temporaire à attribuer",
    durée_heures="Durée du défi en heures (ex: 168 pour 7 jours)"
)
async def defi_semaine(interaction: discord.Interaction, salon: discord.TextChannel, role: discord.Role, durée_heures: int):
    try:
        if durée_heures <= 0 or durée_heures > 10000:
            await interaction.response.send_message("❌ Durée invalide. Choisis entre 1h et 10 000h.", ephemeral=True)
            return

        modal = DefiModal(salon, role, durée_heures)
        await interaction.response.send_modal(modal)
    except Exception as e:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

# ========================================
# 📩 /envoyer_message — Envoyer un message via Modal (version améliorée)
# ========================================
class ModalEnvoyerMessage(Modal, title="📩 Envoyer un message formaté"):
    def __init__(self, salon: discord.TextChannel):
        super().__init__(timeout=None)
        self.salon = salon
        self.contenu = TextInput(
            label="Contenu du message",
            style=TextStyle.paragraph,
            placeholder="Colle ici ton message complet avec mise en forme",
            required=True,
            max_length=2000,
            custom_id="envoyer_message_contenu"
        )
        self.add_item(self.contenu)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.salon.send(textwrap.dedent(self.contenu.value))
            await interaction.followup.send(f"✅ Message envoyé dans {self.salon.mention}", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Le bot n’a pas la permission d’envoyer un message dans ce salon.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)

@tree.command(name="envoyer_message", description="Fait envoyer un message par le bot dans un salon via un modal")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(salon="Salon où envoyer le message")
async def envoyer_message(interaction: discord.Interaction, salon: discord.TextChannel):
    try:
        modal = ModalEnvoyerMessage(salon)
        await interaction.response.send_modal(modal)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {str(e)}", ephemeral=True)

# ========================================
# 🧹 /clear — Supprime un nombre de messages (version améliorée)
# ========================================
@tree.command(name="clear", description="Supprime un nombre de messages dans ce salon (max 100)")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(nombre="Nombre de messages à supprimer (entre 1 et 100)")
async def clear(interaction: discord.Interaction, nombre: int):
    if nombre < 1 or nombre > 100:
        await interaction.response.send_message("❌ Choisis un nombre entre 1 et 100.", ephemeral=True)
        return

    try:
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=nombre)
        await interaction.followup.send(f"🧽 {len(deleted)} messages supprimés avec succès.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Le bot n’a pas la permission de supprimer des messages dans ce salon.", ephemeral=True)
    except Exception as e:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Erreur lors de la suppression : {str(e)}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)



# ========================================
# MODULE D'EXTENSION POUR L'ENVOI DE MESSAGES AUTOMATIQUES PAR ROLE
# ========================================

# Fichier de configuration pour les messages automatiques par rôle
AUTO_DM_FILE = os.path.join(DATA_FOLDER, "auto_dm_configs.json")

class AutoDMCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Dictionnaire des configurations, indexé par un identifiant unique
        # Chaque entrée est de la forme : { "role_id": <str>, "dm_message": <str> }
        self.auto_dm_configs = {}

    async def load_configs(self):
        try:
            configs = await charger_json_async(AUTO_DM_FILE)
            if not isinstance(configs, dict):
                print("⚠️ La configuration chargée n'est pas un dictionnaire. Réinitialisation.")
                configs = {}
            self.auto_dm_configs = configs
            print("⚙️ Configuration automatique DM chargée avec succès.")
        except Exception as e:
            print(f"❌ Erreur critique lors du chargement des configs : {e}")
            self.auto_dm_configs = {}

    async def save_configs(self):
        try:
            await sauvegarder_json_async(AUTO_DM_FILE, self.auto_dm_configs)
            print("⚙️ Configurations sauvegardées.")
        except Exception as e:
            print(f"❌ Erreur lors de la sauvegarde des configs : {e}")

    # Méthode asynchrone appelée lors du chargement du Cog.
    async def cog_load(self):
        await self.load_configs()

    # Listener pour détecter l'attribution d'un rôle
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        try:
            # Détecte les rôles ajoutés
            added_roles = set(after.roles) - set(before.roles)
            if not added_roles:
                return
            for role in added_roles:
                for config in self.auto_dm_configs.values():
                    # Sécurité : on s'assure que la clé "role_id" et "dm_message" existent
                    if not isinstance(config, dict):
                        continue
                    if str(role.id) == config.get("role_id", ""):
                        dm_message = config.get("dm_message", "")
                        if not dm_message:
                            print(f"⚠️ Aucune message DM définie pour la config associée au rôle {role.id}")
                            continue
                        try:
                            await after.send(dm_message)
                            print(f"✅ DM automatique envoyé à {after} pour le rôle {role.name}")
                        except Exception as e:
                            print(f"❌ Échec de l'envoi du DM à {after} pour le rôle {role.name}: {e}")
        except Exception as e:
            print(f"❌ Erreur dans on_member_update : {e}")

    # ---------------------------------------------------
    # Commandes de gestion des configurations de DM automatique
    # ---------------------------------------------------
    @app_commands.command(name="autodm_add", description="Ajoute une configuration d'envoi de DM lors de l'attribution d'un rôle.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(role="Le rôle concerné", dm_message="Le message envoyé en DM")
    async def autodm_add(self, interaction: discord.Interaction, role: discord.Role, dm_message: str):
        try:
            # Vérification minimale : ne pas accepter un message vide
            if not dm_message.strip():
                await interaction.response.send_message("❌ Le message DM ne peut être vide.", ephemeral=True)
                return

            config_id = str(uuid.uuid4())
            self.auto_dm_configs[config_id] = {
                "role_id": str(role.id),
                "dm_message": dm_message.strip()
            }
            await self.save_configs()
            await interaction.response.send_message(f"✅ Configuration ajoutée avec ID `{config_id}` pour le rôle {role.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de l'ajout de la configuration : {e}", ephemeral=True)

    @app_commands.command(name="autodm_list", description="Affiche la liste des configurations d'envoi de DM automatique.")
    @app_commands.checks.has_permissions(administrator=True)
    async def autodm_list(self, interaction: discord.Interaction):
        try:
            if not self.auto_dm_configs:
                await interaction.response.send_message("Aucune configuration d'envoi automatique n'est définie.", ephemeral=True)
                return

            message_lines = []
            for config_id, config in self.auto_dm_configs.items():
                role_obj = interaction.guild.get_role(int(config.get("role_id", 0)))
                role_name = role_obj.name if role_obj else f"ID {config.get('role_id', 'Inconnu')}"
                dm_msg = config.get("dm_message", "Aucun message")
                message_lines.append(f"**ID :** `{config_id}`\n**Rôle :** {role_name}\n**Message DM :** {dm_msg}\n")
            message_final = "\n".join(message_lines)
            await interaction.response.send_message(message_final, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de la récupération des configurations : {e}", ephemeral=True)

    @app_commands.command(name="autodm_remove", description="Supprime une configuration d'envoi automatique de DM.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(config_id="L'identifiant de la configuration à supprimer")
    async def autodm_remove(self, interaction: discord.Interaction, config_id: str):
        try:
            if config_id in self.auto_dm_configs:
                del self.auto_dm_configs[config_id]
                await self.save_configs()
                await interaction.response.send_message(f"✅ Configuration `{config_id}` supprimée.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Identifiant non trouvé.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de la suppression de la configuration : {e}", ephemeral=True)

    @app_commands.command(name="autodm_modify", description="Modifie une configuration d'envoi automatique de DM.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        config_id="L'identifiant de la configuration à modifier",
        new_role="Nouveau rôle (optionnel)",
        new_dm_message="Nouveau message DM (optionnel)"
    )
    async def autodm_modify(self, interaction: discord.Interaction, config_id: str, new_role: discord.Role = None, new_dm_message: str = None):
        try:
            if config_id not in self.auto_dm_configs:
                await interaction.response.send_message("❌ Identifiant non trouvé.", ephemeral=True)
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
            await interaction.response.send_message(f"✅ Configuration `{config_id}` modifiée.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de la modification de la configuration : {e}", ephemeral=True)

# Ajout du Cog d'envoi automatique de DM au bot
bot.add_cog(AutoDMCog(bot))





# ========================================
# 🔧 /creer_categories — Créer plusieurs catégories avec des permissions personnalisées (Admin uniquement)
# ========================================
@tree.command(name="creer_categories", description="Crée plusieurs catégories avec des noms personnalisés (emojis acceptés) et définit les rôles pouvant y accéder. (Admin uniquement)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    names="Liste des noms de catégories séparés par des virgules (ex: '🎮 Jeux, 💬 Discussions, 📚 Lecture')",
    roles="Liste des rôles à autoriser (séparés par des virgules ; utilise les mentions ou les noms exacts)"
)
async def creer_categories(interaction: discord.Interaction, names: str, roles: str):
    # Convertir la chaîne des noms en liste
    liste_categories = [nom.strip() for nom in names.split(",") if nom.strip()]
    
    # Récupérer les rôles à partir de la chaîne (supporte mentions et noms)
    roles_autorises = []
    for role_str in roles.split(","):
        role_str = role_str.strip()
        role_obj = None
        if role_str.startswith("<@&") and role_str.endswith(">"):
            try:
                role_id = int(role_str[3:-1])
                role_obj = interaction.guild.get_role(role_id)
            except Exception:
                pass
        else:
            role_obj = discord.utils.get(interaction.guild.roles, name=role_str)
        if role_obj:
            roles_autorises.append(role_obj)
    
    if not liste_categories:
        await interaction.response.send_message("❌ Aucun nom de catégorie fourni.", ephemeral=True)
        return

    if not roles_autorises:
        await interaction.response.send_message("❌ Aucun rôle valide trouvé. Utilise une mention (ex: <@&123456789>) ou le nom exact du rôle.", ephemeral=True)
        return

    liste_crees = []
    for cat_name in liste_categories:
        # Définir les permissions : deny pour @everyone, allow pour chacun des rôles spécifiés
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False)
        }
        for role in roles_autorises:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True)
        try:
            nouvelle_categorie = await interaction.guild.create_category(name=cat_name, overwrites=overwrites)
            liste_crees.append(nouvelle_categorie.name)
        except Exception as e:
            print(f"❌ Erreur lors de la création de la catégorie '{cat_name}' : {e}")

    if liste_crees:
        await interaction.response.send_message(f"✅ Catégories créées : {', '.join(liste_crees)}", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Aucune catégorie n'a pu être créée.", ephemeral=True)


# ========================================
# 🔧 /creer_salons — Créer plusieurs salons dans une catégorie existante (Admin uniquement)
# ========================================
@tree.command(name="creer_salons", description="Crée plusieurs salons dans une catégorie choisie. (Admin uniquement)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    category="La catégorie dans laquelle créer les salons",
    names="Liste des noms de salons séparés par des virgules (ex: 'général, annonces, debates')",
    type="Type de salon : 'text', 'voice' ou 'both' (pour créer à la fois un salon texte et un salon vocal)"
)
async def creer_salons(interaction: discord.Interaction, category: discord.CategoryChannel, names: str, type: str):
    liste_salons = [n.strip() for n in names.split(",") if n.strip()]
    if not liste_salons:
        await interaction.response.send_message("❌ Aucun nom de salon fourni.", ephemeral=True)
        return

    liste_crees = []
    type_lower = type.lower()
    if type_lower not in ["text", "voice", "both"]:
        await interaction.response.send_message("❌ Type inconnu. Utilise 'text', 'voice' ou 'both'.", ephemeral=True)
        return

    for salon_name in liste_salons:
        try:
            if type_lower == "text":
                salon = await interaction.guild.create_text_channel(name=salon_name, category=category)
                liste_crees.append(salon.name)
            elif type_lower == "voice":
                salon = await interaction.guild.create_voice_channel(name=salon_name, category=category)
                liste_crees.append(salon.name)
            elif type_lower == "both":
                # Créer à la fois un salon texte et un salon vocal
                salon_text = await interaction.guild.create_text_channel(name=f"{salon_name}-text", category=category)
                salon_voice = await interaction.guild.create_voice_channel(name=f"{salon_name}-voice", category=category)
                liste_crees.append(f"{salon_text.name} & {salon_voice.name}")
        except Exception as e:
            print(f"❌ Erreur lors de la création du salon '{salon_name}' : {e}")

    if liste_crees:
        await interaction.response.send_message(f"✅ Salons créés dans la catégorie **{category.name}** : {', '.join(liste_crees)}", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Aucun salon n'a pu être créé.", ephemeral=True)


# ========================================
# 🔧 /creer_roles — Créer plusieurs rôles rapidement (Admin uniquement)
# ========================================
@tree.command(name="creer_roles", description="Crée plusieurs rôles avec des noms personnalisés et une couleur optionnelle. (Admin uniquement)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    names="Liste des noms de rôles séparés par des virgules (ex: 'VIP, Membre, Staff')",
    color="(Optionnel) Code couleur hexadécimal (ex: #FF5733) à appliquer à tous les rôles"
)
async def creer_roles(interaction: discord.Interaction, names: str, color: str = None):
    liste_roles = [role.strip() for role in names.split(",") if role.strip()]
    liste_crees = []
    role_color = None

    # Conversion du code couleur en objet discord.Color si fourni
    if color:
        try:
            color = color.strip()
            if color.startswith("#"):
                color = color[1:]
            role_color = discord.Color(int(color, 16))
        except Exception as e:
            await interaction.response.send_message("❌ Le code couleur est invalide. Utilise un code hexadécimal correct (ex: #FF5733).", ephemeral=True)
            return

    for role_name in liste_roles:
        try:
            nouveau_role = await interaction.guild.create_role(
                name=role_name,
                color=role_color,
                mentionable=True  # Rendre le rôle mentionnable pour une meilleure visibilité
            )
            liste_crees.append(nouveau_role.name)
        except Exception as e:
            print(f"❌ Erreur lors de la création du rôle '{role_name}' : {e}")

    if liste_crees:
        await interaction.response.send_message(f"✅ Rôles créés : {', '.join(liste_crees)}", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Aucun rôle n'a pu être créé.", ephemeral=True)




# ========================================
# MODULE D'EXTENSION DE MODÉRATION
# ========================================
from discord import app_commands
from discord.ext import commands
import asyncio
import discord

class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Liste initiale de mots interdits (en minuscule)
        self.banned_words = {"merde", "putain", "con", "connard", "salop", "enculé", "nique ta mère"}
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ne pas modérer les messages du bot ou ceux des administrateurs
        if message.author.bot:
            return
        if message.author.guild_permissions.administrator:
            return

        content_lower = message.content.lower()
        for banned in self.banned_words:
            if banned in content_lower:
                try:
                    await message.delete()
                    print(f"Message supprimé de {message.author} pour contenu interdit.")
                    try:
                        await message.author.send("Votre message a été supprimé car il contenait des propos interdits.")
                    except Exception as e:
                        print(f"Impossible d'envoyer un DM à {message.author} : {e}")
                except Exception as e:
                    print(f"Erreur lors de la suppression d'un message : {e}")
                break

    # --- Commandes de gestion de la liste des mots bannis ---
    @app_commands.command(name="list_banned_words", description="Affiche la liste des mots bannis.")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_banned_words(self, interaction: discord.Interaction):
        words = ", ".join(sorted(self.banned_words))
        await interaction.response.send_message(f"Liste des mots bannis: {words}", ephemeral=True)

    @app_commands.command(name="add_banned_word", description="Ajoute un mot à la liste des mots bannis.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(word="Le mot à bannir")
    async def add_banned_word(self, interaction: discord.Interaction, word: str):
        word_lower = word.lower()
        if word_lower in self.banned_words:
            await interaction.response.send_message("Ce mot est déjà dans la liste des mots bannis.", ephemeral=True)
        else:
            self.banned_words.add(word_lower)
            await interaction.response.send_message(f"Le mot '{word}' a été ajouté à la liste des mots bannis.", ephemeral=True)

    @app_commands.command(name="remove_banned_word", description="Retire un mot de la liste des mots bannis.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(word="Le mot à retirer")
    async def remove_banned_word(self, interaction: discord.Interaction, word: str):
        word_lower = word.lower()
        if word_lower in self.banned_words:
            self.banned_words.remove(word_lower)
            await interaction.response.send_message(f"Le mot '{word}' a été retiré de la liste des mots bannis.", ephemeral=True)
        else:
            await interaction.response.send_message("Ce mot n'est pas dans la liste des mots bannis.", ephemeral=True)

    # --- Commandes de modération supplémentaires ---
    @app_commands.command(name="mute", description="Mute un utilisateur pour un certain temps (en minutes).")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="Le membre à mute", duration="Durée du mute en minutes")
    async def mute(self, interaction: discord.Interaction, member: discord.Member, duration: int):
        # Cherche ou crée le rôle "Muted"
        muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
        if not muted_role:
            try:
                muted_role = await interaction.guild.create_role(name="Muted", reason="Création du rôle Muted pour la modération.")
                for channel in interaction.guild.channels:
                    try:
                        await channel.set_permissions(muted_role, send_messages=False, speak=False)
                    except Exception as e:
                        print(f"Erreur lors de la configuration des permissions sur {channel.name}: {e}")
            except Exception as e:
                await interaction.response.send_message(f"Erreur lors de la création du rôle Muted: {e}", ephemeral=True)
                return
        try:
            await member.add_roles(muted_role, reason="Mute par modération.")
            await interaction.response.send_message(f"{member.mention} a été mute pour {duration} minutes.", ephemeral=True)
            await asyncio.sleep(duration * 60)
            await member.remove_roles(muted_role, reason="Fin du mute.")
            await interaction.followup.send(f"{member.mention} n'est plus mute.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erreur lors du mute: {e}", ephemeral=True)

    @app_commands.command(name="ban", description="Bannit un utilisateur du serveur.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="Le membre à bannir", reason="Raison du bannissement (facultatif)")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison fournie"):
        try:
            await member.ban(reason=reason)
            await interaction.response.send_message(f"{member.mention} a été banni. Raison: {reason}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erreur lors du bannissement de {member.mention}: {e}", ephemeral=True)

    @app_commands.command(name="kick", description="Expulse un utilisateur du serveur.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="Le membre à expulser", reason="Raison de l'expulsion (facultatif)")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison fournie"):
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(f"{member.mention} a été expulsé. Raison: {reason}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erreur lors de l'expulsion de {member.mention}: {e}", ephemeral=True)

# Ajout du Cog de modération au bot
bot.add_cog(ModerationCog(bot))










# ========================================
# 🌐 Serveur HTTP keep-alive (amélioré)
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
    except OSError as e:
        print(f"❌ Impossible de lancer le serveur HTTP keep-alive : {e}")
    except Exception as e:
        print(f"❌ Erreur inconnue dans keep_alive : {e}")

keep_alive()

# ========================================
# 🚀 Lancement du bot (version améliorée)
# ========================================
@bot.event
async def on_ready():
    try:
        print(f"✅ Connecté en tant que {bot.user} (ID : {bot.user.id})")
    except Exception as e:
        print(f"❌ Erreur dans on_ready : {e}")

async def main():
    global xp_data, messages_programmes, defis_data
    try:
        xp_data = await charger_json_async(XP_FILE)
        messages_programmes = await charger_json_async(MSG_FILE)
        defis_data = await charger_json_async(DEFIS_FILE)
    except Exception as e:
        print(f"❌ Erreur au chargement des données : {e}")

    try:
        await bot.start(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        print(f"❌ Erreur critique au lancement du bot : {e}")

asyncio.run(main())

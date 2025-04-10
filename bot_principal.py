import os
import json
import discord
from discord.ext import commands, tasks
from discord import app_commands, TextStyle, PartialEmoji
from discord.ui import Modal, TextInput
import asyncio
import textwrap
import time
import datetime
from zoneinfo import ZoneInfo  # Pour la gestion des fuseaux
import uuid
import aiofiles
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

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

# ========================================
# Verrou global pour les accès asynchrones aux fichiers
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
        else:
            return str(pe)
    except Exception:
        return str(emoji)

# ========================================
# Variables globales de données persistantes
# ========================================
xp_data = {}
messages_programmes = {}
defis_data = {}

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
        self.reaction_roles = {}
        self.vocal_start_times = {}
        # Configuration XP par défaut
        self.xp_config = {
            "xp_per_message": 10,
            "xp_per_minute_vocal": 5,
            "multipliers": {},           # {channel_id: multiplier (float)}
            "level_roles": {},           # {xp: role_id}
            "announcement_channel": None,
            "announcement_message": "🎉 {mention} a atteint {xp} XP !",
            "xp_command_channel": None,   # Salon autorisé pour /xp et /leaderboard
            "xp_command_min_xp": 0,
            "badges": {},
            "titres": {}
        }
    async def setup_hook(self):
        try:
            synced = await self.tree.sync()
            print(f"🌐 {len(synced)} commandes slash synchronisées")
            if not check_programmed_messages.is_running():
                check_programmed_messages.start()
                print("✅ Boucle check_programmed_messages démarrée")
        except Exception as e:
            print(f"❌ Erreur dans setup_hook : {e}")

bot = MyBot()
tree = bot.tree

# ========================================
# Boucle de vérification des messages programmés et défis récurrents
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
                    print(f"❌ Format de date invalide pour le message {msg_id} : {ve}")
                    continue

                if now >= msg_time:
                    channel = bot.get_channel(int(msg["channel_id"]))
                    if channel:
                        # Traitement selon le type du message programmé
                        if msg["type"] in ["once", "daily", "weekly"]:
                            await channel.send(textwrap.dedent(msg["message"]))
                            print(f"✅ Message {msg_id} envoyé dans #{channel.name}")
                        elif msg["type"] == "weekly_challenge":
                            # Envoi du défi récurrent
                            sent_msg = await channel.send(textwrap.dedent(msg["message"]))
                            await sent_msg.add_reaction("✅")
                            end_timestamp = time.time() + float(msg["duration_hours"]) * 3600
                            defis_data[str(sent_msg.id)] = {
                                "channel_id": channel.id,
                                "role_id": msg["role_id"],
                                "end_timestamp": end_timestamp
                            }
                            await sauvegarder_json_async(DEFIS_FILE, defis_data)
                            asyncio.create_task(retirer_role_apres_defi(channel.guild, sent_msg.id, channel.guild.get_role(int(msg["role_id"]))))
                            print(f"✅ Défi récurrent lancé dans #{channel.name} ; se terminera dans {msg['duration_hours']}h")
                        # Mise à jour de la date ou suppression selon le type
                        if msg["type"] == "once":
                            del messages_programmes[msg_id]
                            messages_modifies = True
                        elif msg["type"] in ["daily"]:
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
                        print(f"⚠️ Salon introuvable pour le message programmé {msg_id}")
            except Exception as e:
                print(f"❌ Erreur traitement message {msg_id} : {e}")

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
# Gestion de l'XP sur messages et vocal
# ========================================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Appliquer XP par message
    xp_val = bot.xp_config["xp_per_message"]
    mult = bot.xp_config["multipliers"].get(str(message.channel.id), 1.0)
    total_xp = int(xp_val * mult)
    current_xp = await add_xp(message.author.id, total_xp)
    
    # Attribution des rôles d'XP si seuil atteint
    for seuil, role_id in bot.xp_config["level_roles"].items():
        if current_xp >= int(seuil):
            role = message.guild.get_role(int(role_id))
            if role and role not in message.author.roles:
                try:
                    await message.author.add_roles(role, reason="Palier XP atteint")
                    if bot.xp_config["announcement_channel"]:
                        channel_annonce = bot.get_channel(int(bot.xp_config["announcement_channel"]))
                        if channel_annonce:
                            texte = bot.xp_config["announcement_message"].replace("{mention}", message.author.mention).replace("{xp}", str(current_xp))
                            await channel_annonce.send(texte)
                except Exception as e:
                    print(f"❌ Erreur rôle XP : {e}")
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
            for seuil, role_id in bot.xp_config["level_roles"].items():
                if current_xp >= int(seuil):
                    role = member.guild.get_role(int(role_id))
                    if role and role not in member.roles:
                        try:
                            await member.add_roles(role, reason="XP vocal atteint")
                            if bot.xp_config["announcement_channel"]:
                                channel_annonce = bot.get_channel(int(bot.xp_config["announcement_channel"]))
                                if channel_annonce:
                                    texte = bot.xp_config["announcement_message"].replace("{mention}", member.mention).replace("{xp}", str(current_xp))
                                    await channel_annonce.send(texte)
                        except Exception as e:
                            print(f"❌ Erreur rôle vocal : {e}")

# ========================================
# Commandes XP et Leaderboard (accessibles à tous dans le salon autorisé)
# ========================================
@tree.command(name="xp", description="Affiche ton XP")
async def xp(interaction: discord.Interaction):
    config = bot.xp_config
    if config["xp_command_channel"] and interaction.channel.id != int(config["xp_command_channel"]):
        await interaction.response.send_message("❌ Cette commande n'est pas autorisée dans ce salon.", ephemeral=True)
        return

    user_xp = get_xp(interaction.user.id)
    if user_xp < config["xp_command_min_xp"]:
        await interaction.response.send_message("❌ Tu n'as pas encore assez d'XP pour voir ton profil.", ephemeral=True)
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
        await interaction.response.send_message("❌ Cette commande n'est pas autorisée dans ce salon.", ephemeral=True)
        return
    classement = sorted(xp_data.items(), key=lambda x: x[1], reverse=True)[:10]
    lignes = []
    for i, (user_id, xp_val) in enumerate(classement):
        membre = interaction.guild.get_member(int(user_id))
        nom = membre.display_name if membre else f"Utilisateur {user_id}"
        lignes.append(f"{i+1}. {nom} — {xp_val} XP")
    texte = "🏆 **Top 10 XP :**\n" + "\n".join(lignes) if lignes else "Aucun membre avec de l'XP."
    await interaction.response.send_message(texte, ephemeral=True)

# ========================================
# Commandes XP ADMIN (toutes protégées par admin)
# ========================================
@tree.command(name="add_xp", description="Ajoute de l'XP à un membre (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(member="Membre ciblé", amount="Quantité d'XP à ajouter")
async def add_xp_cmd(interaction: discord.Interaction, member: discord.Member, amount: int):
    new_total = await add_xp(member.id, amount)
    texte = f"✅ {amount} XP ajoutés à {member.mention}\n🔹 Total : **{new_total} XP**"
    await interaction.response.send_message(texte, ephemeral=True)

@tree.command(name="set_xp_config", description="Modifie l'XP gagné par message et en vocal (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp_per_message="XP par message", xp_per_minute_vocal="XP par minute vocale")
async def set_xp_config(interaction: discord.Interaction, xp_per_message: int, xp_per_minute_vocal: int):
    bot.xp_config["xp_per_message"] = xp_per_message
    bot.xp_config["xp_per_minute_vocal"] = xp_per_minute_vocal
    await interaction.response.send_message(
        f"✅ XP mis à jour : {xp_per_message}/msg, {xp_per_minute_vocal}/min vocal", ephemeral=True)

@tree.command(name="set_xp_role", description="Définit un rôle à débloquer à partir d'un certain XP (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", role="Rôle à attribuer")
async def set_xp_role(interaction: discord.Interaction, xp: int, role: discord.Role):
    bot.xp_config["level_roles"][str(xp)] = role.id
    await interaction.response.send_message(
        f"✅ Le rôle **{role.name}** sera attribué à partir de **{xp} XP**", ephemeral=True)

@tree.command(name="set_xp_boost", description="Ajoute un multiplicateur d'XP à un salon (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon concerné", multiplier="Exemple : 2.0 pour XP x2")
async def set_xp_boost(interaction: discord.Interaction, channel: discord.TextChannel, multiplier: float):
    bot.xp_config["multipliers"][str(channel.id)] = multiplier
    await interaction.response.send_message(
        f"✅ Multiplicateur **x{multiplier}** appliqué à {channel.mention}", ephemeral=True)

@tree.command(name="set_salon_annonce", description="Définit le salon des annonces de niveau (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon cible")
async def set_salon_annonce(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["announcement_channel"] = str(channel.id)
    await interaction.response.send_message(
        f"✅ Les annonces de niveau seront postées dans {channel.mention}", ephemeral=True)

@tree.command(name="set_message_annonce", description="Modifie le message d’annonce de niveau (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message="Utilise {mention} et {xp} comme variables")
async def set_message_annonce(interaction: discord.Interaction, message: str):
    bot.xp_config["announcement_message"] = message
    preview = message.replace("{mention}", interaction.user.mention).replace("{xp}", "1234")
    await interaction.response.send_message(
        f"✅ Message mis à jour !\n\n💬 **Aperçu :**\n{preview}", ephemeral=True)

@tree.command(name="set_channel_xp", description="Définit le salon où /xp et /leaderboard sont utilisables (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon autorisé")
async def set_channel_xp(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["xp_command_channel"] = str(channel.id)
    await interaction.response.send_message(
        f"✅ Les commandes XP seront désormais accessibles dans {channel.mention}", ephemeral=True)

@tree.command(name="set_minimum_xp", description="Définit le XP minimum requis pour /xp (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(min_xp="XP minimum requis")
async def set_minimum_xp(interaction: discord.Interaction, min_xp: int):
    bot.xp_config["xp_command_min_xp"] = min_xp
    await interaction.response.send_message(
        f"✅ Désormais, il faut **{min_xp} XP** pour accéder aux commandes XP", ephemeral=True)

@tree.command(name="ajouter_badge", description="Ajoute un badge débloqué à partir d'un certain XP (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", badge="Nom ou emoji du badge")
async def ajouter_badge(interaction: discord.Interaction, xp: int, badge: str):
    bot.xp_config["badges"][str(xp)] = badge
    await interaction.response.send_message(
        f"✅ Badge **{badge}** ajouté à partir de **{xp} XP**", ephemeral=True)

@tree.command(name="ajouter_titre", description="Ajoute un titre débloqué à partir d'un certain XP (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", titre="Titre à débloquer")
async def ajouter_titre(interaction: discord.Interaction, xp: int, titre: str):
    bot.xp_config["titres"][str(xp)] = titre
    await interaction.response.send_message(
        f"✅ Titre **{titre}** ajouté à partir de **{xp} XP**", ephemeral=True)

# ========================================
# Système de messages programmés (via modaux)
# ========================================
class ProgrammerMessageModal(Modal, title="🗓️ Programmer un message"):
    def __init__(self, salon, type_message, date_heure):
        super().__init__(timeout=None)
        self.salon = salon
        self.type = type_message  # "once", "daily", "weekly" ou "weekly_challenge"
        self.date_heure = date_heure  # Format "JJ/MM/AAAA HH:MM"
        self.contenu = TextInput(
            label="Contenu du message",
            style=TextStyle.paragraph,
            placeholder="Tape ici ton message complet (mise en forme possible)",
            required=True,
            max_length=2000
        )
        self.add_item(self.contenu)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            texte_final = textwrap.dedent(self.contenu.value)
            if len(texte_final) > 2000:
                await interaction.followup.send("❌ Le message est trop long (max 2000 caractères).", ephemeral=True)
                return
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

@tree.command(name="programmer_message", description="Planifie un message automatique (via modal) (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    salon="Salon de destination",
    type="Type : once, daily, weekly ou weekly_challenge",
    date_heure="Date/heure (JJ/MM/AAAA HH:MM)"
)
async def programmer_message(interaction: discord.Interaction, salon: discord.TextChannel, type: str, date_heure: str):
    valid_types = ["once", "daily", "weekly", "weekly_challenge"]
    if type.lower() not in valid_types:
        await interaction.response.send_message("❌ Type invalide. Choisissez parmi : once, daily, weekly ou weekly_challenge.", ephemeral=True)
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

@tree.command(name="supprimer_message_programmé", description="Supprime un message programmé (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message_id="ID du message à supprimer (affiché dans /messages_programmés)")
async def supprimer_message_programme(interaction: discord.Interaction, message_id: str):
    if message_id in messages_programmes:
        del messages_programmes[message_id]
        await sauvegarder_json_async(MSG_FILE, messages_programmes)
        await interaction.response.send_message("✅ Message programmé supprimé.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ ID non trouvé.", ephemeral=True)

@tree.command(name="messages_programmés", description="Affiche la liste des messages programmés (admin)")
@app_commands.checks.has_permissions(administrator=True)
async def messages_programmes_cmd(interaction: discord.Interaction):
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

@tree.command(name="modifier_message_programmé", description="Modifie un message programmé (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message_id="ID du message à modifier")
async def modifier_message_programme(interaction: discord.Interaction, message_id: str):
    if message_id in messages_programmes:
        modal = ModifierMessageModal(message_id)
        await interaction.response.send_modal(modal)
    else:
        await interaction.response.send_message("❌ ID introuvable.", ephemeral=True)

# ========================================
# Système de réaction pour rôles
# ========================================
class RoleReactionModal(Modal, title="✍️ Créer un message avec réaction"):
    def __init__(self, emoji: str, role: discord.Role, salon: discord.TextChannel):
        super().__init__(timeout=None)
        try:
            self.emoji = PartialEmoji.from_str(emoji)
            self.emoji_key = get_emoji_key(self.emoji)
        except Exception as e:
            raise ValueError(f"Emoji invalide : {emoji}") from e
        self.role = role
        self.salon = salon
        self.contenu = TextInput(
            label="Texte du message",
            style=TextStyle.paragraph,
            placeholder="Entre ton message (sauts de ligne autorisés)",
            required=True,
            max_length=2000
        )
        self.add_item(self.contenu)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            message_envoye = await self.salon.send(textwrap.dedent(self.contenu.value))
            await message_envoye.add_reaction(self.emoji)
            bot.reaction_roles[message_envoye.id] = {self.emoji_key: self.role.id}
            await interaction.followup.send(
                f"✅ Message envoyé dans {self.salon.mention}\n- Emoji : {self.emoji}\n- Rôle associé : **{self.role.name}**",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de l'envoi du message : {e}", ephemeral=True)

@tree.command(name="ajout_reaction_id", description="Ajoute une réaction à un message existant (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    role="Rôle à attribuer",
    emoji="Emoji à utiliser",
    message_id="ID du message"
)
async def ajout_reaction_id(interaction: discord.Interaction, role: discord.Role, emoji: str, message_id: str):
    try:
        msg_id = int(message_id)
        msg = await interaction.channel.fetch_message(msg_id)
        await msg.add_reaction(emoji)
        emoji_key = get_emoji_key(emoji)
        bot.reaction_roles.setdefault(msg_id, {})[emoji_key] = role.id
        await interaction.response.send_message(
            f"✅ Réaction {emoji} ajoutée au message `{message_id}` pour le rôle **{role.name}**",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {str(e)}", ephemeral=True)

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
    # Cas du défi : réaction "✅"
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
# Défi hebdomadaire et défi récurrent
# ========================================
# Pour le défi lancé directement (non récurrent), on utilise un modal.
class DefiModal(Modal, title="🔥 Défi de la semaine"):
    def __init__(self, salon, role, duree_heures):
        super().__init__(timeout=None)
        self.salon = salon
        self.role = role
        self.duree_heures = duree_heures
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
            end_timestamp = time.time() + self.duree_heures * 3600
            defis_data[str(msg.id)] = {
                "channel_id": self.salon.id,
                "role_id": self.role.id,
                "end_timestamp": end_timestamp
            }
            await sauvegarder_json_async(DEFIS_FILE, defis_data)
            asyncio.create_task(retirer_role_apres_defi(interaction.guild, msg.id, self.role))
            await interaction.followup.send(
                f"✅ Défi lancé dans {self.salon.mention} avec le rôle **{self.role.name}** pour **{self.duree_heures}h**",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de la création du défi : {e}", ephemeral=True)

async def retirer_role_apres_defi(guild, message_id, role):
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
        print(f"❌ Erreur dans retirer_role_apres_defi : {e}")

# Commande defi_semaine améliorée (admin uniquement)
# Si recurrence est True, les paramètres start_date et challenge_message sont obligatoires
@tree.command(name="defi_semaine", description="Lance un défi hebdomadaire avec rôle temporaire (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    salon="Salon où poster le défi",
    role="Rôle temporaire à attribuer",
    duree_heures="Durée du défi en heures (ex: 168 pour 7 jours)",
    recurrence="Récurrence hebdomadaire (booléen)",
    start_date="Date/heure de début (JJ/MM/AAAA HH:MM) pour défi récurrent (optionnel)",
    challenge_message="Message du défi pour défi récurrent (optionnel)"
)
async def defi_semaine(interaction: discord.Interaction, salon: discord.TextChannel, role: discord.Role, duree_heures: int, recurrence: bool, start_date: str = None, challenge_message: str = None):
    if duree_heures <= 0 or duree_heures > 10000:
        await interaction.response.send_message("❌ Durée invalide. Choisis entre 1h et 10 000h.", ephemeral=True)
        return
    if recurrence:
        if not start_date or not challenge_message:
            await interaction.response.send_message("❌ Pour un défi récurrent, merci de fournir start_date (JJ/MM/AAAA HH:MM) et challenge_message.", ephemeral=True)
            return
        try:
            # Validation de la date de début
            datetime.datetime.strptime(start_date, "%d/%m/%Y %H:%M")
        except ValueError:
            await interaction.response.send_message("❌ Format de start_date invalide. Utilise : JJ/MM/AAAA HH:MM", ephemeral=True)
            return
        # Planification du défi récurrent via le système de messages programmés
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
        await interaction.response.send_message(
            f"✅ Défi récurrent programmé dans {salon.mention} à partir du {start_date} (chaque semaine).",
            ephemeral=True
        )
    else:
        # Lancement immédiat via modal pour personnalisation du message
        try:
            modal = DefiModal(salon, role, duree_heures)
            await interaction.response.send_modal(modal)
        except Exception as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

# ========================================
# Envoi de message via modal (admin)
# ========================================
class ModalEnvoyerMessage(Modal, title="📩 Envoyer un message formaté"):
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
            await interaction.followup.send(f"✅ Message envoyé dans {self.salon.mention}", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Le bot n’a pas la permission d’envoyer un message dans ce salon.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)

@tree.command(name="envoyer_message", description="Envoi un message par le bot dans un salon (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(salon="Salon où envoyer le message")
async def envoyer_message(interaction: discord.Interaction, salon: discord.TextChannel):
    try:
        modal = ModalEnvoyerMessage(salon)
        await interaction.response.send_modal(modal)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {str(e)}", ephemeral=True)

# ========================================
# Commande /clear pour supprimer des messages (admin)
# ========================================
@tree.command(name="clear", description="Supprime un nombre de messages dans ce salon (max 100) (admin)")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(nombre="Nombre de messages à supprimer (entre 1 et 100)")
async def clear(interaction: discord.Interaction, nombre: int):
    if nombre < 1 or nombre > 100:
        await interaction.response.send_message("❌ Choisis un nombre entre 1 et 100.", ephemeral=True)
        return
    try:
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=nombre)
        await interaction.followup.send(f"🧽 {len(deleted)} messages supprimés.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Le bot n’a pas la permission de supprimer des messages dans ce salon.", ephemeral=True)
    except Exception as e:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Erreur lors de la suppression : {str(e)}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)

# ========================================
# ADMIN UTILS – Outils d'administration avancés (suppression de catégories, salons, rôles)
# ========================================
# Modal de confirmation pour suppression définitive
class ConfirmationModal(Modal, title="⚠️ Confirmation requise"):
    def __init__(self, action: str):
        super().__init__(timeout=60)
        self.action = action
        self.confirmation = TextInput(
            label=f"Pour confirmer {action}, tapez CONFIRMER",
            style=TextStyle.short,
            placeholder="CONFIRMER",
            required=True,
            max_length=20
        )
        self.add_item(self.confirmation)
    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmation.value.strip().upper() == "CONFIRMER":
            self.value = True
        else:
            self.value = False
        await interaction.response.defer(ephemeral=True)

class AdminUtilsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="supprimer_categorie", description="Supprime rapidement une catégorie (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def supprimer_categorie(self, interaction: discord.Interaction, categorie: discord.CategoryChannel):
        try:
            await categorie.delete()
            await interaction.response.send_message(f"✅ Catégorie **{categorie.name}** supprimée.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de la suppression de la catégorie : {e}", ephemeral=True)

    @app_commands.command(name="supprimer_salon", description="Supprime rapidement un salon (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def supprimer_salon(self, interaction: discord.Interaction, salon: discord.abc.GuildChannel):
        try:
            await salon.delete()
            await interaction.response.send_message(f"✅ Salon **{salon.name}** supprimé.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de la suppression du salon : {e}", ephemeral=True)

    @app_commands.command(name="reset_roles", description="Retire de tous les membres tous les rôles (sauf admins) (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_roles(self, interaction: discord.Interaction):
        try:
            for member in interaction.guild.members:
                roles_a_retirer = [role for role in member.roles if not role.permissions.administrator]
                if roles_a_retirer:
                    await member.remove_roles(*roles_a_retirer, reason="Réinitialisation des rôles")
            await interaction.response.send_message("✅ Tous les rôles (sauf admins) ont été retirés à tous les membres.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de la réinitialisation des rôles : {e}", ephemeral=True)

    @app_commands.command(name="supprimer_tous_roles", description="Supprime définitivement TOUS les rôles (sauf admins) du serveur (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def supprimer_tous_roles(self, interaction: discord.Interaction):
        modal = ConfirmationModal("la suppression de tous les rôles")
        await interaction.response.send_modal(modal)
        await asyncio.sleep(1)  # Attendre la réponse du modal
        if getattr(modal, "value", False):
            try:
                for role in interaction.guild.roles:
                    if not role.permissions.administrator and role < interaction.guild.me.top_role:
                        await role.delete(reason="Suppression de tous les rôles demandée par un admin")
                await interaction.followup.send("✅ Tous les rôles (sauf admins) ont été définitivement supprimés.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Erreur lors de la suppression des rôles : {e}", ephemeral=True)
        else:
            await interaction.followup.send("❌ Confirmation non validée. Opération annulée.", ephemeral=True)

    @app_commands.command(name="supprimer_tous_salons_categories", description="Supprime définitivement TOUS les salons et catégories du serveur (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def supprimer_tous_salons_categories(self, interaction: discord.Interaction):
        modal = ConfirmationModal("la suppression de tous les salons et catégories")
        await interaction.response.send_modal(modal)
        await asyncio.sleep(1)
        if getattr(modal, "value", False):
            try:
                for channel in interaction.guild.channels:
                    await channel.delete(reason="Suppression de tous les salons et catégories demandée par un admin")
                await interaction.followup.send("✅ Tous les salons et catégories ont été supprimés.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Erreur lors de la suppression : {e}", ephemeral=True)
        else:
            await interaction.followup.send("❌ Confirmation non validée. Opération annulée.", ephemeral=True)

async def setup_admin_utils(bot):
    await bot.add_cog(AdminUtilsCog(bot))

# ========================================
# Module AutoDM (non modifié, admin protégé)
# ========================================
class AutoDMCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_dm_configs = {}
    async def load_configs(self):
        try:
            configs = await charger_json_async(AUTO_DM_FILE)
            if not isinstance(configs, dict):
                print("⚠️ Config invalide – réinitialisation")
                configs = {}
            self.auto_dm_configs = configs
            print("⚙️ Configurations AutoDM chargées.")
        except Exception as e:
            print(f"❌ Erreur lors du chargement des configs : {e}")
            self.auto_dm_configs = {}
    async def save_configs(self):
        try:
            await sauvegarder_json_async(AUTO_DM_FILE, self.auto_dm_configs)
            print("⚙️ Configurations AutoDM sauvegardées.")
        except Exception as e:
            print(f"❌ Erreur lors de la sauvegarde des configs : {e}")
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
                            print(f"⚠️ Aucun message DM défini pour le rôle {role.id}")
                            continue
                        try:
                            await after.send(dm_message)
                            print(f"✅ DM envoyé à {after} pour le rôle {role.name}")
                        except Exception as e:
                            print(f"❌ Échec DM pour {after} : {e}")
        except Exception as e:
            print(f"❌ Erreur dans on_member_update : {e}")
    @app_commands.command(name="autodm_add", description="Ajoute une configuration d'envoi de DM (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(role="Rôle concerné", dm_message="Message à envoyer en DM")
    async def autodm_add(self, interaction: discord.Interaction, role: discord.Role, dm_message: str):
        if not dm_message.strip():
            await interaction.response.send_message("❌ Le message DM ne peut être vide.", ephemeral=True)
            return
        config_id = str(uuid.uuid4())
        self.auto_dm_configs[config_id] = {
            "role_id": str(role.id),
            "dm_message": dm_message.strip()
        }
        await self.save_configs()
        await interaction.response.send_message(f"✅ Config ajoutée avec l'ID `{config_id}` pour le rôle {role.mention}.", ephemeral=True)
    @app_commands.command(name="autodm_list", description="Liste les configurations AutoDM (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def autodm_list(self, interaction: discord.Interaction):
        if not self.auto_dm_configs:
            await interaction.response.send_message("Aucune configuration définie.", ephemeral=True)
            return
        message_lines = []
        for config_id, config in self.auto_dm_configs.items():
            role_obj = interaction.guild.get_role(int(config.get("role_id", 0)))
            role_name = role_obj.name if role_obj else f"ID {config.get('role_id', 'Inconnu')}"
            dm_msg = config.get("dm_message", "Aucun message")
            message_lines.append(f"**ID :** `{config_id}`\n**Rôle :** {role_name}\n**Message DM :** {dm_msg}\n")
        await interaction.response.send_message("\n".join(message_lines), ephemeral=True)
    @app_commands.command(name="autodm_remove", description="Supprime une config AutoDM (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(config_id="ID de la configuration à supprimer")
    async def autodm_remove(self, interaction: discord.Interaction, config_id: str):
        if config_id in self.auto_dm_configs:
            del self.auto_dm_configs[config_id]
            await self.save_configs()
            await interaction.response.send_message(f"✅ Configuration `{config_id}` supprimée.", ephemeral=True)
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
        await interaction.response.send_message(f"✅ Configuration `{config_id}` modifiée.", ephemeral=True)

async def setup_autodm(bot):
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
                        await message.author.send("Ton message a été supprimé car il contenait des propos interdits.")
                    except Exception as e:
                        print(f"Erreur DM à {message.author} : {e}")
                except Exception as e:
                    print(f"Erreur suppression message : {e}")
                break
    @app_commands.command(name="list_banned_words", description="Liste les mots bannis (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def list_banned_words(self, interaction: discord.Interaction):
        words = ", ".join(sorted(self.banned_words))
        await interaction.response.send_message(f"Mots bannis : {words}", ephemeral=True)
    @app_commands.command(name="add_banned_word", description="Ajoute un mot à la liste des mots bannis (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(word="Le mot à bannir")
    async def add_banned_word(self, interaction: discord.Interaction, word: str):
        word_lower = word.lower()
        if word_lower in self.banned_words:
            await interaction.response.send_message("Ce mot est déjà banni.", ephemeral=True)
        else:
            self.banned_words.add(word_lower)
            await interaction.response.send_message(f"Le mot '{word}' a été banni.", ephemeral=True)
    @app_commands.command(name="remove_banned_word", description="Retire un mot de la liste des mots bannis (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(word="Le mot à retirer")
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
                muted_role = await interaction.guild.create_role(name="Muted", reason="Création du rôle Muted pour modération.")
                for channel in interaction.guild.channels:
                    try:
                        await channel.set_permissions(muted_role, send_messages=False, speak=False)
                    except Exception as e:
                        print(f"Erreur config permissions sur {channel.name}: {e}")
            except Exception as e:
                await interaction.response.send_message(f"Erreur création rôle Muted: {e}", ephemeral=True)
                return
        try:
            await member.add_roles(muted_role, reason="Mute par modération.")
            await interaction.response.send_message(f"{member.mention} muté pendant {duration} minutes.", ephemeral=True)
            await asyncio.sleep(duration * 60)
            await member.remove_roles(muted_role, reason="Fin du mute")
            await interaction.followup.send(f"{member.mention} n'est plus mute.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erreur lors du mute : {e}", ephemeral=True)
    @app_commands.command(name="ban", description="Bannit un utilisateur (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="Membre à bannir", reason="Raison (optionnel)")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison"):
        try:
            await member.ban(reason=reason)
            await interaction.response.send_message(f"{member.mention} banni. Raison : {reason}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erreur bannissement de {member.mention}: {e}", ephemeral=True)
    @app_commands.command(name="kick", description="Expulse un utilisateur (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(member="Membre à expulser", reason="Raison (optionnel)")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Aucune raison"):
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(f"{member.mention} expulsé. Raison : {reason}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erreur expulsion de {member.mention}: {e}", ephemeral=True)

async def setup_moderation(bot):
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
        print(f"❌ Erreur lancement serveur keep-alive : {e}")

keep_alive()

@bot.event
async def on_ready():
    try:
        print(f"✅ Connecté en tant que {bot.user} (ID : {bot.user.id})")
    except Exception as e:
        print(f"❌ Erreur dans on_ready : {e}")

# ========================================
# Fonction main – Chargement des données et lancement du bot
# ========================================
async def main():
    global xp_data, messages_programmes, defis_data
    try:
        xp_data = await charger_json_async(XP_FILE)
        messages_programmes = await charger_json_async(MSG_FILE)
        defis_data = await charger_json_async(DEFIS_FILE)
    except Exception as e:
        print(f"❌ Erreur au chargement des données : {e}")
    await setup_admin_utils(bot)
    await setup_autodm(bot)
    await setup_moderation(bot)
    try:
        await bot.start(os.getenv("DISCORD_TOKEN"))
    except Exception as e:
        print(f"❌ Erreur critique au lancement du bot : {e}")

asyncio.run(main())

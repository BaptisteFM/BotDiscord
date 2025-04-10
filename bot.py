import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from dotenv import load_dotenv
import json
import time
import asyncio
import textwrap
import datetime


# Charger le .env et récupérer le TOKEN
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Activer les intents nécessaires
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True
intents.voice_states = True

# Création du bot
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.reaction_roles = {}
        self.xp_data = {}
        self.xp_config = {
            "xp_per_message": 10,
            "xp_per_minute_vocal": 5,
            "multipliers": {},           # {channel_id: x2.0}
            "level_roles": {},           # {xp: role_id}
            "announcement_channel": None,
            "announcement_message": "🎉 {mention} a atteint {xp} XP !",
            "xp_command_channel": None,
            "xp_command_min_xp": 0,
            "badges": {},                # {xp: badge}
            "titres": {}                 # {xp: titre}
        }
        self.vocal_start_times = {}
        self.programmed_messages = []  # [{day, hour, channel_id, content}]
        self.XP_FILE = "xp.json"

    async def setup_hook(self):
        await self.tree.sync()
        print("🌐 Slash commands synchronisées globalement")

bot = MyBot()
tree = bot.tree  # raccourci pour les commandes slash
async def setup_hook(self):
    try:
        synced = await self.tree.sync(guild=None)
        print(f"🌐 {len(synced)} commandes slash synchronisées (globalement)")
    except Exception as e:
        print(f"❌ Erreur synchronisation : {e}")




from discord.ui import Modal, TextInput
from discord import TextStyle


# =======================================
# 🎭 /roledereaction — Ajouter un rôle à un message (ou en créer un via modal)
# =======================================

class RoleReactionModal(discord.ui.Modal, title="✍️ Créer un message avec formatage"):

    contenu = discord.ui.TextInput(
        label="Texte du message",
        style=discord.TextStyle.paragraph,
        placeholder="Entre ton message ici (sauts de ligne autorisés)",
        required=True,
        max_length=2000
    )

    def __init__(self, emoji, role, salon):
        super().__init__(timeout=None)  # ✅ Désactive le timeout automatique
        self.emoji = emoji
        self.role = role
        self.salon = salon

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)  # ✅ Préviens le timeout si traitement un peu long

            message_envoye = await self.salon.send(textwrap.dedent(self.contenu.value))
            await message_envoye.add_reaction(self.emoji)
            bot.reaction_roles[message_envoye.id] = {self.emoji: self.role.id}

            await interaction.followup.send(
                f"✅ Nouveau message envoyé dans {self.salon.mention}\n"
                f"- Emoji utilisé : {self.emoji}\n"
                f"- Rôle associé : **{self.role.name}**",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)


@bot.tree.command(name="roledereaction", description="Ajoute une réaction à un message existant ou en crée un nouveau via un modal")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    emoji="Emoji à utiliser",
    role="Rôle à attribuer",
    message_id="ID du message existant (laisse vide pour en créer un)",
    salon="Salon pour envoyer le message si création"
)
async def roledereaction(
    interaction: discord.Interaction,
    emoji: str,
    role: discord.Role,
    message_id: str = None,
    salon: discord.TextChannel = None
):
    try:
        if message_id:
            await interaction.response.defer(ephemeral=True)

            msg_id_int = int(message_id)
            channel = interaction.channel
            msg = await channel.fetch_message(msg_id_int)
            await msg.add_reaction(emoji)

            if msg_id_int in bot.reaction_roles:
                bot.reaction_roles[msg_id_int][emoji] = role.id
            else:
                bot.reaction_roles[msg_id_int] = {emoji: role.id}

            await interaction.followup.send(
                f"✅ Réaction {emoji} ajoutée au message `{message_id}` pour le rôle **{role.name}**",
                ephemeral=True
            )

        else:
            if not salon:
                await interaction.response.send_message(
                    "❌ Merci de spécifier un salon si tu veux créer un nouveau message.",
                    ephemeral=True
                )
                return

            modal = RoleReactionModal(emoji, role, salon)
            await interaction.response.send_modal(modal)

    except Exception as e:
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Erreur : {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)
        except:
            print(f"❌ Erreur fatale : {e}")



# ========================================
# 🎭 Fonction : /ajout_reaction_id
# Ajoute un emoji à un message déjà publié pour donner un rôle
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

        if msg_id in bot.reaction_roles:
            bot.reaction_roles[msg_id][emoji] = role.id
        else:
            bot.reaction_roles[msg_id] = {emoji: role.id}

        await interaction.response.send_message(
            f"✅ Réaction {emoji} ajoutée au message {msg_id} pour {role.name}", ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {str(e)}", ephemeral=True)




# ========================================
# 🎭 Fonction : /supprimer_reaction_role
# Supprime le lien entre un emoji et un rôle pour un message donné
# ========================================

@tree.command(name="supprimer_reaction_role", description="Supprime le lien entre une réaction et un rôle")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    message_id="ID du message",
    emoji="Emoji à retirer"
)
async def supprimer_reaction_role(interaction: discord.Interaction, message_id: str, emoji: str):
    try:
        msg_id = int(message_id)
        if msg_id in bot.reaction_roles and emoji in bot.reaction_roles[msg_id]:
            del bot.reaction_roles[msg_id][emoji]
            await interaction.response.send_message(
                f"✅ Le lien {emoji} - rôle a été supprimé du message {message_id}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Aucun lien trouvé pour {emoji} sur le message {message_id}", ephemeral=True
            )
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {str(e)}", ephemeral=True)




# ========================================
# 🎭 Gestion automatique des rôles via réactions
# ========================================

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)

    data = bot.reaction_roles.get(payload.message_id)
    if data:
        if isinstance(data, dict):
            role_id = data.get(str(payload.emoji)) or data.get("role_id") if str(payload.emoji) == data.get("emoji") else None
            if role_id:
                role = guild.get_role(int(role_id))
                if role and member:
                    await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == bot.user.id:
        return
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)

    data = bot.reaction_roles.get(payload.message_id)
    if data:
        if isinstance(data, dict):
            role_id = data.get(str(payload.emoji)) or data.get("role_id") if str(payload.emoji) == data.get("emoji") else None
            if role_id:
                role = guild.get_role(int(role_id))
                if role and member:
                    await member.remove_roles(role)



# ========================================
# 🧠 Système XP : XP automatique messages + vocal
# ========================================

# Chargement des données d'XP
XP_FILE = "xp.json"
if os.path.exists(XP_FILE):
    with open(XP_FILE, "r") as f:
        bot.xp_data = json.load(f)
else:
    with open(XP_FILE, "w") as f:
        json.dump({}, f)

# Sauvegarde des données d'XP
def save_xp():
    with open(XP_FILE, "w") as f:
        json.dump(bot.xp_data, f, indent=4)

# Ajouter de l'XP à un membre
def add_xp(user_id, amount):
    user_id = str(user_id)
    bot.xp_data[user_id] = bot.xp_data.get(user_id, 0) + amount
    save_xp()
    return bot.xp_data[user_id]

# Récupérer l'XP actuel d'un membre
def get_xp(user_id):
    return bot.xp_data.get(str(user_id), 0)

# 🎯 Ajout d'XP lors des messages
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    xp = bot.xp_config["xp_per_message"]
    multiplier = bot.xp_config["multipliers"].get(str(message.channel.id), 1.0)
    total_xp = int(xp * multiplier)
    current_xp = add_xp(message.author.id, total_xp)

    # Attribution de rôle si palier atteint
    for level_xp, role_id in bot.xp_config["level_roles"].items():
        if current_xp >= int(level_xp):
            role = message.guild.get_role(int(role_id))
            if role and role not in message.author.roles:
                await message.author.add_roles(role, reason="XP atteint")

                # Annonce de niveau
                if bot.xp_config["announcement_channel"]:
                    channel = bot.get_channel(int(bot.xp_config["announcement_channel"]))
                    if channel:
                        annonce = bot.xp_config["announcement_message"].replace("{mention}", message.author.mention).replace("{xp}", str(current_xp))
                        await channel.send(annonce)

    await bot.process_commands(message)

# ⏱️ Ajout d'XP vocal automatique
@bot.event
async def on_voice_state_update(member, before, after):
    if not before.channel and after.channel:
        bot.vocal_start_times[member.id] = time.time()
    elif before.channel and not after.channel:
        if member.id in bot.vocal_start_times:
            duration = int((time.time() - bot.vocal_start_times[member.id]) / 60)
            multiplier = bot.xp_config["multipliers"].get(str(before.channel.id), 1.0)
            gained = int(duration * bot.xp_config["xp_per_minute_vocal"] * multiplier)
            current_xp = add_xp(member.id, gained)

            for level_xp, role_id in bot.xp_config["level_roles"].items():
                if current_xp >= int(level_xp):
                    role = member.guild.get_role(int(role_id))
                    if role and role not in member.roles:
                        await member.add_roles(role, reason="XP vocal atteint")

                        if bot.xp_config["announcement_channel"]:
                            channel = bot.get_channel(int(bot.xp_config["announcement_channel"]))
                            if channel:
                                annonce = bot.xp_config["announcement_message"].replace("{mention}", member.mention).replace("{xp}", str(current_xp))
                                await channel.send(annonce)
            del bot.vocal_start_times[member.id]





# ========================================
# 📊 Fonctions XP membres : /xp et /leaderboard
# ========================================

@bot.tree.command(name="xp", description="Affiche ton XP (réservé à un salon / niveau minimum)")
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

# ----------------------------------------

@bot.tree.command(name="leaderboard", description="Classement des membres avec le plus d'XP")
async def leaderboard(interaction: discord.Interaction):
    config = bot.xp_config
    user_xp = get_xp(interaction.user.id)

    if config["xp_command_channel"] and interaction.channel.id != int(config["xp_command_channel"]):
        await interaction.response.send_message("❌ Cette commande n'est pas autorisée dans ce salon.", ephemeral=True)
        return

    if user_xp < config["xp_command_min_xp"]:
        await interaction.response.send_message("❌ Tu n'as pas encore assez d'XP pour voir le classement.", ephemeral=True)
        return

    classement = sorted(bot.xp_data.items(), key=lambda x: x[1], reverse=True)[:10]
    lignes = []
    for i, (user_id, xp) in enumerate(classement):
        membre = interaction.guild.get_member(int(user_id))
        if membre:
            lignes.append(f"{i+1}. {membre.display_name} — {xp} XP")

    texte = textwrap.dedent(f"""
        🏆 **Top 10 XP :**
        {'\n'.join(lignes)}
    """)

    await interaction.response.send_message(texte.strip(), ephemeral=True)






# ========================================
# 🛠️ Commandes ADMIN : configuration du système XP
# ========================================

@bot.tree.command(name="add_xp", description="Ajoute de l'XP à un membre (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(member="Membre ciblé", amount="Quantité d'XP à ajouter")
async def add_xp_cmd(interaction: discord.Interaction, member: discord.Member, amount: int):
    total = add_xp(member.id, amount)
    texte = textwrap.dedent(f"""
        ✅ {amount} XP ajoutés à {member.mention}
        🔹 Total : **{total} XP**
    """)
    await interaction.response.send_message(texte.strip(), ephemeral=True)

# ----------------------------------------

@bot.tree.command(name="set_xp_config", description="Modifie l'XP gagné par message et en vocal")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp_per_message="XP/message", xp_per_minute_vocal="XP/minute vocal")
async def set_xp_config(interaction: discord.Interaction, xp_per_message: int, xp_per_minute_vocal: int):
    bot.xp_config["xp_per_message"] = xp_per_message
    bot.xp_config["xp_per_minute_vocal"] = xp_per_minute_vocal
    texte = textwrap.dedent(f"""
        ✅ XP configuré :
        • 💬 Messages : **{xp_per_message} XP**
        • 🎙️ Vocal : **{xp_per_minute_vocal} XP/min**
    """)
    await interaction.response.send_message(texte.strip(), ephemeral=True)

# ----------------------------------------

@bot.tree.command(name="set_xp_role", description="Définit un rôle à débloquer à partir d'un seuil d'XP")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", role="Rôle à attribuer")
async def set_xp_role(interaction: discord.Interaction, xp: int, role: discord.Role):
    bot.xp_config["level_roles"][str(xp)] = role.id
    texte = textwrap.dedent(f"""
        ✅ Le rôle **{role.name}** sera attribué à partir de **{xp} XP**
    """)
    await interaction.response.send_message(texte.strip(), ephemeral=True)

# ----------------------------------------

@bot.tree.command(name="set_xp_boost", description="Ajoute un multiplicateur d'XP à un salon")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon ciblé", multiplier="Ex : 2.0 = XP x2")
async def set_xp_boost(interaction: discord.Interaction, channel: discord.TextChannel, multiplier: float):
    bot.xp_config["multipliers"][str(channel.id)] = multiplier
    texte = textwrap.dedent(f"""
        ✅ Multiplicateur **x{multiplier}** appliqué à {channel.mention}
    """)
    await interaction.response.send_message(texte.strip(), ephemeral=True)

# ----------------------------------------

@bot.tree.command(name="set_salon_annonce_niveau", description="Définit le salon où sont envoyées les annonces de niveau")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon d'annonce")
async def set_salon_annonce(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["announcement_channel"] = str(channel.id)
    texte = textwrap.dedent(f"""
        ✅ Les annonces de niveau seront envoyées dans {channel.mention}
    """)
    await interaction.response.send_message(texte.strip(), ephemeral=True)

# ----------------------------------------

@bot.tree.command(name="set_message_annonce_niveau", description="Modifie le message d’annonce de niveau")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message="Utilise {mention} et {xp} comme variables")
async def set_message_annonce(interaction: discord.Interaction, message: str):
    bot.xp_config["announcement_message"] = message
    texte = textwrap.dedent(f"""
        ✅ Message d'annonce de niveau mis à jour !

        💬 **Aperçu :**
        {message.replace('{mention}', interaction.user.mention).replace('{xp}', '1234')}
    """)
    await interaction.response.send_message(texte.strip(), ephemeral=True)

# ----------------------------------------

@bot.tree.command(name="set_channel_xp_commands", description="Définit le salon pour les commandes /xp et /leaderboard")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon autorisé")
async def set_channel_xp(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["xp_command_channel"] = str(channel.id)
    texte = textwrap.dedent(f"""
        ✅ Les commandes /xp et /leaderboard seront utilisables uniquement dans {channel.mention}
    """)
    await interaction.response.send_message(texte.strip(), ephemeral=True)

# ----------------------------------------

@bot.tree.command(name="set_minimum_xp_command", description="XP minimum requis pour voir /xp ou /leaderboard")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(min_xp="XP minimum requis")
async def set_minimum_xp(interaction: discord.Interaction, min_xp: int):
    bot.xp_config["xp_command_min_xp"] = min_xp
    texte = textwrap.dedent(f"""
        ✅ Il faut maintenant **{min_xp} XP** pour accéder aux commandes /xp et /leaderboard
    """)
    await interaction.response.send_message(texte.strip(), ephemeral=True)

# ----------------------------------------

@bot.tree.command(name="ajouter_badge", description="Définit un badge à débloquer à partir d'un certain XP")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", badge="Nom ou emoji du badge")
async def ajouter_badge(interaction: discord.Interaction, xp: int, badge: str):
    bot.xp_config["badges"][str(xp)] = badge
    texte = textwrap.dedent(f"""
        ✅ Badge **{badge}** attribué à partir de **{xp} XP**
    """)
    await interaction.response.send_message(texte.strip(), ephemeral=True)

# ----------------------------------------

@bot.tree.command(name="ajouter_titre", description="Définit un titre à débloquer à partir d'un certain XP")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", titre="Titre à débloquer")
async def ajouter_titre(interaction: discord.Interaction, xp: int, titre: str):
    bot.xp_config["titres"][str(xp)] = titre
    texte = textwrap.dedent(f"""
        ✅ Titre **{titre}** attribué à partir de **{xp} XP**
    """)
    await interaction.response.send_message(texte.strip(), ephemeral=True)




# ========================================
# ⏰ Système de messages programmés (format FR corrigé)
# ========================================

import datetime, time, os, json, textwrap
from discord.ext import tasks
from discord import app_commands, TextStyle
from discord.ui import Modal, TextInput

# Chargement du fichier JSON
MSG_FILE = "messages_programmes.json"
if os.path.exists(MSG_FILE):
    with open(MSG_FILE, "r") as f:
        bot.programmed_messages = json.load(f)
else:
    bot.programmed_messages = {}
    with open(MSG_FILE, "w") as f:
        json.dump({}, f)

def save_programmed_messages():
    with open(MSG_FILE, "w") as f:
        json.dump(bot.programmed_messages, f, indent=4)

# Boucle de vérification toutes les 60 secondes
@tasks.loop(seconds=60)
async def check_programmed_messages():
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    to_remove = []

    for key, data in bot.programmed_messages.items():
        if data["next"] == now:
            channel = bot.get_channel(int(data["channel_id"]))
            if channel:
                await channel.send(textwrap.dedent(data["message"]))

            if data["type"] == "once":
                to_remove.append(key)
            elif data["type"] == "daily":
                next_time = datetime.datetime.strptime(data["next"], "%d/%m/%Y %H:%M") + datetime.timedelta(days=1)
                bot.programmed_messages[key]["next"] = next_time.strftime("%d/%m/%Y %H:%M")
            elif data["type"] == "weekly":
                next_time = datetime.datetime.strptime(data["next"], "%d/%m/%Y %H:%M") + datetime.timedelta(weeks=1)
                bot.programmed_messages[key]["next"] = next_time.strftime("%d/%m/%Y %H:%M")

    for key in to_remove:
        del bot.programmed_messages[key]

    save_programmed_messages()

# ========================================
# 📅 Modal de programmation
# ========================================

class ProgrammerMessageModal(Modal, title="🗓️ Programmer un message"):

    contenu = TextInput(
        label="Contenu du message (sauts de ligne autorisés)",
        style=TextStyle.paragraph,
        placeholder="Tape ici ton message à programmer...",
        required=True,
        max_length=2000
    )

    def __init__(self, salon, type, date_heure):
        super().__init__()
        self.salon = salon
        self.type = type
        self.date_heure = date_heure
        self.add_item(self.contenu)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            key = str(int(time.time()))
            bot.programmed_messages[key] = {
                "channel_id": str(self.salon.id),
                "message": textwrap.dedent(self.contenu.value),
                "type": self.type.lower(),
                "next": self.date_heure
            }
            save_programmed_messages()

            await interaction.followup.send(
                f"✅ Message planifié pour {self.date_heure} ({self.type}) dans {self.salon.mention}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)

# ========================================
# 📅 Commande /programmer_message
# ========================================

@tree.command(name="programmer_message", description="Planifie un message automatique")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    salon="Salon où envoyer le message",
    type="Type d'envoi : once, daily ou weekly",
    date_heure="Date et heure de 1er envoi (JJ/MM/AAAA HH:MM)"
)
async def programmer_message(interaction: discord.Interaction, salon: discord.TextChannel, type: str, date_heure: str):
    try:
        datetime.datetime.strptime(date_heure, "%d/%m/%Y %H:%M")
    except ValueError:
        await interaction.response.send_message("❌ Format invalide. Utilise : JJ/MM/AAAA HH:MM", ephemeral=True)
        return

    modal = ProgrammerMessageModal(salon, type, date_heure)
    await interaction.response.send_modal(modal)

# ========================================
# 🗑️ Commande /supprimer_message
# ========================================

@tree.command(name="supprimer_message", description="Supprime un message programmé")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message_id="ID du message programmé à supprimer")
async def supprimer_message(interaction: discord.Interaction, message_id: str):
    if message_id in bot.programmed_messages:
        del bot.programmed_messages[message_id]
        save_programmed_messages()
        await interaction.response.send_message("✅ Message supprimé", ephemeral=True)
    else:
        await interaction.response.send_message("❌ ID non trouvé.", ephemeral=True)

# ========================================
# 📋 Commande /messages_programmes
# ========================================

@tree.command(name="messages_programmes", description="Affiche la liste des messages programmés")
@app_commands.checks.has_permissions(administrator=True)
async def messages_programmes(interaction: discord.Interaction):
    if not bot.programmed_messages:
        await interaction.response.send_message("Aucun message programmé.", ephemeral=True)
        return

    texte = "**🗓️ Messages programmés :**\n"
    for msg_id, data in bot.programmed_messages.items():
        texte += f"🆔 `{msg_id}` - Salon : <#{data['channel_id']}> - ⏰ {data['next']} - 🔁 {data['type']}\n"

    await interaction.response.send_message(texte, ephemeral=True)

# ========================================
# ✏️ Commande /modifier_message_programme
# ========================================

@tree.command(name="modifier_message_programme", description="Modifie un message programmé")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message_id="ID du message programmé", nouveau_message="Nouveau contenu")
async def modifier_message_programme(interaction: discord.Interaction, message_id: str, nouveau_message: str):
    if message_id in bot.programmed_messages:
        bot.programmed_messages[message_id]["message"] = textwrap.dedent(nouveau_message)
        save_programmed_messages()
        await interaction.response.send_message("✅ Message mis à jour", ephemeral=True)
    else:
        await interaction.response.send_message("❌ ID introuvable", ephemeral=True)



# ========================================
# 🏁 Défi de la semaine avec rôle temporaire (version MODAL + anti-freeze)
# ========================================

from discord.ui import Modal, TextInput
from discord import TextStyle

class DefiModal(discord.ui.Modal, title="🔥 Défi de la semaine"):

    def __init__(self, salon, role, durée_heures):
        super().__init__()
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
        await interaction.response.defer(ephemeral=True)  # ✅ Protection contre les freezes
        try:
            # Envoi du message avec mise en forme
            msg = await self.salon.send(textwrap.dedent(self.message.value))
            await msg.add_reaction("✅")

            # Stockage pour suivi des réactions
            if not hasattr(bot, "defi_messages"):
                bot.defi_messages = {}
            bot.defi_messages[msg.id] = {
                "role_id": self.role.id,
                "end_timestamp": time.time() + self.durée_heures * 3600
            }

            # Planification de la suppression du rôle
            async def remove_role_later():
                await asyncio.sleep(self.durée_heures * 3600)
                guild = interaction.guild
                for member in guild.members:
                    if self.role in member.roles:
                        try:
                            await member.remove_roles(self.role, reason="Fin du défi")
                        except:
                            pass
                if msg.id in bot.defi_messages:
                    del bot.defi_messages[msg.id]

            asyncio.create_task(remove_role_later())

            await interaction.followup.send(
                f"✅ Défi posté dans {self.salon.mention} avec rôle temporaire **{self.role.name}** pendant **{self.durée_heures}h**",
                ephemeral=True
            )

        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)

# ========================================
# 📌 Commande /defi_semaine — version avec modal
# ========================================
@tree.command(name="defi_semaine", description="Lance un défi hebdomadaire avec rôle temporaire")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    salon="Salon où poster le défi",
    role="Rôle temporaire à attribuer",
    durée_heures="Durée du défi en heures (ex: 168 pour 7 jours)"
)
async def defi_semaine(interaction: discord.Interaction, salon: discord.TextChannel, role: discord.Role, durée_heures: int):
    modal = DefiModal(salon, role, durée_heures)
    await interaction.response.send_modal(modal)

# ========================================
# 🎯 Gestion des réactions défi
# ========================================

@bot.event
async def on_raw_reaction_add(payload):
    if hasattr(bot, "defi_messages") and payload.message_id in bot.defi_messages:
        if str(payload.emoji) == "✅":
            guild = bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            role = guild.get_role(bot.defi_messages[payload.message_id]["role_id"])
            if role and member and not member.bot:
                await member.add_roles(role, reason="Participation au défi")

@bot.event
async def on_raw_reaction_remove(payload):
    if hasattr(bot, "defi_messages") and payload.message_id in bot.defi_messages:
        if str(payload.emoji) == "✅":
            guild = bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            role = guild.get_role(bot.defi_messages[payload.message_id]["role_id"])
            if role and member and not member.bot:
                await member.remove_roles(role, reason="Abandon du défi")



# ========================================
# 📩 /envoyer_message — Envoi via modal (admin, corrigé)
# ========================================

from discord.ui import Modal, TextInput
from discord import TextStyle

class ModalEnvoyerMessage(Modal, title="📩 Envoyer un message formaté"):

    def __init__(self, salon):
        super().__init__()
        self.salon = salon
        self.contenu = TextInput(
            label="Contenu du message",
            style=TextStyle.paragraph,
            placeholder="Colle ici ton message complet avec mise en forme (sauts de ligne inclus)",
            required=True,
            max_length=2000,
            custom_id="envoyer_message_contenu"  # ✅ ID unique pour éviter les conflits
        )
        self.add_item(self.contenu)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)  # ✅ Prévenir le freeze sur messages longs
        try:
            await self.salon.send(textwrap.dedent(self.contenu.value))
            await interaction.followup.send(f"✅ Message envoyé dans {self.salon.mention}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)

@tree.command(name="envoyer_message", description="Fait envoyer un message par le bot dans un salon via un modal")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    salon="Salon où envoyer le message"
)
async def envoyer_message(interaction: discord.Interaction, salon: discord.TextChannel):
    try:
        modal = ModalEnvoyerMessage(salon)
        await interaction.response.send_modal(modal)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {str(e)}", ephemeral=True)



# ========================================
# 🧹 /clear — Supprime un certain nombre de messages dans le salon (corrigé)
# ========================================
@bot.tree.command(name="clear", description="Supprime un nombre de messages dans ce salon (max 100)")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.describe(
    nombre="Nombre de messages à supprimer (entre 1 et 100)"
)
async def clear(interaction: discord.Interaction, nombre: int):
    if nombre < 1 or nombre > 100:
        await interaction.response.send_message("❌ Choisis un nombre entre 1 et 100.", ephemeral=True)
        return

    try:
        await interaction.response.defer(ephemeral=True)  # ✅ Évite le timeout
        deleted = await interaction.channel.purge(limit=nombre)

        await interaction.followup.send(
            f"🧽 {len(deleted)} messages supprimés avec succès.",
            ephemeral=True
        )

    except Exception as e:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Erreur lors de la suppression : {str(e)}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)





@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user.name}")

    if not check_programmed_messages.is_running():
        check_programmed_messages.start()

    try:
        synced = await bot.tree.sync()
        print(f"🌐 {len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"❌ Erreur lors de la synchronisation des commandes : {e}")



bot.run(TOKEN)


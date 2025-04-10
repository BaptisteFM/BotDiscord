import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import Modal, TextInput
from discord import TextStyle

import json
import time
import asyncio
import textwrap
import datetime
from bson import ObjectId
from pymongo import MongoClient
from dotenv import load_dotenv

# ========================================
# 🔐 Chargement sécurisé du fichier .env
# ========================================
if not load_dotenv():
    print("❌ Le fichier .env n'a pas pu être chargé ou est introuvable.")

TOKEN = os.getenv("DISCORD_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")

# Sécurité renforcée : vérifie que les variables sont bien chargées
if not TOKEN:
    raise ValueError("❌ DISCORD_TOKEN est introuvable. Vérifie ton .env et son chargement.")
if not MONGODB_URI:
    raise ValueError("❌ MONGODB_URI est introuvable. Vérifie ton .env et son chargement.")

print("✅ Variables d'environnement chargées.")

# ========================================
# 📡 Connexion à MongoDB Atlas
# ========================================
try:
    mongo_client = MongoClient(MONGODB_URI)
    mongo_client.admin.command("ping")
    print("✅ Connexion MongoDB Atlas réussie.")
except Exception as e:
    raise ConnectionError(f"❌ Échec connexion MongoDB : {e}")

# Base et collections MongoDB
mongo_db = mongo_client["discord_bot"]
xp_collection = mongo_db["xp"]
programmed_messages_collection = mongo_db["programmed_messages"]
defis_collection = mongo_db["defis"]

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
            "multipliers": {},           # {channel_id: x2.0}
            "level_roles": {},           # {xp: role_id}
            "announcement_channel": None,
            "announcement_message": "🎉 {mention} a atteint {xp} XP !",
            "xp_command_channel": None,
            "xp_command_min_xp": 0,
            "badges": {},                # {xp: badge}
            "titres": {}                 # {xp: titre}
        }
        self.programmed_messages = {}

    async def setup_hook(self):
        try:
            mongo_client.admin.command("ping")
            print("✅ MongoDB toujours accessible depuis setup_hook().")
        except Exception as e:
            print(f"❌ Problème MongoDB dans setup_hook() : {e}")

        try:
            synced = await self.tree.sync(guild=None)
            print(f"🌐 {len(synced)} commandes slash synchronisées (globalement)")
        except Exception as e:
            print(f"❌ Erreur de synchronisation des slash commands : {e}")

# ========================================
# 🧠 Instanciation du bot
# ========================================
bot = MyBot()
tree = bot.tree




# ========================================
# 🎭 /roledereaction — Ajoute une réaction à un message existant ou en crée un nouveau via un modal
# ========================================

class RoleReactionModal(discord.ui.Modal, title="✍️ Créer un message avec formatage"):

    def __init__(self, emoji, role, salon):
        super().__init__(timeout=None)
        self.emoji = emoji
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

            emoji_key = (
                str(self.emoji) if not self.emoji.is_custom_emoji()
                else f"<:{self.emoji.name}:{self.emoji.id}>"
            )

            bot.reaction_roles[message_envoye.id] = {emoji_key: self.role.id}

            await interaction.followup.send(
                f"✅ Nouveau message envoyé dans {self.salon.mention}\n"
                f"- Emoji utilisé : {self.emoji}\n"
                f"- Rôle associé : **{self.role.name}**",
                ephemeral=True
            )

        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de l'envoi du message : {e}", ephemeral=True)


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

            try:
                msg_id_int = int(message_id)
                msg = await interaction.channel.fetch_message(msg_id_int)
                await msg.add_reaction(emoji)

                emoji_key = (
                    str(emoji) if not discord.PartialEmoji.from_str(emoji).is_custom_emoji()
                    else emoji
                )

                if msg_id_int in bot.reaction_roles:
                    bot.reaction_roles[msg_id_int][emoji_key] = role.id
                else:
                    bot.reaction_roles[msg_id_int] = {emoji_key: role.id}

                await interaction.followup.send(
                    f"✅ Réaction {emoji} ajoutée au message `{message_id}` pour le rôle **{role.name}**",
                    ephemeral=True
                )

            except Exception as e:
                await interaction.followup.send(f"❌ Erreur lors de l'ajout de la réaction : {e}", ephemeral=True)

        else:
            if not salon:
                await interaction.response.send_message(
                    "❌ Merci de spécifier un salon si tu veux créer un nouveau message.",
                    ephemeral=True
                )
                return

            try:
                modal = RoleReactionModal(emoji, role, salon)
                await interaction.response.send_modal(modal)
            except Exception as e:
                await interaction.response.send_message(f"❌ Erreur lors de l’ouverture du modal : {e}", ephemeral=True)

    except Exception as e:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Erreur inattendue : {str(e)}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Erreur fatale : {str(e)}", ephemeral=True)

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
# 🎭 Gestion automatique des rôles via réactions (blindée + emoji custom)
# ========================================

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    member = guild.get_member(payload.user_id)
    if member is None or member.bot:
        return

    # ✅ Gestion correcte des emojis custom
    emoji_key = (
        str(payload.emoji) if not payload.emoji.is_custom_emoji()
        else f"<:{payload.emoji.name}:{payload.emoji.id}>"
    )

    data = bot.reaction_roles.get(payload.message_id)
    if isinstance(data, dict):
        role_id = data.get(emoji_key)
        if role_id:
            role = guild.get_role(int(role_id))
            if role:
                try:
                    await member.add_roles(role, reason="Réaction ajoutée")
                except Exception as e:
                    print(f"❌ Erreur ajout rôle : {e}")

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    member = guild.get_member(payload.user_id)
    if member is None or member.bot:
        return

    # ✅ Gestion correcte des emojis custom
    emoji_key = (
        str(payload.emoji) if not payload.emoji.is_custom_emoji()
        else f"<:{payload.emoji.name}:{payload.emoji.id}>"
    )

    data = bot.reaction_roles.get(payload.message_id)
    if isinstance(data, dict):
        role_id = data.get(emoji_key)
        if role_id:
            role = guild.get_role(int(role_id))
            if role:
                try:
                    await member.remove_roles(role, reason="Réaction retirée")
                except Exception as e:
                    print(f"❌ Erreur retrait rôle : {e}")





# ========================================
# 🧠 Système XP MongoDB : Messages + Vocal
# ========================================

# ✅ Ajoute de l'XP à un membre
def add_xp(user_id, amount):
    user_id = str(user_id)
    existing = xp_collection.find_one({"user_id": user_id})
    if existing:
        new_total = existing["xp"] + amount
        xp_collection.update_one({"user_id": user_id}, {"$set": {"xp": new_total}})
    else:
        new_total = amount
        xp_collection.insert_one({"user_id": user_id, "xp": new_total})
    return new_total

# ✅ Récupère l'XP actuel d'un membre
def get_xp(user_id):
    user_id = str(user_id)
    result = xp_collection.find_one({"user_id": user_id})
    return result["xp"] if result else 0

# 🎯 Ajoute de l'XP lors des messages
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    xp = bot.xp_config["xp_per_message"]
    multiplier = bot.xp_config["multipliers"].get(str(message.channel.id), 1.0)
    total_xp = int(xp * multiplier)
    current_xp = add_xp(message.author.id, total_xp)

    # 🔓 Attribution de rôle si palier atteint
    for level_xp, role_id in bot.xp_config["level_roles"].items():
        if current_xp >= int(level_xp):
            role = message.guild.get_role(int(role_id))
            if role and role not in message.author.roles:
                await message.author.add_roles(role, reason="XP atteint")

                # 📢 Annonce de niveau
                if bot.xp_config["announcement_channel"]:
                    channel = bot.get_channel(int(bot.xp_config["announcement_channel"]))
                    if channel:
                        annonce = bot.xp_config["announcement_message"].replace("{mention}", message.author.mention).replace("{xp}", str(current_xp))
                        await channel.send(annonce)

    await bot.process_commands(message)

# 🎙️ Ajoute de l'XP vocal automatiquement
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

    # 🔰 Cherche le bon badge
    badge = ""
    for seuil, b in sorted(bot.xp_config["badges"].items(), key=lambda x: int(x[0]), reverse=True):
        if user_xp >= int(seuil):
            badge = b
            break

    # 🏷️ Cherche le bon titre
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

    # 📊 Récupération du classement depuis MongoDB
    classement = list(xp_collection.find().sort("xp", -1).limit(10))

    lignes = []
    for i, record in enumerate(classement):
        membre = interaction.guild.get_member(int(record["user_id"]))
        if membre:
            lignes.append(f"{i+1}. {membre.display_name} — {record['xp']} XP")
        else:
            lignes.append(f"{i+1}. (Utilisateur inconnu) — {record['xp']} XP")

    if not lignes:
        texte = "Aucun membre avec de l'XP pour le moment."
    else:
        texte = textwrap.dedent(f"""
            🏆 **Top 10 XP :**
            {chr(10).join(lignes)}
        """)


    await interaction.response.send_message(texte.strip(), ephemeral=True)




# ========================================
# 🛠️ Commandes ADMIN : configuration du système XP (MongoDB)
# ========================================

from bson.objectid import ObjectId  # Au cas où tu l'utiliserais dans d'autres commandes plus tard

# ----------------------------------------
# ========================================
# 🛠️ Commande /add_xp — version blindée MongoDB
# ========================================
@bot.tree.command(name="add_xp", description="Ajoute de l'XP à un membre (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(member="Membre ciblé", amount="Quantité d'XP à ajouter")
async def add_xp_cmd(interaction: discord.Interaction, member: discord.Member, amount: int):
    try:
        user_id = str(member.id)

        # Vérifie si l'utilisateur a déjà un enregistrement
        user_data = xp_collection.find_one({"user_id": user_id})
        new_total = (user_data["xp"] if user_data else 0) + amount

        # Mets à jour ou insère l'entrée
        xp_collection.update_one(
            {"user_id": user_id},
            {"$set": {"xp": new_total}},
            upsert=True
        )

        texte = textwrap.dedent(f"""
            ✅ {amount} XP ajoutés à {member.mention}
            🔹 Total : **{new_total} XP**
        """)
        await interaction.response.send_message(texte.strip(), ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(
            f"❌ Une erreur est survenue lors de l'ajout d'XP : {str(e)}",
            ephemeral=True
        )


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
    await interaction.response.send_message(
        f"✅ Le rôle **{role.name}** sera attribué à partir de **{xp} XP**",
        ephemeral=True
    )

# ----------------------------------------
@bot.tree.command(name="set_xp_boost", description="Ajoute un multiplicateur d'XP à un salon")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon ciblé", multiplier="Ex : 2.0 = XP x2")
async def set_xp_boost(interaction: discord.Interaction, channel: discord.TextChannel, multiplier: float):
    bot.xp_config["multipliers"][str(channel.id)] = multiplier
    await interaction.response.send_message(
        f"✅ Multiplicateur **x{multiplier}** appliqué à {channel.mention}",
        ephemeral=True
    )

# ----------------------------------------
@bot.tree.command(name="set_salon_annonce_niveau", description="Définit le salon où sont envoyées les annonces de niveau")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon d'annonce")
async def set_salon_annonce(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["announcement_channel"] = str(channel.id)
    await interaction.response.send_message(
        f"✅ Les annonces de niveau seront envoyées dans {channel.mention}",
        ephemeral=True
    )

# ----------------------------------------
@bot.tree.command(name="set_message_annonce_niveau", description="Modifie le message d’annonce de niveau")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message="Utilise {mention} et {xp} comme variables")
async def set_message_annonce(interaction: discord.Interaction, message: str):
    bot.xp_config["announcement_message"] = message
    preview = message.replace("{mention}", interaction.user.mention).replace("{xp}", "1234")
    await interaction.response.send_message(
        f"✅ Message d'annonce mis à jour !\n\n💬 **Aperçu :**\n{preview}",
        ephemeral=True
    )

# ----------------------------------------
@bot.tree.command(name="set_channel_xp_commands", description="Définit le salon pour les commandes /xp et /leaderboard")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon autorisé")
async def set_channel_xp(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["xp_command_channel"] = str(channel.id)
    await interaction.response.send_message(
        f"✅ Les commandes XP sont maintenant limitées à {channel.mention}",
        ephemeral=True
    )

# ----------------------------------------
@bot.tree.command(name="set_minimum_xp_command", description="XP minimum requis pour voir /xp ou /leaderboard")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(min_xp="XP minimum requis")
async def set_minimum_xp(interaction: discord.Interaction, min_xp: int):
    bot.xp_config["xp_command_min_xp"] = min_xp
    await interaction.response.send_message(
        f"✅ Il faut maintenant **{min_xp} XP** pour voir les commandes /xp et /leaderboard",
        ephemeral=True
    )

# ----------------------------------------
@bot.tree.command(name="ajouter_badge", description="Définit un badge à débloquer à partir d'un certain XP")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", badge="Nom ou emoji du badge")
async def ajouter_badge(interaction: discord.Interaction, xp: int, badge: str):
    bot.xp_config["badges"][str(xp)] = badge
    await interaction.response.send_message(
        f"✅ Badge **{badge}** ajouté à partir de **{xp} XP**",
        ephemeral=True
    )

# ----------------------------------------
@bot.tree.command(name="ajouter_titre", description="Définit un titre à débloquer à partir d'un certain XP")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", titre="Titre à débloquer")
async def ajouter_titre(interaction: discord.Interaction, xp: int, titre: str):
    bot.xp_config["titres"][str(xp)] = titre
    await interaction.response.send_message(
        f"✅ Titre **{titre}** ajouté à partir de **{xp} XP**",
        ephemeral=True
    )




# ========================================
# ⏰ Système de messages programmés — MONGODB (VERSION BLINDÉE)
# ========================================

from discord.ext import tasks
from discord import TextStyle, app_commands
from discord.ui import Modal, TextInput
import datetime, textwrap, time
from bson import ObjectId

# 🔁 Boucle de vérification
@tasks.loop(seconds=30)
async def check_programmed_messages():
    await bot.wait_until_ready()
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    try:
        messages = list(programmed_messages_collection.find())
        for msg in messages:
            if msg.get("next") == now:
                try:
                    channel = bot.get_channel(int(msg["channel_id"]))
                    if channel:
                        await channel.send(textwrap.dedent(msg["message"]))
                        print(f"📤 Message envoyé dans {channel.name} ({msg['_id']})")
                except Exception as e:
                    print(f"❌ Erreur envoi message programmé [{msg['_id']}] : {e}")

                if msg.get("type") == "once":
                    programmed_messages_collection.delete_one({"_id": msg["_id"]})
                else:
                    try:
                        current = datetime.datetime.strptime(msg["next"], "%d/%m/%Y %H:%M")
                        if msg["type"] == "daily":
                            current += datetime.timedelta(days=1)
                        elif msg["type"] == "weekly":
                            current += datetime.timedelta(weeks=1)

                        next_date = current.strftime("%d/%m/%Y %H:%M")
                        programmed_messages_collection.update_one(
                            {"_id": msg["_id"]},
                            {"$set": {"next": next_date}}
                        )
                    except Exception as e:
                        print(f"❌ Erreur recalcul date [{msg['_id']}] : {e}")
                        programmed_messages_collection.delete_one({"_id": msg["_id"]})
    except Exception as e:
        print(f"❌ Erreur boucle messages programmés : {e}")

# 📥 Modal de création
class ProgrammerMessageModal(Modal, title="🗓️ Programmer un message"):

    def __init__(self, salon, type, date_heure):
        super().__init__(timeout=None)
        self.salon = salon
        self.type = type
        self.date_heure = date_heure

        self.contenu = TextInput(
            label="Contenu du message",
            style=TextStyle.paragraph,
            placeholder="Tape ici ton message à programmer...",
            required=True,
            max_length=2000
        )
        self.add_item(self.contenu)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            doc = {
                "channel_id": str(self.salon.id),
                "message": textwrap.dedent(self.contenu.value),
                "type": self.type.lower(),
                "next": self.date_heure
            }
            programmed_messages_collection.insert_one(doc)
            await interaction.followup.send(
                f"✅ Message planifié pour **{self.date_heure}** ({self.type}) dans {self.salon.mention}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)

# ✅ /programmer_message
@tree.command(name="programmer_message", description="Planifie un message automatique")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    salon="Salon où envoyer le message",
    type="Type d'envoi : once, daily ou weekly",
    date_heure="Date et heure du 1er envoi (JJ/MM/AAAA HH:MM)"
)
async def programmer_message(interaction: discord.Interaction, salon: discord.TextChannel, type: str, date_heure: str):
    try:
        datetime.datetime.strptime(date_heure, "%d/%m/%Y %H:%M")
    except ValueError:
        await interaction.response.send_message("❌ Format invalide. Utilise : JJ/MM/AAAA HH:MM", ephemeral=True)
        return

    try:
        await interaction.response.send_modal(ProgrammerMessageModal(salon, type, date_heure))
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur lors de l'ouverture du modal : {e}", ephemeral=True)

# 🗑️ /supprimer_message
@tree.command(name="supprimer_message", description="Supprime un message programmé")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message_id="ID MongoDB du message à supprimer")
async def supprimer_message(interaction: discord.Interaction, message_id: str):
    try:
        result = programmed_messages_collection.delete_one({"_id": ObjectId(message_id)})
        if result.deleted_count > 0:
            await interaction.response.send_message("✅ Message supprimé.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ID non trouvé.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {str(e)}", ephemeral=True)

# 📋 /messages_programmes
@tree.command(name="messages_programmes", description="Affiche les messages programmés")
@app_commands.checks.has_permissions(administrator=True)
async def messages_programmes(interaction: discord.Interaction):
    try:
        docs = list(programmed_messages_collection.find())
        if not docs:
            await interaction.response.send_message("Aucun message programmé.", ephemeral=True)
            return

        texte = "**🗓️ Messages programmés :**\n"
        for doc in docs:
            texte += f"🆔 `{doc['_id']}` — Salon : <#{doc['channel_id']}> — ⏰ {doc['next']} — 🔁 {doc['type']}\n"

        await interaction.response.send_message(texte.strip(), ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {str(e)}", ephemeral=True)

# ✏️ /modifier_message_programme
class ModifierMessageModal(Modal, title="✏️ Modifier un message programmé"):
    def __init__(self, message_id):
        super().__init__(timeout=None)
        self.message_id = message_id

        self.nouveau_contenu = TextInput(
            label="Nouveau contenu du message",
            style=TextStyle.paragraph,
            placeholder="Entre le nouveau message ici...",
            required=True,
            max_length=2000
        )
        self.add_item(self.nouveau_contenu)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            result = programmed_messages_collection.update_one(
                {"_id": ObjectId(self.message_id)},
                {"$set": {"message": textwrap.dedent(self.nouveau_contenu.value)}}
            )
            if result.matched_count:
                await interaction.followup.send("✅ Message modifié avec succès.", ephemeral=True)
            else:
                await interaction.followup.send("❌ ID introuvable.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)

@tree.command(name="modifier_message_programme", description="Modifie un message programmé via un modal")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message_id="ID MongoDB du message à modifier")
async def modifier_message_programme(interaction: discord.Interaction, message_id: str):
    try:
        await interaction.response.send_modal(ModifierMessageModal(message_id))
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur ouverture modal : {str(e)}", ephemeral=True)



# ========================================
# 🔥 Modal de défi (VERSION BLINDÉE)
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
            # 🔒 Envoi du message du défi
            msg = await self.salon.send(textwrap.dedent(self.message.value))
            await msg.add_reaction("✅")

            # 🕒 Calcul de la fin
            end_timestamp = time.time() + self.durée_heures * 3600

            # 💾 Insertion MongoDB
            defis_collection.insert_one({
                "message_id": msg.id,
                "channel_id": self.salon.id,
                "role_id": self.role.id,
                "end_timestamp": end_timestamp
            })

            # 🧨 Lancement de la suppression automatique
            asyncio.create_task(remove_role_later(interaction.guild, msg.id, self.role))

            await interaction.followup.send(
                f"✅ Défi lancé dans {self.salon.mention} avec le rôle **{self.role.name}** pour **{self.durée_heures}h**",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de la création du défi : {e}", ephemeral=True)

# ========================================
# 🔄 Suppression automatique du rôle (VERSION BLINDÉE)
# ========================================
async def remove_role_later(guild, message_id, role):
    try:
        data = defis_collection.find_one({"message_id": message_id})
        if not data:
            print(f"⚠️ Données du défi introuvables pour le message {message_id}")
            return

        temps_restant = data["end_timestamp"] - time.time()
        await asyncio.sleep(max(0, temps_restant))

        for member in guild.members:
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason="Fin du défi")
                except Exception as e:
                    print(f"❌ Impossible de retirer le rôle à {member.display_name} : {e}")

        defis_collection.delete_one({"message_id": message_id})
        print(f"✅ Rôle {role.name} retiré à tous et défi supprimé (ID message : {message_id})")

    except Exception as e:
        print(f"❌ Erreur dans remove_role_later : {e}")

# ========================================
# 📌 /defi_semaine — Lancer un défi (VERSION BLINDÉE)
# ========================================
@tree.command(name="defi_semaine", description="Lance un défi hebdomadaire avec rôle temporaire")
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

        await interaction.response.send_modal(DefiModal(salon, role, durée_heures))

    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur lors de la commande : {e}", ephemeral=True)

# ========================================
# ✅ Réactions de participation au défi (VERSION BLINDÉE)
# ========================================
@bot.event
async def on_raw_reaction_add(payload):
    try:
        if str(payload.emoji) != "✅":
            return

        data = defis_collection.find_one({"message_id": payload.message_id})
        if data:
            guild = bot.get_guild(payload.guild_id)
            if not guild:
                return
            member = guild.get_member(payload.user_id)
            if member and not member.bot:
                role = guild.get_role(data["role_id"])
                if role:
                    await member.add_roles(role, reason="Participation au défi")
    except Exception as e:
        print(f"❌ Erreur ajout rôle défi : {e}")

@bot.event
async def on_raw_reaction_remove(payload):
    try:
        if str(payload.emoji) != "✅":
            return

        data = defis_collection.find_one({"message_id": payload.message_id})
        if data:
            guild = bot.get_guild(payload.guild_id)
            if not guild:
                return
            member = guild.get_member(payload.user_id)
            if member and not member.bot:
                role = guild.get_role(data["role_id"])
                if role:
                    await member.remove_roles(role, reason="Abandon du défi")
    except Exception as e:
        print(f"❌ Erreur retrait rôle défi : {e}")

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





# ========================================
# ✅ Connexion et lancement sécurisé du bot
# ========================================

@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user} (ID: {bot.user.id})")
    await bot.wait_until_ready()

    # ✅ Vérifie la connexion MongoDB au démarrage
    try:
        mongo_client.admin.command("ping")
        print("📡 Connexion MongoDB : OK")
    except Exception as e:
        print(f"❌ Connexion MongoDB échouée : {e}")

    # 🔁 Lancer la boucle des messages programmés (MongoDB)
    if not check_programmed_messages.is_running():
        check_programmed_messages.start()
        print("🔄 Boucle check_programmed_messages lancée")

    # 🌐 Synchronisation des commandes slash
    try:
        synced = await bot.tree.sync()
        print(f"🌐 {len(synced)} commandes slash synchronisées")
    except Exception as e:
        print(f"❌ Erreur de synchronisation des commandes : {e}")

# ========================================
# 🚀 Lancement du bot
# ========================================
try:
    bot.run(TOKEN)
except Exception as e:
    print(f"❌ Erreur critique au lancement du bot : {e}")



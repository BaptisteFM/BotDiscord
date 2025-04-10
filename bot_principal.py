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

# ========================================
# 📁 Chemins des fichiers persistants
# ========================================
DATA_FOLDER = "data"
XP_FILE = os.path.join(DATA_FOLDER, "xp.json")
MSG_FILE = os.path.join(DATA_FOLDER, "messages_programmes.json")
DEFIS_FILE = os.path.join(DATA_FOLDER, "defis.json")

# ✅ Création du dossier s'il n'existe pas
os.makedirs(DATA_FOLDER, exist_ok=True)

# ========================================
# 🔧 Chargement ou initialisation des fichiers
# ========================================
def charger_json(path):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({}, f)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

xp_data = charger_json(XP_FILE)
messages_programmes = charger_json(MSG_FILE)
defis_data = charger_json(DEFIS_FILE)

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

    async def setup_hook(self):
        try:
            synced = await self.tree.sync()
            print(f"🌐 {len(synced)} commandes slash synchronisées")
        except Exception as e:
            print(f"❌ Erreur de synchronisation des slash commands : {e}")


# ========================================
# 🧠 Instanciation du bot
# ========================================
bot = MyBot()
tree = bot.tree



# ========================================
# 💾 Fonctions utilitaires pour l'XP
# ========================================

def add_xp(user_id, amount):
    user_id = str(user_id)
    current = xp_data.get(user_id, 0)
    new_total = current + amount
    xp_data[user_id] = new_total
    sauvegarder_json(XP_FILE, xp_data)
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
    current_xp = add_xp(message.author.id, total_xp)

    # 🔓 Attribution automatique des rôles selon XP
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
            current_xp = add_xp(member.id, gained)

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

    for i, (user_id, xp) in enumerate(classement):
        membre = interaction.guild.get_member(int(user_id))
        nom = membre.display_name if membre else f"Utilisateur {user_id}"
        lignes.append(f"{i+1}. {nom} — {xp} XP")

    texte = "🏆 **Top 10 XP :**\n" + "\n".join(lignes) if lignes else "Aucun membre avec de l'XP."
    await interaction.response.send_message(texte, ephemeral=True)

# ========================================
# 🛠️ /add_xp — Ajoute manuellement de l'XP à un membre
# ========================================
@tree.command(name="add_xp", description="Ajoute de l'XP à un membre (admin)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(member="Membre ciblé", amount="Quantité d'XP à ajouter")
async def add_xp_cmd(interaction: discord.Interaction, member: discord.Member, amount: int):
    new_total = add_xp(member.id, amount)
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
    await interaction.response.send_message(f"✅ XP mis à jour : {xp_per_message}/msg, {xp_per_minute_vocal}/min vocal", ephemeral=True)

@tree.command(name="set_xp_role", description="Définit un rôle à débloquer à partir d'un certain XP")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", role="Rôle à attribuer")
async def set_xp_role(interaction: discord.Interaction, xp: int, role: discord.Role):
    bot.xp_config["level_roles"][str(xp)] = role.id
    await interaction.response.send_message(f"✅ Le rôle **{role.name}** sera attribué à partir de **{xp} XP**", ephemeral=True)

@tree.command(name="set_xp_boost", description="Ajoute un multiplicateur d'XP à un salon")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon concerné", multiplier="Ex : 2.0 = XP x2")
async def set_xp_boost(interaction: discord.Interaction, channel: discord.TextChannel, multiplier: float):
    bot.xp_config["multipliers"][str(channel.id)] = multiplier
    await interaction.response.send_message(f"✅ Multiplicateur **x{multiplier}** appliqué à {channel.mention}", ephemeral=True)

@tree.command(name="set_salon_annonce", description="Salon des annonces de niveau")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon cible")
async def set_salon_annonce(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["announcement_channel"] = str(channel.id)
    await interaction.response.send_message(f"✅ Les annonces de niveau seront postées dans {channel.mention}", ephemeral=True)

@tree.command(name="set_message_annonce", description="Modifie le message d’annonce de niveau")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message="Utilise {mention} et {xp} comme variables")
async def set_message_annonce(interaction: discord.Interaction, message: str):
    bot.xp_config["announcement_message"] = message
    preview = message.replace("{mention}", interaction.user.mention).replace("{xp}", "1234")
    await interaction.response.send_message(f"✅ Message mis à jour !\n\n💬 **Aperçu :**\n{preview}", ephemeral=True)

@tree.command(name="set_channel_xp_commands", description="Salon autorisé pour /xp et /leaderboard")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Salon autorisé")
async def set_channel_xp(interaction: discord.Interaction, channel: discord.TextChannel):
    bot.xp_config["xp_command_channel"] = str(channel.id)
    await interaction.response.send_message(f"✅ Les commandes XP sont maintenant limitées à {channel.mention}", ephemeral=True)

@tree.command(name="set_minimum_xp", description="XP minimum requis pour voir /xp et /leaderboard")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(min_xp="XP requis")
async def set_minimum_xp(interaction: discord.Interaction, min_xp: int):
    bot.xp_config["xp_command_min_xp"] = min_xp
    await interaction.response.send_message(f"✅ Il faut maintenant **{min_xp} XP** pour accéder aux commandes XP", ephemeral=True)

@tree.command(name="ajouter_badge", description="Ajoute un badge débloqué à un certain XP")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", badge="Nom ou emoji du badge")
async def ajouter_badge(interaction: discord.Interaction, xp: int, badge: str):
    bot.xp_config["badges"][str(xp)] = badge
    await interaction.response.send_message(f"✅ Badge **{badge}** ajouté à partir de **{xp} XP**", ephemeral=True)

@tree.command(name="ajouter_titre", description="Ajoute un titre débloqué à un certain XP")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(xp="XP requis", titre="Titre à débloquer")
async def ajouter_titre(interaction: discord.Interaction, xp: int, titre: str):
    bot.xp_config["titres"][str(xp)] = titre
    await interaction.response.send_message(f"✅ Titre **{titre}** ajouté à partir de **{xp} XP**", ephemeral=True)



# ========================================
# ⏰ Messages programmés (stockés localement)
# ========================================

# 🔁 Boucle d'envoi automatique
@tasks.loop(seconds=30)
async def check_programmed_messages():
    await bot.wait_until_ready()
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    try:
        for msg_id, msg in list(messages_programmes.items()):
            if msg["next"] == now:
                try:
                    channel = bot.get_channel(int(msg["channel_id"]))
                    if channel:
                        await channel.send(textwrap.dedent(msg["message"]))
                        print(f"📤 Message envoyé dans {channel.name} ({msg_id})")
                except Exception as e:
                    print(f"❌ Erreur envoi message programmé [{msg_id}] : {e}")

                if msg["type"] == "once":
                    del messages_programmes[msg_id]
                else:
                    current = datetime.datetime.strptime(msg["next"], "%d/%m/%Y %H:%M")
                    if msg["type"] == "daily":
                        current += datetime.timedelta(days=1)
                    elif msg["type"] == "weekly":
                        current += datetime.timedelta(weeks=1)
                    messages_programmes[msg_id]["next"] = current.strftime("%d/%m/%Y %H:%M")

        sauvegarder_json(MSG_FILE, messages_programmes)

    except Exception as e:
        print(f"❌ Erreur boucle messages programmés : {e}")

# ✅ Modal de création
class ProgrammerMessageModal(Modal, title="🗓️ Programmer un message"):
    def __init__(self, salon, type, date_heure):
        super().__init__(timeout=None)
        self.salon = salon
        self.type = type
        self.date_heure = date_heure

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
            msg_id = str(int(time.time()))
            messages_programmes[msg_id] = {
                "channel_id": str(self.salon.id),
                "message": textwrap.dedent(self.contenu.value),
                "type": self.type,
                "next": self.date_heure
            }
            sauvegarder_json(MSG_FILE, messages_programmes)
            await interaction.followup.send(
                f"✅ Message programmé dans {self.salon.mention} ({self.type}) pour le **{self.date_heure}**",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : {str(e)}", ephemeral=True)

# ✅ /programmer_message
@tree.command(name="programmer_message", description="Planifie un message automatique (via modal)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    salon="Salon de destination",
    type="Type : once, daily ou weekly",
    date_heure="Date/heure (JJ/MM/AAAA HH:MM)"
)
async def programmer_message(interaction: discord.Interaction, salon: discord.TextChannel, type: str, date_heure: str):
    try:
        datetime.datetime.strptime(date_heure, "%d/%m/%Y %H:%M")
    except ValueError:
        await interaction.response.send_message("❌ Format invalide. Utilise : JJ/MM/AAAA HH:MM", ephemeral=True)
        return

    try:
        modal = ProgrammerMessageModal(salon, type, date_heure)
        await interaction.response.send_modal(modal)
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur lors de l'ouverture du modal : {e}", ephemeral=True)

# 🗑️ /supprimer_message_programmé
@tree.command(name="supprimer_message_programmé", description="Supprime un message programmé")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(message_id="ID du message à supprimer (affiché dans /messages_programmés)")
async def supprimer_message_programmé(interaction: discord.Interaction, message_id: str):
    if message_id in messages_programmes:
        del messages_programmes[message_id]
        sauvegarder_json(MSG_FILE, messages_programmes)
        await interaction.response.send_message("✅ Message programmé supprimé.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ ID non trouvé.", ephemeral=True)

# 📋 /messages_programmés
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

# ✏️ Modal de modification
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
            sauvegarder_json(MSG_FILE, messages_programmes)
            await interaction.followup.send("✅ Message modifié avec succès.", ephemeral=True)
        else:
            await interaction.followup.send("❌ ID introuvable.", ephemeral=True)

# ✏️ /modifier_message_programmé
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


@tree.command(name="roledereaction", description="Crée un message avec une réaction pour donner un rôle")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    emoji="Emoji à utiliser",
    role="Rôle à attribuer",
    salon="Salon cible"
)
async def roledereaction(interaction: discord.Interaction, emoji: str, role: discord.Role, salon: discord.TextChannel):
    try:
        await interaction.response.send_modal(RoleReactionModal(emoji, role, salon))
    except Exception as e:
        await interaction.followup.send(f"❌ Erreur ouverture modal : {e}", ephemeral=True)




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

        emoji_key = (
            str(emoji) if not discord.PartialEmoji.from_str(emoji).is_custom_emoji()
            else emoji
        )

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

    emoji_key = (
        str(payload.emoji) if not payload.emoji.is_custom_emoji()
        else f"<:{payload.emoji.name}:{payload.emoji.id}>"
    )

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

    emoji_key = (
        str(payload.emoji) if not payload.emoji.is_custom_emoji()
        else f"<:{payload.emoji.name}:{payload.emoji.id}>"
    )

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
# 🔥 Modal de défi hebdomadaire (VERSION BLINDÉE)
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
            # Envoi du message de défi dans le salon
            msg = await self.salon.send(textwrap.dedent(self.message.value))
            await msg.add_reaction("✅")

            # Calcul de la fin du défi
            end_timestamp = time.time() + self.durée_heures * 3600

            # Sauvegarde dans le fichier JSON
            defis_data[str(msg.id)] = {
                "channel_id": self.salon.id,
                "role_id": self.role.id,
                "end_timestamp": end_timestamp
            }
            sauvegarder_json(DEFIS_FILE, defis_data)

            # Lancement de la suppression automatique
            asyncio.create_task(retirer_role_après_defi(interaction.guild, msg.id, self.role))

            await interaction.followup.send(
                f"✅ Défi lancé dans {self.salon.mention} avec le rôle **{self.role.name}** pour **{self.durée_heures}h**",
                ephemeral=True
            )

        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de la création du défi : {e}", ephemeral=True)


# ========================================
# ⏳ Retirer le rôle à tous les membres à la fin du défi
# ========================================
async def retirer_role_après_defi(guild, message_id, role):
    try:
        data = defis_data.get(str(message_id))
        if not data:
            print(f"⚠️ Données du défi introuvables pour le message {message_id}")
            return

        temps_restant = data["end_timestamp"] - time.time()
        await asyncio.sleep(max(0, temps_restant))

        for member in guild.members:
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason="Fin du défi hebdomadaire")
                except Exception as e:
                    print(f"❌ Impossible de retirer le rôle à {member.display_name} : {e}")

        del defis_data[str(message_id)]
        sauvegarder_json(DEFIS_FILE, defis_data)
        print(f"✅ Rôle {role.name} retiré à tous et défi supprimé (message : {message_id})")

    except Exception as e:
        print(f"❌ Erreur dans retirer_role_après_defi : {e}")


# ========================================
# 📌 /defi_semaine — Lance un défi avec rôle temporaire
# ========================================
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
# ✅ Ajout de rôle à la réaction ✅ sur un défi
# ========================================
@bot.event
async def on_raw_reaction_add(payload):
    try:
        if str(payload.emoji) != "✅":
            return

        data = defis_data.get(str(payload.message_id))
        if not data:
            return

        guild = bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        role = guild.get_role(data["role_id"])
        if role and role not in member.roles:
            await member.add_roles(role, reason="Participation au défi hebdomadaire")

    except Exception as e:
        print(f"❌ Erreur lors de l'ajout du rôle défi : {e}")


# ========================================
# ❌ Retrait du rôle si l'utilisateur retire la réaction
# ========================================
@bot.event
async def on_raw_reaction_remove(payload):
    try:
        if str(payload.emoji) != "✅":
            return

        data = defis_data.get(str(payload.message_id))
        if not data:
            return

        guild = bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        role = guild.get_role(data["role_id"])
        if role and role in member.roles:
            await member.remove_roles(role, reason="Abandon du défi hebdomadaire")

    except Exception as e:
        print(f"❌ Erreur lors du retrait du rôle défi : {e}")



# ========================================
# 📩 /envoyer_message — Envoi d’un message via Modal (version blindée)
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
            await interaction.followup.send(
                f"✅ Message envoyé dans {self.salon.mention}",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send("❌ Le bot n’a pas la permission d’envoyer un message dans ce salon.", ephemeral=True)
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



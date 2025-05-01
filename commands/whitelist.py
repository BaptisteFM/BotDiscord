import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import asyncio
from datetime import datetime
from utils.utils import (
    is_admin,
    charger_config,
    sauvegarder_config,
    log_erreur,
    role_autorise,
    charger_whitelist,
    sauvegarder_whitelist
)

# Directories and file locking
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DEMANDES_FILE = os.path.join(DATA_DIR, 'demandes_whitelist.json')
WHITELIST_FILE = os.path.join(DATA_DIR, 'whitelist.json')
file_lock = asyncio.Lock()

class ValidationButtons(discord.ui.View):
    def __init__(self, cog, user_id: int, nom: str, prenom: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.nom = nom
        self.prenom = prenom

    async def _send_dm(self, member: discord.Member, content: str):
        try:
            dm = await member.create_dm()
            await dm.send(content)
        except Exception as e:
            # Log DM failure
            await log_erreur(self.cog.bot, member.guild if member.guild else None,
                             f"DM failed for {member.id}: {e}")

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success)
    async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            guild = interaction.guild
            member = guild.get_member(self.user_id)
            if not member:
                return await interaction.followup.send("❌ Utilisateur introuvable.", ephemeral=True)

            # Roles
            role_nv = discord.utils.get(guild.roles, name="Non vérifié")
            role_membre = discord.utils.get(guild.roles, name="Membre")
            if role_nv and role_nv in member.roles:
                await member.remove_roles(role_nv)
            if role_membre and role_membre not in member.roles:
                await member.add_roles(role_membre)

            # Add to whitelist file
            async with file_lock:
                # Charger existant
                if os.path.exists(WHITELIST_FILE):
                    with open(WHITELIST_FILE, 'r', encoding='utf-8') as f:
                        whitelist = json.load(f)
                else:
                    whitelist = []
                if not any(u['user_id'] == str(self.user_id) for u in whitelist):
                    whitelist.append({
                        'user_id': str(self.user_id),
                        'nom': self.nom,
                        'prenom': self.prenom,
                        'validated': datetime.utcnow().isoformat()
                    })
                    with open(WHITELIST_FILE, 'w', encoding='utf-8') as f:
                        json.dump(whitelist, f, indent=4, ensure_ascii=False)

            # Remove pending demande and message
            await self.cog._remove_demande(self.user_id)
            try:
                await interaction.message.delete()
            except:
                pass

            # Send DM to user
            cfg = charger_config()
            welcome = cfg.get('message_validation', '🎉 Bienvenue sur le serveur !')
            await self._send_dm(member, welcome)

            # Confirmation to admin
            await interaction.followup.send("✅ Utilisateur accepté et notifié.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.cog.bot, interaction.guild, f"Erreur accepter: {e}")
            await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def refuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            guild = interaction.guild
            member = guild.get_member(self.user_id)
            if member:
                await self._send_dm(member, "❌ Votre demande a été refusée. Contactez un modérateur si besoin.")

            await self.cog._remove_demande(self.user_id)
            try:
                await interaction.message.delete()
            except:
                pass
            await interaction.followup.send("⛔ Utilisateur refusé et notifié.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.cog.bot, interaction.guild, f"Erreur refuser: {e}")
            await interaction.followup.send("❌ Une erreur est survenue.", ephemeral=True)

class Whitelist(commands.Cog):
    "Gestion des demandes de whitelist."
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        os.makedirs(DATA_DIR, exist_ok=True)
        self.rappel_demande.start()

    def cog_unload(self):
        self.rappel_demande.cancel()

    async def _read_json(self, path: str):
        async with file_lock:
            if not os.path.exists(path):
                return []
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []

    async def _write_json(self, path: str, data):
        async with file_lock:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

    async def _add_demande(self, user_id: int, nom: str, prenom: str):
        demandes = await self._read_json(DEMANDES_FILE)
        entry = next((d for d in demandes if d['user_id'] == str(user_id)), None)
        timestamp = datetime.utcnow().isoformat()
        if entry:
            entry.update({'timestamp': timestamp, 'nom': nom, 'prenom': prenom})
        else:
            demandes.append({'user_id': str(user_id), 'timestamp': timestamp, 'nom': nom, 'prenom': prenom})
        await self._write_json(DEMANDES_FILE, demandes)

    async def _remove_demande(self, user_id: int):
        demandes = await self._read_json(DEMANDES_FILE)
        demandes = [d for d in demandes if d['user_id'] != str(user_id)]
        await self._write_json(DEMANDES_FILE, demandes)

    # Configuration slash commands
    @app_commands.command(name="definir_journal_validation", description="Définit le salon de validation.")
    @app_commands.default_permissions(administrator=True)
    async def definir_journal_validation(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg['journal_validation_channel'] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Salon de validation: {salon.mention}", ephemeral=True)

    @app_commands.command(name="setup_whitelist_reaction", description="Publie le message de demande.")
    @app_commands.default_permissions(administrator=True)
    async def setup_whitelist_reaction(self, interaction: discord.Interaction, salon: discord.TextChannel, emoji: str = "✉️"):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        embed = discord.Embed(title="Demande d'accès", description=f"Réagissez avec {emoji} pour demander l'accès.", color=discord.Color.blurple())
        msg = await salon.send(embed=embed)
        try:
            await msg.add_reaction(emoji)
        except Exception:
            pass
        cfg = charger_config()
        cfg['whitelist_reaction_channel_id'] = str(salon.id)
        cfg['whitelist_reaction_message_id'] = str(msg.id)
        cfg['whitelist_reaction_emoji'] = emoji
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Message posté dans {salon.mention}.", ephemeral=True)

    # Listener pour réactions
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        cfg = charger_config()
        if (str(payload.message_id) != cfg.get('whitelist_reaction_message_id') or
            str(payload.channel_id) != cfg.get('whitelist_reaction_channel_id') or
            str(payload.emoji) != cfg.get('whitelist_reaction_emoji') or
            payload.user_id == self.bot.user.id):
            return
        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        role_nv = discord.utils.get(guild.roles, name="Non vérifié")
        if not member or role_nv not in member.roles:
            return
        # Supprimer la réaction
        channel = self.bot.get_channel(payload.channel_id)
        try:
            await channel.remove_reaction(payload.emoji, member)
        except:
            pass
        # Démarrage questionnaire en DM
        user = self.bot.get_user(payload.user_id)
        try:
            dm = await user.create_dm()
            await dm.send("Je vous pose quelques questions…")
        except discord.Forbidden:
            return await channel.send(f"{member.mention}, active tes MP.", delete_after=10)
        def check(m):
            return m.author.id == payload.user_id and isinstance(m.channel, discord.DMChannel)
        try:
            await dm.send("Quel est votre prénom ?")
            r1 = await self.bot.wait_for('message', check=check, timeout=60.0)
            prenom = r1.content.strip()
            await dm.send("Quel est votre nom ?")
            r2 = await self.bot.wait_for('message', check=check, timeout=60.0)
            nom = r2.content.strip()
        except asyncio.TimeoutError:
            return await dm.send("⏱️ Temps écoulé. Recommencez.")
        # Enregistrer la demande
        await self._add_demande(payload.user_id, nom, prenom)
        # Envoyer en validation
        embed = discord.Embed(title="📨 Nouvelle demande d'accès",
                              description=f"<@{payload.user_id}>\n**Prénom**: {prenom}\n**Nom**: {nom}",
                              color=discord.Color.blurple())
        embed.set_footer(text=f"ID: {payload.user_id}")
        channel_val = cfg.get('journal_validation_channel')
        if channel_val:
            target = guild.get_channel(int(channel_val))
            view = ValidationButtons(self, payload.user_id, nom, prenom)
            await target.send(embed=embed, view=view)
            await dm.send("✅ Demande envoyée aux modérateurs.")
        else:
            await dm.send("⚠️ Salon de validation non configuré.")

    # Rappel des demandes
    @tasks.loop(hours=1)
    async def rappel_demande(self):
        try:
            cfg = charger_config()
            rid = cfg.get('salon_rappel_whitelist')
            if not rid:
                return
            channel = self.bot.get_channel(int(rid))
            demandes = await self._read_json(DEMANDES_FILE)
            for d in demandes:
                user = self.bot.get_user(int(d['user_id']))
                if user:
                    await channel.send(f"⏰ Rappel: {user.mention} attend validation.")
        except Exception as e:
            await log_erreur(self.bot, None, f"rappel_demande: {e}")

    # Admin commands: recherche, retrait, liste
    @app_commands.command(name="rechercher_whitelist", description="Recherche dans la whitelist.")
    async def rechercher_whitelist(self, interaction: discord.Interaction, query: str):
        if not (await is_admin(interaction.user) or role_autorise(interaction, "rechercher_whitelist")):
            return await interaction.response.send_message("❌ Pas la permission.", ephemeral=True)
        approved = await charger_whitelist()
        matches = [u for u in approved if query.lower() in u.get('nom','').lower() or query.lower() in u.get('prenom','').lower()]
        if not matches:
            return await interaction.response.send_message(f"❌ Aucun résultat pour '{query}'.", ephemeral=True)
        desc = "\n".join(f"• {m['prenom']} {m['nom']} (ID:{m['user_id']})" for m in matches)
        embed = discord.Embed(title="Résultats de recherche", description=desc, color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="retirer_whitelist", description="Retire un membre de la whitelist.")
    @app_commands.default_permissions(administrator=True)
    async def retirer_whitelist(self, interaction: discord.Interaction, utilisateur: discord.Member):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        approved = await charger_whitelist()
        entry = next((u for u in approved if u.get('user_id') == str(utilisateur.id)), None)
        if not entry:
            return await interaction.response.send_message("ℹ️ Utilisateur non whitelisté.", ephemeral=True)
        approved.remove(entry)
        await sauvegarder_whitelist(approved)
        # Rôles
        r_nv = discord.utils.get(interaction.guild.roles, name="Non vérifié")
        r_m = discord.utils.get(interaction.guild.roles, name="Membre")
        if r_m and r_m in utilisateur.roles:
            await utilisateur.remove_roles(r_m)
        if r_nv and r_nv not in utilisateur.roles:
            await utilisateur.add_roles(r_nv)
        await interaction.response.send_message(f"✅ {utilisateur.mention} retiré.", ephemeral=True)

    @app_commands.command(name="lister_whitelist", description="Liste des membres whitelistés.")
    @app_commands.default_permissions(administrator=True)
    async def lister_whitelist(self, interaction: discord.Interaction):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        approved = await charger_whitelist()
        count = len(approved)
        desc = "\n".join(f"• {u['prenom']} {u['nom']} (ID:{u['user_id']})" for u in approved) or "Aucun membre."
        embed = discord.Embed(title=f"Whitelist ({count})", description=desc, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
